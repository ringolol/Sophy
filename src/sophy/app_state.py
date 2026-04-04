import asyncio
from dataclasses import dataclass, field

from .config import load_guard_config
from .guards import set_guard_config
from .history_provider import set_history_provider
from .session import Session


@dataclass
class AppState:
    session: Session = field(default_factory=Session)
    is_solver_busy: asyncio.Event = field(default_factory=asyncio.Event)
    agent_thread_id: int | None = None


def init_app() -> AppState:
    set_guard_config(load_guard_config())

    state = AppState()
    set_history_provider(lambda *args, **kwargs: state.session.get_summary(*args, **kwargs))

    return state
