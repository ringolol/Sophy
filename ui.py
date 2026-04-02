import os
from rich.console import Console

console = Console()

def print_debug(*args, **kwargs):
    if not os.environ.get("DEBUG", ""):
        return
    console.print(*args, **kwargs)
