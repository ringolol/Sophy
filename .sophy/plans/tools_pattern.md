# Plan: Auto-approve guards for file edits and command patterns

## Context

The `confirm` decorator in `guards.py` asks for user confirmation on every destructive tool call. This is safe but slow. We want two auto-approval mechanisms:

1. **Allow all edits** — auto-approve file content modifications (edit, insert, write) when the target is inside the project directory. Still show the diff, just skip the y/n prompt. Delete and move still require confirmation.
2. **Allowed command patterns** — auto-approve shell commands matching user-defined regexps, with safety for compound commands.

## Config schema (`.sophy/config.json`)

Two new top-level fields:

```json
{
  "models": [...],
  "allow_all_edits": true,
  "allowed_command_patterns": [
    "^git (status|diff|log|show|branch)",
    "^ls\\b",
    "^python\\b"
  ]
}
```

## Files to modify

### 1. `config.py` — load guard settings

Add dataclass and loader function:

```python
@dataclass
class GuardConfig:
    allow_all_edits: bool = False
    allowed_command_patterns: list[re.Pattern] = field(default_factory=list)  # compiled at load
    project_dir: str = ""  # os.path.dirname(os.path.abspath(CONFIG_PATH))
```

`load_guard_config()` reads from `CONFIG_PATH`, compiles patterns, resolves `project_dir`.

### 2. `guards.py` — modify `confirm` decorator

Add module-level config holder + setter (same pattern as `tools.py`'s `set_history_provider`):

```python
_guard_config: GuardConfig | None = None

def set_guard_config(config: GuardConfig):
    global _guard_config
    _guard_config = config
```

#### Auto-approve logic inside `confirm`:

**File content tools** (`edit_file`, `insert_text`, `write_new_file`):
- If `allow_all_edits` is on:
  - Resolve file path via `os.path.realpath()` (defeats symlink escapes)
  - Check it starts with `project_dir + os.sep`
  - If yes → still show the diff (call previewer + `_print_diff`), but skip the y/n prompt
  - If no → normal confirmation flow

**`run_command`**:
- Detect compound commands via regex: `(\|\||&&|;|\||&|`|\$\(|[<>])`
- If compound: only auto-approve if the **entire** command matches a pattern (prevents `ls && rm -rf /`)
- If simple: auto-approve if command matches any pattern via `re.match()`
- On auto-approve: still print the args panel, just skip the y/n prompt

**Everything else** (`delete_file`, `move_file`, `dangerous_python_interpreter`):
- Always require confirmation, no auto-approve path

### 3. `sophy.py` — wire it up

After config loading, call `set_guard_config(load_guard_config())`.

## Security invariants

- `os.path.realpath()` resolves symlinks — no symlink escape from project dir
- Strict prefix check: path must start with `project_dir + os.sep` (not just `project_dir`)
- Compound command detection is conservative — any shell metachar forces full-string match
- `dangerous_python_interpreter` is never auto-approved
- Delete/move never auto-approved

## Verification

1. `allow_all_edits: true` + edit file in project → diff shown, no prompt, tool runs
2. Edit file outside project (e.g. `~/.bashrc`) → normal y/n prompt
3. Symlink inside project pointing outside → realpath resolves out, prompt shown
4. `^git (status|diff|log)` pattern + `git status` → auto-approved
5. `git status && rm -rf /` → prompt shown (compound, full string doesn't match)
6. `curl example.com` with no matching pattern → prompt shown
7. `delete_file` on in-project file → prompt shown (not auto-approved even with allow_all_edits)
