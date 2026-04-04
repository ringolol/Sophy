#!/usr/bin/env python3

import time
import traceback

from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import WordCompleter
from smolagents.memory import ActionStep, Timing

from .config import ModelPreset, pick_model, load_guard_config, load_config
from .utils import parse_arguments
from .guards import ToolDeniedException, set_guard_config
from .ui import console, print_session_separator
from .debug import print_debug
from .context_compression import maybe_compress, compress
from .session import Session, load_session, pick_session
from .history_provider import set_history_provider
from .factory import log_context_usage, make_model, make_solver_agent, make_explorer_agent


# guards
set_guard_config(load_guard_config())

# sessions
session_holder = [Session()]
set_history_provider(session_holder[0].get_summary)


def agent_loop():
    args = parse_arguments()
    config = load_config()
    custom_models = []
    if args.model and args.api_base and args.api_key:
        custom_models.append(ModelPreset(args.model, args.api_base, args.api_key, "Custom"))
    available_presets = custom_models + config.models
    custom_commands = config.custom_commands
    solver_preset = pick_model(available_presets)

    available_explorer_presets = [p for p in available_presets if p.explorer]
    explorer_preset = available_explorer_presets[0] if available_explorer_presets else solver_preset

    # models
    explorer_model = make_model(explorer_preset)
    solver_model = make_model(solver_preset)

    # agents
    explorer_agent = make_explorer_agent(explorer_model, use_code_format=not explorer_preset.tools)
    solver_agent = make_solver_agent(solver_preset, solver_model, explorer_agent)

    def switch_model(preset: ModelPreset):
        nonlocal solver_preset, solver_agent, explorer_agent, explorer_model
        solver_preset = preset
        new_model = make_model(preset)

        solver_agent = make_solver_agent(preset, new_model, explorer_agent)
        load_session(solver_agent, session_holder[0], print_history=False)
        console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]")
        print_session_separator()

    print_debug(f'[dim]{solver_agent.system_prompt}[/dim]')
    session_holder[0] = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
    console.print(f"[dim][bold]Model:[/bold] {solver_preset.label}[/dim]")
    console.print("Type /quit to exit, /resume to switch sessions, /new to create a new session, /model to switch model, /compress to compress context. Ctrl+C to stop execution")
    load_session(solver_agent, session_holder[0])
    print_session_separator()

    bindings = KeyBindings()

    @bindings.add('enter')
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.newline()

    commands = ['/quit', '/new', '/fork', '/compress', '/resume', '/model'] + [c.command for c in custom_commands]
    completer = WordCompleter(commands, ignore_case=True, sentence=True)

    while True:
        session = session_holder[0]
        try:
            task = prompt(
                "❯ ",
                multiline=True,
                key_bindings=bindings,
                completer=completer,
                complete_while_typing=True
            ).strip()
        except KeyboardInterrupt:
            console.print("[dim]cya[/dim]")
            exit()
        if not task:
            continue

        if task == "/quit":
            if session.entries:
                session.save_auto()
                console.print(f"[green]Session {session.id} saved.[/green]")
            break
        if task == "/new":
            if session.entries:
                session.save_auto()
            session_holder[0] = Session()
            solver_agent.memory.reset()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            print_session_separator()
            continue
        if task == "/fork":
            if session.entries:
                session.save_auto()
            
            # Create a new session and copy the entries from the current one
            new_session = Session(entries=list(session.entries), is_forked=True)
            session_holder[0] = new_session
            
            # The memory is already restored in solver_agent due to load_session(solver_agent, session) 
            # happening before or during the loop, but we should ensure the agent's memory 
            # matches the new session (which is a copy of the old one anyway).
            # The solver_agent's memory is already at the state of the current session entries.
            
            console.print(f"[dim][bold]Session forked to:[/bold] {session_holder[0].id}[/dim]\n")
            print_session_separator()
            continue
        if task == "/compress":
            compress(solver_agent, session_holder)
            continue
        if task == "/resume":
            if session.entries:
                session.save_auto()
            session_holder[0] = pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            load_session(solver_agent, session_holder[0])
            print_session_separator()
            continue
        if task == "/model":
            switch_model(pick_model(available_presets, default=solver_preset))
            continue

        for cmd in custom_commands:
            if task == cmd.command:
                task = cmd.prompt
                print_debug(task)

        try:
            maybe_compress(solver_agent, session_holder, solver_preset)
            result = solver_agent.run(task, reset=False)
            log_context_usage(_, solver_agent)
            session = session_holder[0]

            tools_used = []
            for step in solver_agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session.add_entry(
                task=task,
                result=str(result),
                steps=solver_agent.memory.get_full_steps(),
                tools_used=tools_used,
            )
        except (KeyboardInterrupt, ToolDeniedException):
            console.print(f"\n[red]The execution was stopped manually[/red]\n")
            observation_step = ActionStep(
                step_number=solver_agent.step_number,
                observations="[User stopped the last tool execution manually! Be attentive User could ask you to change something about the last task!]",
                timing=Timing(start_time=time.time(), end_time=time.time())
            )
            solver_agent.memory.steps.append(observation_step)
            session_holder[0].add_entry(
                task=task,
                result="[interrupted]",
                steps=solver_agent.memory.get_full_steps(),
                tools_used=[tc.name for step in solver_agent.memory.steps if isinstance(step, ActionStep) and step.tool_calls for tc in step.tool_calls],
            )
        except Exception:
            console.print(f'[red]{traceback.format_exc()}[/red]')
        finally:
            session_holder[0].save_auto()


def main():
    try:
        agent_loop()
    except KeyboardInterrupt:
        console.print("\n[dim]cya![/dim]")
        exit()


if __name__ == "__main__":
    main()
