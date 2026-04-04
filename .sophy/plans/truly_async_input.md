# Plan: Truly Async Agent Execution with Non-Blocking UI

The current implementation uses `await asyncio.to_thread(solver_agent.run, ...)`, which correctly offloads the agent execution but still `await`s its completion in the main loop before returning to `prompt_async()`. This blocks the user from entering new tasks while the agent is running.

## Objectives
- Allow the agent to run in the background.
- Keep the prompt active and available for the user to see, but **disabled** while the agent is active.
- Prevent the user from submitting a new task until the agent completes.

## Architectural Strategy
Instead of `await`ing the agent execution directly in the main `while` loop, we will treat the agent as a background task.

1.  **Background Task Management**: 
    - Keep a reference to the active `asyncio.Task` for the agent.
    - When a command is submitted, it is run as a background task, and the UI state is set to `is_busy`.

2.  **Implementation**:
    - `while True` loop will only contain `await session.prompt_async()`.
    - When a command is entered, use `asyncio.create_task(run_agent(task))` to start the agent.
    - The prompt session key-bindings should include a filter to prevent submission (the `enter` key) while `is_busy` is set.
    - The `run_agent` task will update `is_busy` state, which will automatically update the UI prompt via `get_prompt()`.

## Steps
1.  **Modify `async_agent_loop`**:
    - Ensure `is_busy` (Event) is checked in `prompt_toolkit` `Condition` on the `enter` keybinding.
    - When a task is accepted, set `is_busy` and `asyncio.create_task(run_agent(task))`.
2.  **Define `run_agent(task_text, ...)`**:
    - Wrapper function to run `solver_agent.run` in a thread, handle state (`is_busy`), and UI updates (clearing `is_busy` and refreshing).
    - It must handle exceptions, update history, and `finally` clear `is_busy`.
3.  **UI/UX**:
    - The `get_prompt` function will automatically show the `[BUSY]` status.
    - Ensure `patch_stdout` is used properly so that background output does not overwrite the prompt buffer.

## Code Implementation Example

```python
# In src/sophy/__main__.py

async def run_agent(task, inject_system_prompt):
    is_busy.set()
    refresh_ui()
    try:
        # Perform logic from the current loop's "if task" block here
        # ... e.g., maybe_compress, then to_thread, then add_entry ...
    finally:
        is_busy.clear()
        refresh_ui()
        session_holder[0].save_auto()

# In main while loop:
        if not task: continue
        # ... (other commands)
        
        # New task execution:
        asyncio.create_task(run_agent(task, inject_system_prompt))
```
