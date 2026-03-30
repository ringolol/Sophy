import subprocess
import os
import glob as glob_module

from smolagents import tool
from smolagents.default_tools import PythonInterpreterTool, DuckDuckGoSearchTool, VisitWebpageTool, FinalAnswerTool
from smolagents.local_python_executor import InterpreterError

from utils import confirm


_history_provider = None


def set_history_provider(fn):
    """Register a callback that returns conversation summary text."""
    global _history_provider
    _history_provider = fn


@tool
def get_conversation_history(last_n: int = 5) -> str:
    """Returns recent conversation history.

    Args:
        last_n: Number of recent conversations to return. Defaults to 5.
    """
    if _history_provider is None:
        return "No history provider configured."
    return _history_provider(last_n)

@tool
def read_file(file_path: str) -> str:
    """Reads a file.

    Args:
        file_path: The path to the file to read.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    width = len(str(len(lines)))
    numbered = [f"{i:>{width}} | {line}" for i, line in enumerate(lines, 1)]
    return "".join(numbered)

@tool
@confirm
def write_new_file(file_path: str, content: str) -> str:
    """Writes a new file.

    Args:
        file_path: The path to the file to write.
        content: The content to write to the file.
    """
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written {len(content)} chars to {file_path}"

@tool
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
@confirm
def run_command(command: str) -> str:
    """Runs a shell command.

    Args:
        command: The shell command to execute.
    """
    result = subprocess.run(
        command, 
        shell=True, 
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
@confirm
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
        return f"Error: old_content not found in {file_path}."
    if count > 1:
        return f"Error: old_content matches {count} locations in {file_path}. Provide more context to make it unique."
    new_file = content.replace(old_content, new_content, 1)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_file)
    return f"Edited {file_path}"

@tool
@confirm
def insert_text(file_path: str, line_number: int, content: str) -> str:
    """Inserts text before a given line number.

    Args:
        file_path: The path to the file to edit.
        line_number: The line number to insert before.
        content: The text to insert.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not content.endswith("\n"):
        content += "\n"
    insert_at = max(0, min(line_number - 1, len(lines)))
    lines.insert(insert_at, content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Inserted text at line {insert_at + 1} in {file_path}"

@tool
def ask_user(question: str) -> str:
    """Ask User a question. Use it to clarify a task or choose a solution
    
    Args:
        question: a question to ask
    """
    return input(f"{question}\n❯ ").strip()

@tool
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
@confirm
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
@confirm
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
def execute_python(code: str) -> str:
    """Execute Python code.
    
    Args:
        code: Python code or expression to evaluate.
    """
    try:
        result = PythonInterpreterTool().forward(code)
        return result
    except InterpreterError:
        # Fallback to safe Python interpreter
        return dangerous_python_interpreter(code)


_web_search = DuckDuckGoSearchTool()
_web_search.description = "DuckDuckGo search."
_visit_webpage = VisitWebpageTool()
_visit_webpage.description = "Reads a URL as markdown."
_final_answer = FinalAnswerTool()
_final_answer.description = "Returns your final answer."

TOOLS = [
    read_file,
    edit_file,
    insert_text,
    write_new_file,
    run_command,
    search_content,
    search_files,
    list_directory,
    get_tree,
    delete_file,
    move_file,
    get_conversation_history,
    execute_python,
    _web_search,
    _visit_webpage,
    _final_answer,
]
