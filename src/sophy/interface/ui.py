import asyncio
import functools
import difflib
import html

from io import StringIO

from rich.console import Console
from rich.syntax import Syntax
from prompt_toolkit.application import run_in_terminal

from pygments.lexers import guess_lexer

from sophy.utils.debug import print_debug

# Pygments alias -> Prism.js/libprisma alias (Telegram uses libprisma)
_PYGMENTS_TO_PRISM = {
    "python3": "python",
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "zsh": "bash",
    "objc": "objectivec",
    "posh": "powershell",
    "rb": "ruby",
    "cs": "csharp",
    "hs": "haskell",
    "kt": "kotlin",
    "tex": "latex",
}

# Pygments names that don't map to any real language in Prism.js
_PRISM_IGNORE = {"text", "output", "pycon", "pytb", "teratermmacro"}


def _guess_language(code: str) -> str:
    try:
        lexer = guess_lexer(code)
        name = lexer.aliases[0]
    except Exception:
        return ""
    if name in _PRISM_IGNORE:
        return ""
    return _PYGMENTS_TO_PRISM.get(name, name)


class ObservableConsole(Console):
    """Rich Console that notifies listeners on every print() call.

    Listeners receive the plain-text version of the output, enabling
    non-CLI backends (e.g. Telegram) to mirror all output.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._listeners: list = []

    def add_listener(self, callback):
        """Register a callback(plain_text: str) invoked on every print."""
        self._listeners.append(callback)

    def remove_listener(self, callback):
        self._listeners.remove(callback)

    def print(self, *args, **kwargs):
        if self._listeners:
            # Capture plain-text version for listeners
            capture_console = Console(file=StringIO(), force_terminal=False, no_color=True, width=120)
            capture_console.print(*args, **{k: v for k, v in kwargs.items() if k != "file"})
            plain_text = capture_console.file.getvalue()
            for listener in self._listeners:
                try:
                    listener(plain_text)
                except Exception:
                    pass
        super().print(*args, **kwargs)


console = ObservableConsole()

_main_loop = None


def set_main_loop(loop):
    global _main_loop
    _main_loop = loop


def prompt_in_terminal(question: str) -> str:
    """Prompt the user from a background thread, suspending the active prompt."""
    def _ask():
        return input(question)

    async def _run():
        import sys
        sys.stdout.flush()  # flush prompt
        await asyncio.sleep(0.21)  # wait for prompt write, it takes 0.2s
        return await run_in_terminal(_ask, in_executor=False)

    future = asyncio.run_coroutine_threadsafe(_run(), _main_loop)  # type: ignore
    return future.result()


def print_session_separator():
    console.rule(style="dim")


def log_context_usage(step_log, agent):
    # Try to get token usage from the latest step
    if agent.memory.steps and hasattr(agent.memory.steps[-1], "token_usage") and agent.memory.steps[-1].token_usage:
        input_tokens = agent.memory.steps[-1].token_usage.input_tokens
        context_window = agent.model.context_window
        if input_tokens and context_window:
            usage_ratio = input_tokens / context_window
            color = "green"
            if usage_ratio > 1:
                color = "red"
            elif usage_ratio > 0.8:
                color = "yellow"
            bar_length = 10
            filled_length = int(bar_length * usage_ratio)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            console.print(
                f"[dim]Context usage: [{color}]{bar} {usage_ratio:.0%}[/{color}][/dim]"
            )


def print_footer(agent):
    log_context_usage(None, agent)
    print_session_separator()


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


def command_preview(result_preview: bool = False):
    def command_preview_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal result_preview

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
            if result_preview:
                escaped_result = html.escape(str(result))
                lang = _guess_language(str(result))
                code_tag = f'<code class="language-{lang}">' if lang else "<code>"
                res_preview = Syntax(
                    f"\n<pre>{code_tag}\n{escaped_result}\n</code></pre>",
                    "html",
                    theme='monokai',
                    word_wrap=True
                )
                console.print(res_preview)
            print_debug(f"Result:\n{result}", debug_name="TOOLS' RESULT")

            return result
        return wrapper
    return command_preview_decorator


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

