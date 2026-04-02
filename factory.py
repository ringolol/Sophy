from utils import ModelPreset, load_config, console, MAX_AGENT_STEPS
from smolagents import ToolCallingAgent, LogLevel, CodeAgent
from prompts import build_solver_prompt, explorer_prompt
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

def make_main_agent(preset: ModelPreset, model: ThinkingModel, explorer_agent):
    base_kwargs = dict(
        tools=TOOLS,
        add_base_tools=False,
        model=model,
        max_steps=MAX_AGENT_STEPS,
        verbosity_level=LogLevel.INFO,
        stream_outputs=True,
        managed_agents=[explorer_agent],
        step_callbacks=[remind_final_answer],
    )
    if preset.tools:
        agent = ToolCallingAgent(
            **{
                **base_kwargs,
                "prompt_templates": build_solver_prompt(use_code_format=False),
            }
        )
    else:
        agent = CodeAgent(
            **{
                **base_kwargs,
                "prompt_templates": build_solver_prompt(use_code_format=True),
            }
        )
    apply_monkey_patches(agent)
    return agent

def make_explorer_agent(model: ThinkingModel):
    explorer = ToolCallingAgent(
        tools=EXPLORATION_TOOLS,
        add_base_tools=False,
        prompt_templates=explorer_prompt,
        model=model,
        max_steps=MAX_AGENT_STEPS,
        verbosity_level=LogLevel.INFO,
        stream_outputs=True,
        name="explorer",
        description="-",
        provide_run_summary=False,
        step_callbacks=[remind_final_answer],
    )
    apply_explorer_monkey_patches(explorer)
    return explorer
