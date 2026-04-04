from dataclasses import dataclass
from typing import Callable, Dict, Optional
from .ui import console, print_footer
from .session import Session, load_session, pick_session
from .agent_factory import make_solver_agent, make_model
from .config import pick_model
from .context_compression import compress
from .debug import print_debug

@dataclass
class Command:
    cmd: str
    description: str
    handler: Callable

@dataclass
class CommandResult:
    consumed: bool = True
    task: Optional[str] = None
    inject_system_prompt: bool = True

class CommandRegistry:
    commands: Dict[str, Command]

    def __init__(self):
        self.commands = {}

    def add(self, cmd: str, description: str):
        def decorator(func: Callable):
            self.commands[cmd] = Command(cmd=cmd, description=description, handler=func)
            return func
        return decorator

command_registry = CommandRegistry()


class CommandHandler:
    def __init__(self, solver_agent, app_state, solver_preset, available_presets, explorer_agent, custom_commands=None, prompt_fn=None):
        self.solver_agent = solver_agent
        self.app_state = app_state
        self.solver_preset = solver_preset
        self.available_presets = available_presets
        self.explorer_agent = explorer_agent
        self.custom_commands = custom_commands or []
        self.prompt_fn = prompt_fn
        self._register_custom_commands()

    def _print_footer(self):
        print_footer(self.solver_agent)

    def _register_custom_commands(self):
        for cmd in self.custom_commands:
            prompt = cmd.prompt

            async def handler(handler, prompt=prompt):
                print_debug(prompt)
                return CommandResult(consumed=False, task=prompt)

            command_registry.commands[cmd.command] = Command(
                cmd=cmd.command,
                description=f"custom: {cmd.prompt[:50]}{'...' if len(cmd.prompt) > 50 else ''}",
                handler=handler,
            )

    async def handle_command(self, command_str) -> CommandResult:
        if command_str in command_registry.commands:
            result = await command_registry.commands[command_str].handler(self)
            return result if isinstance(result, CommandResult) else CommandResult(consumed=True)
        return CommandResult(consumed=True)


@command_registry.add(cmd="?", description="show this help")
async def help_handler(handler: CommandHandler):
    console.print("Commands:")
    for cmd in command_registry.commands.values():
        console.print(f"  {cmd.cmd} - {cmd.description}")
    console.print("\nCtrl+C to stop execution")


@command_registry.add(cmd="/quit", description="exit")
async def quit_handler(handler: CommandHandler):
    if handler.app_state.session.entries:
        handler.app_state.session.save_auto()
        console.print(f"[green]Session {handler.app_state.session.id} saved.[/green]")
    exit(0)


@command_registry.add(cmd="/new", description="create a new session")
async def new_handler(handler: CommandHandler):
    if handler.app_state.session.entries:
        handler.app_state.session.save_auto()
    handler.app_state.session = Session()
    handler.solver_agent.memory.reset()
    console.print(f"[dim][bold]Session:[/bold] {handler.app_state.session.id}[/dim]")
    handler._print_footer()


@command_registry.add(cmd="/fork", description="fork session")
async def fork_handler(handler: CommandHandler):
    if handler.app_state.session.entries:
        handler.app_state.session.save_auto()
    new_session = Session(entries=list(handler.app_state.session.entries), is_forked=True)
    handler.app_state.session = new_session
    console.print(f"[dim][bold]Session forked to:[/bold] {handler.app_state.session.id}[/dim]")
    handler._print_footer()


@command_registry.add(cmd="/compress", description="compress context")
async def compress_handler(handler: CommandHandler):
    compress(handler.solver_agent, handler.app_state)
    handler._print_footer()


@command_registry.add(cmd="/resume", description="switch sessions")
async def resume_handler(handler: CommandHandler):
    if handler.app_state.session.entries:
        handler.app_state.session.save_auto()
    handler.app_state.session = await pick_session()
    console.print(f"[dim][bold]Session:[/bold] {handler.app_state.session.id}[/dim]")
    load_session(handler.solver_agent, handler.app_state.session)
    handler._print_footer()


@command_registry.add(cmd="/model", description="switch model")
async def model_handler(handler: CommandHandler):
    preset = await pick_model(handler.available_presets, default=handler.solver_preset)
    if preset != handler.solver_preset:
        handler.solver_preset = preset
        new_model = make_model(preset)
        handler.solver_agent = make_solver_agent(preset, new_model, handler.explorer_agent)
        load_session(handler.solver_agent, handler.app_state.session, print_history=False)
        console.print(f"[dim][bold]Model:[/bold] {preset.label}[/dim]")
    handler._print_footer()


@command_registry.add(cmd="/pure", description="send prompt without system prompt injection")
async def pure_handler(handler: CommandHandler):
    try:
        task = await handler.prompt_fn("❯ [PURE] ")
        task = task.strip()
    except KeyboardInterrupt:
        return CommandResult(consumed=True)
    if not task:
        return CommandResult(consumed=True)
    return CommandResult(consumed=False, task=task, inject_system_prompt=False)
