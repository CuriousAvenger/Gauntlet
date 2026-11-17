# Working on Gauntlet

- Python ≥ 3.11, standard library only (optional `pypdf`). Run tests with `pytest -q`
  and the trust-layer eval with `python -m gauntlet eval planted`.
- `gauntlet/core/` holds the orchestrator and role briefs (markdown). After editing
  them, regenerate the runner files: `python -m gauntlet install --runner claude-code --dir .`
- Checks live in `gauntlet/checks/`; label rules in `gauntlet/labels.py`. A new
  check must be wired into `checks.applicable_checks`/`run_checks` and into the
  label requirements, and should get a planted error in `gauntlet/evaluation.py`.
- To research a question with Gauntlet itself, use `/gauntlet "<question>"`.
