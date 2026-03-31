# Sophy - A Coding Agent Harness

Sophy is an AI-powered coding agent built on top of the smolagents library. It implements a tool-call loop where an agent solves tasks passed by users through interactive CLI.

## Architecture

### Tech Stack:
- Python 3.11
- smolagents framework
- Ollama models (local LLM, currently using qwen3.5:35b-a3b)

### Core Components:

1. **sophy.py** - Main entry point:
   - Initializes a ToolCallingAgent with custom tools and model configuration
   - Runs an interactive loop where users input tasks
   - Supports session management commands (/quit, /new, /resume)
   - Auto-saves sessions after each agent interaction

2. **tools.py** - Agent's tool definitions:
   - File operations: read_file, write_new_file, edit_file, insert_text, delete_file, move_file
   - Search operations: search_files, search_content
   - System commands: run_command, execute_python
   - Navigation: list_directory, get_tree
   - Web: web_search, visit_webpage
   - Communication: ask_user, get_conversation_history
   - Completion signal: final_answer

3. **session.py** - Session manager:
   - Tracks conversation sessions stored in .sophy/sessions/
   - Each session contains task/result pairs with steps and tools used
   - Provides session persistence and summary generation
   - Allows switching between saved sessions

4. **model.py** - Custom model wrapper:
   - Extends OpenAIServerModel for local Ollama integration
   - Handles reasoning content display in panels
   - Streams responses with token usage tracking

5. **monkey_patches.py** - Behavioral customizations:
   - Custom logger with colored panels
   - Noise reduction (hides observation logs, tool call JSON)
   - Enhanced tool execution with parallel processing

6. **prompts.py** - System prompt configuration:
   - Direct prompt template enforcing tool-call-only responses
   - Mandatory JSON format rule
   - Reads CLAUDE.md for project context injection

7. **utils.py** - Utilities:
   - confirm decorator requiring user approval before dangerous operations
   - Preview diffs before file modifications
   - Step counting and final answer reminders
   - Supported model configuration

## Key Design Principles

- Strict JSON tool-calls only - Agent cannot output prose
- User confirmation - Critical operations require explicit approval
- Session persistence - All interactions are saved for later resumption
- Local-first - Uses local Ollama models via local API
- Interactive CLI - Rich console output with colored panels and diffs
