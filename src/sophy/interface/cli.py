from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import WordCompleter

from sophy.interface.commands import CommandHandler, command_registry
from sophy.interface.ui import console


def configure_command_handler(ctx, app_state) -> tuple[CommandHandler, list[str]]:
    command_handler = CommandHandler(
        ctx.solver_agent, app_state, ctx.solver_preset, ctx.available_presets,
        ctx.explorer_agent, custom_commands=ctx.config.custom_commands,
    )

    commands_list = list(command_registry.commands.keys())
    slash_commands = [c for c in commands_list if c != "?"]
    console.print(f"Commands: {', '.join(slash_commands)}\nType ? for details")

    return command_handler, commands_list


def configure_prompt_toolkit(is_solver_busy, commands_list) -> tuple[PromptSession, WordCompleter]:
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


def setup_cli(ctx, app_state) -> tuple[CommandHandler, PromptSession, WordCompleter]:
    command_handler, commands_list = configure_command_handler(ctx, app_state)

    prompt_session, completer = configure_prompt_toolkit(app_state.is_solver_busy, commands_list)

    command_handler.prompt_fn = lambda prompt_text: prompt_session.prompt_async(
        prompt_text, multiline=True, completer=completer, complete_while_typing=True
    )

    return command_handler, prompt_session, completer


def get_prompt_decor(is_solver_busy):
    def _decor():
        if is_solver_busy.is_set():
            return HTML('<b>❯</b> <ansiyellow>[BUSY]</ansiyellow> ')
        return HTML('<b>❯</b> ')
    return _decor
