import functools
import os

from rich.console import Console
from rich.syntax import Syntax


console = Console()


def print_debug(*args, **kwargs):
    if not os.environ.get("DEBUG", ""):
        return
    console.print(*args, **kwargs)


def command_preview(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        console.print(f"[bold blue]{wrapper.__name__}...[/bold blue]")
        if args or kwargs:
            for key, value in kwargs.items():
                console.print(f"  [cyan]{key}[/cyan]: {value}")
            for i, arg in enumerate(args):
                console.print(f"  [cyan]arg{i}[/cyan]: {arg}")

        result = func(*args, **kwargs)

        return result
    return wrapper


def final_output(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        console.print(Syntax(result, "markdown", theme='monokai', word_wrap=True))
        return result
    return wrapper


def patch_tool(tool_instance, fn):
    """Patches the forward method of a tool instance to include command preview."""

    tool_instance.forward = fn(tool_instance.forward)
    name = getattr(tool_instance, "name", tool_instance.__class__.__name__)
    tool_instance.forward.__name__ = name

    return tool_instance

