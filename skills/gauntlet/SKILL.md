---
name: gauntlet
description: Research a question and answer it with checked claims. Use when the user asks what the evidence says, whether something is true, for a literature review, or to investigate or compare findings in any field. Every claim in the report carries a label showing how it was checked (exact quotes from saved sources, tests on held-out data, independent replication), and new ideas are labelled tested, refuted or untested.
---

# Gauntlet

Answer a research question so that every claim shows how it was checked. You (and your
subagents, if you have them) do the reading, thinking and writing. The scripts in
`scripts/` do the checking a model cannot do reliably for itself: they keep exact copies
of sources, confirm quotes word for word, run tests on seeds you never see, and refuse
labels the evidence has not earned.

## The scripts

Run them with `python3 <this skill's folder>/scripts/<script>`. Each prints JSON. Pick a
short project name (e.g. `readout-shots`) and pass it every time; records go to
`research/<project>/` in the current directory, where you can read them directly
(`claims.jsonl`, `sources/`, `runs/`).

| Script | Use it to |
|---|---|
| `source.py PROJECT URL [--find REGEX]` | Read a source. Gauntlet fetches it and keeps an exact copy; quote from this text, not from your own web tools, which may summarise |
| `claim.py PROJECT` (JSON on stdin) | Record a claim with quotes, or an idea with the test that would settle it |
| `run_test.py PROJECT IDEA ROLE SCRIPT` | Have Gauntlet run a test script on your seeds and on held-out seeds |
| `label.py PROJECT ID LABEL` | Give a claim a label; refused, with reasons, unless earned |
| `report.py PROJECT --question Q --answer FILE` | Re-check everything and write `report.md` |

Each script's `--help` shows its exact usage.

## The loop

1. **Scope.** Restate the question. Ask one clarifying question only if it would change
   what to read. Choose a depth: *quick* (~10 sources, ideas left untested), *standard*
   (~30 sources, top 3 ideas tested), *deep* (50+ sources, repeat steps 3–5 while new
   evidence keeps arriving, up to 6 rounds). Plan 3–8 sub-questions; see the field guide below.
2. **Read** (role: `roles/reader.md`). Split the sub-questions among readers, ~5 sources each.
3. **Map** (role: `roles/synthesizer.md`). What sources agree on, where they disagree, what is open.
4. **Ideas** (roles: `roles/ideator.md`, `roles/prover.md`, `roles/breaker.md`). Propose ideas
   for the open questions. Except in quick depth, test the top ideas: a prover and a breaker
   work independently, and a second prover replicates any passing test from the idea alone,
   without seeing the first prover's code.
5. **Check** (role: `roles/referee.md`). Referees who did not record the claims label them.
6. **Report** (role: `roles/writer.md`). The writer drafts the answer; `report.py` re-checks
   every label and builds the report around it.

If you can start subagents, give each one the role file, its task and the project name.
Use a fast model for readers, ideators, provers and breakers, and your strongest model for
the synthesizer and referees. If you cannot, play the roles yourself, one at a time.

Finish by telling the user the answer in two or three sentences with its labels, what was
not checked, and the path to `report.md`.

## Rules for every role

1. Never state a claim more strongly than its label.
2. Quote only from `source.py` output, word for word. A source that cannot be read is never cited.
3. Test results come from `run_test.py`. Its output outranks anyone's summary.
4. Never soften a claim, loosen a pass condition or change seeds to make something pass.
   A refuted idea is a result.
5. Say "not found in the sources read", never "new", "novel", "first" or "proved".
6. For medical, legal or financial questions, pass `--high-stakes` to `report.py`, rely on
   systematic reviews, guidelines or official sources for anything labelled established,
   and give no advice.

## Field guide

| Field | Where to look | How ideas get tested |
|---|---|---|
| Math, physics, theory CS | arXiv, textbooks, surveys | Numerics on many random instances |
| Software, engineering | Official docs, repositories, standards | Benchmarks against a stated baseline |
| Economics, policy | Statistical agencies, working papers, journals | Statistics on public data |
| Medicine, biology | PubMed Central, systematic reviews, guidelines | Re-analysis of published data only |
| History, humanities | Primary sources, archives, scholarship | Searching the documents; otherwise interpretation |

Ideas no available test can settle stay untested, with the test that would settle them.
