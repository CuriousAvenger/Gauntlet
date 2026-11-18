---
name: gauntlet
description: Research a question, answer it with checked claims, and explore new ideas. Use when the user asks what the evidence says, whether something is true, for a literature review, for new research directions, or to investigate or compare findings in any field. Every claim in the report carries a label showing how it was checked (exact quotes from saved sources, tests on held-out data, independent replication); new ideas evolve through a tournament and are labelled tested, refuted or untested, each with its closest prior work.
---

# Gauntlet

Answer a research question so that every claim shows how it was checked. You (and your
subagents, if you have them) do the reading, thinking and writing. The scripts in
`scripts/` do the checking a model cannot do reliably for itself: they keep exact copies
of sources, confirm quotes word for word, run tests on seeds you never see, and refuse
labels the evidence has not earned.

## The scripts

Run them with `python3 .skills/gauntlet/scripts/<script>` from the research folder (the
folder containing `AGENTS.md`). Each prints JSON. Records are plain files in that folder
that you can read directly: `claims.jsonl`, `sources/`, `runs/`, `tournament.jsonl`, and later
`report.md`.

| Script | Use it to |
|---|---|
| `search.py "QUERY"` | Search arXiv (and OpenAlex, if `OPENALEX_API_KEY` is set) beyond the sources already read |
| `source.py URL [--find REGEX]` | Read a source. Gauntlet fetches it and keeps an exact copy (arXiv papers pinned to one version); quote from this text, not from your own web tools, which may summarise |
| `claim.py` (JSON on stdin) | Record a claim with quotes, or an idea with its closest prior work and the test that would settle it |
| `rank.py pairs` / `match` / `top` / `review` | Get pairs of ideas to compare, record verdicts, see the leaderboard and the diverse top, and review what the verdicts rewarded |
| `run_test.py IDEA ROLE SCRIPT` | Have Gauntlet run a test script on your seeds and on held-out seeds |
| `label.py ID LABEL` | Give a claim a label; refused, with reasons, unless earned |
| `report.py --answer FILE` | Re-check everything and write `report.md` |

Each script's `--help` shows its exact usage. In the role files, `scripts/` means
`.skills/gauntlet/scripts/`.

## The loop

1. **Scope.** Read the question in `AGENTS.md` and restate it. Ask one clarifying question
   only if it would change what to read. Choose a depth (table below) and plan 3–8
   sub-questions; see the field guide.
2. **Read** (role: `roles/reader.md`). Split the sub-questions among readers, ~5 sources each.
3. **Map** (role: `roles/synthesizer.md`). What sources agree on, where they disagree, what is open.
4. **Explore**, one generation at a time:
   1. *Diverge or evolve* (role: `roles/ideator.md`). Pick distinct **lenses**: fields or
      angles that bear on the question from different directions (for a readout-cost
      question: statistics, signal processing, numerical linear algebra, hardware). Give
      each ideator one lens. Generation 1 diverges; later generations evolve the diverse top.
   2. *Compare* (role: `roles/judge.md`). Judges, never the ideators themselves, work through
      `rank.py pairs` until every idea has been compared about three times. Then one judge
      writes the meta-review, `meta_review.md`: what kept winning and losing, and why. The next
      generation's ideators read it.
   3. *Test* (roles: `roles/prover.md`, `roles/breaker.md`). Take the diverse top from
      `rank.py top`: the best idea of each cluster, not the top few of one cluster. For each,
      a prover and a breaker work independently, and a second prover replicates any passing
      test from the idea alone, without seeing the first prover's code. Refuted ideas stay
      in the record: the next generation learns from why they failed.
   4. *Stop or continue.* Stop when the generation limit is reached, or when a generation
      puts no new idea into the diverse top (`rank.py top` reports this per generation).
5. **Check** (role: `roles/referee.md`). Referees who did not record the claims label them.
6. **Report** (role: `roles/writer.md`). The writer drafts the answer; `report.py` re-checks
   every label and builds the report around it, including a frontier of the strongest
   untested ideas.

| Depth | Sources | Lenses | Generations | Ideas tested per generation |
|---|---|---|---|---|
| quick | ~10 | 3 | 1 | none: ideas stay untested |
| standard | ~30 | 4 | 2 | top 3 of the diverse top |
| deep | 50+ | 5–6 | up to 5 | top 5 of the diverse top |

If you can start subagents, give each one the role file and its task.
Use a fast model for readers, ideators, provers and breakers, and your strongest model for
the synthesizer, judges and referees. If you cannot, play the roles yourself, one at a time.

Finish by telling the user the answer in two or three sentences with its labels, the most
promising ideas, what was not checked, and the path to `report.md`.

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
