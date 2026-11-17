"""Provenance: every number in a claim's statement links to a source passage
or a test log. Invented or misremembered numbers fail here.

A number matches if it appears in the evidence, or if an evidence value rounds
to it at the precision the statement shows ("8" is linked by a log value of
8.14; "8.0" is not).
"""

from __future__ import annotations

from ..util import extract_number_values
from . import CheckResult


def evidence_text(project, claim) -> tuple[str, list[str]]:
    parts, missing = [], []
    for ev in claim.get("sources", []):
        parts.append(ev.get("passage", ""))
    for t in claim.get("tests", []):
        for key in ("log",):
            if t.get(key):
                p = project.root / t[key]
                if p.exists():
                    parts.append(p.read_text(encoding="utf-8", errors="replace"))
                else:
                    missing.append(t[key])
        rep = t.get("replica") or {}
        if rep.get("log"):
            p = project.root / rep["log"]
            if p.exists():
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
            else:
                missing.append(rep["log"])
    return "\n".join(parts), missing


def check(project, claim) -> CheckResult:
    text, missing = evidence_text(project, claim)
    details = [f"log file missing: {m}" for m in missing]
    evidence = extract_number_values(text)
    exact = {c for c, _, _ in evidence}
    values = [v for _, v, _ in evidence]
    nums = extract_number_values(claim["statement"])
    unlinked = []
    for canon, val, dec in nums:
        if canon in exact:
            continue
        # A rounded figure is linked if some evidence value rounds to it at the
        # precision the statement shows (8.14 in a log supports "8", not "8.0").
        if dec == 0 and float(val).is_integer() and any(
            round(v) == val and not float(v).is_integer() for v in values
        ):
            continue
        if dec > 0 and any(round(v, dec) == round(val, dec) for v in values):
            continue
        unlinked.append(canon)
    for n in unlinked:
        details.append(f"number {n} in the statement appears in no quoted passage or log")
    if nums and not unlinked:
        details.append(f"all {len(nums)} number(s) linked to evidence")
    if not nums:
        details.append("statement contains no numbers")
    return CheckResult("provenance", not unlinked and not missing, details)
