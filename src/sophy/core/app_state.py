from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sophy.core.config import load_guard_config
from sophy.core.session import Session
from sophy.core.session_utils.history_provider import set_history_provider
from sophy.tools.guards import set_guard_config

if TYPE_CHECKING:
    from sophy.interface.base import FrontendRouter


@dataclass
class AppState:
    session: Session = field(default_factory=Session)
    is_solver_busy: asyncio.Event = field(default_factory=asyncio.Event)
    agent_thread_id: int | None = None
    frontend: FrontendRouter | None = None


_current_app_state: AppState | None = None


def init_app() -> AppState:
    global _current_app_state

    set_guard_config(load_guard_config())

    state = AppState()
    set_history_provider(lambda *args, **kwargs: state.session.get_summary(*args, **kwargs))
    _current_app_state = state

    return state
