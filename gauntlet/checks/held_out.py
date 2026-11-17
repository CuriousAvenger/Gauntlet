"""Held-out check: every supporting test passed on seeds the harness drew at
random after the author finished developing it (see testing.py), and the
script has not changed since. Catches answer-fitted simulations."""

from __future__ import annotations

from .. import testing
from . import CheckResult


def check(project, claim) -> CheckResult:
    tests = [t for t in claim.get("tests", []) if t["role"] == "support"]
    if not tests:
        return CheckResult("held_out", False, ["no supporting test has been run (use run_test with role=support)"])
    ok, details = True, []
    for t in tests:
        tid = t["id"]
        if testing.is_stale(project, t):
            ok = False
            details.append(f"{tid}: script changed since it was run; run_test again")
            continue
        dev_fail = [r["seed"] for r in t["dev_runs"] if not r["pass"]]
        held = t.get("held_out_runs", [])
        if set(r["seed"] for r in held) & set(t["dev_seeds"]):
            ok = False
            details.append(f"{tid}: held-out seeds overlap development seeds")
            continue
        held_fail = [(r["seed"], r["error"] or "pass=false") for r in held if not r["pass"]]
        if not held:
            ok = False
            details.append(f"{tid}: no held-out runs")
        elif held_fail:
            ok = False
            details.append(f"{tid}: failed on held-out seeds {held_fail}" +
                           (" (passed on development seeds: likely fitted to them)" if not dev_fail else ""))
        else:
            details.append(f"{tid}: passed {len(held)} held-out seed(s)")
        if dev_fail:
            ok = False
            details.append(f"{tid}: failed on development seeds {dev_fail}")
    return CheckResult("held_out", ok, details)
