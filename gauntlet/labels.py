"""The trust layer: labels, the evidence each needs, and gated label changes.

A claim's label can only be set when its requirements are met *now*. The audit
re-checks every claim each cycle and moves any claim whose evidence no longer
holds to the strongest label it still earns.
"""

from __future__ import annotations

from typing import Any

from . import testing
from .checks import CheckResult, record_results, run_checks
from .util import now_iso

SOURCED_LABELS = ("established", "reported", "contested")
IDEA_LABELS = ("tested", "refuted", "untested")
LABELS = SOURCED_LABELS + IDEA_LABELS
PENDING = "pending"

DISPLAY = {
    "established": "Established",
    "reported": "Reported",
    "contested": "Contested",
    "tested": "New idea: tested",
    "refuted": "New idea: refuted",
    "untested": "New idea: untested",
    PENDING: "Pending (not yet checked)",
}

MEANING = {
    "established": "Independent sources agree",
    "reported": "One source says so",
    "contested": "Sources disagree",
    "tested": "Proposed here, passed a test",
    "refuted": "Proposed here, failed a test",
    "untested": "Proposed here, no check run",
}

# Order used when the audit looks for the strongest label a claim still earns.
FALLBACK_ORDER = {
    "sourced": ["established", "contested", "reported"],
    "idea": ["refuted", "tested", "untested"],
}


def display(label: str) -> str:
    return DISPLAY.get(label, label)


def _passed(results: dict[str, CheckResult], *names: str) -> list[str]:
    unmet = []
    for n in names:
        r = results.get(n)
        if r is None:
            unmet.append(f"{n} check not applicable or not run")
        elif not r.passed:
            unmet.append(f"{n} check failed: " + "; ".join(r.details)[:400])
    return unmet


def requirements(project, claim: dict[str, Any], results: dict[str, CheckResult]) -> dict[str, list[str]]:
    """For every label, the list of unmet requirements (empty = label allowed)."""
    out: dict[str, list[str]] = {}
    kind = claim["kind"]
    srcs = claim.get("sources", [])
    profile = project.profile()

    for label in LABELS:
        unmet: list[str] = []
        if label in SOURCED_LABELS and kind != "sourced":
            unmet.append("label is for claims from sources; this claim is a new idea")
        if label in IDEA_LABELS and kind != "idea":
            unmet.append("label is for new ideas; this claim comes from sources")
        if unmet:
            out[label] = unmet
            continue

        if label in SOURCED_LABELS:
            unmet += _passed(results, "quote", "support", "provenance", "like_for_like")
            ids = [e.get("source_id") for e in srcs]
            sides = {e.get("side", "for") for e in srcs}
            if label == "established":
                distinct = _independent_sources(project, ids)
                if distinct < 2:
                    unmet.append(f"needs 2+ independent sources, has {distinct}")
                if "against" in sides:
                    unmet.append("a source disagrees; use 'contested'")
                if profile.get("high_stakes"):
                    kinds = set(profile.get("authoritative_kinds") or [])
                    have = {(project.source(i) or {}).get("kind") for i in ids}
                    if kinds and not kinds & have:
                        unmet.append(
                            "high-stakes topic: Established needs a source of kind "
                            + ", ".join(sorted(kinds))
                        )
            elif label == "reported":
                if len(set(ids)) < 1:
                    unmet.append("needs 1 source")
                if "against" in sides:
                    unmet.append("a source disagrees; use 'contested'")
            elif label == "contested":
                if not {"for", "against"} <= sides:
                    unmet.append("needs quoted passages on both sides (side=for and side=against)")

        elif label == "untested":
            if not (claim.get("settling_test") or "").strip():
                unmet.append("must state the test that would settle it (settling_test)")

        elif label == "tested":
            support = [t for t in claim.get("tests", []) if t["role"] == "support"]
            if not support:
                unmet.append("needs a supporting test run by the harness (run_test role=support)")
            for t in claim.get("tests", []):
                if t["role"] == "counterexample" and any(r["pass"] is False for r in testing.runs(t)):
                    unmet.append(f"{t['id']}: a counterexample ({t['agent']}) broke the idea")
            unmet += _passed(results, "held_out", "replication", "provenance", "like_for_like")
            if srcs:
                unmet += _passed(results, "quote", "support")

        elif label == "refuted":
            failing = [f"{t['id']}@seed{r['seed']}" for t in claim.get("tests", [])
                       if not testing.is_stale(project, t) for r in testing.runs(t) if r["pass"] is False]
            if not failing:
                unmet.append("needs a run that reports pass=false (a counterexample or failing test)")
        out[label] = unmet
    return out


def _independent_sources(project, ids: list[str]) -> int:
    """Count sources that are distinct documents (different id and URL/title)."""
    seen = set()
    for sid in ids:
        s = project.source(sid) or {}
        key = (s.get("url") or s.get("title") or sid).strip().lower().rstrip("/")
        seen.add(key)
    return len(seen)


def evaluate(project, claim: dict[str, Any]):
    results = run_checks(project, claim)
    record_results(claim, results)
    return results, requirements(project, claim, results)


def set_label(project, cid: str, label: str, by: str | None = None,
              reason: str = "") -> tuple[bool, list[str], dict[str, Any]]:
    """Gate: run the checks and set the label only if every requirement is met.

    Returns (ok, unmet requirements, claim). Check results are saved either way.
    """
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}; choose from {LABELS}")
    claim = project.claim(cid)
    results, reqs = evaluate(project, claim)
    unmet = reqs[label]
    if not unmet:
        old = claim["label"]
        claim["label"] = label
        claim["history"].append({"at": now_iso(), "event": "label", "from": old, "to": label, "by": by, "reason": reason})
    else:
        claim["history"].append({"at": now_iso(), "event": "label-refused", "wanted": label, "by": by, "unmet": unmet})
    project.put_claim(claim)
    return not unmet, unmet, claim


def strongest_allowed(claim: dict[str, Any], reqs: dict[str, list[str]]) -> str:
    for label in FALLBACK_ORDER[claim["kind"]]:
        if not reqs.get(label):
            return label
    return PENDING


def audit(project, rerun_stale: bool = True, by: str = "audit", rerun_all: bool = False) -> list[dict[str, Any]]:
    """Re-check every labelled claim (the notebook re-audit).

    Tests whose script changed since it ran are re-run first (with fresh
    held-out seeds), so a result cannot outlive the code that produced it. A
    claim whose label is no longer earned moves to the strongest label it does
    earn: a tested idea whose test now fails becomes refuted. Returns changes.
    """
    changes = []
    claims = project.claims()
    for claim in claims:
        if rerun_stale:
            for t in claim.get("tests", []):
                if (rerun_all or testing.is_stale(project, t)) and (project.root / t["script"]).is_file():
                    testing.execute(project, claim, t)
                    claim["history"].append({"at": now_iso(), "event": "rerun", "test": t["id"], "by": by})
        results, reqs = evaluate(project, claim)
        cur = claim["label"]
        if cur == PENDING or (cur in reqs and not reqs[cur]):
            continue
        new = strongest_allowed(claim, reqs)
        if new == cur:
            continue
        claim["label"] = new
        reason = "; ".join(reqs.get(cur, []))[:500]
        claim["history"].append({"at": now_iso(), "event": "downgrade", "from": cur, "to": new, "by": by, "reason": reason})
        changes.append({"id": claim["id"], "from": cur, "to": new, "reason": reason})
    project.save_claims(claims)
    return changes
