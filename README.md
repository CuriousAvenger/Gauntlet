# Gauntlet

A research template for AI agents. Copy it into a new folder for each problem you want
to research, write the question, and let your agent work on it. The result is a report
where **every claim shows how it was checked**: facts carry exact quotes from saved
sources, and new ideas carry the tests they passed or failed, or say they are untested.

It works with any agent that has a shell and reads `AGENTS.md` or loads skills. It needs
Python 3.10+ and nothing else.

## Use it

1. Copy this repository into a new folder for one research problem (on GitHub: *Use this
   template*).
2. Write the question under `## Question` in `AGENTS.md`.
3. Open the folder with your agent and ask it to research the question.

`AGENTS.md` also points the agent to `.skills/gauntlet/SKILL.md`, which holds the research
loop. `.skills/gauntlet/` is a standard Agent Skills folder, for agents that load skills.

## What the folder holds

```
AGENTS.md         the question (you write it) and how any agent should work here
.skills/gauntlet/
  SKILL.md        the research loop, rules and field guide
  roles/          reader, synthesizer, ideator, prover, breaker, referee, writer
  scripts/        source.py, claim.py, run_test.py, label.py, report.py
    lib/          the checks they share
    tests/        tests for the scripts
sources/          exact copies of every source read
runs/             test scripts and the log of every run
claims.jsonl      every claim and idea, with quotes, tests and label   (created by the run)
evidence_map.md   what sources agree and disagree on, what is open      (created by the run)
report.md         the final report                                      (created by the run)
```

## How it works

The agent does the reading, thinking and writing. Small scripts do the checks a model cannot
reliably do for itself:

| The agent… | Gauntlet… |
|---|---|
| reads a source (`source.py`) | fetches the page itself and keeps an exact copy |
| records a claim with a quote (`claim.py`) | confirms the quote is word for word in that copy and every number traces to it |
| tests an idea (`run_test.py`) | runs the code itself, on the agent's seeds and on held-out seeds it picks at random |
| labels a claim (`label.py`) | refuses any label the evidence has not earned |
| writes the answer (`report.py`) | re-checks every label, refuses an answer that overstates, and builds the report |

| Label | Requires |
|---|---|
| Established | Two or more independent sources, quoted word for word |
| Reported | One source, quoted word for word |
| Contested | Quotes on both sides |
| New idea: tested | Passed on held-out seeds, and independently written code reproduces the result within 10% |
| New idea: refuted | A run failed |
| New idea: untested | States the test that would settle it |

## Working on Gauntlet itself

- Keep it provider-agnostic: no agent-specific files, tool names or wording.
- Scripts: Python 3.10+, standard library only, one JSON object on stdout; exit 0 = done,
  1 = refused, 2 = misuse.
- Before adding code, ask whether an instruction in `SKILL.md` could do the job instead.
  Code is only for checks that must not depend on the model's honesty or memory.
- Run the tests with `pip install pytest && pytest`.
