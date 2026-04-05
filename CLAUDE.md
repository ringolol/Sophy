## Project Idea
Sophy is a coding agent harness. It implements a tool-call loop in which agents solves tasks passed by user.

## Stack
- python 3.11
- smolagents
- openai api compatible models

## Main Python Files (src/sophy/)
- Main entry point: __main__.py
- Application state management: app_state.py
- Configuration management: config.py
- Agent instantiation: agents.py, agent_factory.py
- Agents' tools: tools.py
- Agents' prompts: prompts.py, prompts_data/
- User command handling: commands.py
- Session manager: session.py, history_provider.py
- Customizations to smolagents: patched_model.py, patched_agents.py, smolagents_patches.py
- Utils & Co: utils.py, guards.py, ui.py, debug.py, paths.py, cli.py
