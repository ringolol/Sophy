from __future__ import annotations

import asyncio
import html
import re
import traceback

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.enums import ParseMode

from sophy.interface.base import InterfaceBackend
from sophy.interface.ui import console
from sophy.utils.debug import print_debug

TELEGRAM_MSG_LIMIT = 4096



_CODE_OPEN_RE = re.compile(r'^<pre><code(?:\s[^>]*)?>')
_CODE_CLOSE = "</code></pre>"


def _split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """Split a message into chunks that fit Telegram's limit."""

    if len(text) <= limit:
        return [text]

    # Detect <pre><code ...> wrapper (with optional class attribute)
    m = _CODE_OPEN_RE.match(text)
    is_code = m is not None and text.endswith(_CODE_CLOSE)

    if is_code:
        tag_open = m.group(0)
        tag_overhead = len(tag_open) + len(_CODE_CLOSE)
        limit -= tag_overhead
        text = text[len(tag_open):-len(_CODE_CLOSE)]
    else:
        tag_open = ""

    def try_wrap(s: str) -> str:
        if not is_code:
            return s
        return f"{tag_open}{s}{_CODE_CLOSE}"

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(try_wrap(text))
            break
        # Try to split at newline
        split_at = text.rfind('\n', 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(try_wrap(text[:split_at]))
        text = text[split_at:].lstrip('\n')
    return chunks


class TelegramBackend(InterfaceBackend):
    """InterfaceBackend implementation for Telegram using aiogram."""

    def __init__(self, token: str, chat_id: int, loop: asyncio.AbstractEventLoop):
        self._bot = Bot(token=token)
        self._dp = Dispatcher()
        self._router = Router()
        self._dp.include_router(self._router)

        self._chat_id = chat_id
        self._loop = loop
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._confirm_queue: asyncio.Queue[bool] = asyncio.Queue()
        self._select_queue: asyncio.Queue[str | None] = asyncio.Queue()

        self._polling_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._register_handlers()

    def _register_handlers(self):
        @self._router.message(F.chat.id == self._chat_id)
        async def on_message(message: Message):
            text = message.text
            if not text:
                return

            print_debug(f"chat_id={message.chat.id} text={text!r}", debug_name="TG INPUT")

            # Handle /stop — interrupt agent without going through input queue
            if text.strip() == "/stop":
                from sophy.agents.agents import interrupt_agent
                try:
                    from sophy.core.app_state import _current_app_state
                    if _current_app_state and _current_app_state.is_solver_busy.is_set():
                        interrupt_agent(_current_app_state)
                        await self._send_plain("Agent interrupted.")
                    else:
                        await self._send_plain("Agent is not running.")
                except Exception:
                    print_debug(traceback.format_exc(), debug_name="TG /stop ERROR")
                    await self._send_plain("Could not interrupt agent.")
                return

            # Telegram sends /command as text — normalize to match Sophy's format
            # e.g. "/new" stays "/new", "/model" stays "/model"
            self._input_queue.put_nowait(text)

        @self._router.callback_query(F.message.chat.id == self._chat_id)
        async def on_callback(callback: CallbackQuery):
            data = callback.data or ""
            print_debug(f"callback data={data!r}", debug_name="TG CALLBACK")
            await callback.answer()

            if data in ("confirm_yes", "confirm_no"):
                self._confirm_queue.put_nowait(data == "confirm_yes")
                if callback.message:
                    label = "Yes" if data == "confirm_yes" else "No"
                    try:
                        await callback.message.edit_text(  # type: ignore[union-attr]
                            f"{callback.message.text}\n> {label}",  # type: ignore[union-attr]
                        )
                    except Exception:
                        print_debug(traceback.format_exc(), debug_name="TG EDIT CONFIRM")
            elif data.startswith("select_"):
                self._select_queue.put_nowait(data.removeprefix("select_"))
                if callback.message:
                    try:
                        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
                    except Exception:
                        print_debug(traceback.format_exc(), debug_name="TG EDIT SELECT")

    def register_as_console_listener(self):
        """Register this backend as a listener on the ObservableConsole.

        All console.print() output will be forwarded to Telegram as plain text.
        """
        console.add_listener(self._on_console_output)

    def _on_console_output(self, plain_text: str):
        text = plain_text.strip()
        if not text:
            return
        # Skip horizontal rules — console.rule() renders as long ─ lines
        if all(c in "─ " for c in text):
            return
        asyncio.run_coroutine_threadsafe(self._send(text), self._loop)

    async def _set_bot_commands(self):
        """Register Sophy commands in Telegram's command menu."""
        from sophy.interface.commands import command_registry

        commands = []
        for cmd, command in command_registry.commands.items():
            if not cmd.startswith("/"):
                continue
            # Telegram commands must be lowercase, no leading slash in the API
            name = cmd.lstrip("/")
            commands.append(BotCommand(command=name, description=command.description))

        # Add Telegram-only commands
        commands.append(BotCommand(command="stop", description="interrupt running agent"))

        await self._bot.set_my_commands(commands)

    async def start_polling(self):
        """Start the bot polling loop. Call as a background task."""
        self.register_as_console_listener()
        await self._set_bot_commands()
        print_debug(f"chat_id={self._chat_id}", debug_name="TG POLLING START")
        self._polling_task = asyncio.create_task(
            self._dp.start_polling(self._bot, handle_signals=False)
        )
        await self._send("Bot connected.")

    async def stop(self):
        if self._polling_task:
            self._polling_task.cancel()
        await self._bot.session.close()

    async def _send(self, text: str):
        """Send an HTML message, splitting if needed."""
        for chunk in _split_message(text):
            try:
                await self._bot.send_message(
                    self._chat_id, chunk, parse_mode=ParseMode.HTML
                )
            except Exception:
                print_debug(traceback.format_exc(), debug_name="TG SEND HTML")
                # Fallback to plain text if HTML fails
                try:
                    plain = re.sub(r'<[^>]+>', '', chunk)
                    await self._bot.send_message(self._chat_id, plain)
                except Exception:
                    print_debug(traceback.format_exc(), debug_name="TG SEND FALLBACK")

    async def _send_plain(self, text: str):
        """Send a plain text message, splitting if needed."""
        for chunk in _split_message(text):
            try:
                await self._bot.send_message(self._chat_id, chunk)
            except Exception:
                print_debug(traceback.format_exc(), debug_name="TG SEND PLAIN")

    # --- InterfaceBackend implementation ---

    async def get_input(self) -> str:
        return await self._input_queue.get()

    async def prompt_confirm(self, message: str) -> bool:
        # Drain any stale confirms
        while not self._confirm_queue.empty():
            self._confirm_queue.get_nowait()

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Yes", callback_data="confirm_yes"),
            InlineKeyboardButton(text="No", callback_data="confirm_no"),
        ]])
        clean_msg = re.sub(r'\[y/n\]:?\s*$', '', message, flags=re.IGNORECASE).strip()
        await self._bot.send_message(
            self._chat_id, clean_msg, reply_markup=keyboard
        )
        return await self._confirm_queue.get()

    _SELECT_MAX_BUTTONS = 20

    async def prompt_select(self, title: str, choices: list[dict]) -> dict | None:
        while not self._select_queue.empty():
            self._select_queue.get_nowait()

        # Telegram limits total inline keyboard size — cap number of buttons
        capped = choices[:self._SELECT_MAX_BUTTONS]
        buttons = []
        for i, c in enumerate(capped):
            buttons.append([
                InlineKeyboardButton(
                    text=c["title"],
                    callback_data=f"select_{i}",
                )
            ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await self._bot.send_message(
            self._chat_id, title, reply_markup=keyboard
        )

        data = await self._select_queue.get()
        if data is None:
            return None
        try:
            idx = int(data)
            return choices[idx]
        except (ValueError, IndexError):
            return None

    def send_text(self, text: str, style: str = "") -> None:
        asyncio.run_coroutine_threadsafe(self._send_plain(text), self._loop)

    def send_rule(self) -> None:
        return
        # asyncio.run_coroutine_threadsafe(
        #     self._send_plain("───────────────"), self._loop
        # )

    def send_status(self, text: str) -> None:
        asyncio.run_coroutine_threadsafe(self._send_plain(text), self._loop)
