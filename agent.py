from smolagents import ToolCallingAgent, OpenAIServerModel, tool, LogLevel
from smolagents.memory import ActionStep
import subprocess
import os
import glob as glob_module
import difflib
import functools
import shutil


class ToolDeniedException(BaseException):
    pass


class ThinkingModel(OpenAIServerModel):
    def generate_stream(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
        from smolagents.models import ChatMessageStreamDelta, ChatMessageToolCallStreamDelta, TokenUsage
        completion_kwargs = self._prepare_completion_kwargs(
            messages=messages,
            stop_sequences=stop_sequences,
            response_format=response_format,
            tools_to_call_from=tools_to_call_from,
            model=self.model_id,
            custom_role_conversions=self.custom_role_conversions,
            convert_images_to_image_urls=True,
            **kwargs,
        )
        self._apply_rate_limit()
        thinking = False
        for event in self.retryer(
            self.client.chat.completions.create,
            **completion_kwargs,
            stream=True,
            stream_options={"include_usage": True},
        ):
            if event.usage:
                yield ChatMessageStreamDelta(
                    content="",
                    token_usage=TokenUsage(
                        input_tokens=event.usage.prompt_tokens,
                        output_tokens=event.usage.completion_tokens,
                    ),
                )
            if event.choices:
                choice = event.choices[0]
                if choice.delta:
                    raw = choice.delta.model_extra or {}
                    reasoning = raw.get("reasoning") or getattr(choice.delta, "reasoning_content", None)
                    if reasoning:
                        if not thinking:
                            print("\n💭 Thinking: ", end="")
                            thinking = True
                        print(f"{reasoning}", end="")
                    elif thinking and choice.delta.content:
                        thinking = False
                        print('-' * shutil.get_terminal_size().columns)
                        print()
                    yield ChatMessageStreamDelta(
                        content=choice.delta.content,
                        tool_calls=[
                            ChatMessageToolCallStreamDelta(
                                index=d.index, id=d.id, type=d.type, function=d.function,
                            )
                            for d in choice.delta.tool_calls
                        ] if choice.delta.tool_calls else None,
                    )
                elif not getattr(choice, "finish_reason", None):
                    raise ValueError(f"No content or tool calls in event: {event}")

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

@tool
def read_file(file_path: str) -> str:
    """Reads and returns the contents of a file.

    Args:
        file_path: The path to the file to read.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

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

def remind_final_answer(step):
    if not isinstance(step, ActionStep):
        return
    if step.step_number >= agent.max_steps - 2:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You are running low on steps. "
            "Call `final_answer` NOW with your best answer."
        )    

model = ThinkingModel(
    model_id="glm-4.7-flash",
    # model_id="qwen3.5:35b-a3b",
    api_base="http://localhost:11434/v1",
    api_key="ollama",
)

agent = ToolCallingAgent(
    tools=[read_file, write_file, search_files, run_command],
    add_base_tools=True,
    model=model,
    max_steps=10,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    step_callbacks=[remind_final_answer],
    instructions=(
        "\nIMPORTANT: When you have the answer, you MUST call the `final_answer` tool. "
        "Do NOT just write the answer in text. You MUST use: "
        '{"name": "final_answer", "arguments": {"answer": "your answer here"}}'
    ),
)

if __name__ == "__main__":
    print("Agent ready. Type 'quit' to exit.\n")

    task_prefix = ""
    while True:
        task = input("❯ ").strip()
        if task.lower() in ("quit", "exit", "q"):
            break
        if not task:
            continue
        try:
            result = agent.run(task_prefix + task)
            task_prefix = ""
            print(f"\nAgent: {result}\n")
        except ToolDeniedException as e:
            print(f"\n{e}\n")
            task_prefix = str(e) + '\n\n'