# Sophy - A Coding Agent Harness

Sophy is an AI-powered coding agent built on top of the `smolagents` library. It implements a robust tool-call loop where a primary **Solver** agent performs tasks by delegating discovery and navigation to a specialized **Explorer** sub-agent.

## Architecture

### Tech Stack:
- Python 3.11+
- [smolagents](https://github.com/huggingface/smolagents) framework
- Supports any LLM with an OpenAI-compatible API via `ThinkingModel`

### Core Components:

1. **sophy.py** - Main entry point:
   - Manages the interactive CLI loop using `prompt_toolkit`.
   - Coordinates the dual-agent setup (Solver + Explorer).
   - Handles high-level session commands (`/quit`, `/new`, `/resume`, `/model`, `/compress`).

2. **factory.py** - Agent & Model Assembly:
   - The "glue" module that constructs agents with specific roles.
   - **Solver Agent:** Equipped with the full `TOOLS` suite; manages the Explorer as a tool.
   - **Explorer Agent:** A restricted agent using only `EXPLORATION_TOOLS` to safely navigate and search the codebase.

3. **tools.py** - Agent Capabilities:
   - **`TOOLS`**: Full suite including `edit_file`, `write_new_file`, `run_command`, `execute_python`, and `web_search`.
   - **`EXPLORATION_TOOLS`**: Read-only subset (`list_directory`, `search_content`, `read_file`, `get_tree`) for the Explorer.
   - Includes safety features like the `@confirm` decorator for destructive actions.

4. **model.py** - `ThinkingModel` Wrapper:
   - Custom interface for LLMs that supports "thinking" steps (reasoning).
   - Handles context window management and role conversions for different API providers.

5. **session.py** & **context_compression.py** - Persistence & Memory:
   - **session.py**: Tracks conversation history, tool steps, and metadata in `.sophy/sessions/`.
   - **context_compression.py**: Provides logic to summarize or truncate history to fit within model context limits.

6. **prompts.py** & **prompts_data/**:
   - Defines specialized system prompts for different agent roles.
   - Enforces the "No Prose" rule and strict JSON tool-call formats.

7. **monkey_patches.py**:
   - Customizes `smolagents` behavior, including enhanced logging, noise reduction in outputs, and specialized step handling.

8. **utils.py**:
   - Shared utilities for configuration loading, CLI formatting (via `rich`), and user confirmation prompts.

## Key Design Principles

- **Dual-Agent Strategy**: Separates environment discovery (Explorer) from execution (Solver) to increase reliability.
- **Flexible Tool-Calling**: Supports both native JSON tool-calls and code-tag formats (using `CodeAgent`), depending on the model's capabilities.
- **No Prose Policy**: Agents communicate exclusively through valid tool-call blobs; no conversational prose.
- **Human-in-the-Loop**: Critical operations (file edits, shell commands) require explicit user approval.
- **Session Persistence**: Complete history of tasks and tool executions is saved for later resumption.
- **Context Awareness**: Automatic context compression helps handle long-running debugging or development sessions.

