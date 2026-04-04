# Custom Commands Feature Plan

## Overview
Implement a "custom commands" feature that allows users to define custom commands in `.sophy/config.json`. These commands can map a short command string (e.g., `/git`) to a pre-defined prompt that will be sent to the `solver_agent`.

## Tasks

1. **Update Configuration Structure**:
   - Add a `custom_commands` field to `.sophy/config.json`.
   - The field should be a list of objects: `{"command": string, "prompt": string}`.

2. **Handle Custom Commands in `__main__.py`**:
   - Modify the main input loop in `src/sophy/__main__.py` to check user input against defined custom commands.
   - If a match is found:
     - Replace the user input with the corresponding `prompt`.
     - Pass this prompt directly to `solver_agent.run()`.

## Implementation Details

- **Config Handling**: Ensure the new `custom_commands` field is correctly loaded when the configuration is parsed in `src/sophy/config.py` or wherever it is currently handled.
- **Main Loop Logic**:
  - In `src/sophy/__main__.py`, before passing input to the `solver_agent`, iterate through `custom_commands`.
  - Perform string matching (e.g., `if input.startswith(command)` or strict equality depending on requirements).
  - Inject the prompt if a match occurs.
