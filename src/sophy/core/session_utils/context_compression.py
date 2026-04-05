from smolagents.memory import ActionStep, TaskStep
from smolagents.models import ChatMessage, MessageRole

from sophy.core.session import Session
from sophy.interface.ui import console, prompt_in_terminal
from sophy.core.config import ModelPreset


SUMMARIZATION_PROMPT = (
    "Your task is to create a detailed summary of the conversation so far, "
    "pay close attention to the user's explicit requests and your previous actions. "
    "This summary should be thorough in capturing technical details, code patterns, "
    "and architectural decisions that would be essential for continuing development "
    "work without losing context."
)

COMPRESSION_THRESHOLD = 0.85


def _get_last_input_tokens(agent) -> int | None:
    for step in reversed(agent.memory.steps):
        if isinstance(step, ActionStep) and step.token_usage:
            return step.token_usage.input_tokens
    return None


def summarize_context(agent) -> str:
    messages = agent.write_memory_to_messages(summary_mode=True)

    summary_messages = [
        ChatMessage(role=MessageRole.USER, content=[{"type": "text", "text": SUMMARIZATION_PROMPT}]),
    ]

    response = agent.model.generate(summary_messages)
    return response.content.strip()


def _get_last_task_steps(agent) -> list:
    last_task_idx = None
    for i in range(len(agent.memory.steps) - 1, -1, -1):
        if isinstance(agent.memory.steps[i], TaskStep):
            last_task_idx = i
            break
    if last_task_idx is None:
        return []
    return agent.memory.steps[last_task_idx:]


def compress(agent, app_state) -> None:
    if not agent.memory.steps:
        console.print("[dim]Nothing to compress.[/dim]")
        return

    console.print("[bold yellow]Compressing context...[/bold yellow]")

    old_session = app_state.session
    old_session.save_auto()
    console.print(f"[dim]Old session {old_session.id} saved.[/dim]")

    recent_steps = list(_get_last_task_steps(agent))
    summary = summarize_context(agent)

    new_session = Session()
    new_session.add_entry(
        task="[compressed context from previous session]",
        result=summary,
        steps=[],
        tools_used=[],
    )
    app_state.session = new_session

    agent.memory.reset()
    agent.memory.steps.append(TaskStep(task=f"Previous conversation summary:\n{summary}"))
    agent.memory.steps.extend(recent_steps)

    console.print(f"[bold green]New session {new_session.id} created with compressed context.[/bold green]")


def maybe_compress(agent, app_state, model_preset: ModelPreset) -> None:
    input_tokens = _get_last_input_tokens(agent)
    if input_tokens is None:
        return

    context_window = model_preset.context
    usage_ratio = input_tokens / context_window
    if usage_ratio < COMPRESSION_THRESHOLD:
        return

    console.print(
        f"\n[bold yellow]Context usage high[/bold yellow] "
        f"({input_tokens}/{context_window} tokens, {usage_ratio:.0%} used)"
    )
    if prompt_in_terminal("\033[36mCompress context?\033[0m [y/n]: ").strip().lower() != "y":
        return

    compress(agent, app_state)
