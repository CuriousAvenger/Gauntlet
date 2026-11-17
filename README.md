# Gauntlet

A research harness for any agent that speaks MCP. Ask a research question and get a
report where **every claim shows how it was checked**: a fact carries its quote, a new
idea carries the test it passed or failed, or says it is untested.

Design: [docs/design.md](docs/design.md).

## Connect it

One MCP server over stdio. Needs `python3` 3.10+ and nothing else (`pypdf`, if present,
adds PDF sources). Add it to your client:

```json
{
  "mcpServers": {
    "gauntlet": { "command": "python3", "args": ["/path/to/gauntlet/server.py"] }
  }
}
```

Then ask a research question. The server tells the model to start with
`get_brief("orchestrator")`; clients that show MCP prompts also get a `research` prompt.
If your client ignores server instructions, add to your agent instructions: *"For research
questions, call the gauntlet get_brief tool with role orchestrator and follow it."*

Projects are written to `research/<question-slug>/` where the server runs (or
`$GAUNTLET_HOME`); the report is `report.md` there, and `write_report` returns its text.

## Agents decide, code verifies

The briefs (`gauntlet/briefs/`) carry the workflow and all judgement: what to read, what a
passage means, which ideas are worth testing, whether a comparison is fair. The code does
only what a model cannot be trusted to do for itself:

- **Sources:** fetches each URL and stores its text and hash, so a quote is checked against
  what the source says, not the model's memory of it.
- **Quotes and numbers:** a label needs every passage found verbatim in the stored text and
  every number in the claim traceable to a passage or a test log.
- **Tests:** runs the model's test scripts itself, on its seeds and then on held-out seeds
  it picks at random, and compares an independent replication's numbers.
- **Labels:** refuses any label those checks don't support.
- **Report:** re-audits every label (re-running changed test scripts) before writing, and
  refuses an answer that cites unlabelled claims or untested ideas or states uncited numbers.

| Label | Requires |
|---|---|
| Established | 2+ independent sources, quotes verbatim, numbers traceable; on high-stakes topics a systematic review, meta-analysis, guideline or official source |
| Reported | 1 source, same checks |
| Contested | Passages on both sides |
| New idea: tested | Support test passed on development and held-out seeds; an independent replication within 10%; no counterexample broke it |
| New idea: refuted | A run reported `pass: false` |
| New idea: untested | The test that would settle it |

Test scripts take `--seed N` and print `GAUNTLET_RESULT {"pass": true, "headline": {"ratio": 8.1}}`.

## What's in `gauntlet/`

| File | Purpose |
|---|---|
| `protocol.py` | MCP over stdio (tools and prompts), no dependencies |
| `tools.py` | The 13 tools agents call |
| `briefs/`, `briefs.py` | Orchestrator and seven role briefs, served by `get_brief` |
| `labels.py` | Quote and number checks, label requirements, re-audit |
| `testing.py` | Runs test scripts on development and held-out seeds |
| `sources.py` | Fetches pages (HTML, text, PDF) |
| `project.py` | The per-question folder |
| `report.py` | Builds the report |
| `packs/` | Expert packs; `quantum-readout` carries the PhysicsC191A lessons |

## Development

```bash
pip install pytest && pytest -q
```
