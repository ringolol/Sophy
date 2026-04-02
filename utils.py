import argparse
import json
import os
import difflib
import functools
from dataclasses import dataclass
import requests

from smolagents.memory import ActionStep
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
import questionary


MAX_AGENT_STEPS = 30
DEFAULT_CONTEXT_WINDOW = 128000


_cached_context_window: int | None = None


def get_context_window(model_id: str, api_base: str = "http://localhost:11434") -> int:
    global _cached_context_window
    try:
        resp = requests.post(f"{api_base}/api/show", json={"name": model_id})
        resp.raise_for_status()
        _cached_context_window = resp.json().get("model_info", {}).get("num_ctx", DEFAULT_CONTEXT_WINDOW)
    except (requests.RequestException, KeyError):
        pass
    return _cached_context_window or DEFAULT_CONTEXT_WINDOW

console = Console()


CONFIG_PATH = ".sophy/config.json"


@dataclass
class ModelPreset:
    model_id: str
    api_base: str
    api_key: str
    label: str
    context: int = DEFAULT_CONTEXT_WINDOW
    tools: bool = True
    system_prompt: bool = True
    explorer: bool = False


def _resolve_env(value: str) -> str:
    if value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value


def load_config() -> list[ModelPreset]:
    if not os.path.isfile(CONFIG_PATH):
        return []
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    return [
        ModelPreset(
            model_id=m["model_id"],
            api_base=m["api_base"],
            api_key=_resolve_env(m["api_key"]),
            label=m.get("label", m["model_id"]),
            context=m.get("context", DEFAULT_CONTEXT_WINDOW),
            tools=m.get("tools", True),
            system_prompt=m.get("system_prompt", True),
            explorer=m.get("explorer", False),
        )
        for m in data.get("models", [])
    ]


def pick_model(models: list[ModelPreset]) -> ModelPreset:
    def provider(api_base: str):
        if "google" in api_base:
            return "Google"
        if "yandex" in api_base:
            return "Yandex"
        return "Ollama"

    choices = [
        questionary.Choice(title=p.label, value=p, description=f"\n    Provider: {provider(p.api_base)}\n    Tools: {p.tools}")
        for p in models
    ]

    choice = questionary.select(
        "Choose a model:",
        choices=choices,
        use_indicator=True,
        show_description=True,
    ).ask()

    if choice:
        return choice

    exit()


class ToolDeniedException(BaseException):
    pass


def _print_diff(old_lines, new_lines, path) -> bool:
    """Print a colored unified diff with 3 lines of context."""
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}",
        n=3,
    ))
    if not diff:
        console.print("[dim](no changes)[/dim]")
        return False
    diff_text = "".join(diff)
    console.print(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
    return True


def _preview_edit(kwargs):
    """Build old/new lines for an edit_file call."""
    path = kwargs.get("file_path", "")
    old_content = kwargs.get("old_content", "")
    new_content = kwargs.get("new_content", "")
    try:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
    except FileNotFoundError:
        return None, None, path
    new_file = original.replace(old_content, new_content, 1)
    return original.splitlines(keepends=True), new_file.splitlines(keepends=True), path


def _preview_insert(kwargs):
    """Build old/new lines for an insert_text call."""
    path = kwargs.get("file_path", "")
    line_number = kwargs.get("line_number", 1)
    content = kwargs.get("content", "")
    try:
        with open(path, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    except FileNotFoundError:
        return None, None, path
    if not content.endswith("\n"):
        content += "\n"
    insert_at = max(0, min(line_number - 1, len(old_lines)))
    new_lines = old_lines[:insert_at] + content.splitlines(keepends=True) + old_lines[insert_at:]
    return old_lines, new_lines, path


def _preview_write(kwargs):
    """Build old/new lines for a write_new_file call."""
    path = kwargs.get("file_path", "")
    content = kwargs.get("content", "")
    try:
        with open(path, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    except FileNotFoundError:
        old_lines = []
    return old_lines, content.splitlines(keepends=True), path


_PREVIEWERS = {
    "edit_file": _preview_edit,
    "insert_text": _preview_insert,
    "write_new_file": _preview_write,
}


def confirm(fn):
    """Confirmation decorator"""

    @functools.wraps(fn)
    def guarded_fn(*args, **kwargs):
        console.print()
        console.rule(f"[bold yellow]Agent wants to run: {fn.__name__}[/bold yellow]")
        previewer = _PREVIEWERS.get(fn.__name__)
        if previewer:
            old_lines, new_lines, path = previewer(kwargs)
            if old_lines is not None:
                if not _print_diff(old_lines, new_lines, path):
                    def dummy(*args, **kwargs):
                        return "File have NOT been changed!"
                    return dummy
            else:
                console.print(f"[green](new file: {path})[/green]")
        else:
            console.print(Panel(str(kwargs), title="Args", border_style="dim"))
        while (answer := input("Allow? [y/n]: ").strip().lower()) not in ("y", "n"):
            print("\033[A\033[2K", end="", flush=True)
        print("\033[A\033[2K", end="", flush=True)
        if answer != "y":
            raise ToolDeniedException()
        return fn(*args, **kwargs)

    return guarded_fn


def path_expand(fn):
    """Expands path arguments"""

    @functools.wraps(fn)
    def expanded_args_fn(*args, **kwargs):
        to_expand = ['file_path', 'directory', 'path', 'source', 'destination']
        for kwarg in to_expand:
            if kwarg in kwargs:
                kwargs[kwarg] = os.path.expanduser(kwargs[kwarg])
        return fn(*args, **kwargs)

    return expanded_args_fn


def remind_final_answer(step):
    """Callback to remind agent to call final_answer when running low on steps."""
    if not isinstance(step, ActionStep):
        return
    if step.step_number > MAX_AGENT_STEPS - 1:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You have no more steps! "
            "Call `final_answer` NOW with your best answer."
        )


@functools.wraps(console.print)
def print_debug(*args, **kwargs):
    if not os.environ.get("DEBUG", ""):
        return
    console.print(*args, **kwargs)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Sophy coding agent harness")
    parser.add_argument("--api_base", type=str, default=None, help="API base URL for the model")
    parser.add_argument("--api_key", type=str, default=None, help="API key for the model")
    parser.add_argument("--model", type=str, default=None, help="Model ID to use")
    return parser.parse_args()
