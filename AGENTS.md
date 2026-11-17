# Working on Gauntlet

Gauntlet is one Agent Skills folder: `skills/gauntlet/`. `SKILL.md` and `roles/` hold the
instructions; `scripts/` holds the checks a model cannot reliably do for itself.

- Keep it provider-agnostic: no agent-specific files, tool names or wording.
- Scripts: Python 3.10+, standard library only, one JSON object on stdout,
  exit 0 = done, 1 = refused, 2 = misuse.
- Before adding code, ask whether an instruction could do the job instead. Code is only for
  checks that must not depend on the model's honesty or memory.
- `pytest` must pass.
