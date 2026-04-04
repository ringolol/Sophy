import typing

from .config import ModelPreset
from .ui import console
from .utils import MAX_AGENT_STEPS, remind_final_answer
from smolagents import LogLevel
from .patched_agents import CustomToolCallingAgent, CustomCodeAgent
from .prompts import build_prompt, AgentRole
from .tools import TOOLS, EXPLORATION_TOOLS
from .smolagents_patches import apply_monkey_patches, apply_explorer_monkey_patches
from .patched_model import ThinkingModel


def make_model(preset: ModelPreset) -> ThinkingModel:
    kwargs = {}
    if not preset.system_prompt:
        kwargs["custom_role_conversions"] = {
            "system": "user",
            "tool-call": "assistant",
            "tool-response": "user",
        }
    return ThinkingModel(
        model_id=preset.model_id,
        api_base=preset.api_base,
        api_key=preset.api_key,
        context_window=preset.context,
        **kwargs,
    )

def log_context_usage(step_log, agent):
    # Try to get token usage from the latest step
    if agent.memory.steps and hasattr(agent.memory.steps[-1], "token_usage") and agent.memory.steps[-1].token_usage:
        input_tokens = agent.memory.steps[-1].token_usage.input_tokens
        context_window = agent.model.context_window
        if input_tokens and context_window:
            usage_ratio = input_tokens / context_window
            color = "green"
            if usage_ratio > 1:
                color = "red"
            elif usage_ratio > 0.8:
                color = "yellow"
            bar_length = 10
            filled_length = int(bar_length * usage_ratio)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            console.print(
                f"[dim]Context usage: [{color}]{bar} {usage_ratio:.0%}[/{color}][/dim]"
            )

def make_agent(
    role: AgentRole,
    model: ThinkingModel,
    tools: list,
    extra_kwargs: typing.Optional[dict] = None,
    monkey_patch_func=None,
    use_code_format: bool = False
):
    base_kwargs: dict = dict(
        tools=tools,
        add_base_tools=False,
        model=model,
        max_steps=MAX_AGENT_STEPS,
        verbosity_level=LogLevel.ERROR,
        stream_outputs=True,
        step_callbacks=[remind_final_answer],
    )
    if extra_kwargs:
        base_kwargs.update(extra_kwargs)

    agent_class = CustomCodeAgent if use_code_format else CustomToolCallingAgent
    agent = agent_class(
        **base_kwargs,
        prompt_templates=build_prompt(role, use_code_format=use_code_format),
    )
    if monkey_patch_func:
        monkey_patch_func(agent)
    return agent

def make_solver_agent(preset: ModelPreset, model: ThinkingModel, explorer_agent):
    return make_agent(
        role=AgentRole.SOLVER,
        model=model,
        tools=TOOLS,
        extra_kwargs={"managed_agents": [explorer_agent]},
        monkey_patch_func=apply_monkey_patches,
        use_code_format=not preset.tools
    )

def make_explorer_agent(model: ThinkingModel, use_code_format: bool = False):
    return make_agent(
        role=AgentRole.EXPLORER,
        model=model,
        tools=EXPLORATION_TOOLS,
        extra_kwargs={"name": "explorer", "description": "-"},
        monkey_patch_func=apply_explorer_monkey_patches,
        use_code_format=use_code_format
    )
