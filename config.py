import os
import json
from dataclasses import dataclass

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


def _resolve_env(value: str) -> str:
    if value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value

def load_config() -> list[ModelPreset]:
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
