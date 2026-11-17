"""The trust layer: labels, the evidence each needs, and gated label changes.

A claim's label can only be set when its requirements are met *now*. The audit
re-checks every claim each cycle and moves any claim whose evidence no longer
holds to the strongest label it still earns.
"""

from __future__ import annotations

from typing import Any

from .checks import CheckResult, record_results, run_checks
from .util import now_iso, parse_result_line

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


def _test_result(project, rel: str | None) -> dict[str, Any] | None:
    if not rel:
        return None
    p = project.root / rel
    if not p.exists():
        return None
    return parse_result_line(p.read_text(encoding="utf-8", errors="replace"))


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
            tests = [t for t in claim.get("tests", []) if t.get("role", "support") == "support"]
            if not tests:
                unmet.append("needs a test script and its output log")
            for t in tests:
                if not t.get("script"):
                    unmet.append(f"{t['id']}: no script recorded")
                res = _test_result(project, t.get("log"))
                if res is None:
                    unmet.append(f"{t['id']}: log missing or has no GAUNTLET_RESULT line")
                elif not res.get("pass"):
                    unmet.append(f"{t['id']}: test log reports pass=false")
            for t in claim.get("tests", []):
                if t.get("role") == "counterexample":
                    res = _test_result(project, t.get("log"))
                    if res is not None and not res.get("pass", True):
                        unmet.append(f"{t['id']}: a counterexample run failed the idea")
            unmet += _passed(results, "held_out", "replication", "provenance", "like_for_like")
            if srcs:
                unmet += _passed(results, "quote", "support")

        elif label == "refuted":
            failing = []
            for t in claim.get("tests", []):
                res = _test_result(project, t.get("log"))
                if res is not None and res.get("pass") is False:
                    failing.append(t["id"])
            for t in claim.get("tests", []):
                for r in t.get("held_out_runs", []):
                    if r.get("pass") is False:
                        failing.append(f"{t['id']}@seed{r['seed']}")
            if not failing:
                unmet.append("needs a counterexample or failing test output (a log with pass=false)")
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


def evaluate(project, claim: dict[str, Any], execute: bool = True):
    results = run_checks(project, claim, execute=execute)
    record_results(claim, results)
    return results, requirements(project, claim, results)


def set_label(project, cid: str, label: str, by: str | None = None, reason: str = "",
              execute: bool = True) -> tuple[bool, list[str], dict[str, Any]]:
    """Gate: run the checks and set the label only if every requirement is met.

    Returns (ok, unmet requirements, claim). Check results are saved either way.
    """
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}; choose from {LABELS}")
    claim = project.claim(cid)
    results, reqs = evaluate(project, claim, execute=execute)
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


def audit(project, execute: bool = True, by: str = "audit") -> list[dict[str, Any]]:
    """Re-check every labelled claim. A claim whose label is no longer earned is
    moved to the strongest label it does earn (or back to pending). Ideas whose
    tests now fail move to refuted. Returns the list of changes."""
    changes = []
    claims = project.claims()
    for claim in claims:
        results, reqs = evaluate(project, claim, execute=execute)
        cur = claim["label"]
        if cur == PENDING:
            continue
        if cur in reqs and not reqs[cur] and not (cur == "tested" and not reqs["refuted"]):
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
