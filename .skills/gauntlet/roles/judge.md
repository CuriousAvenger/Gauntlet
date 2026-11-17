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
   - **Plausibility:** does the evidence in the claims make it worth a test?
3. Record each verdict: `scripts/rank.py match IDEA_A IDEA_B WINNER --reason "..."`, where
   WINNER is one of the two ids, or `draw`. One sentence of reason, naming the deciding criterion.

Report how many pairs you judged and any idea you think should be dropped, and why.
