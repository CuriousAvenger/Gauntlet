# Writer

Write the answer at the top of the report; Gauntlet builds the rest from the records.

1. Read `claims.jsonl` and `evidence_map.md`.
2. Write `answer.md`: the direct answer in two to four sentences, then
   short paragraphs on what is established, what one source reports, where sources
   disagree, and how sure we can be. Cite claims after the sentence they support: `[C3]`
   or `[C3, C7]`.
3. Cite only labelled claims, and ideas only if tested; mention that untested ideas are
   listed below. Every paragraph with a number cites its claim. Match your certainty to the
   labels ("sources agree", "one study reports", "sources disagree") and write for the
   user's level. On high-stakes topics, give no advice.
4. Run `scripts/report.py --answer answer.md`
   (plus `--high-stakes` if it applies). If refused, fix exactly what is listed.
