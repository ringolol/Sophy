# Monkey patches for agent.py
"""
This module contains all monkey patches that customize the behavior of the smolagents library.
"""

import re
import smolagents.utils as smol_utils
from smolagents.monitoring import YELLOW_HEX as SMOL_AGENTS_YELLOW
from smolagents.monitoring import AgentLogger, escape_code_brackets
from smolagents.agents import ToolCallingAgent, ToolCall, ToolOutput, AgentImage, AgentAudio, LogLevel
from smolagents.models import ChatMessage
from rich.panel import Panel
from rich.text import Text
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context

# Color customization for the tool panel
PANEL_COLORS = {
    "task": "#0DBC79",       # Color for task panel title
    "observation": "#C0C0C0",# Color for observation panels
    "custom": "#FFFFFF",     # Default custom color
    "tool": "#d4b702",
    "sub-agent": "#4A9ECC",
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
def apply_custom_logger(agent, task_color: str = PANEL_COLORS["task"], observation_color: str = PANEL_COLORS["observation"]):
    """Apply custom logger with per-panel colors.

    Args:
        agent: The agent instance to apply the logger to
        task_color: Custom color for task panel border
        observation_color: Custom color for observation panel border
    """
    agent.logger = CustomAgentLogger(
        level=LogLevel.INFO,
        console=agent.logger.console,
        task_color=task_color,
        observation_color=observation_color
    )


# Hide observation logs — they're noisy and we show tool results via confirm()
def hide_observation_logs(agent):
    """Hide observation logs to reduce noise."""
    _original_log = agent.logger.log
    def _filtered_log(*args, **kwargs):
        if args and isinstance(args[0], str) and args[0].startswith("Observations:"):
            return
        _original_log(*args, **kwargs)
    agent.logger.log = _filtered_log


# Hide raw tool call JSON from the streamed Live display
def hide_tool_call_json(agent):
    """Hide raw tool call JSON from the streamed Live display."""
    _TOOL_CALL_RE = re.compile(r"\{\"name\":\s*\".*$", re.DOTALL)
    def _clean_render(self):
        text = str(self.content or "")
        text = _TOOL_CALL_RE.sub("", text)
        return text.strip()
    ChatMessage.render_as_markdown = _clean_render


def _make_patched_process_tool_calls(tool_color: str):
    """Create a process_tool_calls method with a custom tool panel color."""
    def _process_tool_calls(self, chat_message, memory_step):
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

        def process_single_tool_call(tool_call: ToolCall) -> ToolOutput:
            tool_name = tool_call.name
            tool_arguments = tool_call.arguments or {}
            self.logger.log(
                Panel(
                    Text(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}"),
                    border_style=tool_color,
                ),
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
    return _process_tool_calls


_patched_process_tool_calls = _make_patched_process_tool_calls(PANEL_COLORS["tool"])


def apply_explorer_monkey_patches(agent):
    sub_agent_color = PANEL_COLORS["sub-agent"]
    """Apply monkey patches for the explorer sub-agent (distinct colors, hidden observations)."""
    apply_custom_logger(agent, task_color=sub_agent_color, observation_color=PANEL_COLORS["observation"])
    hide_observation_logs(agent)
    agent.process_tool_calls = _make_patched_process_tool_calls(sub_agent_color).__get__(agent)


def fix_malformed_code_tags():
    """Patch parse_code_blobs to strip malformed </code (missing >) from extracted code."""
    _original_parse = smol_utils.parse_code_blobs

    def _patched_parse(text, code_block_tags):
        result = _original_parse(text, code_block_tags)
        if result:
            result = re.sub(r'</?code>?\s*', '', result).rstrip()
        return result

    smol_utils.parse_code_blobs = _patched_parse
    # Also patch the reference in agents module
    import smolagents.agents as smol_agents
    smol_agents.parse_code_blobs = _patched_parse


fix_malformed_code_tags()


def apply_monkey_patches(agent):
    """Apply all monkey patches to an agent instance."""
    apply_custom_logger(agent)
    hide_observation_logs(agent)
    hide_tool_call_json(agent)
    # Patch the process_tool_calls method
    ToolCallingAgent.process_tool_calls = _patched_process_tool_calls
