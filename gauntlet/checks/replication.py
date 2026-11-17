"""Replication: every supporting test is reproduced by a second agent with its
own script (role=replication). Both pass on all seeds, and the mean of every
headline number agrees within the configured relative tolerance (default 10%)."""

from __future__ import annotations

from statistics import mean

from .. import testing
from . import CheckResult


def _headline_means(test) -> dict[str, float]:
    vals: dict[str, list[float]] = {}
    for r in testing.runs(test):
        for k, v in (r.get("headline") or {}).items():
            try:
                vals.setdefault(k, []).append(float(v))
            except (TypeError, ValueError):
                pass
    return {k: mean(v) for k, v in vals.items()}


def check(project, claim) -> CheckResult:
    tol = project.config.replication_rel_tol
    tests = claim.get("tests", [])
    support = [t for t in tests if t["role"] == "support"]
    if not support:
        return CheckResult("replication", False, ["no supporting test to replicate"])
    ok, details = True, []
    for t in support:
        reps = [r for r in tests if r["role"] == "replication" and r.get("replicates") == t["id"]]
        indep = [r for r in reps if r["agent"] != t["agent"] and r["script"] != t["script"]
                 and r.get("script_sha256") != t.get("script_sha256")]
        if not indep:
            ok = False
            details.append(f"{t['id']}: needs a replication by a different agent with its own script"
                           + (" (existing replicas share the agent or script)" if reps else ""))
            continue
        a = _headline_means(t)
        for r in indep:
            if testing.is_stale(project, r):
                ok = False
                details.append(f"{r['id']}: replica script changed since it was run")
                continue
            if not all(x["pass"] for x in testing.runs(r)):
                ok = False
                details.append(f"{r['id']} (replica of {t['id']} by {r['agent']}): not all runs passed")
                continue
            b = _headline_means(r)
            for k, va in a.items():
                if k not in b:
                    ok = False
                    details.append(f"{r['id']}: did not report headline '{k}'")
                    continue
                rel = abs(va - b[k]) / max(abs(va), abs(b[k]), 1e-12)
                good = rel <= tol
                ok &= good
                details.append(f"{t['id']} vs {r['id']}: {k} {va:.4g} vs {b[k]:.4g} "
                               f"(diff {rel:.1%}, tol {tol:.0%}) {'ok' if good else 'MISMATCH'}")
            if not a:
                details.append(f"{t['id']} vs {r['id']}: no headline numbers; replica passed")
    return CheckResult("replication", ok, details)
