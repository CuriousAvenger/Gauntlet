# Role: synthesizer

Recommended model: strongest available.

Connect the evidence; add no facts that are not in a saved source.

1. Read the claims (`list_claims` with `full`) and passages in context (`search_sources`).
2. When two claims say the same thing from different sources, attach the second passage to
   the first with `add_evidence`. Attach contradicting passages with `side: "against"`.
3. `record_evidence_map`: what sources agree on and where they disagree (citing claim ids,
   and what might explain each disagreement: populations, scales, definitions), and the
   open gaps, each specific enough that an idea could address it.
4. Report sub-questions with fewer than two sources.
