import asyncio
import os
import re
import json
from dataclasses import dataclass, field

import questionary

from .ui import console
from .paths import get_config_path


DEFAULT_CONTEXT_WINDOW = 128000


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
    config_path = get_config_path()
    project_dir = os.path.dirname(os.path.abspath(config_path))

    if not os.path.isfile(config_path):
        return GuardConfig(project_dir=project_dir)

    with open(config_path) as f:
        data = json.load(f)
    patterns = [re.compile(p) for p in data.get("allowed_command_patterns", [])]
    return GuardConfig(
        allow_all_edits=False,
        allowed_command_patterns=patterns,
        project_dir=project_dir,
    )


@dataclass
class CustomCommand:
    command: str
    prompt: str


@dataclass
class Config:
    models: list[ModelPreset]
    custom_commands: list[CustomCommand]


def load_config() -> Config:
    def _resolve_env(value: str) -> str:
        if value.startswith("$"):
            return os.environ.get(value[1:], "")
        return value

    config_path = get_config_path()

    if not os.path.isfile(config_path):
        return Config(models=[], custom_commands=[])
    with open(config_path) as f:
        data = json.load(f)

    models = [
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

    custom_commands = [
        CustomCommand(command=c["command"], prompt=c["prompt"])
        for c in data.get("custom_commands", [])
    ]

    return Config(models=models, custom_commands=custom_commands)


async def pick_model(models: list[ModelPreset], default: ModelPreset = None) -> ModelPreset:
    def provider(api_base: str):
        if "google" in api_base:
            return "Google"
        if "yandex" in api_base:
            return "Yandex"
        return "Ollama"

    if not models:
        console.print("[red]No Model Provided. Configure .sophy/config.json or use arguments to setup it.[/red]")
        exit(1)

    choices = [
        questionary.Choice(title=p.label, value=p, description=f"\n    Provider: {provider(p.api_base)}\n    Tools: {p.tools}")
        for p in models
    ]

    from questionary import Style
    style = Style([
        ('highlighted', 'fg:cyan'),
    ])

    default_index = 0
    if default:
        for i, p in enumerate(models):
            if p == default:
                default_index = i
                break

    choice = await asyncio.to_thread(
        lambda: questionary.select(
            "Choose a model:",
            choices=choices,
            default=models[default_index],
            use_indicator=True,
            show_description=True,
            style=style,
        ).ask()
    )

    if choice:
        return choice

    exit(1)
