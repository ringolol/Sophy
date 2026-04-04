import functools
import os
import re

from .ui import console


_guard_config = None
_COMPOUND_CMD_RE = re.compile(r'(\|\||&&|;|\||&|`|\$\(|\$\{|[<>()\n])')
_AUTO_EDIT_TOOLS = frozenset({"edit_file", "write_new_file"})


def set_guard_config(config):
    global _guard_config
    _guard_config = config


class ToolDeniedException(BaseException):
    pass


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

        if auto:
            result = fn(*args, **kwargs)
            console.print("[dim][green](auto-approved)[/green][/dim]")
            return result

        while (answer := console.input("[cyan]Allow?[/cyan] \[y/n]: ").strip().lower()) not in ("y", "n"):
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
