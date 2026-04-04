# Plan: Dedicated Explorer Model

## Current State
- `sophy.py` creates an explorer agent (`ToolCallingAgent`) using the same model as the main agent.
- The model for both agents can be changed via `/model` command, which calls `switch_model` that updates `explorer.model` and recreates the main agent.
- Model presets are defined in `.sophy/config.json` with fields: `model_id`, `label`, `api_base`, `api_key`, `tools`, `system_prompt`.

## Desired Behavior
- The explorer agent should use a dedicated model, which is determined at startup and remains fixed (not changeable by user).
- The model for the explorer should be configurable via a new boolean field `"explorer": true` in `config.json`. If multiple models have `explorer: true`, we select the first one.
- If no model is marked as explorer, fallback to using the same model as the main agent at the start.

## Implementation Steps

### 1. Extend `ModelPreset` dataclass
- In `utils.py`, add a field `explorer: bool = False` to the `ModelPreset` dataclass.

### 2. Update `load_config`
- In `utils.py`, modify `load_config` to read the `explorer` field from JSON (default `False`).

### 3. Determine explorer model at startup
- In `sophy.py`, after loading presets, we need to pick an explorer model:
   - Filter `_available_presets` (those with API keys) for presets with `explorer=True`.
   - If any, choose one (e.g., the first). Let's call it `_explorer_preset`.
   - Otherwise, set `_explorer_preset = _active_preset` (the main agent's initial model).

### 4. Create explorer with its own model
- Instead of using `model` (which is built from `_active_preset`), create a separate model for the explorer:
   - `explorer_model = _make_model(_explorer_preset)`
   - Use `explorer_model` when constructing the explorer agent.

### 5. Modify `switch_model`
- In `switch_model`, we should NOT update `explorer.model`. Remove the line `explorer.model = new_model`.
- Only update the main agent's model.

## Edge Cases
- If the user changes the main model via `/model`, the explorer model stays the same.

## Testing
- Create a test config with a model marked as explorer.
- Run Sophy and verify that the explorer uses that model (by checking logs or using a test that prints model info).
- Use `/model` to switch main agent model and verify that explorer model does not change.

## Files to Change
- `utils.py`: extend `ModelPreset` and `load_config`.
- `sophy.py`: adjust startup logic and `switch_model`.

