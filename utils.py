import difflib
import functools
import enum

from smolagents.memory import ActionStep

from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel


MAX_AGENT_STEPS = 30

console = Console()


class SupportedModels(enum.Enum):
    qwen_3_5_35b_a3b = "qwen3.5:35b-a3b"
    glm_4_7_flash_30b = "glm-4.7-flash"


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
                        return "(no changes)"
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


def remind_final_answer(step):
    """Callback to remind agent to call final_answer when running low on steps."""
    if not isinstance(step, ActionStep):
        return
    if step.step_number > MAX_AGENT_STEPS - 1:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You are running low on steps. "
            "Call `final_answer` NOW with your best answer."
        )