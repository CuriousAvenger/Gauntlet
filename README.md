# Gauntlet

A research harness that works in any agent that speaks MCP. Ask a research question
and you get a report where **every claim shows how it was checked**: a fact carries its
quote, a new idea carries the test it passed or failed, or says it is untested.

Design: [docs/design.md](docs/design.md).

## Connect it

Gauntlet is one MCP server (stdio). Requirements: `python3` 3.10+, nothing to install.

```bash
git clone https://github.com/curiousavenger/gauntlet
```

Add it to your client's MCP servers. Most clients accept this shape:

```json
{
  "mcpServers": {
    "gauntlet": { "command": "python3", "args": ["/path/to/gauntlet/server.py"] }
  }
}
```

Or install it as a package and launch the console script `gauntlet-mcp`
(for example `uvx --from git+https://github.com/curiousavenger/gauntlet gauntlet-mcp`).

Then ask a research question. The server tells the model to call
`get_brief("orchestrator")` for research questions. In clients that show MCP prompts,
the `research` prompt starts the same thing. If your client ignores server
instructions, add one line to your agent instructions file (AGENTS.md or similar):

> For research questions, call the gauntlet `get_brief` tool with role "orchestrator" and follow it.

Research projects are written to `research/<question-slug>/` in the directory the
server runs in (override with `GAUNTLET_HOME`). The report is
`research/<slug>/report.md`, and `write_report` also returns its text.

## Why there is code at all

Prompts can ask a model to be careful; they cannot make it so. Everything Gauntlet
guarantees is done by code the model cannot talk its way around:

- **Sources:** the server fetches each URL and stores the text with its hash, then
  checks every quote against that stored text.
- **Tests:** the server runs the model's test scripts itself, on its seeds and then
  on held-out seeds it draws at random afterwards, and keeps the logs.
- **Labels:** a label is refused unless the checks pass (quotes found, numbers
  traceable, comparisons like-for-like, held-out runs passed, independent
  replication agrees).
- **Report:** the report's findings come from the records; the model writes only
  the answer, which is refused if it overstates.
- **Tamper evidence:** records are signed after every call, so an edit made outside
  the tools is detected, recorded in the report, and every claim is re-checked.

That code is Python because the model's test scripts are Python (numerics and data
re-analysis), `python3` is already on nearly every machine, and the standard library is
enough, so there is nothing to install.

## What's in `gauntlet/`

| File | Role |
|---|---|
| `protocol.py` | MCP over stdio (JSON-RPC: tools and prompts) with argument validation; no dependencies |
| `tools.py` | The 19 tools the model calls; every call verifies and re-seals the project |
| `briefs/` + `briefs.py` | The orchestrator and seven role briefs (markdown) and the code that fills in agent name, task, topic profile and expert pack |
| `labels.py` | What each label requires, the label gate, and the audit that downgrades labels that no longer hold |
| `checks/` | Quote, referee support, provenance, like-for-like, held-out, replication, wording |
| `testing.py` | Runs test scripts: development seeds, then random held-out seeds; detects edited scripts |
| `sources.py` | Fetches URLs (HTML, text, PDF if `pypdf` is present) and spots paywalls |
| `project.py` | The per-question folder: state, sources, claims, evidence map |
| `report.py` | Assembles `report.md` and refuses answers that overstate |
| `integrity.py` | Signs records after each call; detects and records outside edits |
| `cost.py` | Up-front estimates, the usage ledger, stop conditions |
| `profiles.py` + `profiles/` | Topic profiles for five field families plus general |
| `packs/` | Expert packs; `quantum-readout` carries the PhysicsC191A lessons |
| `evaluation.py` | The planted-error evaluation |

## How a run goes

The orchestrator brief drives **Scope → Survey → Synthesize → Explore → Check → Report**
and hands each piece of work to a role through `get_brief(role, agent, task)`:

| Role | Recommended model | Main tools |
|---|---|---|
| reader | fast, inexpensive | `save_source`, `search_sources`, `record_claim` |
| synthesizer | strongest | `add_evidence`, `record_evidence_map` |
| ideator | fast, inexpensive | `propose_idea` |
| prover | fast, inexpensive | `run_test` (support or replication) |
| breaker | fast, inexpensive | `run_test` (counterexample) |
| referee | strongest | `judge_evidence`, `check_claim`, `set_label` |
| writer | mid | `write_report` |

If the agent can start subagents, each brief goes to one. If it can't, the agent follows
the briefs itself one at a time. Briefs are self-contained and need no file access,
so chat-only clients work too: test scripts are passed as `code`, and the profile and
evidence map come back from `status`.

### Labels

| Label | Requires |
|---|---|
| Established | 2+ independent read sources; each passage found verbatim; a referee other than the author judged it supports; numbers traceable; comparisons like-for-like; on high-stakes topics an authoritative source (systematic review, guideline, official) |
| Reported | 1 source, same checks |
| Contested | Passages on both sides |
| New idea: tested | A support test passed on the author's seeds and on held-out seeds the harness drew; an independent replication (another agent, its own script) within 10% on every headline number; no counterexample failed it |
| New idea: refuted | A run reported `pass: false` |
| New idea: untested | The test that would settle it |

Test scripts accept `--seed N` and print
`GAUNTLET_RESULT {"pass": true, "headline": {"shot_reduction": 8.51}}`.

### Cost and limits

| Depth | Sources | Ideas tested per cycle | Cycles | Default budget |
|---|---|---|---|---|
| quick | ~10 | 0 (listed as untested) | 1 | $5 |
| standard | ~30 | 3 | 1 | $10 |
| deep | 50+ | 5 | up to 6 | $40 |

`start_research` returns an estimate first. MCP servers cannot see token usage, so the
orchestrator reports it with `log_usage` when its environment provides counts.
`get_brief` refuses new research work once the budget is spent; the writer can always
finish. Independent of usage reports, sources are capped at twice the depth's target
and tests at 12 per idea. Override defaults with `gauntlet.toml` (see
`gauntlet.toml.example`).

### Topic profiles and expert packs

`start_research` drafts a profile for one of five field families or general: where to
look, how ideas get tested, reader level, and a high-stakes flag (medicine, legal or
financial decisions), which adds a not-advice notice. Fix it with `update_profile`. Pass
`pack: "quantum-readout"`, or a directory of markdown files, to add seed sources, test
conventions and known mistakes to every brief.

## Development

```bash
pip install pytest
pytest -q                     # protocol, tools, checks, labels, integrity, briefs, report
python -m gauntlet eval       # planted-error evaluation through the real server
```

The planted-error evaluation catches 15 of 15 seeded errors, and honest controls still
pass. The errors: made-up citation, stretched number, single source as established, scale
mismatch, answer-fitted simulation, replication mismatch, refuted idea left as tested,
paywalled citation, self-refereeing, ignored counterexample, a label forged by editing
`claims.jsonl`, a source rewritten on disk, banned wording, an untested idea in the
answer, and research past the budget. `eval/questions.md` holds the 30-question set for
the blind answer-quality test; `python -m gauntlet sample <slug>` writes a review sheet
for the citation and label-honesty tests.
