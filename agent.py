import os
from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates, ToolCallingAgent, LogLevel
from smolagents.memory import ActionStep
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Color customization for the tool panel
from smolagents.monitoring import YELLOW_HEX as SMOL_AGENTS_YELLOW
from smolagents.monitoring import AgentLogger, escape_code_brackets

# Per-panel color customization
# Define custom colors for specific panels
PANEL_COLORS = {
    "task": "#0DBC79",       # Color for task panel title
    "observation": "#C0C0C0",# Color for observation panels
    "custom": "#FFFFFF",     # Default custom color
}

# Patch the YELLOW_HEX constant for default behavior
import smolagents.monitoring as smol_monitoring
smol_monitoring.YELLOW_HEX = PANEL_COLORS["custom"]

# Custom AgentLogger with per-panel color support
class CustomAgentLogger(AgentLogger):
    """Enhanced logger with customizable task and observation colors."""
    
    def __init__(self, level: LogLevel = LogLevel.INFO, console=None, 
                 task_color: str = PANEL_COLORS["task"], 
                 observation_color: str = PANEL_COLORS["observation"]):
        """Initialize CustomAgentLogger with custom colors.
        
        Args:
            level: Log level
            console: Rich Console instance
            task_color: Custom color for task panel border (e.g., "#FFD93D")
            observation_color: Custom color for observation panel border (e.g., "#6BCB77")
        """
        super().__init__(level, console)
        self.task_color = task_color
        self.observation_color = observation_color
    
    def log_task(self, content: str, subtitle: str, title: str | None = None, level=LogLevel.INFO) -> None:
        """Log task with custom color for 'New run' panel.
        
        Args:
            content: Task content to log
            subtitle: Subtitle for the panel
            title: Optional title to append
            level: Log level
        """
        # Use custom color for task panel
        self.log(
            Panel(
                f"\n[bold]{escape_code_brackets(content)}\n",
                title="[bold]" + (f"New run - {title}" if title else "New run"),
                subtitle=subtitle,
                border_style=self.task_color,
                subtitle_align="left",
            ),
            level=level,
        )
    
    def log_observation(self, content: str, title: str | None = None, level=LogLevel.INFO) -> None:
        """Log observation with custom color.
        
        Args:
            content: Observation content to log
            title: Optional title for the panel
            level: Log level
        """
        self.log(
            Panel(
                f"Observations:\n{escape_code_brackets(content)}",
                title="[bold]Observations" + (f" - {title}" if title else ""),
                border_style=self.observation_color,
                title_align="left",
            ),
            level=level,
        )

# Apply custom logger to agent after creation
def apply_custom_logger(task_color: str = PANEL_COLORS["task"], observation_color: str = PANEL_COLORS["observation"]):
    """Apply custom logger with per-panel colors.
    
    Args:
        task_color: Custom color for task panel border
        observation_color: Custom color for observation panel border
    """
    agent.logger = CustomAgentLogger(
        level=LogLevel.INFO, 
        console=agent.logger.console,
        task_color=task_color,
        observation_color=observation_color
    )

from utils import ToolDeniedException, SupportedModels
from model import ThinkingModel
from tools import TOOLS, set_history_provider
from prompts import build_prompt
from session import Session, list_sessions, restore_memory

console = Console()


def remind_final_answer(step):
    if not isinstance(step, ActionStep):
        return
    if step.step_number >= agent.max_steps - 2:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You are running low on steps. "
            "Call `final_answer` NOW with your best answer."
        )


def pick_session() -> Session:
    saved = list_sessions()
    table = Table(title="Sessions", show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold")
    table.add_column("ID")
    table.add_column("Date")
    table.add_column("Entries", justify="right")
    table.add_column("Preview")
    table.add_row("0", "[green]New session[/green]", "", "", "")
    for i, s in enumerate(saved, 1):
        table.add_row(str(i), s['id'], s['created_at'][:10], str(s['entry_count']), s['preview'])
    console.print(table)
    choice = input("Choose session [0]: ").strip()
    if not choice or choice == "0":
        return Session()
    try:
        idx = int(choice)
        if 1 <= idx <= len(saved):
            return Session.load(saved[idx - 1]["path"])
    except ValueError:
        pass
    console.print("[red]Invalid choice, starting new session.[/red]")
    return Session()


session = Session()
set_history_provider(session.get_summary)

model = ThinkingModel(
    model_id=SupportedModels.qwen_3_5_35b_a3b.value,
    api_base="http://localhost:11434/v1",
    api_key="ollama",
)


agent = ToolCallingAgent(
    tools=TOOLS,
    add_base_tools=False,
    prompt_templates=PromptTemplates(
        system_prompt=build_prompt(TOOLS),
        planning=PlanningPromptTemplate(
            initial_plan="",
            update_plan_pre_messages="",
            update_plan_post_messages="",
        ),
        managed_agent=ManagedAgentPromptTemplate(task="", report=""),
        final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
    ),
    model=model,
    max_steps=20,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    step_callbacks=[remind_final_answer],
)

# Apply custom logger with per-panel colors
apply_custom_logger()

# Hide observation logs — they're noisy and we show tool results via confirm()
_original_log = agent.logger.log
def _filtered_log(*args, **kwargs):
    if args and isinstance(args[0], str) and args[0].startswith("Observations:"):
        return
    _original_log(*args, **kwargs)
agent.logger.log = _filtered_log

# Hide raw tool call JSON from the streamed Live display
import re
from smolagents.models import ChatMessage
_TOOL_CALL_RE = re.compile(r"\{\"name\":\s*\".*$", re.DOTALL)
def _clean_render(self):
    text = str(self.content or "")
    text = _TOOL_CALL_RE.sub("", text)
    return text.strip()
ChatMessage.render_as_markdown = _clean_render

# console.print(agent.system_prompt)

# Monkey patch ToolCallingAgent.process_tool_calls to change Panel border color
from smolagents.agents import ToolCallingAgent, ToolCall, ToolOutput, AgentImage, AgentAudio, LogLevel
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from rich.panel import Panel
from rich.text import Text

def _patched_process_tool_calls(self, chat_message, memory_step):
    """Patched version with custom panel border color."""
    parallel_calls: dict[str, ToolCall] = {}
    assert chat_message.tool_calls is not None
    for chat_tool_call in chat_message.tool_calls:
        tool_call = ToolCall(
            name=chat_tool_call.function.name,
            arguments=chat_tool_call.function.arguments,
            id=chat_tool_call.id
        )
        yield tool_call
        parallel_calls[tool_call.id] = tool_call

    # Custom color for tool calling panels (line 1371 location in smolagents)
    CUSTOM_TOOL_PANEL_COLOR = "#d4b702"  # Custom green color

    def process_single_tool_call(tool_call: ToolCall) -> ToolOutput:
        tool_name = tool_call.name
        tool_arguments = tool_call.arguments or {}
        # Monkey patched line 1371: change Panel border style to custom color
        self.logger.log(
            Panel(Text(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}"), border_style=CUSTOM_TOOL_PANEL_COLOR),
            level=LogLevel.INFO,
        )
        tool_call_result = self.execute_tool_call(tool_name, tool_arguments)
        tool_call_result_type = type(tool_call_result)
        if tool_call_result_type in [AgentImage, AgentAudio]:
            if tool_call_result_type == AgentImage:
                observation_name = "image.png"
            elif tool_call_result_type == AgentAudio:
                observation_name = "audio.mp3"
            self.state[observation_name] = tool_call_result
            observation = f"Stored '{observation_name}' in memory."
        else:
            observation = str(tool_call_result).strip()
        self.logger.log(
            f"Observations: {observation.replace('[', '|')}",
            level=LogLevel.INFO,
        )
        is_final_answer = tool_name == "final_answer"

        return ToolOutput(
            id=tool_call.id,
            output=tool_call_result,
            is_final_answer=is_final_answer,
            observation=observation,
            tool_call=tool_call,
        )

    outputs = {}
    if len(parallel_calls) == 1:
        tool_call = list(parallel_calls.values())[0]
        tool_output = process_single_tool_call(tool_call)
        outputs[tool_output.id] = tool_output
        yield tool_output
    else:
        with ThreadPoolExecutor(self.max_tool_threads) as executor:
            futures = []
            for tool_call in parallel_calls.values():
                ctx = copy_context()
                futures.append(executor.submit(ctx.run, process_single_tool_call, tool_call))
            for future in as_completed(futures):
                tool_output = future.result()
                outputs[tool_output.id] = tool_output
                yield tool_output

    memory_step.tool_calls = [parallel_calls[k] for k in sorted(parallel_calls.keys())]
    memory_step.observations = memory_step.observations or ""
    for tool_output in [outputs[k] for k in sorted(outputs.keys())]:
        memory_step.observations += tool_output.observation + "\n"
    memory_step.observations = (
        memory_step.observations.rstrip("\n") if memory_step.observations else memory_step.observations
    )

# Apply monkey patch
ToolCallingAgent.process_tool_calls = _patched_process_tool_calls

def load_session(s: Session):
    """Print session history and restore agent memory."""
    if s.entries:
        console.rule(f"[bold cyan]Session History ({len(s.entries)} entries)[/bold cyan]")
        for entry in s.entries:
            console.print(Panel(entry.task, title="[bold green]You[/bold green]", title_align="left", border_style="green", padding=(0, 1)))
            console.print(Panel(entry.result, title="[bold yellow]Agent[/bold yellow]", title_align="left", border_style="yellow", padding=(0, 1)))
        console.rule(style="dim")
        console.print()
        restore_memory(agent, s)


if __name__ == "__main__":
    session = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session.id}[/dim]")
    console.print("Type /quit to save & exit, /resume to switch sessions.\n")
    load_session(session)

    task_prefix = ""
    while True:
        task = input("❯ ").strip()
        # Clear the input line(s) — account for wrapping across multiple terminal lines
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            cols = 80
        prompt_len = 2  # "❯ "
        total_len = prompt_len + len(task)
        lines = max(1, (total_len + cols - 1) // cols)
        print(f"\033[{lines}A" + "\033[2K\033[1B" * lines + f"\033[{lines}A", end="", flush=True)
        if not task:
            continue
        if task == "/quit":
            if session.entries:
                session.save_auto()
                console.print(f"[green]Session {session.id} saved.[/green]")
            break
        if task == "/new":
            if session.entries:
                session.save_auto()
            session = Session()
            agent.memory.reset()
            console.print(f"[bold]Session:[/bold] {session.id}\n")
            continue
        if task == "/resume":
            if session.entries:
                session.save_auto()
            session = pick_session()
            console.print(f"[bold]Session:[/bold] {session.id}\n")
            load_session(session)
            continue
        try:
            result = agent.run(task_prefix + task, reset=False)
            task_prefix = ""

            # Extract history from memory before next run resets it
            tools_used = []
            for step in agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session.add_entry(
                task=task,
                result=str(result),
                steps=agent.memory.get_full_steps(),
                tools_used=tools_used,
            )
            session.save_auto()
        except ToolDeniedException as e:
            console.print(f"\n[red]{e}[/red]\n")
            task_prefix = str(e) + '\n\n'
