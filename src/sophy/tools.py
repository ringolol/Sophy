import difflib
import subprocess
import shlex
import os
import glob as glob_module
import warnings

from smolagents import tool
from smolagents.default_tools import PythonInterpreterTool, DuckDuckGoSearchTool, VisitWebpageTool, FinalAnswerTool
from smolagents.local_python_executor import InterpreterError
from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings

from .guards import confirm, path_expand
from .ui import command_preview, final_output, patch_tool


_history_provider = None

# supress tools' warnings
warnings.filterwarnings("ignore")


def set_history_provider(fn):
    """Register a callback that returns conversation summary text."""
    global _history_provider
    _history_provider = fn


@tool
@command_preview
def get_conversation_history(last_n: int = 5) -> str:
    """Returns recent conversation history.

    Args:
        last_n: Number of recent conversations to return. Defaults to 5.
    """
    if _history_provider is None:
        return "No history provider configured."
    return _history_provider(last_n)

@tool
@path_expand
@command_preview
def read_file(file_path: str) -> str:
    """Reads a file.

    Args:
        file_path: The path to the file to read.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

@tool
@command_preview
@confirm
@path_expand
def write_new_file(file_path: str, content: str) -> str:
    """Writes a new file.

    Args:
        file_path: The path to the file to write.
        content: The content to write to the file.
    """
    exists = os.path.exists(file_path)
    original_lines = []
    if exists:
        with open(file_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()

    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    new_lines = content.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{file_path}" if exists else "/dev/null",
        tofile=f"b/{file_path}",
        lineterm=""
    ))
    return f"Written {len(content)} chars to {file_path}\n" + "\n".join(diff)

@tool
@path_expand
@command_preview
def search_files(pattern: str, directory: str = ".") -> str:
    """Glob search for files.

    Args:
        pattern: Glob pattern to match (e.g. "**/*.py", "*.txt").
        directory: Directory to search in. Defaults to current directory.
    """
    matches = glob_module.glob(os.path.join(directory, pattern), recursive=True)
    if not matches:
        return "No files found."
    return "\n".join(matches[:50])

@tool
@path_expand
@command_preview
def search_content(text_pattern: str, directory: str = ".", file_pattern: str = "*") -> str:
    """Searches file contents for a text pattern (grep).

    Args:
        text_pattern: Text or regex pattern to search for.
        directory: Directory to search in. Defaults to current directory.
        file_pattern: Glob pattern to filter files (e.g. "*.py"). Defaults to all files.
    """
    import re
    try:
        regex = re.compile(text_pattern)
    except re.error:
        regex = re.compile(re.escape(text_pattern))
    results = []
    for file_path in glob_module.glob(os.path.join(directory, "**", file_pattern), recursive=True):
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append(f"{file_path}:{i}: {line.rstrip()}")
                        if len(results) >= 100:
                            return "\n".join(results) + "\n... (truncated at 100 matches)"
        except (OSError, PermissionError):
            continue
    if not results:
        return "No matches found."
    return "\n".join(results)

@tool
@command_preview
@confirm
@path_expand
def run_command(command: str) -> str:
    """Runs a shell command.

    Args:
        command: The shell command to execute.
    """
    result = subprocess.run(
        shlex.split(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30
    )
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\nSTDERR:\n" + result.stderr
    if result.returncode != 0:
        output += f"\n(exit code {result.returncode})"
    return output or "(no output)"

@tool
@command_preview
@confirm
@path_expand
def edit_file(file_path: str, old_content: str, new_content: str) -> str:
    """Edits a file by replacing an exact match of old_content with new_content.

    Args:
        file_path: The path to the file to edit.
        old_content: The exact text to find and replace.
        new_content: The replacement text.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    count = content.count(old_content)
    if count == 0:
        return f"Error: old_content not found in {file_path}. Try again!"
    if count > 1:
        return f"Error: old_content matches {count} locations in {file_path}. Provide more context to make it unique!"
    new_file = content.replace(old_content, new_content, 1)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_file)

    diff = list(difflib.unified_diff(
        content.splitlines(),
        new_file.splitlines(),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm=""
    ))
    return f"Edited {file_path}\n" + "\n".join(diff)


@tool
@command_preview
def ask_user(question: str) -> str:
    """Do not hesitate to use it for clarification, confirmation, or additional information from User!

    Args:
        question: a question to ask
    """
    bindings = KeyBindings()

    @bindings.add('enter')
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.newline()

    return prompt(f"{question}\n❯ ", multiline=True, key_bindings=bindings).strip()

@tool
@path_expand
@command_preview
def list_directory(path: str = ".") -> str:
    """Lists directory contents.

    Args:
        path: directory path, supports relative notation"""
    try:
        entries = os.listdir(path)
        output = f"DirectoryContents(path='{path}'):\n"

        for entry in sorted(entries):
            full_path = os.path.join(path, entry)
            if os.path.isfile(full_path):
                size = os.path.getsize(full_path)
                output += f"  File: {entry} ({size} bytes)\n"
            elif os.path.isdir(full_path):
                output += f"  Dir:  {entry}/\n"
            else:
                output += f"  ???  {entry}\n"

        return output
    except FileNotFoundError:
        return f"Error: Directory '{path}' does not exist."
    except PermissionError:
        return f"Error: Permission denied when accessing '{path}'."
    except Exception as e:
        return f"Error: {str(e)}"

@tool
@path_expand
@command_preview
def get_tree(path: str = ".", max_depth: int = 5) -> str:
    """Returns a directory tree view with depth limit.

    Args:
        path: directory path to generate tree for. Defaults to current directory.
        max_depth: maximum depth to traverse. Defaults to 5.
    """
    def _build_tree(root, current_depth=0, prefix=''):
        if current_depth > max_depth:
            return prefix + '. . . (max depth reached)\n'

        try:
            entries = sorted(os.listdir(root))
        except (PermissionError, OSError) as e:
            return prefix + f'Error: {str(e)}\n'

        output = ''
        for i, entry in enumerate(entries):
            full_path = os.path.join(root, entry)
            is_last = (i == len(entries) - 1)
            is_dir = os.path.isdir(full_path)

            connector = '└── ' if is_last else '├── '

            if is_dir:
                output += prefix + connector + entry + '/\n'
                if current_depth < max_depth:
                    extension = '    ' if is_last else '│   '
                    output += _build_tree(full_path, current_depth + 1, prefix + extension)
            else:
                output += prefix + connector + entry + '\n'

        return output

    return _build_tree(path, 0, '')

@tool
@command_preview
@confirm
@path_expand
def delete_file(file_path: str) -> str:
    """Deletes a file.

    Args:
        file_path: The path to the file to delete.
    """
    try:
        os.remove(file_path)
        return f"Deleted file: {file_path}"
    except FileNotFoundError:
        return f"Error: File '{file_path}' not found."
    except PermissionError:
        return f"Error: Permission denied when deleting '{file_path}'."
    except OSError as e:
        return f"Error deleting file: {str(e)}"

@tool
@command_preview
@confirm
@path_expand
def move_file(source: str, destination: str) -> str:
    """Moves a file or a directory.

    Args:
        source: The source file/directory path.
        destination: The destination file/directory path.
    """
    dest_dir = os.path.dirname(destination)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    try:
        os.rename(source, destination)
        return f"Moved {source} to {destination}"
    except FileNotFoundError:
        return f"Error: Source '{source}' not found."
    except IsADirectoryError:
        return f"Error: Both source and destination must be directories for move operation between directories."
    except OSError as e:
        return f"Error moving file: {str(e)}"


@confirm
def dangerous_python_interpreter(code: str) -> str:
    import io
    import contextlib
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            exec(compile(code, '<string>', 'exec'), {})
        output = stdout.getvalue()
        return output if output else "(no output)"
    except Exception as e:
        output = stdout.getvalue()
        return (output + f"\nError: {e}") if output else f"Error: {e}"

@tool
@command_preview
def execute_python(code: str) -> str:
    """Execute Python code.

    Args:
        code: Python code or expression to evaluate.
    """
    try:
        result = PythonInterpreterTool(timeout_seconds=5*60).forward(code)
        return result
    except InterpreterError:
        # Fallback to safe Python interpreter
        return dangerous_python_interpreter(code)


@tool
@command_preview
def explorer(task: str) -> str:
    """Use this for ANY task that involves reading, searching, or navigating files! Unless you already know the exact file path AND only need one file.

    Args:
        task: A detailed description of the exploration task.
    """
    return ""


web_search = DuckDuckGoSearchTool()
patch_tool(web_search, command_preview)
web_search.description = "DuckDuckGo search."
visit_webpage = VisitWebpageTool()
patch_tool(visit_webpage, command_preview)
visit_webpage.description = "Reads a URL as markdown."
final_answer = FinalAnswerTool()
patch_tool(final_answer, command_preview)
patch_tool(final_answer, final_output)
final_answer.description = "Returns your final answer."

EXPLORATION_TOOLS = [
    read_file,
    search_files,
    search_content,
    list_directory,
    get_tree,
    final_answer,
]

TOOLS = [
    read_file,
    edit_file,
    write_new_file,
    run_command,
    ask_user,
    search_content,
    search_files,
    list_directory,
    get_tree,
    delete_file,
    move_file,
    get_conversation_history,
    execute_python,
    web_search,
    visit_webpage,
    final_answer,
]

SUB_AGENTS = [
    explorer,
]
