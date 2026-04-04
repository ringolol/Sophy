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
3.  **KeyBinding Updates**:
    - Modify `KeyBindings` to conditionally disable the `enter` key submission when `is_busy` is set.
    - If `is_busy` is set and the user presses `enter`, print a warning: "Agent is busy, please wait for it to finish."
4.  **Async Loop**:
    ```python
    async def async_agent_loop():
        with patch_stdout():
            # Define KeyBindings with condition
            bindings = KeyBindings()
            
            @bindings.add('enter', filter=~is_busy_condition)
            def _(event):
                event.current_buffer.validate_and_handle()
                
            @bindings.add('enter', filter=is_busy_condition)
            def _(event):
                console.print("[yellow]Agent is busy, please wait for it to finish.[/yellow]")

            while True:
                task = await session.prompt_async("\n❯ ", key_bindings=bindings)
                # The prompt now only returns if the agent is not busy
                await asyncio.to_thread(solver_agent.run, task)
    ```
5.  **Refactor**:
    - Update all calls to `solver_agent.run` to be wrapped in thread execution.
    - Ensure `session_holder` and `solver_agent` state access is protected/synchronized.

## 4. Risks & Mitigations
- **Thread Safety**: Use locks if multiple threads modify `session.entries` or agent memory.
- **UI Flickering**: Ensure `Rich` console prints are captured by `patch_stdout()`.
