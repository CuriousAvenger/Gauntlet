"""Replication: a second agent, working from a separate brief, reproduces every
headline number of a test.

    "replica": {"log": "runs/prover-2/replica.log", "agent": "prover-2", "brief": "runs/prover-2/brief.md"}

Headline numbers are read from the ``GAUNTLET_RESULT`` line of each log
(``"headline": {"shot_reduction": 8.51}``) and must agree within the
configured relative tolerance (default 10%).
"""

from __future__ import annotations

from ..util import parse_result_line
from . import CheckResult


def _read_result(project, rel):
    p = project.root / rel
    if not p.exists():
        return None, f"log missing: {rel}"
    res = parse_result_line(p.read_text(encoding="utf-8", errors="replace"))
    if res is None:
        return None, f"no GAUNTLET_RESULT line in {rel}"
    return res, ""


def check(project, claim) -> CheckResult:
    tol = project.config.replication_rel_tol
    tests = [t for t in claim.get("tests", []) if t.get("role", "support") == "support"]
    if not tests:
        return CheckResult("replication", False, ["no supporting tests recorded"])
    ok, details = True, []
    for t in tests:
        tid = t.get("id")
        rep = t.get("replica")
        if not rep or not rep.get("log"):
            ok = False
            details.append(f"{tid}: no replication by a second agent")
            continue
        if not rep.get("agent") or rep.get("agent") == t.get("agent"):
            ok = False
            details.append(f"{tid}: replica must come from a different agent (got {rep.get('agent')!r})")
            continue
        if t.get("brief") and rep.get("brief") == t.get("brief"):
            ok = False
            details.append(f"{tid}: replica used the same brief; it needs a separate brief")
            continue
        a, why_a = _read_result(project, t.get("log", ""))
        b, why_b = _read_result(project, rep["log"])
        if a is None or b is None:
            ok = False
            details.append(f"{tid}: {why_a or why_b}")
            continue
        if not b.get("pass"):
            ok = False
            details.append(f"{tid}: replica run did not pass")
            continue
        ha, hb = a.get("headline") or {}, b.get("headline") or {}
        if not ha:
            details.append(f"{tid}: no headline numbers; replica passed")
            continue
        for k, va in ha.items():
            if k not in hb:
                ok = False
                details.append(f"{tid}: replica did not report headline '{k}'")
                continue
            try:
                fa, fb = float(va), float(hb[k])
            except (TypeError, ValueError):
                same = str(va) == str(hb[k])
                ok &= same
                details.append(f"{tid}: {k}: {va!r} vs {hb[k]!r} ({'match' if same else 'MISMATCH'})")
                continue
            denom = max(abs(fa), abs(fb), 1e-12)
            rel = abs(fa - fb) / denom
            good = rel <= tol
            ok &= good
            details.append(f"{tid}: {k}: {fa:g} vs {fb:g} (rel diff {rel:.1%}, tol {tol:.0%}) {'ok' if good else 'MISMATCH'}")
    return CheckResult("replication", ok, details)
