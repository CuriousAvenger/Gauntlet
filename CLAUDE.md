# Working on Gauntlet

Gauntlet is a Claude Code plugin: skill (`skills/research`), subagents (`agents/`), an
MCP server (`gauntlet/mcp/`) and hooks (`hooks/hooks.json` → `gauntlet/hooks.py`).

- Python ≥ 3.10, standard library only. `pytest -q` and `python -m gauntlet eval` must pass.
- `prompts/` is the source of truth for every brief. Never edit `skills/`, `agents/` or
  `integrations/` by hand: edit `prompts/`, then run `python scripts/build.py`
  (a test fails if generated files are stale).
- Tools are for models: few and task-shaped, `project` optional, writes signed with `agent`,
  errors as instructions (raise `ToolError`). Keep results compact.
- A new check goes in `gauntlet/checks/`, is wired into `checks.applicable_checks`/`run_checks`
  and `labels.requirements`, and gets a planted error in `gauntlet/evaluation.py`.
- Hooks must never raise or block on their own failure; return None to allow.
- To try the plugin from this checkout: `/plugin marketplace add ./` then `/plugin install gauntlet@gauntlet`.
