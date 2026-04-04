import asyncio
from dataclasses import dataclass, field

from .config import load_guard_config
from .guards import set_guard_config
from .history_provider import set_history_provider
from .session import Session


@dataclass
class AppState:
    session_holder: list = field(default_factory=list)
    is_solver_busy: asyncio.Event = field(default_factory=asyncio.Event)
    agent_thread_id_holder: list = field(default_factory=lambda: [None])


def init_app() -> AppState:
    set_guard_config(load_guard_config())

    session_holder = [Session()]
    set_history_provider(session_holder[0].get_summary)

    return AppState(
        session_holder=session_holder,
        is_solver_busy=asyncio.Event(),
        agent_thread_id_holder=[None],
    )
