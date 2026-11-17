"""Like-for-like: compared numbers share units, baseline and scale.

A claim whose statement makes a comparison (x-fold, 'faster', 'fewer',
'more than', percentages of change) must carry a comparison record:

    {"a": {"value": 8.0, "unit": "shots", "baseline": "classical shadows", "scale": "n=16, eps=1e-2"},
     "b": {"value": 1.0, "unit": "shots", "baseline": "classical shadows", "scale": "n=16, eps=1e-2"}}
"""

from __future__ import annotations

import re

from . import CheckResult

_COMPARISON = re.compile(
    r"(\d\s*[x×]\b|\bx\s*\d|×|-fold\b|\bfold\b|\bspeed-?ups?\b|\bfaster\b|\bslower\b|\bfewer\b"
    r"|\bmore than\b|\bless than\b|\boutperform|\bbetter than\b|\bworse than\b|\bcompared (to|with)\b"
    r"|\breduc(es|ed|tion)\b.*\d|\bincreas(es|ed)\b.*\d)",
    re.I,
)
FIELDS = ("unit", "baseline", "scale")


def makes_comparison(statement: str) -> bool:
    return bool(_COMPARISON.search(statement))


def check(project, claim) -> CheckResult:
    comps = claim.get("comparisons", [])
    details, ok = [], True
    if makes_comparison(claim["statement"]) and not comps:
        return CheckResult(
            "like_for_like", False,
            ["statement makes a comparison but no comparison record (units, baseline, scale) was given"],
        )
    for i, c in enumerate(comps):
        a, b = c.get("a", {}), c.get("b", {})
        this_ok = True
        for f in FIELDS:
            va, vb = a.get(f), b.get(f)
            if va in (None, "") or vb in (None, ""):
                this_ok = False
                details.append(f"comparison {i}: '{f}' missing on {'a' if va in (None, '') else 'b'}")
            elif str(va).strip().lower() != str(vb).strip().lower():
                this_ok = False
                details.append(f"comparison {i}: {f} differs ({va!r} vs {vb!r})")
        ok &= this_ok
        if this_ok:
            details.append(f"comparison {i}: like-for-like")
    if not comps:
        details.append("no comparisons made")
    return CheckResult("like_for_like", ok, details)
