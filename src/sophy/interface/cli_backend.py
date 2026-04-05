from __future__ import annotations

import asyncio

import questionary
from questionary import Style
from prompt_toolkit.application import run_in_terminal

from sophy.interface.base import InterfaceBackend
from sophy.interface.ui import console


_QUESTIONARY_STYLE = Style([("highlighted", "fg:cyan")])


class CLIBackend(InterfaceBackend):
    """InterfaceBackend implementation for the terminal (prompt_toolkit + Rich)."""

    async def get_input(self) -> str:
        # Actual input is handled by the main REPL loop in __main__.py
        # This method is used when the agent thread needs user input (e.g. ask_user tool)
        def _ask():
            return input("❯ ")

        async def _run():
            import sys
            sys.stdout.flush()
            await asyncio.sleep(0.21)
            return await run_in_terminal(_ask, in_executor=False)

        return await _run()

    async def prompt_confirm(self, message: str) -> bool:
        def _ask():
            return input(message)

        async def _run():
            import sys
            sys.stdout.flush()
            await asyncio.sleep(0.21)
            return await run_in_terminal(_ask, in_executor=False)

        while True:
            answer = (await _run()).strip().lower()
            if answer in ("y", "n"):
                return answer == "y"

    async def prompt_select(self, title: str, choices: list[dict]) -> dict | None:
        # Map questionary values back to original choice dicts
        value_to_choice = {}
        q_choices = []
        for c in choices:
            val = c.get("value", c)
            key = id(val)
            value_to_choice[key] = c
            q_choices.append(questionary.Choice(
                title=c["title"],
                value=val,
                description=c.get("description"),
            ))

        selected = await asyncio.to_thread(
            lambda: questionary.select(
                title,
                choices=q_choices,
                use_indicator=True,
                style=_QUESTIONARY_STYLE,
            ).ask()
        )

        if selected is None:
            return None
        return value_to_choice.get(id(selected))

    def send_text(self, text: str, style: str = "") -> None:
        if style:
            console.print(f"[{style}]{text}[/{style}]")
        else:
            console.print(text)

    def send_code(self, code: str, language: str = "") -> None:
        from rich.syntax import Syntax
        console.print(Syntax(code, language or "text", theme="monokai", word_wrap=True))

    def send_diff(self, diff_text: str) -> None:
        from rich.syntax import Syntax
        console.print(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))

    def send_rule(self) -> None:
        console.rule(style="dim")

    def send_status(self, text: str) -> None:
        console.print(f"[dim]{text}[/dim]")
