import subprocess
import os
import glob as glob_module

from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates, ToolCallingAgent, tool, LogLevel

from utils import confirm


__all__ = [
    "read_file",
    "write_file",
    "search_files",
    "run_command",
    "chat_with_human",
    "list_directory"
]

@tool
def read_file(file_path: str) -> str:
    """Reads and returns the contents of a file.

    Args:
        file_path: The path to the file to read.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f"{f.read()}"

@tool
@confirm
def write_file(file_path: str, content: str) -> str:
    """Writes content to a file, creating directories if needed.

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
    """Searches for files matching a glob pattern recursively.

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
    """Executes a shell command and returns its output.

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
    """Lists the directory with file types and sizes
    
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

# @tool
# @confirm
# def delete_file(file_path: str) -> str:
#     """Safely deletes files with confirmation"""
#     return f"Deleted {file_path}"

@tool
@confirm
def move_file(source: str, destination: str) -> str:
    """Moves file or directory to destination
    
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
    
# @tool
# def get_conversation_history(limit: int = 10) -> str:
#     """Returns recent conversation context for better understanding"""
#     return ""