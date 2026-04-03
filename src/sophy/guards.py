import difflib
import functools
import os
import re
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel

from .ui import console


_guard_config = None
_COMPOUND_CMD_RE = re.compile(r'(\|\||&&|;|\||&|`|\$\(|\$\{|[<>()\n])')
_AUTO_EDIT_TOOLS = frozenset({"edit_file", "insert_text", "write_new_file"})


def set_guard_config(config):
    global _guard_config
    _guard_config = config


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

def _can_auto_approve(fn_name, kwargs):
    """Check if this call can be auto-approved based on guard config."""
    if _guard_config is None:
        return False

    # File content edits: auto-approve if inside project dir
    if fn_name in _AUTO_EDIT_TOOLS and _guard_config.allow_all_edits:
        path = kwargs.get("file_path", "")
        real = os.path.realpath(path)
        if real.startswith(_guard_config.project_dir + os.sep):
            return True

    # Commands: auto-approve only simple commands matching allowed patterns
    if fn_name == "run_command" and _guard_config.allowed_command_patterns:
        cmd = kwargs.get("command", "")
        if not _COMPOUND_CMD_RE.search(cmd):
            for pattern in _guard_config.allowed_command_patterns:
                if pattern.match(cmd):
                    return True

    return False


def confirm(fn):
    """Confirmation decorator"""

    @functools.wraps(fn)
    def guarded_fn(*args, **kwargs):
        auto = _can_auto_approve(fn.__name__, kwargs)

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

        if auto:
            console.print("[dim][green](auto-approved)[/green][/dim]")
            return fn(*args, **kwargs)

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
