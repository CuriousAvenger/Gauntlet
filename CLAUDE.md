# Working on Gauntlet

A harness-agnostic MCP server (`server.py` → `gauntlet/tools.py`). Agents do judgement via
the briefs in `gauntlet/briefs/`; code does only what a model cannot be trusted to do
(store sources, match quotes, trace numbers, run tests, gate labels, build the report).

- Python ≥ 3.10, standard library only. `pytest -q` must pass.
- No client-specific code, config or wording; briefs must not assume file access or a shell.
- Before adding code, ask whether a brief could do it instead. Add a check only if a model
  cannot reliably do it itself, and give it a test.
