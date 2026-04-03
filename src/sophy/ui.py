import functools
import os

from rich.console import Console


console = Console()


def print_debug(*args, **kwargs):
    if not os.environ.get("DEBUG", ""):
        return
    console.print(*args, **kwargs)


def command_preview(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Print command name and arguments prettily
        console.print(f"[bold blue]Executing:[/bold blue] [green]{func.__name__}[/green]")
        if args or kwargs:
            console.print("[dim]Arguments:[/dim]")
            for key, value in kwargs.items():
                console.print(f"  [cyan]{key}[/cyan]: {value}")
            for i, arg in enumerate(args):
                console.print(f"  [cyan]arg{i}[/cyan]: {arg}")

        result = func(*args, **kwargs)

        console.print(f"[bold blue]Finished:[/bold blue] [green]{func.__name__}[/green]")
        return result
    return wrapper


def patch_tool(tool_instance, fn):
    """Patches the forward method of a tool instance to include command preview."""
    tool_instance.forward = fn(tool_instance.forward)

    # Update the name of the wrapped forward method to match the tool's name
    # for cleaner logs
    name = getattr(tool_instance, "name", tool_instance.__class__.__name__)
    tool_instance.forward.__name__ = name

    return tool_instance

