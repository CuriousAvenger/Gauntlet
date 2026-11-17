---
field: software-engineering
reader_level: $reader_level
high_stakes: $high_stakes
test_mode: benchmark
authoritative_kinds: official-docs, standard, peer-reviewed
pack: $pack
---
# Topic profile

**Question:** $question

Drafted automatically in the Scope stage. Accept it, or edit it in plain words:
the orchestrator re-reads this file before every stage.

## Field

software-engineering

## Where to look

Official documentation, source repositories (README, code, issues, changelogs), standards (RFCs, specs), engineering blogs from the maintainers, peer-reviewed systems papers.

## How new ideas get tested

Benchmarks against a stated baseline on the same machine, same inputs and same versions; several runs with spread reported.

## If no test exists

Labelled **New idea: untested**, with the benchmark (inputs, baseline, metric) that would settle it.

## Reader level

`$reader_level` — one of `general` (no background assumed), `student`
(undergraduate background), `expert` (field vocabulary allowed). The report's
top section is written at this level; the expert appendix always keeps full detail.

## Notes for this field

- Pin versions: a claim about a library is a claim about a version.
- A benchmark without a baseline on identical hardware is not a comparison.
