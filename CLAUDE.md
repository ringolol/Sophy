## Project Idea
Sophy is a coding agent harness. It implements a tool-call loop in which agents solves tasks passed by the user.

## Stack
- python 3.11
- smolagents
- openai api compatible models

## Project Structure (src/sophy/)
- Entry point: __main__.py
- core/ — App state, config manager, session manager
- agents/ — Agent instantiation
  - agents/patches/ — smolagents customizations
- tools/ — Agent tools
- prompts/ — Agent prompt building
- interface/ — CLI, user commands, UI helpers
- utils/ — debug, guards, paths, utils
