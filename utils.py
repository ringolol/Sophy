import difflib
import functools


DIRECT_PROMPT = """You are a task-solving agent that operates strictly through a Tool-Call Loop. You MUST solve the user's task by emitting valid JSON tool calls.

# The Loop
1. **Action**: You output a JSON blob calling a tool.
2. **Observation**: You will receive the tool's output.
3. **Repeat**: Use the observation to inform your next Action.
4. **Finality**: To finish, you MUST call the `final_answer` tool. This is the ONLY way to end the task.

Action format:
{"name": "tool_name", "arguments": {"arg": "value"}}

Example:
Task: "What is 5 + 3 + 1294.678?"

Action:
{"name": "python_interpreter", "arguments": {"code": "5 + 3 + 1294.678"}}
Observation: 1302.678

Action:
{"name": "final_answer", "arguments": {"answer": "1302.678"}}

AVAILABLE TOOLS:
- read_file: Reads a file. Args: {file_path: string}
- write_file: Writes a file. Args: {file_path: string, content: string}
- search_files: Glob search for files. Args: {pattern: string, directory?: string}
- run_command: Runs a shell command. Args: {command: string}
- list_directory: Lists directory contents. Args: {path?: string}
- python_interpreter: Evaluates Python code (stdlib only: math, re, datetime, collections, itertools, statistics, random, time, queue, stat, unicodedata). Args: {code: string}
- web_search: DuckDuckGo search. Args: {query: string}
- visit_webpage: Reads a URL as markdown. Args: {url: string}
- final_answer: Returns your final answer. Args: {answer: any}

MANDATORY RULES — VIOLATION MEANS FAILURE:
1. NO PROSE: Do not explain your thought process unless the tool requires it. Output the JSON Action blob immediately.
2. JSON INTEGRITY: Every response MUST contain a valid JSON tool call. If you provide no JSON, you fail. If you see the error "does not contain any JSON blob" — you failed to include an Action. Fix it immediately.
3. LITERAL ARGS: Use literal values in arguments, NEVER variable names.
4. NO REDUNDANCY: Do NOT repeat a tool call with identical parameters.
5. FINAL ANSWER. When you have the answer, you MUST call final_answer. This is the ONLY way to complete the task. Anything else causes an infinite loop.

Now Begin!"""


class ToolDeniedException(BaseException):
    pass


def confirm(fn):
    """Confirmation decorator"""

    @functools.wraps(fn)
    def guarded_fn(*args, **kwargs):
        print(f"\n--- Agent wants to run: {fn.__name__} ---")
        if fn.__name__ == "write_file":
            path = kwargs.get("file_path", "")
            content = kwargs.get("content", "")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old_lines = f.readlines()
            except FileNotFoundError:
                old_lines = []
            diff = "".join(difflib.unified_diff(
                old_lines, content.splitlines(keepends=True),
                fromfile=f"a/{path}", tofile=f"b/{path}",
            ))
            if diff:
                for line in diff.splitlines():
                    if line.startswith("+"):
                        print(f"\033[32m{line}\033[0m")
                    elif line.startswith("-"):
                        print(f"\033[31m{line}\033[0m")
                    elif line.startswith("@@"):
                        print(f"\033[90m{line}\033[0m")
                    else:
                        print(line)
            else:
                print(f"(new file: {path})")
        else:
            print(f"Args: {kwargs}")
        while (answer := input("Allow? [y/n]: ").strip().lower()) not in ("y", "n"):
            pass
        if answer != "y":
            raise ToolDeniedException("User denied the last tool execution. Be attentive User may ask you to explain or change something about the last task!")
        return fn(*args, **kwargs)

    return guarded_fn