# Plan: Refactor Sophy for Asynchronous Input
This plan outlines the steps to refactor Sophy to support non-blocking user input while the solver agent is running.

## 1. Objectives
- Allow the user to type into the prompt buffer during `solver_agent.run()`.
- Prevent the user from submitting the task until `solver_agent.run()` completes.
- Keep the UI responsive and prevent garbled console output.

## 2. Architectural Changes
- **Move to `async`**: Convert `agent_loop` and the main entry point to `async`.
- **Use `prompt_toolkit` Async**: Switch from `prompt()` to `PromptSession.prompt_async()`.
- **Concurrency**: Use `asyncio.to_thread()` to execute `solver_agent.run()` in a separate thread, keeping the main event loop running for UI responsiveness.
- **Console Synchronization**: Use `patch_stdout()` to ensure that agent output and user input coexist without breaking the terminal view.

## 3. Implementation Steps
1.  **Dependencies**: Ensure `asyncio` and `prompt_toolkit.patch_stdout` are utilized.
2.  **State Management**: Introduce `asyncio.Event` to track whether the agent is active (`is_busy`).
3.  **KeyBinding & UI Updates**:
    - Introduce `asyncio.Event` to track whether the agent is active (`is_busy`).
    - Use a dynamic `HTML` prompt function (`get_prompt`) that shows `❯ [BUSY] ` when the agent is running.
    - Call `get_app().invalidate()` whenever `is_busy` changes to force a prompt refresh.
    - Use a `prompt_toolkit` `Condition` to disable the `enter` key submission when `is_busy` is set.
4.  **Async Loop**:
    ```python
    import asyncio
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import Condition

    is_busy = asyncio.Event()

    def get_prompt():
        if is_busy.is_set():
            return HTML('<b><ansicyan>❯</ansicyan></b> <ansired>[BUSY]</ansired> ')
        return HTML('<b><ansicyan>❯</ansicyan></b> ')

    def refresh_ui():
        try:
            get_app().invalidate()
        except Exception:
            pass

    @Condition
    def is_not_busy():
        return not is_busy.is_set()

    async def async_agent_loop():
        session = PromptSession()
        # Add the filter to your enter key binding
        @bindings.add('enter', filter=is_not_busy)
        def _(event):
            event.current_buffer.validate_and_handle()

        while True:
            with patch_stdout():
                # prompt_async will automatically call get_prompt()
                task = await session.prompt_async(get_prompt, key_bindings=bindings)

            is_busy.set()
            refresh_ui()

            try:
                # asyncio.to_thread keeps the UI event loop alive while the agent runs
                await asyncio.to_thread(solver_agent.run, task)
            ...
            finally:
                is_busy.clear()
                refresh_ui()
    ```

5.  **Refactor**:
    - Update all calls to `solver_agent.run` to be wrapped in thread execution.
