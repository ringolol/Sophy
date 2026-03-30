import subprocess
import os
import glob as glob_module

from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates, ToolCallingAgent, tool, LogLevel
from smolagents.default_tools import PythonInterpreterTool, DuckDuckGoSearchTool, VisitWebpageTool, FinalAnswerTool

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
        return f"{f.read()}"

@tool
@confirm
def write_file(file_path: str, content: str) -> str:
    """Writes a file.

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
def chat_with_human(question: str) -> str:
    """Requests human clarification
    
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
    """Moves a file or a directory
    
    Args:
        source: The source file/directory path
        destination: The destination file/directory path
    """
    # Create destination directory structure if needed
    dest_dir = os.path.dirname(destination)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    
    # Move the file/directory
    try:
        os.rename(source, destination)
        return f"Moved {source} to {destination}"
    except FileNotFoundError:
        return f"Error: Source '{source}' not found."
    except IsADirectoryError:
        return f"Error: Both source and destination must be directories for move operation between directories."
    except OSError as e:
        return f"Error moving file: {str(e)}"

_python_interpreter = PythonInterpreterTool()
_python_interpreter.description = "Evaluates Python code (stdlib only: math, re, datetime, collections, itertools, statistics, random, time, queue, stat, unicodedata)."
_web_search = DuckDuckGoSearchTool()
_web_search.description = "DuckDuckGo search."
_visit_webpage = VisitWebpageTool()
_visit_webpage.description = "Reads a URL as markdown."
_final_answer = FinalAnswerTool()
_final_answer.description = "Returns your final answer."

TOOLS = [
    read_file,
    write_file,
    search_files,
    run_command,
    list_directory,
    delete_file,
    move_file,
    get_conversation_history,
    _python_interpreter,
    _web_search,
    _visit_webpage,
    _final_answer,
]
