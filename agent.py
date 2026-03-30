from smolagents import ToolCallingAgent, OpenAIServerModel, tool, DuckDuckGoSearchTool
from smolagents.memory import ActionStep
import subprocess
import os
import glob as glob_module
import difflib
import json


# --- Model ---
model = OpenAIServerModel(
    model_id="qwen3.5:35b-a3b",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
    extra_body={"think": False},
)


# --- Tools ---
@tool
def read_file(file_path: str) -> str:
    """Reads and returns the contents of a file.

    Args:
        file_path: The path to the file to read.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


@tool
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
def run_command(command: str) -> str:
    """Executes a shell command and returns its output.

    Args:
        command: The shell command to execute.
    """
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=30
    )
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\nSTDERR:\n" + result.stderr
    if result.returncode != 0:
        output += f"\n(exit code {result.returncode})"
    return output or "(no output)"


# --- Confirmation callback ---                                                    
DANGEROUS_TOOLS = {"write_file", "run_command"}


def show_write_diff(tc):
    args = tc.arguments if isinstance(tc.arguments, dict) else json.loads(tc.arguments)
    path = args.get("file_path", "")
    new_content = args.get("content", "")
    try:
        with open(path, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    except FileNotFoundError:
        old_lines = []
    diff = difflib.unified_diff(
        old_lines, new_content.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    )
    print("".join(diff) or f"(new file: {path})")


def confirm_step(step):
    if not isinstance(step, ActionStep) or step.tool_calls is None:
        return
    dangerous = [tc for tc in step.tool_calls if tc.name in DANGEROUS_TOOLS]
    if not dangerous:
        return
    print(f"\n--- Agent wants to run: {', '.join(tc.name for tc in dangerous)} ---")
    for tc in dangerous:
        if tc.name == "write_file":
            show_write_diff(tc)
    print(step.model_output)
    while (answer := input("Allow? [y/n]: ").strip().lower()) not in ("y", "n"):
        pass
    if answer != "y":
        raise KeyboardInterrupt("User denied tool execution.")    


# --- Agent ---
WORKING_DIR = os.getcwd()

agent = ToolCallingAgent(
    tools=[read_file, write_file, search_files, run_command, DuckDuckGoSearchTool()],
    model=model,
    max_steps=15,
    verbosity_level=2,
    step_callbacks=[confirm_step], 
)

print(agent.system_prompt)
print('===')

if __name__ == "__main__":
    print("Agent ready. Type 'quit' to exit.\n")
    while True:
        task = input("You: ").strip()
        if task.lower() in ("quit", "exit", "q"):
            break
        if not task:
            continue
        result = agent.run(task)
        print(f"\nAgent: {result}\n")
