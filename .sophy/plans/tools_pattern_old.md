# Plan: Enhance `confirm` function in `guards.py`

## Goal
1.  **"Allow All Edits" Mode**: Implement a mode where the solver can edit files without user confirmation, provided the files are within the project directory.
2.  **Allowed Commands Patterns**: Allow running certain commands without confirmation based on regex patterns stored in `.sophy/config.json`.

## Detailed Steps

### 1. Update `guards.py`
- Modify the `confirm` function signature to accept parameters for "special mode" (e.g., `allow_all_edits`) and "command pattern checking".
- Add logic to check if a file path is within the project directory for the "allow all edits" mode.

### 2. Update `.sophy/config.json`
- Add a field (e.g., `allowed_command_patterns`) to store regex patterns for automatically allowed commands.
- Implement security validation to ensure these patterns are safe (e.g., preventing shell injection via chained commands like `|`, `&`, `>>`).

## Implementation Logic
- **Global State**: Introduce a global `SessionConfig` object or similar mechanism to track the current mode ("allow all edits", etc.) and reloadable configurations from `.sophy/config.json`.
- **Dynamic Configuration**: `confirm` will query this global state at runtime, allowing the mode to be toggled dynamically without re-applying decorators.
- **Path validation**: Use `os.path.abspath` and verify that the file path starts with the project\'s root path.
- **Command validation**:
 - Load patterns from `config.json`.
 - If a command matches a pattern, skip the `confirm` prompt.
 - If a command contains dangerous characters (`|`, `&`, `;`, `>`, etc.) and is NOT explicitly allowed, force a confirmation prompt regardless of patterns.


## Security Considerations
- Ensure that the "allow all edits" mode is strictly scoped to the project directory to prevent unauthorized modification of system or configuration files outside the workspace.
- The command pattern matcher must be conservative to prevent unintended execution of complex, potentially malicious command chains.
