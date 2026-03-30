import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


SUMMARY_EXCLUDED_KEYS = {"model_input_messages", "observations", "observations_images"}


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
            part = f"[#{i+1}] User: {entry.task}\nResult: {entry.result}"
            if entry.tools_used:
                part += f"\nTools used: {', '.join(entry.tools_used)}"
            filtered_steps = [
                {k: v for k, v in step.items() if k not in SUMMARY_EXCLUDED_KEYS}
                for step in entry.steps
            ]
            part += f"\nSteps: {json.dumps(filtered_steps, default=str)}"
            parts.append(part)
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        entries = [ConversationEntry(**e) for e in data.get("entries", [])]
        return cls(id=data["id"], entries=entries, created_at=data["created_at"])

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Session":
        with open(path) as f:
            return cls.from_dict(json.load(f))
