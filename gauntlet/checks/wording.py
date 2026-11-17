"""Wording lint (trust rule 5): no 'novel', 'first', 'proved' and the like.

Say "not found in the sources read", never "new" or "first". Labels carry
certainty; prose must not add more.
"""

from __future__ import annotations

import re

BANNED = [
    (r"\bnovel(ty)?\b", "say 'not found in the sources read'"),
    (r"\bfor the first time\b|\bthe first (to|time|ever)\b|\bfirst-ever\b|\bfirst ever\b", "never claim priority"),
    (r"\b(we|this|it|which|has been|have been|was|is) (proved|proven)\b|\bproves\b|\bprove[sd]? that\b", "use the label, not 'proved'"),
    (r"\bground-?breaking\b|\bunprecedented\b|\bbreakthrough\b|\brevolutionary\b", "drop the hype word"),
    (r"\b(definitely|undeniably|beyond (any )?doubt|conclusively)\b", "certainty belongs in the label"),
    (r"\bnew (result|finding|discovery|theorem|method)\b|\b(is|are) new\b", "say 'not found in the sources read'"),
]


def lint(text: str) -> list[tuple[str, str, str]]:
    """Return (matched text, hint, context) for each banned phrase."""
    hits = []
    for pat, hint in BANNED:
        for m in re.finditer(pat, text, re.I):
            s = max(0, m.start() - 40)
            ctx = text[s:m.end() + 40].replace("\n", " ")
            hits.append((m.group(0), hint, ctx))
    return hits
