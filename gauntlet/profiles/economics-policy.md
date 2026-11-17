---
field: economics-policy
reader_level: $reader_level
high_stakes: $high_stakes
test_mode: statistics
authoritative_kinds: official, peer-reviewed, systematic-review
pack: $pack
---
# Topic profile

**Question:** $question

Drafted automatically in the Scope stage. Accept it, or edit it in plain words:
the orchestrator re-reads this file before every stage.

## Field

economics-policy

## Where to look

Reports from statistical agencies and central banks, working papers (NBER, SSRN, RePEc), peer-reviewed journals, public datasets.

## How new ideas get tested

Statistics on public data: the script downloads the dataset, states the specification, and reports estimates with uncertainty. Robustness on held-out periods or regions.

## If no test exists

Labelled **New idea: untested**, with the dataset and specification that would settle it.

## Reader level

`$reader_level` — one of `general` (no background assumed), `student`
(undergraduate background), `expert` (field vocabulary allowed). The report's
top section is written at this level; the expert appendix always keeps full detail.

## Notes for this field

- Separate correlation from causal estimates; say which design each source uses.
- Compared numbers must share currency, base year and population.
