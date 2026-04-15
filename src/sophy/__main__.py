import asyncio
import os
import time
import traceback

from prompt_toolkit.patch_stdout import patch_stdout
from smolagents.memory import ActionStep, Timing

from sophy.agents.agents import initialize_agents, interrupt_agent, run_agent_sync
from sophy.core.app_state import init_app
from sophy.core.session_utils.context_compression import maybe_compress
from sophy.interface.base import FrontendRouter, set_frontend
from sophy.interface.cli import get_prompt_decor, setup_cli
from sophy.interface.cli_backend import CLIBackend
from sophy.interface.commands import command_registry
from sophy.interface.ui import console, print_footer, set_main_loop
from sophy.tools.guards import ToolDeniedException
from sophy.utils.utils import parse_arguments


async def run_agent(app_state, solver_agent, solver_preset, task, inject_system_prompt):
    app_state.is_solver_busy.set()
    try:
        maybe_compress(solver_agent, app_state, solver_preset)
        if not inject_system_prompt:
            console.print("[dim]running task without system prompt injection.[/dim]")

        final_answer = await asyncio.to_thread(
            run_agent_sync, app_state, solver_agent, task, False, inject_system_prompt
        )

        tools_used = []
        for step in solver_agent.memory.steps:
            if isinstance(step, ActionStep) and step.tool_calls:
                for tc in step.tool_calls:
                    tools_used.append(tc.name)

        app_state.session.add_entry(
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
            timing=Timing(start_time=time.time(), end_time=time.time()),
        )
        solver_agent.memory.steps.append(observation_step)
        app_state.session.add_entry(
            task=task,
            result="[interrupted]",
            steps=solver_agent.memory.get_full_steps(),
            tools_used=[
                tc.name
                for step in solver_agent.memory.steps
                if isinstance(step, ActionStep) and step.tool_calls
                for tc in step.tool_calls
            ],
        )
    except Exception:
        console.print(f"[red]{traceback.format_exc()}[/red]")
    finally:
        app_state.is_solver_busy.clear()
        app_state.session.save_auto()
        print_footer(solver_agent)


async def start_telegram(
    frontend: FrontendRouter, loop: asyncio.AbstractEventLoop
) -> None:
    """Start Telegram backend and add it to the frontend router."""
    from sophy.interface.telegram_backend import TelegramBackend

    token = os.environ.get("SOPHY_TELEGRAM_TOKEN", "")
    chat_id_str = os.environ.get("SOPHY_TELEGRAM_CHAT_ID", "")

    if not token:
        console.print("[red]SOPHY_TELEGRAM_TOKEN env var not set.[/red]")
        return
    if not chat_id_str:
        console.print("[red]SOPHY_TELEGRAM_CHAT_ID env var not set.[/red]")
        return

    try:
        chat_id = int(chat_id_str)
    except ValueError:
        console.print("[red]SOPHY_TELEGRAM_CHAT_ID must be an integer.[/red]")
        return

    tg = TelegramBackend(token, chat_id, loop)
    frontend.add_backend(tg)
    await tg.start_polling()
    console.print("[green]Telegram bot connected.[/green]")


async def _get_cli_input(prompt_session, prompt_decor, completer):
    """Get input from CLI. Returns (task_str, 'cli') or raises KeyboardInterrupt."""
    with patch_stdout(raw=True):
        task = await prompt_session.prompt_async(
            prompt_decor,
            multiline=True,
            completer=completer,
            complete_while_typing=True,
        )
    return task.strip()


async def _get_telegram_input(frontend: FrontendRouter) -> str:
    """Get input from any non-CLI backend (Telegram). Waits forever."""
    # Get input from the second backend (index 1 = Telegram)
    if len(frontend.backends) < 2:
        # No Telegram backend, block forever
        await asyncio.Event().wait()
        return ""  # unreachable
    return await frontend.backends[1].get_input()


async def async_agent_loop():
    loop = asyncio.get_running_loop()
    set_main_loop(loop)

    args = parse_arguments()

    # Initialize frontend router with CLI backend
    frontend = FrontendRouter()
    frontend.set_loop(loop)
    cli_backend = CLIBackend()
    frontend.add_backend(cli_backend)
    set_frontend(frontend)

    # Start Telegram early so it's available during model selection
    if args.telegram:
        await start_telegram(frontend, loop)

    app_state = init_app()
    app_state.frontend = frontend
    ctx = await initialize_agents(args)

    command_handler, prompt_session, completer = setup_cli(ctx, app_state)
    prompt_decor = get_prompt_decor(app_state.is_solver_busy)

    # session init (reuse /resume flow)
    console.print(f"[dim][bold]Model:[/bold] {ctx.solver_preset.label}[/dim]")
    await command_handler.handle_command("/resume")

    # Persistent futures — never cancel the CLI prompt, reuse across iterations
    cli_fut: asyncio.Future[str] | None = None
    tg_fut: asyncio.Future[str] | None = None

    while True:
        task = None
        source_backend = cli_backend
        has_telegram = len(frontend.backends) > 1

        try:
            if not has_telegram:
                # CLI-only mode (original behavior)
                task = await _get_cli_input(prompt_session, prompt_decor, completer)
            else:
                # Ensure both futures are alive
                if cli_fut is None or cli_fut.done():
                    cli_fut = asyncio.ensure_future(
                        _get_cli_input(prompt_session, prompt_decor, completer)
                    )
                if tg_fut is None or tg_fut.done():
                    tg_fut = asyncio.ensure_future(_get_telegram_input(frontend))

                # Race — do NOT cancel the loser
                done, _pending = await asyncio.wait(
                    {cli_fut, tg_fut}, return_when=asyncio.FIRST_COMPLETED
                )

                winner = done.pop()
                if winner is tg_fut:
                    source_backend = frontend.backends[1]
                    tg_fut = None  # consumed, will recreate next iteration
                else:
                    cli_fut = None  # consumed, will recreate next iteration
                task = winner.result()
        except KeyboardInterrupt:
            if app_state.is_solver_busy.is_set():
                interrupt_agent(app_state)
            else:
                exit(0)
            continue

        if not task:
            continue

        # Set active backend for this task (confirmations will go here)
        frontend.active_backend = source_backend

        # Mirror the user prompt to the other backends
        for b in frontend.backends:
            if b is not source_backend:
                b.send_text(f"❯ {task}")

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
            run_agent(
                app_state,
                ctx.solver_agent,
                ctx.solver_preset,
                task,
                inject_system_prompt,
            )
        )


def main():
    try:
        asyncio.run(async_agent_loop())
    except KeyboardInterrupt:
        console.print("\n[dim]cya![/dim]")
        exit(0)
