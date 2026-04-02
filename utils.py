import argparse
import functools
import os
from smolagents.memory import ActionStep

import config
import guards
import ui

MAX_AGENT_STEPS = 30

def remind_final_answer(step):
    """Callback to remind agent to call final_answer when running low on steps."""
    if not isinstance(step, ActionStep):
        return
    if step.step_number > MAX_AGENT_STEPS - 1:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You have no more steps! "
            "Call `final_answer` NOW with your best answer."
        )

def parse_arguments():
    parser = argparse.ArgumentParser(description="Sophy coding agent harness")
    parser.add_argument("--api_base", type=str, default=None, help="API base URL for the model")
    parser.add_argument("--api_key", type=str, default=None, help="API key for the model")
    parser.add_argument("--model", type=str, default=None, help="Model ID to use")
    return parser.parse_args()

def pick_model(models: list[config.ModelPreset]) -> config.ModelPreset:
    import questionary
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
