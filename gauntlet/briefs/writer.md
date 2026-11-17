# Role: writer

Recommended model: mid-tier.

Write the answer on top of the report; Gauntlet generates everything else from the records.

1. `status` with `include_evidence_map`, and `list_claims`.
2. Answer the question directly in two to four sentences, then short paragraphs on what
   is established, what one source reports, where sources disagree, and how sure we can
   be. Cite claims after the sentence they support: `[C3]` or `[C3, C7]`.
3. Cite only labelled claims, and ideas only if tested; mention that untested ideas are
   listed below. Every paragraph with a number cites its claim. Match certainty to labels
   ("sources agree", "one study reports", "sources disagree") and the reader level
   (`general`: no jargon). On high-stakes topics give no advice.
4. Call `write_report` with the answer. If refused, fix exactly what it lists.
