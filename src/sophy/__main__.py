import asyncio
import time
import traceback

from prompt_toolkit.patch_stdout import patch_stdout
from smolagents.memory import ActionStep, Timing

from sophy.agents.agents import initialize_agents, run_agent_sync, interrupt_agent
from sophy.core.app_state import init_app
from sophy.core.session_utils.context_compression import maybe_compress
from sophy.interface.base import FrontendRouter, set_frontend
from sophy.interface.cli import setup_cli, get_prompt_decor
from sophy.interface.cli_backend import CLIBackend
from sophy.interface.commands import command_registry
from sophy.tools.guards import ToolDeniedException
from sophy.interface.ui import console, set_main_loop, print_footer


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
            timing=Timing(start_time=time.time(), end_time=time.time())
        )
        solver_agent.memory.steps.append(observation_step)
        app_state.session.add_entry(
            task=task,
            result="[interrupted]",
            steps=solver_agent.memory.get_full_steps(),
            tools_used=[tc.name for step in solver_agent.memory.steps if isinstance(step, ActionStep) and step.tool_calls for tc in step.tool_calls],
        )
    except Exception:
        console.print(f'[red]{traceback.format_exc()}[/red]')
    finally:
        app_state.is_solver_busy.clear()
        app_state.session.save_auto()
        print_footer(solver_agent)


async def async_agent_loop():
    loop = asyncio.get_running_loop()
    set_main_loop(loop)

    # Initialize frontend router with CLI backend
    frontend = FrontendRouter()
    frontend.set_loop(loop)
    frontend.add_backend(CLIBackend())
    set_frontend(frontend)

    app_state = init_app()
    app_state.frontend = frontend
    ctx = await initialize_agents()

    command_handler, prompt_session, completer = setup_cli(ctx, app_state)
    prompt_decor = get_prompt_decor(app_state.is_solver_busy)

    # session init (reuse /resume flow)
    console.print(f"[dim][bold]Model:[/bold] {ctx.solver_preset.label}[/dim]")
    await command_handler.handle_command("/resume")

    while True:
        try:
            with patch_stdout(raw=True):
                task = await prompt_session.prompt_async(
                    prompt_decor,
                    multiline=True,
                    completer=completer,
                    complete_while_typing=True
                )
                task = task.strip()
        except KeyboardInterrupt:
            if app_state.is_solver_busy.is_set():
                interrupt_agent(app_state)
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
            run_agent(app_state, ctx.solver_agent, ctx.solver_preset, task, inject_system_prompt)
        )


def main():
    try:
        asyncio.run(async_agent_loop())
    except KeyboardInterrupt:
        console.print("\n[dim]cya![/dim]")
        exit(0)
