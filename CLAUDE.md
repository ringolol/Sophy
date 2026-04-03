## Stack
- python 3.11
- smolagents
- openai api compatable models

## Main Python Files (src/sophy/)
- Main entry point: __main__.py
- Agents' tools: tools.py
- Agents' prompts: prompts.py, prompts_data/
- Agents' instantiation factory: factory.py
- Session manager: session.py
- Customizations to smolagents: patched_model.py, patched_agents.py, smolagents_patches.py
- Configuration management: config.py
- Utils & Co: utils.py, guards.py, ui.py

## Project Idea
Sophy is a coding agent harness. It implements a tool-call loop in which agent solves tasks passed by user.
