#!/usr/bin/env python3

import argparse
import os
import traceback

from smolagents import ToolCallingAgent, LogLevel, CodeAgent
from smolagents.memory import ActionStep

from monkey_patches import apply_monkey_patches, apply_explorer_monkey_patches
from utils import ToolDeniedException, ModelPreset, load_config, pick_model, console, remind_final_answer, MAX_AGENT_STEPS
from context_compression import maybe_compress, compress
from model import ThinkingModel
from tools import TOOLS, EXPLORATION_TOOLS, set_history_provider
from session import Session, load_session, pick_session
from prompts import direct_solver_prompt, direct_code_solver_prompt, explorer_prompt


session_holder = [Session()]
set_history_provider(session_holder[0].get_summary)

parser = argparse.ArgumentParser(description="Sophy coding agent harness")
parser.add_argument("--api_base", type=str, default=None, help="API base URL for the model")
parser.add_argument("--api_key", type=str, default=None, help="API key for the model")
parser.add_argument("--model", type=str, default=None, help="Model ID to use")
args = parser.parse_args()

_all_presets = load_config()
if args.model and args.api_base and args.api_key:
    _all_presets.append(ModelPreset(args.model, args.api_base, args.api_key, "Custom"))

_available_presets = [p for p in _all_presets if p.api_key]
if not _available_presets:
    console.print("[red]No models available. Provide --model/--api_base/--api_key args or create .sophy/config.json[/red]")
    raise SystemExit(1)

if len(_available_presets) == 1:
    _active_preset = _available_presets[0]
else:
    _active_preset = pick_model(_available_presets)

explorer_presets = [p for p in _available_presets if p.explorer]
if explorer_presets:
    _explorer_preset = explorer_presets[0]
else:
    _explorer_preset = _active_preset


def _make_model(preset: ModelPreset) -> ThinkingModel:
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
        **kwargs,
    )


def _make_main_agent(preset: ModelPreset, model: ThinkingModel):
    base_kwargs = dict(
        tools=TOOLS,
        add_base_tools=False,
        model=model,
        max_steps=MAX_AGENT_STEPS,
        verbosity_level=LogLevel.INFO,
        stream_outputs=True,
        managed_agents=[explorer],
        step_callbacks=[remind_final_answer],
    )
    if preset.tools:
        agent = ToolCallingAgent(
            **{
                **base_kwargs,
                "prompt_templates": direct_solver_prompt
            }
        )
    else:
        agent = CodeAgent(
            **{
                **base_kwargs,
                "prompt_templates": direct_code_solver_prompt,
            }
        )
    apply_monkey_patches(agent)
    return agent


def switch_model(preset: ModelPreset):
    global _active_preset, main_agent
    _active_preset = preset
    new_model = _make_model(preset)
    main_agent = _make_main_agent(preset, new_model)
    console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]\n")


# Create separate models for explorer and main agent
explorer_model = _make_model(_explorer_preset)
main_model = _make_model(_active_preset)

explorer = ToolCallingAgent(
    tools=EXPLORATION_TOOLS,
    add_base_tools=False,
    prompt_templates=explorer_prompt,
    model=explorer_model,
    max_steps=MAX_AGENT_STEPS,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    name="explorer",
    description="-",
    provide_run_summary=False,
    step_callbacks=[remind_final_answer],
)
apply_explorer_monkey_patches(explorer)

main_agent = _make_main_agent(_active_preset, main_model)

def agent_loop():
    console.print(f'[dim]{main_agent.system_prompt}[/dim]')
    session_holder[0] = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
    console.print(f"[dim][bold]Model:[/bold] {_active_preset.label}[/dim]")
    console.print("Type /quit to exit, /resume to switch sessions, /new to create a new session, /model to switch model, /compress to compress context. Ctrl+C to stop execution\n")
    load_session(main_agent, session_holder[0])

    task_prefix = ""
    while True:
        session = session_holder[0]
        task = input("❯ ").strip()
        if not task:
            continue
        if task == "/quit":
            if session.entries:
                session.save_auto()
                console.print(f"[green]Session {session.id} saved.[/green]")
            break
        if task == "/new":
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session_holder[0] = Session()
            main_agent.memory.reset()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            continue
        if task == "/compress":
            compress(main_agent, session_holder)
            continue
        if task == "/resume":
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session_holder[0] = pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            load_session(main_agent, session_holder[0])
            continue
        if task == "/model":
            preset = pick_model(_available_presets, _active_preset.model_id)
            switch_model(preset)
            continue

        try:
            maybe_compress(main_agent, session_holder)
            result = main_agent.run(task_prefix + task, reset=False)
            task_prefix = ""
            session = session_holder[0]

            tools_used = []
            for step in main_agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session.add_entry(
                task=task,
                result=str(result),
                steps=main_agent.memory.get_full_steps(),
                tools_used=tools_used,
            )
        except (KeyboardInterrupt, ToolDeniedException):
            console.print(f"\n[red]The execution was stopped manually[/red]\n")
            task_prefix = "[User stopped the last tool execution manually! Be attentive User could ask you to change something about the last task!]\n\n"
            session_holder[0].add_entry(
                task=task,
                result="[interrupted]",
                steps=main_agent.memory.get_full_steps(),
                tools_used=[tc.name for step in main_agent.memory.steps if isinstance(step, ActionStep) and step.tool_calls for tc in step.tool_calls],
            )
        except Exception:
            console.print(f'[red]{traceback.format_exc()}[/red]')
        finally:
            session_holder[0].save_auto()


def main():
    agent_loop()


if __name__ == "__main__":
    main()
