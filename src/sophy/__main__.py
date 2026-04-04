import asyncio
import ctypes
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any

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
from .ui import console, set_main_loop, print_footer
from .debug import print_debug
from .context_compression import maybe_compress
from .session import Session
from .history_provider import set_history_provider
from .factory import make_model, make_solver_agent, make_explorer_agent


# guards
set_guard_config(load_guard_config())

# sessions
session_holder = [Session()]
set_history_provider(session_holder[0].get_summary)

# solver busy flag
is_solver_busy = asyncio.Event()

# agent thread tracking
agent_thread_id_holder = [None]


@dataclass
class AgentContext:
    solver_agent: Any
    explorer_agent: Any
    solver_preset: ModelPreset
    available_presets: list
    config: Any


async def initialize_agents() -> AgentContext:
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

    return AgentContext(
        solver_agent=solver_agent,
        explorer_agent=explorer_agent,
        solver_preset=solver_preset,
        available_presets=available_presets,
        config=config,
    )


def configure_command_handler(ctx, session_holder) -> tuple[CommandHandler, list[str]]:
    command_handler = CommandHandler(
        ctx.solver_agent, session_holder, ctx.solver_preset, ctx.available_presets,
        ctx.explorer_agent, custom_commands=ctx.config.custom_commands,
    )

    commands_list = list(command_registry.commands.keys())
    slash_commands = [c for c in commands_list if c != "?"]
    console.print(f"Commands: {', '.join(slash_commands)}\nType ? for details")

    return command_handler, commands_list


def configure_prompt_toolkit(commands_list) -> tuple[PromptSession, WordCompleter]:
    bindings = KeyBindings()

    @bindings.add('enter', filter=Condition(lambda: not is_solver_busy.is_set()))
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.newline()

    completer = WordCompleter(commands_list, ignore_case=True, sentence=True)
    prompt_session: PromptSession = PromptSession(key_bindings=bindings)
    return prompt_session, completer


def setup_cli(ctx, session_holder) -> tuple[CommandHandler, PromptSession, WordCompleter]:
    command_handler, commands_list = configure_command_handler(ctx, session_holder)

    prompt_session, completer = configure_prompt_toolkit(commands_list)

    command_handler.prompt_fn = lambda prompt_text: prompt_session.prompt_async(
        prompt_text, multiline=True, completer=completer, complete_while_typing=True
    )

    return command_handler, prompt_session, completer


def get_prompt_decor():
    if is_solver_busy.is_set():
        return HTML('<b>❯</b> <ansiyellow>[BUSY]</ansiyellow> ')
    return HTML('<b>❯</b> ')


def run_agent_sync(solver_agent, task, reset, inject_system_prompt):
    agent_thread_id_holder[0] = threading.current_thread().ident  # type: ignore
    try:
        return solver_agent.run(task, reset=reset, inject_system_prompt=inject_system_prompt)
    finally:
        agent_thread_id_holder[0] = None


def interrupt_agent():
    tid = agent_thread_id_holder[0]
    if tid is not None:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(tid),
            ctypes.py_object(KeyboardInterrupt),
        )


async def run_agent(solver_agent, solver_preset, session_holder, task, inject_system_prompt):
    is_solver_busy.set()
    try:
        maybe_compress(solver_agent, session_holder, solver_preset)
        if not inject_system_prompt:
            console.print("[dim]running task without system prompt injection.[/dim]")

        final_answer = await asyncio.to_thread(run_agent_sync, solver_agent, task, False, inject_system_prompt)

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
        print_footer(solver_agent)


async def async_agent_loop():
    set_main_loop(asyncio.get_running_loop())

    ctx = await initialize_agents()

    command_handler, prompt_session, completer = setup_cli(ctx, session_holder)

    # session init (reuse /resume flow)
    console.print(f"[dim][bold]Model:[/bold] {ctx.solver_preset.label}[/dim]")
    await command_handler.handle_command("/resume")

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
            ctx.solver_agent = command_handler.solver_agent
            ctx.solver_preset = command_handler.solver_preset
            if result.consumed:
                continue
            task = result.task
            inject_system_prompt = result.inject_system_prompt

        if not task:
            continue

        asyncio.create_task(
            run_agent(ctx.solver_agent, ctx.solver_preset, session_holder, task, inject_system_prompt)
        )


def main():
    try:
        asyncio.run(async_agent_loop())
    except KeyboardInterrupt:
        console.print("\n[dim]cya![/dim]")
        exit(0)
