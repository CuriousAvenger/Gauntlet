"""Support check: a referee has judged that each quoted passage supports the
claim (or, for contested claims, the side it is filed under).

A referee verdict is only accepted from an agent other than the one that
wrote the claim.
"""

from __future__ import annotations

from . import CheckResult


def latest_verdicts(claim) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for v in claim.get("referee", []):
        if "source_index" in v:
            out[int(v["source_index"])] = v
    return out


def check(project, claim) -> CheckResult:
    srcs = claim.get("sources", [])
    if not srcs:
        return CheckResult("support", False, ["claim cites no sources"])
    verdicts = latest_verdicts(claim)
    ok, details = True, []
    for i, ev in enumerate(srcs):
        v = verdicts.get(i)
        tag = f"[{i}] {ev.get('source_id')}"
        if v is None:
            ok = False
            details.append(f"{tag}: no referee verdict yet")
        elif v.get("verdict") != "supports":
            ok = False
            details.append(f"{tag}: referee verdict '{v.get('verdict')}' by {v.get('by')}: {v.get('note', '')}".rstrip(": "))
        elif claim.get("agent") and v.get("by") == claim.get("agent"):
            ok = False
            details.append(f"{tag}: verdict given by the claim's own author ({v.get('by')}); needs a separate referee")
        else:
            details.append(f"{tag}: supports (referee {v.get('by')})")
    return CheckResult("support", ok, details)
