import asyncio
import ctypes
import threading
import time
import traceback

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.application import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import WordCompleter
from smolagents.memory import ActionStep, Timing

from .config import ModelPreset, pick_model, load_guard_config, load_config
from .utils import parse_arguments
from .guards import ToolDeniedException, set_guard_config
from .ui import console, print_session_separator, set_main_loop
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

# solver busy flag
is_solver_busy = asyncio.Event()


def get_prompt_decor():
    if is_solver_busy.is_set():
        return HTML('<b>❯</b> <ansiyellow>[BUSY]</ansiyellow> ')
    return HTML('<b>❯</b> ')


async def async_agent_loop():
    set_main_loop(asyncio.get_running_loop())
    args = parse_arguments()
    config = load_config()

    # get available presets
    custom_models = []
    if args.model and args.api_base and args.api_key:
        custom_models.append(ModelPreset(args.model, args.api_base, args.api_key, "Custom"))
    available_presets = custom_models + config.models
    available_explorer_presets = [p for p in available_presets if p.explorer]

    # models presets
    solver_preset = await pick_model(available_presets)
    explorer_preset = available_explorer_presets[0] if available_explorer_presets else solver_preset

    # models
    solver_model = make_model(solver_preset)
    explorer_model = make_model(explorer_preset)

    # agents
    explorer_agent = make_explorer_agent(explorer_model, use_code_format=not explorer_preset.tools)
    solver_agent = make_solver_agent(solver_preset, solver_model, explorer_agent)
    print_debug(f'[dim]{solver_agent.system_prompt}[/dim]')

    # session
    session_holder[0] = await pick_session()

    # print header
    def print_header():
        console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
        console.print(f"[dim][bold]Model:[/bold] {solver_preset.label}[/dim]")
    print_header()

    # commands
    custom_commands = config.custom_commands
    commands_list = ["?", "/quit", "/resume", "/new", "/model", "/compress", "/pure", "/fork"] + [c.command for c in custom_commands]

    # print commands
    console.print(f"Commands: {', '.join(commands_list[1:])}\nType ? for details")

    # load sessions
    load_session(solver_agent, session_holder[0])

    # print footer
    def print_footer():
        log_context_usage(None, solver_agent)
        print_session_separator()
    print_footer()

    # prompt configurations
    bindings = KeyBindings()

    @bindings.add('enter', filter=Condition(lambda: not is_solver_busy.is_set()))
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.newline()

    completer = WordCompleter(commands_list, ignore_case=True, sentence=True)
    prompt_session = PromptSession(key_bindings=bindings)

    # keyboard interrupt thread logic
    agent_thread_id = None

    def run_agent_sync(task, reset, inject_system_prompt):
        nonlocal agent_thread_id
        agent_thread_id = threading.current_thread().ident
        try:
            return solver_agent.run(task, reset=reset, inject_system_prompt=inject_system_prompt)
        finally:
            agent_thread_id = None

    def interrupt_agent():
        nonlocal agent_thread_id
        if agent_thread_id is not None:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(agent_thread_id),
                ctypes.py_object(KeyboardInterrupt),
            )

    # run agent task
    async def run_agent(task, inject_system_prompt):
        is_solver_busy.set()
        try:
            maybe_compress(solver_agent, session_holder, solver_preset)
            if not inject_system_prompt:
                console.print("[dim]running task without system prompt injection.[/dim]")

            final_answer = await asyncio.to_thread(run_agent_sync, task, False, inject_system_prompt)

            tools_used = []
            for step in solver_agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session_holder[0].add_entry(
                task=task,
                result=str(final_answer),
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
            is_solver_busy.clear()
            session_holder[0].save_auto()
            print_footer()

    # main loop
    while True:
        try:
            # user prompt
            with patch_stdout(raw=True):
                task = await prompt_session.prompt_async(
                    get_prompt_decor,
                    multiline=True,
                    completer=completer,
                    complete_while_typing=True
                )
                task = task.strip()
        except KeyboardInterrupt:
            if is_solver_busy.is_set():
                interrupt_agent()
            else:
                exit()
            continue

        # commands
        if task == "?":
            console.print("Commands:")
            commands = [
                "/quit - exit",
                "/resume - switch sessions",
                "/new - create a new session",
                "/model - switch model",
                "/compress - compress context",
                "/pure <prompt> - run without system prompt",
                "/fork - fork session"
            ]
            for cmd in commands:
                console.print(f"  {cmd}")

            if custom_commands:
                console.print("\nCustom commands:")
                prompt_limit = 100
                for cmd in custom_commands:
                    prompt_text = (cmd.prompt[:prompt_limit] + '...') if len(cmd.prompt) > prompt_limit else cmd.prompt
                    console.print(f"  {cmd.command} ➔ {prompt_text}")

            console.print("\nCtrl+C to stop execution")
            continue
        if task == "/quit":
            if session_holder[0].entries:
                session_holder[0].save_auto()
                console.print(f"[green]Session {session_holder[0].id} saved.[/green]")
            break
        if task == "/new":
            if session_holder[0].entries:
                session_holder[0].save_auto()
            session_holder[0] = Session()
            solver_agent.memory.reset()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
            print_footer()
            continue
        if task == "/fork":
            if session_holder[0].entries:
                session_holder[0].save_auto()

            new_session = Session(entries=list(session_holder[0].entries), is_forked=True)
            session_holder[0] = new_session

            console.print(f"[dim][bold]Session forked to:[/bold] {session_holder[0].id}[/dim]")
            print_footer()
            continue
        if task == "/compress":
            compress(solver_agent, session_holder)
            print_footer()
            continue
        if task == "/resume":
            if session_holder[0].entries:
                session_holder[0].save_auto()
            session_holder[0] = await pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
            load_session(solver_agent, session_holder[0])
            print_footer()
            continue
        if task == "/model":
            def switch_model(preset: ModelPreset):
                nonlocal solver_preset, solver_agent, explorer_agent, explorer_model
                if preset == solver_preset:
                    return
                solver_preset = preset
                new_model = make_model(preset)

                solver_agent = make_solver_agent(preset, new_model, explorer_agent)
                load_session(solver_agent, session_holder[0], print_history=False)
                console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]")
            switch_model(await pick_model(available_presets, default=solver_preset))
            print_footer()
            continue

        inject_system_prompt = True
        if task == "/pure":
            inject_system_prompt = False
            try:
                task = await prompt_session.prompt_async(
                    "❯ [PURE] ",
                    multiline=True,
                    completer=completer,
                    complete_while_typing=True
                )
                task = task.strip()
            except KeyboardInterrupt:
                continue

        for cmd in custom_commands:
            if task == cmd.command:
                task = cmd.prompt
                print_debug(task)

        if not task:
            continue

        asyncio.create_task(
            run_agent(task, inject_system_prompt)
        )


def main():
    try:
        asyncio.run(async_agent_loop())
    except KeyboardInterrupt:
        console.print("\n[dim]cya![/dim]")
        exit()
