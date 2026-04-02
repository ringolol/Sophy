#!/usr/bin/env python3

import traceback
from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import WordCompleter
from smolagents.memory import ActionStep

from utils import ToolDeniedException, ModelPreset, pick_model, console, parse_arguments, print_debug
from context_compression import maybe_compress, compress
from tools import set_history_provider
from session import Session, load_session, pick_session
from factory import get_model_presets, make_model, make_solver_agent, make_explorer_agent


# sessions
session_holder = [Session()]
set_history_provider(session_holder[0].get_summary)


def agent_loop():
    args = parse_arguments()

    available_presets = get_model_presets(args)
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
        load_session(solver_agent, session_holder[0])
        console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]\n")

    print_debug(f'[dim]{solver_agent.system_prompt}[/dim]')
    session_holder[0] = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
    console.print(f"[dim][bold]Model:[/bold] {solver_preset.label}[/dim]")
    console.print("Type /quit to exit, /resume to switch sessions, /new to create a new session, /model to switch model, /compress to compress context. Ctrl+C to stop execution\n")
    load_session(solver_agent, session_holder[0])

    bindings = KeyBindings()

    @bindings.add('enter')
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.newline()

    commands = ['/quit', '/new', '/compress', '/resume', '/model']
    completer = WordCompleter(commands, ignore_case=True, sentence=True)

    task_prefix = ""
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
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session_holder[0] = Session()
            solver_agent.memory.reset()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            continue
        if task == "/compress":
            compress(solver_agent, session_holder)
            continue
        if task == "/resume":
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session_holder[0] = pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            load_session(solver_agent, session_holder[0])
            continue
        if task == "/model":
            switch_model(pick_model(available_presets))
            continue

        try:
            maybe_compress(solver_agent, session_holder, solver_preset)
            result = solver_agent.run(task_prefix + task, reset=False)
            task_prefix = ""
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
            task_prefix = "[User stopped the last tool execution manually! Be attentive User could ask you to change something about the last task!]\n\n"
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
