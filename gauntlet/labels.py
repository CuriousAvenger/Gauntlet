"""Labels and the mechanical checks behind them.

Only checks a model cannot reliably do itself live here: is the quote really in the
saved source, does every number trace to a passage or a log, did the harness's own
test runs pass on held-out seeds, and does an independent replication agree. Judgement
(does a passage *support* the claim, is a comparison fair) belongs to the referee.
"""

from __future__ import annotations

import re
from statistics import mean
from typing import Any

from . import testing
from .util import normalize_text, numbers, sha256_file

LABELS = ("established", "reported", "contested", "tested", "refuted", "untested")
DISPLAY = {"established": "Established", "reported": "Reported", "contested": "Contested",
           "tested": "New idea: tested", "refuted": "New idea: refuted", "untested": "New idea: untested",
           "pending": "Pending"}
MEANING = {"established": "Independent sources agree", "reported": "One source says so",
           "contested": "Sources disagree", "tested": "Proposed here, passed a test",
           "refuted": "Proposed here, failed a test", "untested": "Proposed here, no check run"}
AUTHORITATIVE = {"systematic-review", "meta-analysis", "guideline", "official"}
REPLICATION_TOL = 0.10
MIN_QUOTE = 20


# ---- checks --------------------------------------------------------------------------

def find_passage(passage: str, text: str) -> bool:
    """Exact match after normalisation; '...' skips text, fragments must appear in order."""
    hay, pos = normalize_text(text), 0
    for frag in re.split(r"\.\.\.|…", passage):
        frag = normalize_text(frag).strip(" .")
        if not frag:
            continue
        idx = hay.find(frag, pos)
        if idx < 0:
            return False
        pos = idx + len(frag)
    return pos > 0


def quote_problems(project, claim: dict[str, Any]) -> list[str]:
    problems = []
    for i, ev in enumerate(claim["sources"]):
        src, tag = project.source(ev["source_id"]), f"evidence {i} ({ev['source_id']})"
        if src is None or src["status"] != "read":
            problems.append(f"{tag}: source is not saved and read")
        elif sha256_file(project.root / src["file"]) != src["sha256"]:
            problems.append(f"{tag}: saved source text was modified after capture")
        elif len(normalize_text(ev["passage"])) < MIN_QUOTE:
            problems.append(f"{tag}: quote a full sentence, not a fragment")
        elif not find_passage(ev["passage"], project.source_text(src)):
            problems.append(f"{tag}: passage not found verbatim in the saved source")
    return problems


def provenance_problems(project, claim: dict[str, Any]) -> list[str]:
    """Every number in the statement appears in a passage or a run log (rounding to the
    precision the statement shows is allowed: a log value 8.14 supports "8", not "8.0")."""
    evidence = " ".join(ev["passage"] for ev in claim["sources"])
    for t in claim["tests"]:
        for r in testing.runs(t):
            path = project.root / r["log"]
            evidence += "\n" + (path.read_text(errors="replace") if path.exists() else "")
    values = [v for v, _ in numbers(evidence)]
    return [f"number {v:g} in the statement appears in no passage or test log"
            for v, dec in numbers(claim["statement"])
            if not any(round(e, dec) == round(v, dec) for e in values)]


def _headline_means(test: dict[str, Any]) -> dict[str, float]:
    vals: dict[str, list[float]] = {}
    for r in testing.runs(test):
        for k, v in r["headline"].items():
            if isinstance(v, (int, float)):
                vals.setdefault(k, []).append(float(v))
    return {k: mean(v) for k, v in vals.items()}


def test_problems(project, idea: dict[str, Any]) -> list[str]:
    """Why an idea is not (yet) tested: support runs, held-out runs, replication, counterexamples."""
    tests = idea["tests"]
    support = [t for t in tests if t["role"] == "support"]
    if not support:
        return ["no support test has been run"]
    problems = []
    for t in tests:
        if testing.is_stale(project, t):
            problems.append(f"{t['id']}: script changed since it ran")
        elif t["role"] == "counterexample" and any(r["pass"] is False for r in testing.runs(t)):
            problems.append(f"{t['id']}: a counterexample broke the idea")
    for t in support:
        failed = [r["seed"] for r in testing.runs(t) if not r["pass"]]
        if failed:
            fitted = all(r["pass"] for r in t["dev_runs"])
            problems.append(f"{t['id']}: failed on seeds {failed}"
                            + (" (passed only on its development seeds)" if fitted else ""))
        reps = [r for r in tests if r["role"] == "replication" and r["replicates"] == t["id"]
                and r["sha256"] != t["sha256"]]
        if not reps:
            problems.append(f"{t['id']}: needs an independent replication (its own script)")
        base = _headline_means(t)
        for rep in reps:
            if not all(r["pass"] for r in testing.runs(rep)):
                problems.append(f"{rep['id']}: replication did not pass on every seed")
                continue
            other = _headline_means(rep)
            for k, a in base.items():
                b = other.get(k)
                if b is None:
                    problems.append(f"{rep['id']}: replication did not report headline '{k}'")
                elif abs(a - b) > REPLICATION_TOL * max(abs(a), abs(b), 1e-12):
                    problems.append(f"{rep['id']}: {k} {b:.4g} vs {a:.4g} in {t['id']} (over 10% apart)")
    return problems


# ---- the gate ---------------------------------------------------------------------------

def requirements(project, claim: dict[str, Any]) -> dict[str, list[str]]:
    """Unmet requirements for every label (empty list = label earned)."""
    sides = [ev.get("side", "for") for ev in claim["sources"]]
    shared = quote_problems(project, claim) + provenance_problems(project, claim)
    if claim["kind"] == "sourced":
        out = {lab: [f"a new idea label; {claim['id']} comes from sources"] for lab in ("tested", "refuted", "untested")}
        urls = {(project.source(ev["source_id"]) or {}).get("url") or ev["source_id"]
                for ev, side in zip(claim["sources"], sides) if side == "for"}
        out["reported"] = shared + ([] if "for" in sides else ["needs a source that says so"]) \
            + (["a source disagrees; use contested"] if "against" in sides else [])
        out["established"] = list(out["reported"]) + ([] if len(urls) >= 2 else ["needs 2+ independent sources"])
        if project.state()["high_stakes"] and not any(
                (project.source(ev["source_id"]) or {}).get("kind") in AUTHORITATIVE for ev in claim["sources"]):
            out["established"].append("high-stakes topic: needs a systematic review, meta-analysis, guideline or official source")
        out["contested"] = shared + ([] if {"for", "against"} <= set(sides) else ["needs passages on both sides"])
        return out
    out = {lab: [f"a sourced-claim label; {claim['id']} is a new idea"] for lab in ("established", "reported", "contested")}
    out["untested"] = [] if claim.get("settling_test") else ["needs the test that would settle it"]
    out["tested"] = shared + test_problems(project, claim)
    failing = [t["id"] for t in claim["tests"] if not testing.is_stale(project, t)
               and any(r["pass"] is False for r in testing.runs(t))]
    out["refuted"] = [] if failing else ["needs a run that reported pass=false"]
    return out


def set_label(project, cid: str, label: str) -> list[str]:
    """Set the label if earned; return what is missing otherwise (empty = done)."""
    claim = project.claim(cid)
    unmet = requirements(project, claim)[label]
    if not unmet:
        claim["label"] = label
        project.put_claim(claim)
    return unmet


def reaudit(project) -> list[dict[str, str]]:
    """Re-run tests whose scripts changed, then move any label no longer earned to the
    strongest one that is (a tested idea whose test now fails becomes refuted)."""
    order = {"sourced": ("established", "contested", "reported"), "idea": ("refuted", "tested", "untested")}
    claims, changes = project.claims(), []
    for c in claims:
        for t in c["tests"]:
            if testing.is_stale(project, t) and (project.root / t["script"]).is_file():
                testing.execute(project, t)
        if c["label"] == "pending":
            continue
        reqs = requirements(project, c)
        if not reqs[c["label"]] and not (c["label"] == "tested" and not reqs["refuted"]):
            continue
        new = next((lab for lab in order[c["kind"]] if not reqs[lab]), "pending")
        changes.append({"id": c["id"], "from": c["label"], "to": new})
        c["label"] = new
    project.save_claims(claims)
    return changes
