# Reorganization Plan for `src/sophy`

The current structure of `src/sophy` has become flat and difficult to navigate. I propose organizing the files into logical sub-modules to improve maintainability and readability.

## Proposed Structure

```
src/sophy/
├── core/                # Core application logic and state
│   ├── app_state.py
│   ├── config.py
│   ├── session.py
│   └── history_provider.py
├── agents/              # Agent management and customization
│   ├── agent_factory.py
│   ├── agents.py
│   ├── patches/         # Patches for smolagents
│   │   ├── patched_agents.py
│   │   ├── patched_model.py
│   │   └── smolagents_patches.py
├── tools/               # Tools used by agents
│   └── tools.py
├── prompts/             # Prompt management
│   ├── prompts.py
│   └── prompts_data/    # Existing directory
├── interface/           # UI and CLI interaction
│   ├── cli.py
│   ├── commands.py
│   └── ui.py
├── utils/               # Utilities and support modules
│   ├── debug.py
│   ├── guards.py
│   ├── paths.py
│   └── utils.py
├── __init__.py
└── __main__.py          # Entry point
```

## Migration Steps

1.  **Create Directories:** Create the new sub-directories (`core`, `agents`, `tools`, `prompts`, `interface`, `utils`) within `src/sophy`.
2.  **Move Files:** Carefully move each Python module into its new location.
3.  **Update Imports:** Update all internal import statements within the project to reflect the new directory structure.
4.  **Update Entry Points:** Ensure `__main__.py` and any other references correctly point to the moved modules.
5.  **Verify:** Run `./venv/bin/mypy src/sophy/` and fix the broken imports.
