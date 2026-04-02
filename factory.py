from utils import ModelPreset, load_config, console, MAX_AGENT_STEPS
from smolagents import ToolCallingAgent, LogLevel, CodeAgent
from prompts import build_prompt, AgentRole
from tools import TOOLS, EXPLORATION_TOOLS
from monkey_patches import apply_monkey_patches, apply_explorer_monkey_patches
from model import ThinkingModel
from utils import remind_final_answer


def get_model_presets(args):
    _all_presets = load_config()
    if args.model and args.api_base and args.api_key:
        _all_presets.append(ModelPreset(args.model, args.api_base, args.api_key, "Custom"))

    _available_presets = [p for p in _all_presets if p.api_key]
    if not _available_presets:
        console.print("[red]No models available. Provide --model/--api_base/--api_key args or create .sophy/config.json[/red]")
        raise SystemExit(1)

    return _available_presets

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

def make_agent(
    role: AgentRole,
    model: ThinkingModel,
    tools: list,
    extra_kwargs: dict = None,
    monkey_patch_func=None,
    use_code_format: bool = False
):
    base_kwargs = dict(
        tools=tools,
        add_base_tools=False,
        model=model,
        max_steps=MAX_AGENT_STEPS,
        verbosity_level=LogLevel.INFO,
        stream_outputs=True,
        step_callbacks=[remind_final_answer],
    )
    if extra_kwargs:
        base_kwargs.update(extra_kwargs)

    agent_class = CodeAgent if use_code_format else ToolCallingAgent
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
