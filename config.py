import os
import re
import json
from dataclasses import dataclass, field

import questionary


DEFAULT_CONTEXT_WINDOW = 128000
CONFIG_PATH = ".sophy/config.json"

@dataclass
class ModelPreset:
    model_id: str
    api_base: str
    api_key: str
    label: str
    context: int = DEFAULT_CONTEXT_WINDOW
    tools: bool = True
    system_prompt: bool = True
    explorer: bool = False


@dataclass
class GuardConfig:
    allow_all_edits: bool = False
    allowed_command_patterns: list[re.Pattern] = field(default_factory=list)
    project_dir: str = ""


def load_guard_config() -> GuardConfig:
    project_dir = os.path.dirname(os.path.abspath(CONFIG_PATH))
    if not os.path.isfile(CONFIG_PATH):
        return GuardConfig(project_dir=project_dir)
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    patterns = [re.compile(p) for p in data.get("allowed_command_patterns", [])]
    return GuardConfig(
        allow_all_edits=False,
        allowed_command_patterns=patterns,
        project_dir=project_dir,
    )


def load_config() -> list[ModelPreset]:
    def _resolve_env(value: str) -> str:
        if value.startswith("$"):
            return os.environ.get(value[1:], "")
        return value

    if not os.path.isfile(CONFIG_PATH):
        return []
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    return [
        ModelPreset(
            model_id=m["model_id"],
            api_base=m["api_base"],
            api_key=_resolve_env(m["api_key"]),
            label=m.get("label", m["model_id"]),
            context=m.get("context", DEFAULT_CONTEXT_WINDOW),
            tools=m.get("tools", True),
            system_prompt=m.get("system_prompt", True),
            explorer=m.get("explorer", False),
        )
        for m in data.get("models", [])
    ]


def pick_model(models: list[ModelPreset]) -> ModelPreset:
    def provider(api_base: str):
        if "google" in api_base:
            return "Google"
        if "yandex" in api_base:
            return "Yandex"
        return "Ollama"

    choices = [
        questionary.Choice(title=p.label, value=p, description=f"\n    Provider: {provider(p.api_base)}\n    Tools: {p.tools}")
        for p in models
    ]

    choice = questionary.select(
        "Choose a model:",
        choices=choices,
        use_indicator=True,
        show_description=True,
    ).ask()

    if choice:
        return choice

    exit()
