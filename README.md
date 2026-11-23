# Gauntlet

A research template for AI agents. Copy it into a new folder for each problem, write the
question, and let your agent research it. The report shows **how every claim was
checked**: facts carry exact quotes from saved sources; new ideas carry the tests they
passed or failed, or say they are untested.

It also explores: ideators from different fields propose ideas, judges rank them in a
tournament, the best of each cluster are tested, and the winners evolve into the next
generation. Each idea must quote its closest prior work, because models overrate their
own novelty.

Works with any agent that has a shell and reads `AGENTS.md` or loads skills. Needs only
Python 3.10+.

## Use it

1. Copy this repository into a new folder (on GitHub: *Use this template*).
2. Write the question under `## Question` in `AGENTS.md`.
3. Ask your agent to research it. The result is `report.md`.

Optional: set `OPENALEX_API_KEY` (free) to search journals in every field, refuse
retracted papers and find open copies of paywalled ones. Without it, search uses arXiv.

## The folder

```
AGENTS.md          your question, and how agents work here
.skills/gauntlet/
  SKILL.md         the research loop, rules and field guide
  roles/           reader, synthesizer, ideator, judge, prover, breaker, referee, writer
  scripts/         the checks (below); lib/ holds their helpers
sources/           exact copies of every source read
runs/              test scripts and the log of every run
```

A run adds `claims.jsonl`, `tournament.jsonl`, `evidence_map.md`, `meta_review.md`,
`answer.md` and `report.md`.

## How it works

The agent reads, thinks and writes. The scripts check what a model can't be trusted to
check itself:

| Script | What it guarantees |
|---|---|
| `source.py` | Gauntlet fetches each source itself and keeps an exact copy (arXiv pinned to one version) |
| `search.py` | Searches arXiv and OpenAlex beyond the sources already read |
| `claim.py` | Quotes are word for word in the saved copy; every number traces to a quote; ideas quote their closest prior work; duplicate ideas are refused |
| `rank.py` | Judges' verdicts are kept and replayed into Elo scores; similar ideas are clustered so the top stays diverse |
| `run_test.py` | Tests run on the author's seeds and on held-out seeds Gauntlet picks; tests that ignore the seed don't count |
| `label.py` | A label is refused unless the evidence earns it, and the reason is recorded |
| `report.py` | Every label is re-checked first; an answer that overstates is refused |

| Label | Requires |
|---|---|
| Established | Two or more independent works (not two versions of one paper) |
| Reported | One source |
| Contested | Quotes on both sides |
| New idea: tested | Passed on held-out seeds; independent code reproduces it within 10% |
| New idea: refuted | A run failed |
| New idea: untested | Closest prior work quoted, difference stated, settling test given |

The scripts are safe for parallel subagents (they lock the records), cap a folder at 60
ideas and 60 tests (`GAUNTLET_MAX_IDEAS`, `GAUNTLET_MAX_TESTS`), and print one JSON object:
exit 0 means done, 1 refused, 2 misuse.

## Example

An inflated number is caught; the honest claim earns its label:

```
$ echo '{"statement": "Shots fell 11-fold.", "quotes": [{"url": "https://example.org/paper",
        "quote": "the number of shots needed to reach precision 0.01 fell by a factor of 8.0"}]}' | python3 .skills/gauntlet/scripts/claim.py
{"id": "C1", "label": "pending", "fix": ["the number 11 is not in any quote or test log"]}

$ python3 .skills/gauntlet/scripts/label.py C2 reported --reason "one source states it"
{"id": "C2", "label": "Reported"}
```

## Changing Gauntlet

Keep it provider-agnostic and standard-library only. Add code only for checks that must
not depend on the model's honesty or memory; everything else belongs in `SKILL.md` or a role.
