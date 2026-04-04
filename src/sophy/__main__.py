import asyncio
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

is_busy = asyncio.Event()

def get_prompt_decor():
    if is_busy.is_set():
        return HTML('<b>❯</b> <ansiyellow>[BUSY]</ansiyellow> ')
    return HTML('<b>❯</b> ')

def refresh_ui():
    try:
        get_app().invalidate()
    except Exception:
        pass

@Condition
def is_not_busy():
    return not is_busy.is_set()

async def async_agent_loop():
    set_main_loop(asyncio.get_running_loop())
    args = parse_arguments()
    config = load_config()
    custom_models = []
    if args.model and args.api_base and args.api_key:
        custom_models.append(ModelPreset(args.model, args.api_base, args.api_key, "Custom"))
    available_presets = custom_models + config.models
    custom_commands = config.custom_commands
    solver_preset = await pick_model(available_presets)

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
        if preset == solver_preset:
            return
        solver_preset = preset
        new_model = make_model(preset)

        solver_agent = make_solver_agent(preset, new_model, explorer_agent)
        load_session(solver_agent, session_holder[0], print_history=False)
        console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]")

    print_debug(f'[dim]{solver_agent.system_prompt}[/dim]')
    session_holder[0] = await pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
    console.print(f"[dim][bold]Model:[/bold] {solver_preset.label}[/dim]")

    commands_list = ["?", "/quit", "/resume", "/new", "/model", "/compress", "/pure", "/fork"] + [c.command for c in custom_commands]
    console.print(f"Commands: {', '.join(commands_list[1:])}\nType ? for details")

    load_session(solver_agent, session_holder[0])
    print_session_separator()

    bindings = KeyBindings()

    @bindings.add('enter', filter=is_not_busy)
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.newline()

    completer = WordCompleter(commands_list, ignore_case=True, sentence=True)
    session = PromptSession(key_bindings=bindings)

    async def run_agent(task, inject_system_prompt):
        is_busy.set()
        refresh_ui()
        try:
            maybe_compress(solver_agent, session_holder, solver_preset)
            if not inject_system_prompt:
                console.print("[dim]running task without system prompt injection.[/dim]")

            # Use run_in_executor/to_thread to keep UI alive
            result = await asyncio.to_thread(solver_agent.run, task, reset=False, inject_system_prompt=inject_system_prompt)

            log_context_usage(_, solver_agent)

            tools_used = []
            for step in solver_agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session_holder[0].add_entry(
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
            is_busy.clear()
            refresh_ui()
            session_holder[0].save_auto()

    while True:
        with patch_stdout(raw=True):
            task = await session.prompt_async(
                get_prompt_decor,
                multiline=True,
                completer=completer,
                complete_while_typing=True
            )
            task = task.strip()

        if not task:
            continue

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
            print_session_separator()
            continue
        if task == "/fork":
            if session_holder[0].entries:
                session_holder[0].save_auto()

            new_session = Session(entries=list(session_holder[0].entries), is_forked=True)
            session_holder[0] = new_session

            console.print(f"[dim][bold]Session forked to:[/bold] {session_holder[0].id}[/dim]")
            print_session_separator()
            continue
        if task == "/compress":
            compress(solver_agent, session_holder)
            print_session_separator()
            continue
        if task == "/resume":
            if session_holder[0].entries:
                session_holder[0].save_auto()
            session_holder[0] = await pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
            load_session(solver_agent, session_holder[0])
            print_session_separator()
            continue
        if task == "/model":
            switch_model(await pick_model(available_presets, default=solver_preset))
            print_session_separator()
            continue

        inject_system_prompt = True
        if task.startswith("/pure"):
            inject_system_prompt = False
            task = task.replace("/pure", "").strip()

        if not task:
            continue

        for cmd in custom_commands:
            if task == cmd.command:
                task = cmd.prompt
                print_debug(task)

        asyncio.create_task(run_agent(task, inject_system_prompt))


def main():
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If a loop is already running, we can't use asyncio.run()
            # We just create a task in the current loop
            loop.create_task(async_agent_loop())
        else:
            asyncio.run(async_agent_loop())
    except KeyboardInterrupt:
        console.print("\n[dim]cya![/dim]")
        exit()
