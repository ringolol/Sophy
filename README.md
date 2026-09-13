# Sophy

AI coding agent harness — an interactive CLI that gives an LLM tools to read, write, edit files, run shell commands, and navigate your codebase. Built on [smolagents](https://github.com/huggingface/smolagents). 

_It's more of a playground and a study of how agentic systems work than a production tool._

> ⚠️ **This project was fully vibe-coded by free models (e.g. gemini 3.1 flash lite).**

![Demo](demo.gif)

## Features

- **Dual-agent architecture** — Solver (executes) delegates discovery to Explorer (read-only navigation)
- **Human-in-the-loop** — destructive operations (edits, shell commands, deletions) require confirmation; whitelist patterns for auto-approval
- **Session management** — `/new`, `/fork`, `/resume` with full history persistence in `.sophy/sessions/`
- **Multi-model** — `/model` switches between configured presets; any OpenAI-compatible API
- **Context compression** — `/compress` summarizes or truncates long conversation history
- **Telegram backend** — `/telegram` connects a Telegram bot as an alternate interface
- **Custom slash commands** — define shortcuts that expand to full prompts
- **`/pure`** — send a prompt without system prompt injection

## Limitations

- Python 3.11+ only
- Requires an OpenAI-compatible API endpoint (no local-only models without a proxy)
- Web search is DuckDuckGo only

## Installation

```bash
pip install .
```

Or with pipx:

```bash
make install
```

For development:

```bash
make install-dev
make install-deps
```

## Usage

```bash
sophy
```

Starts an interactive prompt. Type a task and the Solver agent executes it. Built-in commands:

| Command | Description |
|---|---|
| `?` | Show help |
| `/new` | Create a new session |
| `/fork` | Fork current session |
| `/resume` | Switch to another session |
| `/model` | Switch model preset |
| `/compress` | Compress conversation context |
| `/pure` | Send prompt without system injection |
| `/telegram` | Connect Telegram bot |
| `/quit` | Exit |

Custom slash commands defined in config also appear here.

Add `--telegram` to connect the Telegram bot on startup:

```bash
sophy --telegram
```

Requires `SOPHY_TELEGRAM_TOKEN` and `SOPHY_TELEGRAM_CHAT_ID` environment variables.

### Getting your chat ID

Message `@userinfobot` on Telegram to get your numeric user ID. For groups, send a message in the group then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` — the `chat.id` field is your ID.

## Configuration

Config lives at `~/.sophy/config.json`. Copy the default:

```bash
make update-config
```

### `models`

Array of model presets. Each entry:

```json
{
  "label": "My Model",
  "model_id": "gpt-4o",
  "context": 128000,
  "api_base": "https://api.openai.com/v1/",
  "api_key": "$OPENAI_API_KEY",
  "tools": true
}
```

- `api_key` — literal value or `$ENV_VAR` reference
- `context` — context window size in tokens (default: 128000)
- `tools` — whether the model supports native tool calling

### `allowed_command_patterns`

Regex patterns for shell commands that bypass confirmation:

```json
{
  "allowed_command_patterns": [
    "^git (status|diff|log)",
    "^ls "
  ]
}
```

### `custom_commands`

Slash commands that expand to full prompts:

```json
{
  "custom_commands": [
    {
      "command": "/git",
      "prompt": "look at the changes, come up with a detailed message and commit them"
    }
  ]
}
```

## Tools

**Solver** (full suite): `read_file`, `write_new_file`, `edit_file`, `delete_file`, `move_file`, `run_command`, `execute_python`, `search_files`, `search_content`, `list_directory`, `get_tree`, `web_search`, `visit_webpage`, `ask_user`, `get_conversation_history`, `final_answer` — plus the `explorer` sub-agent.

**Explorer** (read-only): `read_file`, `search_files`, `search_content`, `list_directory`, `get_tree`.
