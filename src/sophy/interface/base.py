from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod


class InterfaceBackend(ABC):
    """Abstract base class for user-facing I/O backends (CLI, Telegram, etc.)."""

    @abstractmethod
    async def get_input(self) -> str:
        """Block until the user sends a message. Returns the message text."""

    @abstractmethod
    async def prompt_confirm(self, message: str) -> bool:
        """Ask a yes/no confirmation. Returns True for yes."""

    @abstractmethod
    async def prompt_select(self, title: str, choices: list[dict]) -> dict | None:
        """Present a selection menu.

        Each choice dict has at least 'title' and 'value' keys.
        Returns the selected choice dict, or None on cancellation.
        """

    @abstractmethod
    def send_text(self, text: str, style: str = "") -> None:
        """Send plain or styled text to the user."""

    @abstractmethod
    def send_rule(self) -> None:
        """Send a horizontal separator."""

    @abstractmethod
    def send_status(self, text: str) -> None:
        """Send a status/footer message (e.g. token usage)."""


_frontend: "FrontendRouter | None" = None


def set_frontend(router: "FrontendRouter"):
    global _frontend
    _frontend = router


def get_frontend() -> "FrontendRouter":
    if _frontend is None:
        raise RuntimeError("FrontendRouter not initialized — call set_frontend() first")
    return _frontend


class FrontendRouter:
    """Multiplexes output to all backends, routes input to the active one."""

    def __init__(self):
        self.backends: list[InterfaceBackend] = []
        self._active_backend: InterfaceBackend | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def add_backend(self, backend: InterfaceBackend):
        self.backends.append(backend)
        if self._active_backend is None:
            self._active_backend = backend

    @property
    def active_backend(self) -> InterfaceBackend:
        if self._active_backend is None:
            raise RuntimeError("No backend registered")
        return self._active_backend

    @active_backend.setter
    def active_backend(self, backend: InterfaceBackend):
        self._active_backend = backend

    # --- Input (delegate to active backend) ---

    async def get_input(self) -> str:
        return await self.active_backend.get_input()

    async def prompt_confirm(self, message: str) -> bool:
        if len(self.backends) <= 1:
            return await self.active_backend.prompt_confirm(message)

        # Race all backends — first to respond wins.
        # Don't cancel losers: CLI's input() can't be safely cancelled.
        futs = [asyncio.ensure_future(b.prompt_confirm(message)) for b in self.backends]
        done, _ = await asyncio.wait(futs, return_when=asyncio.FIRST_COMPLETED)
        return done.pop().result()

    async def prompt_select(self, title: str, choices: list[dict]) -> dict | None:
        if len(self.backends) <= 1:
            return await self.active_backend.prompt_select(title, choices)

        futs = [asyncio.ensure_future(b.prompt_select(title, choices)) for b in self.backends]
        done, _ = await asyncio.wait(futs, return_when=asyncio.FIRST_COMPLETED)
        return done.pop().result()

    # --- Sync bridges for calling from agent thread ---

    def prompt_confirm_sync(self, message: str, timeout: float = 300) -> bool:
        """Sync bridge for prompt_confirm(). Call from agent thread.

        Raises ToolDeniedException on timeout (5 min default).
        """
        from sophy.tools.guards import ToolDeniedException

        assert self._loop is not None, "FrontendRouter: event loop not set"
        future = asyncio.run_coroutine_threadsafe(
            self.prompt_confirm(message), self._loop
        )
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise ToolDeniedException("Confirmation timed out")

    def get_input_sync(self, prompt_text: str = "", timeout: float = 300) -> str:
        """Sync bridge for get_input(). Call from agent thread."""
        from sophy.tools.guards import ToolDeniedException

        assert self._loop is not None, "FrontendRouter: event loop not set"
        future = asyncio.run_coroutine_threadsafe(
            self.active_backend.get_input(), self._loop
        )
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise ToolDeniedException("Input timed out")

    def prompt_select_sync(self, title: str, choices: list[dict], timeout: float = 300) -> dict | None:
        """Sync bridge for prompt_select(). Call from agent thread."""
        assert self._loop is not None, "FrontendRouter: event loop not set"
        future = asyncio.run_coroutine_threadsafe(
            self.prompt_select(title, choices), self._loop
        )
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            return None

    # --- Output (broadcast to all backends) ---

    def send_text(self, text: str, style: str = "") -> None:
        for b in self.backends:
            b.send_text(text, style)

    def send_rule(self) -> None:
        for b in self.backends:
            b.send_rule()

    def send_status(self, text: str) -> None:
        for b in self.backends:
            b.send_status(text)
