# Working on Gauntlet

Gauntlet is a harness-agnostic MCP server (stdio, `server.py` → `gauntlet/tools.py`).
Nothing in it may depend on a particular agent client: no client-specific config,
hooks, agent files or tool names.

- Python ≥ 3.10, standard library only. `pytest -q` and `python -m gauntlet eval` must pass.
- Briefs live in `gauntlet/briefs/` and are served by `get_brief`. They must not assume
  file access or a shell (a test checks this); everything goes through tools.
- Tools are for models: few and task-shaped, `project` optional, writes signed with
  `agent`, errors as instructions (raise `ToolError`), compact results.
- Guarantees belong in code (checks, labels, testing, integrity), not in prompts.
- A new check goes in `gauntlet/checks/`, is wired into `checks.applicable_checks`/`run_checks`
  and `labels.requirements`, and gets a planted error in `gauntlet/evaluation.py`.
