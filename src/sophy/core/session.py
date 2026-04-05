import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from smolagents import MultiStepAgent, Panel
from smolagents.memory import TaskStep, ActionStep, ToolCall
from smolagents.monitoring import Timing, TokenUsage
import questionary

from sophy.interface.ui import console
from sophy.utils.paths import get_user_session_dir


@dataclass
class ConversationEntry:
    task: str
    result: str
    steps: list[dict]
    tools_used: list[str]
    timestamp: str


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    entries: list[ConversationEntry] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_forked: bool = False

    def add_entry(self, task: str, result: str, steps: list[dict], tools_used: list[str]):
        self.entries.append(ConversationEntry(
            task=task,
            result=result,
            steps=steps,
            tools_used=tools_used,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))

    def get_summary(self, last_n: int = 5) -> str:
        if not self.entries:
            return "No previous conversations."

        recent = self.entries[-last_n:]
        parts = []
        for i, entry in enumerate(recent):
            lines = [f"[#{i+1}] User: {entry.task}"]
            # Summarize tool calls from steps
            for step in entry.steps:
                if "task" in step:
                    continue
                tool_calls = step.get("tool_calls") or []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "?")
                    args = fn.get("arguments", {})
                    if name == "final_answer":
                        continue
                    # Show a compact representation of the call
                    if isinstance(args, dict):
                        arg_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                    else:
                        arg_str = str(args)
                    lines.append(f"  -> {name}({arg_str})")
                # Show observation snippet if present
                obs = step.get("observations")
                if obs:
                    snippet = obs.strip().replace("\n", " ")
                    if len(snippet) > 120:
                        snippet = snippet[:120] + "..."
                    lines.append(f"     = {snippet}")
            lines.append(f"  Result: {entry.result}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        entries = [ConversationEntry(**e) for e in data.get("entries", [])]
        return cls(id=data["id"], entries=entries, created_at=data["created_at"], is_forked=data.get("is_forked", False))

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def save_auto(self):
        sessions_dir = get_user_session_dir()
        os.makedirs(sessions_dir, exist_ok=True)
        self.save(os.path.join(sessions_dir, f"{self.id}.json"))

    @classmethod
    def load(cls, path: str) -> "Session":
        with open(path) as f:
            return cls.from_dict(json.load(f))


def list_sessions() -> list[dict]:
    """Returns session metadata sorted by creation time (newest first)."""
    sessions_dir = get_user_session_dir()
    sessions: list = []

    if not os.path.isdir(sessions_dir):
        return sessions

    for fname in os.listdir(sessions_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(sessions_dir, fname)
        try:
            with open(path) as f:
                data = json.load(f)
            first_task = data["entries"][0]["task"] if data.get("entries") else ""
            sessions.append({
                "id": data["id"],
                "created_at": data["created_at"],
                "is_forked": data.get("is_forked", False),
                "entry_count": len(data.get("entries", [])),
                "preview": first_task[:100].replace("\n", " ").rstrip('.') + '...',
                "path": path,
            })
        except (json.JSONDecodeError, KeyError):
            continue
    sessions.sort(key=lambda s: s["created_at"], reverse=True)
    return sessions


def load_session(agent, s: Session, print_history=True):
    """Print session history and restore agent memory."""
    if s.entries:
        restore_memory(agent, s)

        if not print_history:
            return
        console.rule(f"[bold cyan]Session History ({len(s.entries)} entries)[/bold cyan]")
        for entry in s.entries:
            console.print(Panel(entry.task, title="[bold green]You[/bold green]", title_align="left", border_style="green", padding=(0, 1)))
            console.print(Panel(entry.result, title="[bold yellow]Agent[/bold yellow]", title_align="left", border_style="yellow", padding=(0, 1)))


async def pick_session() -> Session:

    saved = list_sessions()

    choices = [
        questionary.Choice(title="[New Session]", value="NEW_SESSION")
    ] + [
        questionary.Choice(title=f"{'[F] ' if s['is_forked'] else ''}{s['id']} - {s['preview']}", value=s)
        for s in saved
    ]

    from questionary import Style
    style = Style([
        ('highlighted', 'fg:cyan'),
    ])

    selected = await asyncio.to_thread(
        lambda: questionary.select(
            "Choose a session:",
            choices=choices,
            use_indicator=True,
            style=style,
        ).ask()
    )

    # questionary returns None on Ctrl+C or Esc
    if selected is None:
        console.print("[dim]Aborted.[/dim]")
        exit(0)

    if selected == "NEW_SESSION":
        return Session()

    return Session.load(selected["path"])


def _step_from_dict(d: dict) -> TaskStep | ActionStep:
    """Reconstruct a memory step from its dict representation."""
    if "task" in d:
        return TaskStep(task=d["task"])
    timing_data = d.get("timing", {})
    timing = Timing(start_time=timing_data.get("start_time", 0), end_time=timing_data.get("end_time"))
    tool_calls = None
    if d.get("tool_calls"):
        tool_calls = [
            ToolCall(
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"],
                id=tc["id"],
            )
            for tc in d["tool_calls"]
        ]
    token_usage = None
    if d.get("token_usage"):
        token_usage = TokenUsage(
            input_tokens=d["token_usage"]["input_tokens"],
            output_tokens=d["token_usage"]["output_tokens"],
        )
    return ActionStep(
        step_number=d.get("step_number", 0),
        timing=timing,
        tool_calls=tool_calls,
        model_output=d.get("model_output"),
        observations=d.get("observations"),
        action_output=d.get("action_output"),
        token_usage=token_usage,
        is_final_answer=d.get("is_final_answer", False),
    )


def restore_memory(agent: MultiStepAgent, session: "Session"):
    """Restore agent memory from a loaded session."""
    agent.memory.reset()
    for entry in session.entries:
        for step_dict in entry.steps:
            agent.memory.steps.append(_step_from_dict(step_dict))
