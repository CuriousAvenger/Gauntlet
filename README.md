# Gauntlet

A research skill for AI agents. Ask a research question and get a report where **every
claim shows how it was checked**: facts carry exact quotes from saved sources, new ideas
carry the tests they passed or failed, or say they are untested.

It is one folder in the open [Agent Skills](https://agentskills.io) format, so it works with
any agent that loads skills and has a shell. It needs Python 3.10+ and nothing else.

## Install

Copy `skills/gauntlet/` into the folder your agent loads skills from (see your agent's
docs). If your agent does not support skills, add this line to your `AGENTS.md`:

> For research questions, follow `skills/gauntlet/SKILL.md`.

Then ask a research question. Projects are written to `research/<project>/` in the current
directory; the report is `research/<project>/report.md`.

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

## Layout

```
skills/gauntlet/
  SKILL.md        the research loop, rules and field guide
  roles/          reader, synthesizer, ideator, prover, breaker, referee, writer
  scripts/        source.py, claim.py, run_test.py, label.py, report.py
    gauntlet/     the checks they share
tests/
```

## Development

```bash
pip install pytest && pytest
```
