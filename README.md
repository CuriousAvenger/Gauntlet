# Gauntlet

A research template for AI agents. Copy it into a new folder for each problem you want
to research, write the question, and let your agent work on it. The result is a report
where **every claim shows how it was checked**: facts carry exact quotes from saved
sources, and new ideas carry the tests they passed or failed, or say they are untested.

Beyond answering, it explores. Ideators working from different fields propose ideas,
judges compare them in a tournament, and the strongest ideas from different clusters
are tested, then evolved into the next generation. Every idea must quote the closest
existing work and say what it adds, because models are poor judges of their own novelty.

It works with any agent that has a shell and reads `AGENTS.md` or loads skills. It needs
Python 3.10+ and nothing else.

## Use it

1. Copy this repository into a new folder for one research problem (on GitHub: *Use this
   template*).
2. Write the question under `## Question` in `AGENTS.md`.
3. Open the folder with your agent and ask it to research the question.

Optional: set `OPENALEX_API_KEY` (free from OpenAlex) to search journals in every field;
without it, literature search uses arXiv only.

`AGENTS.md` also points the agent to `.skills/gauntlet/SKILL.md`, which holds the research
loop. `.skills/gauntlet/` is a standard Agent Skills folder, for agents that load skills.

## What the folder holds

```
AGENTS.md         the question (you write it) and how any agent should work here
.skills/gauntlet/
  SKILL.md        the research loop, rules and field guide
  roles/          reader, synthesizer, ideator, judge, prover, breaker, referee, writer
  scripts/
    search.py     searches arXiv and OpenAlex beyond the sources already read
    source.py     reads sources and keeps exact copies (arXiv papers pinned to one version)
    claim.py      records claims and ideas; checks quotes and numbers; filters duplicate ideas
    rank.py       pairs ideas for judging, keeps Elo scores, picks the best of each cluster,
                  summarises verdicts for the meta-review
    run_test.py   runs tests on the agent's seeds and on held-out seeds, with resource limits
    label.py      gives labels the evidence earns
    report.py     re-checks everything and writes the report
    lib/          specialised helpers: arXiv reader, literature search, source identity,
                  web fetching, word-overlap similarity
    tests/        tests for the scripts
sources/          exact copies of every source read
runs/             test scripts and the log of every run
claims.jsonl      every claim and idea, with quotes, tests and label   (created by the run)
tournament.jsonl  every judged comparison of two ideas                (created by the run)
meta_review.md    what the judges rewarded, for the next generation   (created by the run)
evidence_map.md   what sources agree and disagree on, what is open      (created by the run)
report.md         the final report                                      (created by the run)
```

## How it works

The agent does the reading, thinking and writing. Small scripts do the checks a model cannot
reliably do for itself:

| The agent… | Gauntlet… |
|---|---|
| searches the literature (`search.py`) | queries arXiv (and OpenAlex) and marks results already read |
| reads a source (`source.py`) | fetches the page itself and keeps an exact copy; pins arXiv papers to one version; records each source's identity, so a preprint and its journal version count as one work |
| records a claim with a quote (`claim.py`) | confirms the quote is word for word in that copy and every number traces to it |
| proposes an idea (`claim.py`) | requires the closest prior work quoted word for word, refuses near-duplicates of earlier ideas, and suggests the closest passages to quote |
| judges two ideas (`rank.py`) | records the verdict, recomputes Elo scores from every verdict, and groups similar ideas so the top stays diverse |
| tests an idea (`run_test.py`) | runs the code itself, on the agent's seeds and on held-out seeds it picks at random |
| labels a claim (`label.py`) | refuses any label the evidence has not earned |
| writes the answer (`report.py`) | re-checks every label, refuses an answer that overstates, and builds the report |

| Label | Requires |
|---|---|
| Established | Two or more independent works (not two versions of one paper), quoted word for word |
| Reported | One source, quoted word for word |
| Contested | Quotes on both sides |
| New idea: tested | Passed on held-out seeds, and independently written code reproduces the result within 10% |
| New idea: refuted | A run failed |
| New idea: untested | Closest prior work quoted word for word, the difference stated, and the test that would settle it |

## Working on Gauntlet itself

- Keep it provider-agnostic: no agent-specific files, tool names or wording.
- Scripts: Python 3.10+, standard library only, one JSON object on stdout; exit 0 = done,
  1 = refused, 2 = misuse.
- Before adding code, ask whether an instruction in `SKILL.md` could do the job instead.
  Code is only for checks that must not depend on the model's honesty or memory.
- Run the tests with `pip install pytest && pytest`.
