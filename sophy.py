#!/usr/bin/env python3

import traceback

from smolagents.memory import ActionStep

from utils import ToolDeniedException, ModelPreset, pick_model, console, parse_arguments
from context_compression import maybe_compress, compress
from tools import set_history_provider
from session import Session, load_session, pick_session
from factory import get_model_presets, make_model, make_main_agent, make_explorer_agent


session_holder = [Session()]
set_history_provider(session_holder[0].get_summary)

args = parse_arguments()

_available_presets = get_model_presets(args)

if len(_available_presets) == 1:
    _active_preset = _available_presets[0]
else:
    _active_preset = pick_model(_available_presets)

explorer_presets = [p for p in _available_presets if p.explorer]
if explorer_presets:
    _explorer_preset = explorer_presets[0]
else:
    _explorer_preset = _active_preset

def switch_model(preset: ModelPreset):
    global _active_preset, main_agent
    _active_preset = preset
    new_model = make_model(preset)
    main_agent = make_main_agent(preset, new_model, explorer)
    console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]\n")

# models
explorer_model = make_model(_explorer_preset)
main_model = make_model(_active_preset)

# agents
explorer = make_explorer_agent(explorer_model)
main_agent = make_main_agent(_active_preset, main_model, explorer)


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
