import asyncio
import functools
import difflib

from rich.console import Console
from rich.syntax import Syntax
from prompt_toolkit.application import run_in_terminal

from .debug import print_debug


console = Console()

_main_loop = None


def set_main_loop(loop):
    global _main_loop
    _main_loop = loop


def prompt_in_terminal(question: str) -> str:
    """Prompt the user from a background thread, suspending the active prompt."""
    def _ask():
        return input(question)

    async def _run():
        return await run_in_terminal(_ask, in_executor=False)

    future = asyncio.run_coroutine_threadsafe(_run(), _main_loop)
    return future.result()


def print_session_separator():
    console.rule(style="dim")


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
    "write_new_file": _preview_write,
}


def command_preview(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        name = wrapper.__name__

        previewer = _PREVIEWERS.get(name)
        if previewer:
            console.print(f"[yellow]{name}:[/yellow]")
            old_lines, new_lines, path = previewer(kwargs)
            if old_lines is not None:
                _print_diff(old_lines, new_lines, path)
            else:
                console.print(f"[green](new file: {path})[/green]")
        elif args or kwargs:
            all_args = list(args) + list(kwargs.values())
            if len(all_args) == 1:
                arg_val = all_args[0]
                console.print(f"[yellow]{name}[/yellow]: {arg_val}")
            else:
                console.print(f"[yellow]{name}[/yellow]")
                for key, value in kwargs.items():
                    console.print(f"   - [cyan]{key}[/cyan]: {value}")
                for i, arg in enumerate(args):
                    console.print(f"   - [cyan]arg{i}[/cyan]: {arg}")

        result = func(*args, **kwargs)
        print_debug(f"[bold blue]Result:[/bold blue]\n{result}")

        return result
    return wrapper


def final_preview(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        console.print(Syntax(result, "markdown", theme='monokai', word_wrap=True))
        console.print()
        return result
    return wrapper


def patch_tool(tool_instance, fn):
    """Patches the forward method of a tool instance to include command preview."""

    tool_instance.forward = fn(tool_instance.forward)
    name = getattr(tool_instance, "name", tool_instance.__class__.__name__)
    tool_instance.forward.__name__ = name

    return tool_instance

