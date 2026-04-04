# Plan: Refactor `src/sophy/__main__.py`

## Goal
The `__main__.py` file has grown significantly and handles too many responsibilities (command dispatch, state management, event loop control, agent orchestration). We want to modularize it to support the new async architecture and improve maintainability.

## Proposed Changes

1. [DONE] **Modularize Commands (`commands.py`)**
   - Create `src/sophy/commands.py`.
   - Define a registry or a dispatch map for command handlers.
   - Replace the `if/elif` chain in the main loop with calls to these handlers.

2. **Refactor `async_agent_loop`**
   - Extract logic into smaller, dedicated functions:
     - `initialize_agents()` (presets, models, agents)
     - `configure_prompt()` (prompt configurations)
     - `configure_command_handler` (command handler)
     - move `run_agent` outside with its support function (run_agent_sync, interrupt_agent)
   - Move initialization logic out of the main loop.

3. **Improve State Management**
   - Replace `session_holder` (list-based) with a proper `AppContext` or `State` class.
   - Centralize `session`, `solver_agent`, `solver_preset`, etc., in this object.

4. **Refactor `run_agent` and Interrupt Logic**
   - Move agent execution and thread-based interruption logic to a new file or utility module (e.g., `src/sophy/agent_executor.py`).
   - Keep the main event loop clean and focused on input/command processing.

5. **Consolidate Initialization**
   - Create an `init_app()` function to handle global initializations (`set_guard_config`, setting up history providers, etc.).
   - This improves testability and simplifies the startup flow.
