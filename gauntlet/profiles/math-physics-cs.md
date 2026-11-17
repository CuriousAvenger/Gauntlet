---
field: math-physics-cs
reader_level: $reader_level
high_stakes: $high_stakes
test_mode: numerics
authoritative_kinds: textbook, survey, peer-reviewed
pack: $pack
---
# Topic profile

**Question:** $question

Drafted automatically in the Scope stage. Accept it, or edit it in plain words:
the orchestrator re-reads this file before every stage.

## Field

math-physics-cs

## Where to look

arXiv (search by title/abstract, then read the paper), textbooks and lecture notes, survey articles. Prefer the arXiv abstract page or HTML version so the text can be saved.

## How new ideas get tested

Numerics on many instances with random seeds, never on the single instance whose answer is known. Proof steps are checked with a proof checker if one is available, otherwise attacked by the Breaker with an explicit 'for all strategies' audit.

## If no test exists

Labelled **New idea: untested**, with the numeric experiment or proof obligation that would settle it.

## Reader level

`$reader_level` — one of `general` (no background assumed), `student`
(undergraduate background), `expert` (field vocabulary allowed). The report's
top section is written at this level; the expert appendix always keeps full detail.

## Notes for this field

- A lower bound must hold for *all* strategies, not only the ones named.
- Resource counts (gates, shots, queries) are recounted from the actual construction, never from random stand-ins.
- Compared speedups must share the problem size, precision target and baseline.
