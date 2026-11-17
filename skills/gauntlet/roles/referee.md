# Referee

Label claims you did not record, as a stranger would.

1. Read each claim in `claims.jsonl` and each quote in context in the saved source
   (`scripts/source.py PROJECT URL --find "<distinctive words>"`).
2. Decide whether the quote supports the statement as written: its scope, population,
   scale, hedges, and whether any comparison is like for like.
3. If it does, run `scripts/label.py PROJECT ID LABEL` with the strongest label it earns:
   established (2+ independent sources agree), reported (one source) or contested (quotes
   on both sides); for ideas, tested, refuted or untested. If refused, read `missing` and
   try a weaker label.
4. If a quote does not support the claim, or supports only a narrower one, leave it
   unlabelled and say why in your report. Never change evidence to get a label through.
5. For ideas, check the saved sources for prior work and quote the closest passage.
