# Gauntlet

A research assistant where **every claim shows how it was checked**. Gauntlet reads
sources, builds a sourced answer, and proposes and tests new ideas as it goes. Cheap
models do most of the reading and testing, a stronger model checks the work, and the
person decides what to trust.

A fact from a source carries its quote. A new idea carries the test it passed or
failed, or says it is untested. Nothing is shown as more certain than its evidence.

See [docs/design.md](docs/design.md) for the design.

## How it is built

Gauntlet has two halves:

1. **Role briefs** (`gauntlet/core/`): plain-markdown instructions for an orchestrator
   and seven subagents (reader, synthesizer, ideator, prover, breaker, referee,
   writer). Any agent runner that can spawn subagents and run shell commands can
   execute them. Adapters for Claude Code and opencode are included.
2. **The `gauntlet` CLI** (Python, standard library only): the trust layer. Agents
   record everything through it: sources, claims, quotes, tests, verdicts and labels.
   It runs the automatic checks, **refuses any label the evidence does not earn**,
   re-audits labels every cycle, and assembles the report.

The agents do the judgement work. The CLI makes sure no agent can skip the checks.

## Install

```bash
pip install -e .            # or: pip install -e ".[pdf,dev]" for PDF sources and tests
```

Python 3.11+. Without installing, `python -m gauntlet ...` works from the repo root.

## Quick start (Claude Code)

The repo already contains the generated agent files (`.claude/agents/gauntlet-*.md`)
and the `/gauntlet` command. To use Gauntlet in another directory:

```bash
gauntlet install --runner claude-code --dir /path/to/workdir
```

Then, in Claude Code:

```
/gauntlet "Can quantum computers speed up fluid simulation?" --depth standard
```

The orchestrator creates the project, shows the cost estimate and topic profile, and
runs Scope → Survey → Synthesize → Explore → Check → Report. Ask a follow-up later
with `/gauntlet <project-slug> <follow-up question>`.

**Other runners:** `gauntlet install --runner opencode` writes `.opencode/` agents.
For anything else, `gauntlet brief <role> -p <slug>` prints a self-contained brief
(trust rules + role + project context) to use as a subagent's instructions.

## What the CLI enforces

```bash
gauntlet ask "Does sleep deprivation impair memory consolidation?" --depth quick
gauntlet source add --url https://... --kind systematic-review --agent reader-1
gauntlet source grep S1 "consolidation"                         # exact lines to quote
gauntlet claim add "<statement>" --cite S1 "<exact passage>" --by reader-1
gauntlet claim referee C1 --index 0 --verdict supports --by referee-1
gauntlet claim label C1 established --by referee-1               # refused unless checks pass
gauntlet idea add "<idea>" --gap G1 --settling-test "<test>"     # labelled untested
gauntlet test add I1 --script runs/prover-1/t.py --log runs/prover-1/t.log --agent prover-1 \
    --held-out-cmd "python runs/prover-1/t.py --seed {seed}" --seeds 101,202,303 --dev-seeds 0
gauntlet test replica I1 T1 --log runs/prover-2/r.log --agent prover-2 --brief runs/prover-2/brief.md
gauntlet audit                                                   # re-check every label
gauntlet report                                                  # refused if the answer overstates
gauntlet status
```

### Labels and what each requires

| Label | Requires |
|---|---|
| Established | 2+ independent read sources; every passage found verbatim and judged *supports* by a referee who is not the claim's author; provenance and like-for-like pass; on high-stakes topics, a systematic review, guideline or official source among them |
| Reported | 1 source, same checks |
| Contested | Quoted passages on both sides (`--cite` and `--against`) |
| New idea: tested | Test script + log reporting `pass: true`; held-out re-runs on fresh seeds pass; a second agent with a separate brief reproduces every headline number (±10%); provenance and like-for-like pass |
| New idea: refuted | A log or held-out run reporting `pass: false` |
| New idea: untested | The test that would settle it |

### Automatic checks (`gauntlet/checks/`)

| Check | What it does |
|---|---|
| `quote_check` | The passage appears in the **saved** source text (normalised for case, whitespace, quotes and dashes; `...` skips text in order). The source must be read, not paywalled, and unmodified since capture (sha256). |
| `support` | A referee verdict of *supports* exists for each passage, from an agent other than the author. |
| `provenance` | Every number in the statement appears in a quoted passage or test log (rounding to the precision shown is allowed). |
| `like_for_like` | A statement that compares numbers needs a comparison record whose unit, baseline and scale match. |
| `held_out` | Re-runs the test command on held-out seeds that must not overlap the development seeds. |
| `replication` | Compares headline numbers from the original and an independent replica log. |
| `wording` | Rejects *novel, first, proved, breakthrough, definitely* and the like in claims and the answer. |

Test scripts end with one line Gauntlet reads; nobody's summary replaces it:

```
GAUNTLET_RESULT {"pass": true, "headline": {"shot_reduction": 8.51}}
```

### The report

`gauntlet report` builds `report.md` from the writer's `answer.md` and from
`claims.jsonl`: the answer (each citation shown with its label), findings by label,
new ideas (with the settling test for untested ones), **what was not checked**, and an
expert appendix (every quote, test, log, check result, downgrade, source and the run's
spend). It refuses to write the report if the answer cites a pending claim or an
untested idea, states a number without citing a claim, or uses banned wording.
`--draft` writes it anyway with a DRAFT banner and the list of problems.

## Project folder

```
projects/<question-slug>/
  project.json      question, depth, rounds, cycles, budget, models
  profile.md        topic profile (editable; field, reader level, high-stakes, test mode)
  sources/          index.jsonl + S<n>.txt (text saved by Gauntlet, hashed)
  evidence_map.md   agree / disagree / gaps (G1, G2, ...)
  claims.jsonl      every claim, label, evidence, checks, history
  ideas.md          rendered from idea claims
  runs/             agent scripts and logs, held-out runs, cost ledger
  answer.md         the writer's answer
  report.md         the assembled report
```

## Depth, cost and stop conditions

```bash
gauntlet estimate
```

| Mode | Sources | Ideas tested per cycle | Max cycles | Default budget |
|---|---|---|---|---|
| quick | ~10 | 0 (listed as untested) | 1 | $5 |
| standard | ~30 | 3 | 1 | $10 |
| deep | 50+ | 5 | 6 | $40 |

Estimates use per-tier model prices. The orchestrator logs each subagent's tokens
(`gauntlet cost log`), checks `gauntlet budget-check` before each stage, and in deep
mode runs cycles until `gauntlet cycle end` reports a stop condition: cycles run out,
budget spent, or three cycles in a row with no new evidence.

Model routing and prices are settings: copy `gauntlet.toml.example` to `gauntlet.toml`.
Defaults: strong `claude-opus-5-5`, mid `claude-sonnet-5-5`, cheap `claude-haiku-5-5`.

## Topic profiles and expert packs

`gauntlet ask` drafts `profile.md` from the question for one of five field families
(math/physics/CS, software, economics/policy, medicine/biology, history/humanities) or
`general`. Medicine and questions about legal or financial decisions are marked
high-stakes: the report carries a not-advice notice, and Established needs an
authoritative source.

Expert packs add seed sources, test conventions, known mistakes and notation:
`gauntlet ask "..." --pack quantum-readout` (or `--pack path/to/your/pack`). The
built-in `quantum-readout` pack carries the PhysicsC191A lessons.

## Evaluation

```bash
gauntlet eval planted     # seeds known errors into a scratch project; must catch >= 90%
gauntlet eval sample -p <slug> --n 100   # CSV sheet for human citation/label review
```

The planted-error eval currently catches 11 of 11: made-up citation, stretched
number, single source labelled established, scale mismatch, answer-fitted simulation,
replication mismatch, refuted idea left as tested (caught by the audit), paywalled
citation, self-refereed claim, banned wording and an untested idea in the answer. It
also checks that honest controls still get through. `eval/questions.md` holds the
30-question set for the blind answer-quality test.

## Status

| Milestone | State |
|---|---|
| 1. Quick mode | Done (CLI + briefs); needs live runs |
| 2. Trust layer | Done: labels, claims.jsonl, all five checks, wording lint, audit, "not checked" section |
| 3. Explore and Check | Done: ideator, prover, breaker, referee briefs; held-out and replication checks |
| 4. Topic profiles | Done: six profile templates, field detection, quantum-readout pack (seed list to complete) |
| 5. Evaluation | Planted errors automated; review sheets, question set ready; live expert, replay and usability tests not yet run |
| 6. Public release | README done; worked examples and disclosure guidance pending |

## Development

```bash
pip install -e ".[dev]"
pytest -q
gauntlet install --runner claude-code --dir .   # after editing gauntlet/core/*.md
```
