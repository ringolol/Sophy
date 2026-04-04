import asyncio
import ctypes
import threading
import time
import traceback

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import WordCompleter
from smolagents.memory import ActionStep, Timing

from .commands import CommandHandler, command_registry
from .config import ModelPreset, pick_model, load_guard_config, load_config
from .utils import parse_arguments
from .guards import ToolDeniedException, set_guard_config
from .ui import console, print_session_separator, set_main_loop
from .debug import print_debug
from .context_compression import maybe_compress
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

    # command handler (registers custom commands into the registry)
    custom_commands = config.custom_commands

    async def prompt_fn(prompt_text):
        return await prompt_session.prompt_async(prompt_text, multiline=True, completer=completer, complete_while_typing=True)

    command_handler = CommandHandler(solver_agent, session_holder, solver_preset, available_presets, explorer_agent, custom_commands=custom_commands, prompt_fn=prompt_fn)

    commands_list = list(command_registry.commands.keys())
    slash_commands = [c for c in commands_list if c != "?"]
    console.print(f"Commands: {', '.join(slash_commands)}\nType ? for details")

    # prompt configurations
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

    while True:
        try:
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
                exit(0)
            continue

        inject_system_prompt = True
        if task in command_registry.commands:
            result = await command_handler.handle_command(task)
            solver_agent = command_handler.solver_agent
            solver_preset = command_handler.solver_preset
            if result.consumed:
                continue
            task = result.task
            inject_system_prompt = result.inject_system_prompt

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
        exit(0)
