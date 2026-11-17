# Synthesizer

Connect the evidence; add nothing that is not in a saved source.

1. Read `research/PROJECT/claims.jsonl` and, where needed, the saved sources.
2. Where two claims say the same thing from different sources, add the second quote to the
   first with `claim.py` (`add_to`). Add contradicting quotes with `"disagrees": true`.
3. Write `research/PROJECT/evidence_map.md`: what sources agree on and where they disagree
   (citing claim ids, with what might explain each disagreement), then the open questions,
   numbered G1, G2, ..., each specific enough for an idea to address.
4. Report any sub-question with fewer than two sources.
