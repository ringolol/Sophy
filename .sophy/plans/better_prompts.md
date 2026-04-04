# Findings on smolagents Memory and Exceptions

The `smolagents` package handles exceptions during agent runs by incorporating them into the agent's memory, allowing the agent to learn from its mistakes.

## How it Works

1.  **Exception Capture**: In `smolagents/agents.py`, the `MultiStepAgent._run_stream` method wraps the step execution in a `try...except AgentError` block. When an `AgentError` is encountered, it is stored in the `action_step.error` attribute.
    
    ```python
    try:
        for output in self._step_stream(action_step):
            # ...
        # ...
    except AgentError as e:
        # Other AgentError types are caused by the Model, so we should log them and iterate.
        action_step.error = e
    finally:
        self._finalize_step(action_step)
        self.memory.steps.append(action_step)
    ```

2.  **Memory Integration**: In `smolagents/memory.py`, the `ActionStep.to_messages` method checks for the `error` attribute. If it exists, it formats the error as a `ChatMessage` with the `TOOL_RESPONSE` role. This ensures the error message is passed back to the LLM in subsequent steps.

    ```python
    if self.error is not None:
        error_message = (
            "Error:\n"
            + str(self.error)
            + "\nNow let's retry: take care not to repeat previous errors! If you have retried several times, try a completely different approach.\n"
        )
        message_content = f"Call id: {self.tool_calls[0].id}\n" if self.tool_calls else ""
        message_content += error_message
        messages.append(
            ChatMessage(role=MessageRole.TOOL_RESPONSE, content=[{"type": "text", "text": message_content}])
        )
    ```

## Conclusion

Exceptions of type `AgentError` are explicitly captured and fed back into the agent's memory as tool responses, enabling the agent to retry the task with the updated context of the failure.
