# Plan: Support User-Level Fallback for .sophy

## Objective
Implement a fallback mechanism where `sophy` searches for data/configuration in `~/.sophy` if the corresponding file or folder is not found in the project's local `.sophy/` directory.

## Current Usage Analysis
Currently, `.sophy/` is hardcoded for:
- `config.json`: Loaded by `src/sophy/config.py`.
- `sessions/`: Used by `src/sophy/session.py` to store chat history.

## Proposed Changes

### 1. Configuration (`src/sophy/config.py`)
- Modify `load_config` and `load_guard_config` to:
    - Check for local `CONFIG_PATH = ".sophy/config.json"`.
    - If not found, check `os.path.expanduser("~/.sophy/config.json")`.
    - Handle cases where user-level config might be missing as well.

### 2. Sessions (`src/sophy/session.py`)
- Modify session directory logic:
    - Define a base search path for sessions.
    - When listing or creating sessions, prioritize the project-local `.sophy/sessions/` directory.
    - To support user-level sessions for multiple projects, structure the global session storage as: `~/.sophy/sessions/{proj_path_str}/`.
    - `proj_path_str` should be the sanitized absolute path of the project, replacing all non `[a-zA-Z]` characters with `_`.
    - If local session folder does not exist, initialize it in the project root, but for global persistence, use the project-specific path under `~/.sophy/sessions/`.

### 3. Utility / Helper Functions
- Create a `sophy_path(relative_path: str)` and a `get_project_session_dir()` helper function:
    ```python
    import re
    import os

    def get_project_session_dir() -> str:
        # Sanitize path: replace non-alphabetic/underscore chars with _
        abs_path = os.path.abspath(os.getcwd())
        proj_path_str = re.sub(r'[^a-zA-Z]', '_', abs_path)
        return os.path.expanduser(f"~/.sophy/sessions/{proj_path_str}")
    ```
- Update all hardcoded `.sophy/` references to use these helpers.

## Implementation Steps
1. Refactor path resolution in `config.py` and `session.py` to use a unified path helper.
2. Ensure that write operations (like creating a new session) still default to the project-local `.sophy/` folder to prevent cluttering the user's home directory unless explicitly configured otherwise.
3. Verify behavior with both local and user-level configs present.
