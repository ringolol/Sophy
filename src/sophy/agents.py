import ctypes
import threading
from dataclasses import dataclass
from typing import Any

from .config import ModelPreset, pick_model, load_config
from .debug import print_debug
from .factory import make_model, make_solver_agent, make_explorer_agent
from .utils import parse_arguments


@dataclass
class AgentContext:
    solver_agent: Any
    explorer_agent: Any
    solver_preset: ModelPreset
    available_presets: list
    config: Any


async def initialize_agents() -> AgentContext:
    args = parse_arguments()
    config = load_config()

    # get available presets
    custom_models = []
    if args.model and args.api_base and args.api_key:
        custom_models.append(ModelPreset(args.model, args.api_base, args.api_key, "Custom"))
    available_presets = custom_models + config.models
    available_explorer_presets = [p for p in available_presets if p.explorer]

    # models presets
    solver_preset = await pick_model(available_presets)
    explorer_preset = available_explorer_presets[0] if available_explorer_presets else solver_preset

    # models
    solver_model = make_model(solver_preset)
    explorer_model = make_model(explorer_preset)

    # agents
    explorer_agent = make_explorer_agent(explorer_model, use_code_format=not explorer_preset.tools)
    solver_agent = make_solver_agent(solver_preset, solver_model, explorer_agent)
    print_debug(f'[dim]{solver_agent.system_prompt}[/dim]')

    return AgentContext(
        solver_agent=solver_agent,
        explorer_agent=explorer_agent,
        solver_preset=solver_preset,
        available_presets=available_presets,
        config=config,
    )


def run_agent_sync(agent_thread_id_holder, solver_agent, task, reset, inject_system_prompt):
    agent_thread_id_holder[0] = threading.current_thread().ident  # type: ignore
    try:
        return solver_agent.run(task, reset=reset, inject_system_prompt=inject_system_prompt)
    finally:
        agent_thread_id_holder[0] = None


def interrupt_agent(agent_thread_id_holder):
    tid = agent_thread_id_holder[0]
    if tid is not None:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(tid),
            ctypes.py_object(KeyboardInterrupt),
        )
