# Gauntlet

A research harness for agent runners. Ask Claude Code a research question and Gauntlet
takes over: cheap subagents read and test, a strong subagent referees, and a tool layer
refuses any label the evidence has not earned. The result is a report where **every
claim shows how it was checked**: a fact carries its quote, a new idea carries the test
it passed or failed, or says it is untested.

Design: [docs/design.md](docs/design.md).

## Install (Claude Code)

```
/plugin marketplace add curiousavenger/gauntlet
/plugin install gauntlet@gauntlet
```

Requires `python3` (3.10+) on PATH. Nothing else to install: the MCP server and hooks
use only the standard library (`pypdf`, if present, adds PDF sources).

Then just ask, e.g. *"What does the evidence say about whether sleep deprivation impairs
memory consolidation?"* The `research` skill is model-invoked for research questions;
`/gauntlet:research <question> [quick|standard|deep]` invokes it explicitly. Projects
are written to `research/<question-slug>/` in your workspace, with the report at
`research/<slug>/report.md`.

## How it works

```
 user question
      │
      ▼
 skills/research ──── orchestrator (main session) ───────────────────────────────┐
      │  Scope → Survey → Synthesize → Explore → Check → Report                  │
      │                                                                          │
      ├─ agents/reader       (haiku)   save_source, search_sources, record_claim │
      ├─ agents/synthesizer  (opus)    add_evidence, record_evidence_map         │
      ├─ agents/ideator      (haiku)   propose_idea                              │
      ├─ agents/prover       (haiku)   run_test (support / replication)          │
      ├─ agents/breaker      (haiku)   run_test (counterexample)                 │
      ├─ agents/referee      (opus)    judge_evidence, check_claim, set_label    │
      └─ agents/writer       (sonnet)  write_report                              │
                                   │                                             │
                    MCP server (gauntlet/mcp) — the only writer of evidence      │
                                   │                                             │
 hooks: cost capture · budget gate · evidence-file guard · resume context ◄──────┘
```

| Layer | What it does | Where |
|---|---|---|
| **Skill** | The orchestrator brief; triggers on research questions | `skills/research/SKILL.md` |
| **Subagents** | Role briefs with model tier and tool restrictions | `agents/*.md` |
| **MCP server** | 17 typed tools; the trust layer; stdlib JSON-RPC over stdio | `gauntlet/mcp/` |
| **Hooks** | Run automatically; no agent has to remember them | `hooks/hooks.json`, `gauntlet/hooks.py` |

### What the harness enforces (not the prompts)

- **Labels are gated.** `set_label` re-runs the checks and refuses a label whose
  evidence is missing, returning exactly what is missing.

  | Label | Requires |
  |---|---|
  | Established | 2+ independent read sources; each passage found verbatim; a referee (not the author) judged it supports; provenance and like-for-like pass; on high-stakes topics an authoritative source (systematic review, guideline, official) |
  | Reported | 1 source, same checks |
  | Contested | Passages on both sides |
  | New idea: tested | A support test that passed on the author's seeds **and** on held-out seeds the harness drew; an independent replication (different agent, different script) within 10% on every headline number; no counterexample run failed |
  | New idea: refuted | A run that reported `pass: false` |
  | New idea: untested | The test that would settle it |

- **Sources are captured by the harness.** `save_source` fetches and stores the text and
  its hash; quotes are matched against that text, not an agent's copy. Paywalled
  sources are listed as unread and can never be cited.
- **Tests are run by the harness.** Agents write scripts; `run_test` executes them on
  their development seeds and then on held-out seeds chosen at random after the fact,
  and keeps the logs. Scripts print one line Gauntlet reads:
  `GAUNTLET_RESULT {"pass": true, "headline": {"shot_reduction": 8.51}}`.
- **Separation of duties.** Claim authors cannot referee their own claims; replications
  must come from another agent with its own script.
- **Re-audit.** `audit` re-runs any test whose script changed since it ran and
  downgrades labels that no longer hold (a tested idea whose test now fails becomes
  refuted).
- **The report cannot overstate.** `write_report` refuses an answer that cites a pending
  claim or an untested idea, states a number without a citation, or uses *novel, first,
  proved, breakthrough*. The findings, ideas, "what was not checked" and the expert
  appendix are generated from the records, not written by a model.

### Hooks

| Event | Effect |
|---|---|
| `PreToolUse` Write/Edit/Bash | Denies writes to evidence records (`claims.jsonl`, `sources/`, harness logs, report) so they change only through the tools. Agents' own scripts under `runs/<agent>/` are fine. |
| `PreToolUse` Agent | Denies new Gauntlet research subagents once the project's budget is spent (the writer may still finish). |
| `SubagentStop` | Reads the subagent's transcript and bills its token usage to the project ledger. |
| `Stop` | Bills the orchestrator's turns since the project started. |
| `SessionStart` | Tells a resumed session about an open research project. |

## Depth and cost

| Depth | Sources | Ideas tested per cycle | Cycles | Default budget |
|---|---|---|---|---|
| quick | ~10 | 0 (listed as untested) | 1 | $5 |
| standard | ~30 | 3 | 1 | $10 |
| deep | 50+ | 5 | up to 6 | $40 |

`start_research` returns a per-stage estimate before anything is spent. Deep mode stops
when cycles run out, the budget is spent, or three cycles add no new evidence. Override
budgets, prices and tolerances with a `gauntlet.toml` in your workspace (see
`gauntlet.toml.example`). Subagent models are set in `agents/*.md` (defaults: Opus 5.5
for referee and synthesizer, Sonnet 5.5 for the writer, Haiku 5.5 for readers and
testers).

## Topic profiles and expert packs

`start_research` drafts `profile.md` for one of five field families (math/physics/CS,
software, economics/policy, medicine/biology, history/humanities) or general: where to
look, how ideas get tested, reader level and a high-stakes flag (adds a not-advice
notice). Edit it in plain words; the orchestrator re-reads it.

Expert packs add seed sources, test conventions, known mistakes and notation: pass
`pack: "quantum-readout"` (built in, from PhysicsC191A) or a directory path.

## Other runners

The MCP server and the briefs are runner-neutral.

- **opencode:** copy `integrations/opencode/.opencode/` into your project and merge
  `integrations/opencode/opencode.json` (set the path to `runtime/mcp_server.py`).
  Invoke with `/research`. Usage is not captured automatically there; the orchestrator
  can call `log_usage`. *These files follow opencode's documented format but have not
  been verified against a live opencode install yet.*
- **Any MCP client:** run `python3 runtime/mcp_server.py` (stdio) and give subagents the
  briefs in `agents/`.

## Development

```bash
pip install pytest
pytest -q                          # unit, protocol, hook and packaging tests
python -m gauntlet eval            # planted-error evaluation through the real tool surface
python scripts/build.py            # regenerate skill/agents/opencode files from prompts/
```

Layout:

```
prompts/            source of truth for the orchestrator, role briefs and trust rules
scripts/build.py    generates skills/, agents/, integrations/ from prompts/
gauntlet/           harness library
  mcp/              MCP server (protocol + tools)
  hooks.py          hook handlers
  labels.py         label requirements, gate and audit
  checks/           quote, support, provenance, like-for-like, held-out, replication, wording
  testing.py        harness-executed tests with random held-out seeds
  project.py report.py cost.py sources.py profiles.py evaluation.py
runtime/            launchers used by .mcp.json and hooks.json
```

The planted-error evaluation catches 14 of 14 seeded errors: made-up citation, stretched
number, single source as established, scale mismatch, answer-fitted simulation,
replication mismatch, refuted idea left as tested, paywalled citation, self-refereeing,
ignored counterexample, direct edits to the claim ledger, shell rewrites of a saved
source, banned wording, and an untested idea in the answer. Honest controls must still
pass. `eval/questions.md` holds the 30-question set for the blind answer-quality test;
`python -m gauntlet sample <slug>` writes a review sheet for the citation and label
honesty tests.
