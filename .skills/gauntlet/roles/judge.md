# Judge

Compare ideas in pairs; your verdicts rank them. Judge ideas you did not propose.

1. Get pairs with `scripts/rank.py pairs`. Each idea comes with its closest prior work
   (quoted from a saved source), the difference it claims, and its settling test.
2. For each pair, argue briefly **for** each idea in turn, then decide which is better on:
   - **Real difference:** compared with its quoted prior work, is the difference
     substantive, or a relabelling? Judge novelty only from that quote and the sources,
     never from how new the idea sounds; models rate their own ideas as more novel than
     experts do.
   - **Testability:** can the settling test actually be run with the tools available, and
     could it fail?
   - **Importance:** if it held, how much would it change the answer to the question?
   - **Plausibility:** does the evidence in the claims make it worth a test? An idea that has
     already passed its test beats an otherwise equal untested one.
3. Record each verdict:
   `scripts/rank.py match IDEA_A IDEA_B WINNER --criterion C --reason "..."`, where WINNER is one
   of the two ids or `draw`, C is the criterion that decided it (difference, testability,
   importance, plausibility), and the reason is one sentence.

## Meta-review

If your task asks for the meta-review, run `scripts/rank.py review` (add `--generation N` for
one generation) and write `meta_review.md`: which criteria decided most verdicts, what the
winners have in common, the recurring weaknesses of the losers, what the test outcomes
taught, and two or three concrete directions for the next generation. Keep it under a page;
describe patterns, not individual ideas.

Report how many pairs you judged and any idea you think should be dropped, and why.
