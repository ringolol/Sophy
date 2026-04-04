# Refactoring Plan for sophy.py

## Objectives
- Reduce complexity of `sophy.py` by extracting logic into dedicated modules.
- Create a clear separation between configuration, model initialization, agent creation, and the main interaction loop.

## Proposed Changes

### 1. New Module: `factory.py`
Create `factory.py` to handle the instantiation logic for models and agents.
- **Move `_make_model(preset: ModelPreset)`**: From `sophy.py` to `factory.py`.
- **Move `_make_main_agent(...)`**: From `sophy.py` to `factory.py`.
- **Create `make_explorer_agent(...)`**: Extract the explorer agent creation logic from `sophy.py` to `factory.py`.

### 2. Update `sophy.py`
- **Argument Parsing**: Extract the `argparse` logic into a function `parse_arguments()` and move it to `utils.py` or a new `config.py` (if applicable). Given the project structure, `utils.py` seems appropriate.
- **Clean-up**:
    - Import the factory functions from `factory.py`.
    - Simplify the top-level script by calling `parse_arguments()` and the factory functions.
    - Keep only the `agent_loop` and the main entry point logic in `sophy.py`.

## Implementation Steps

1.  **Create `factory.py`**: Implement model and agent creation logic.
2.  **Update `utils.py`**: Add `parse_arguments()` function.
3.  **Refactor `sophy.py`**:
    - Clean up imports.
    - Remove the moved functions and variable initialization logic.
    - Call the new initialization functions in `main()`.
4.  **Verification**: Ensure the functionality remains unchanged (manual testing of basic commands).
