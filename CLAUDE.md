## Project Idea
Sophy is a coding agent harness. It implements a tool-call loop in which agents solves tasks passed by user.

## Stack
- python 3.11
- smolagents
- openai api compatible models

## Project Structure (src/sophy/)
- Entry point: __main__.py
- core/ — App state, config, session, history, context compression
- agents/ — Agent instantiation (agents.py, agent_factory.py)
  - agents/patches/ — smolagents customizations (patched_agents, patched_model, smolagents_patches)
- tools/ — Agent tools
- prompts/ — Prompt building (prompts.py, prompts_data/)
- interface/ — CLI, commands, UI helpers
- utils/ — debug, guards, paths, utils
