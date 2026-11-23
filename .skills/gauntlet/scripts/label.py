#!/usr/bin/env python3
"""Give a claim a label; refused, with what is missing, unless the evidence earns it.

  label.py CLAIM_ID LABEL --reason "why the evidence earns it"

Claims from sources: established (2+ independent sources agree), reported (one source),
contested (quotes on both sides). Ideas: untested (grounded: closest prior work quoted and
the difference stated), tested (also passed on held-out seeds and an independent replication
agrees), refuted (a run failed).

This file also owns the label rules and the re-audit that report.py runs.
"""
from __future__ import annotations

import argparse
import datetime
from statistics import mean
from typing import Any

from claim import claims, get_claim, grounding_problems, number_problems, put_claim, quote_problems, save_claims
from lib.identity import count_works
from run_test import execute, is_stale
from source import ROOT, Parser, finish, locked, sources

LABELS = ("established", "reported", "contested", "tested", "refuted", "untested")
NAMES = {"established": "Established", "reported": "Reported", "contested": "Contested",
         "tested": "New idea: tested", "refuted": "New idea: refuted", "untested": "New idea: untested",
         "pending": "Pending"}
REPLICATION_TOL = 0.10


def _headlines(test: dict[str, Any]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for run in test["runs"]:
        for k, v in run["headline"].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                values.setdefault(k, []).append(float(v))
    return {k: mean(v) for k, v in values.items()}


def test_problems(idea: dict[str, Any]) -> list[str]:
    support = [t for t in idea["tests"] if t["role"] == "support"]
    if not support:
        return ["no support test has been run"]
    problems = []
    for t in idea["tests"]:
        if is_stale(t):
            problems.append(f"{t['id']}: its script was edited after it ran")
        elif t["role"] == "counterexample" and any(r["pass"] is False for r in t["runs"]):
            problems.append(f"{t['id']}: a counterexample broke the idea")
    for t in support:
        logs = {(ROOT / r["log"]).read_text(errors="replace") for r in t["runs"] if (ROOT / r["log"]).exists()}
        if len(t["runs"]) > 1 and len(logs) == 1:
            problems.append(f"{t['id']}: its output is identical for every seed, so the held-out seeds tested "
                            "nothing; generate the instances from --seed")
        failed = [r["seed"] for r in t["runs"] if not r["pass"]]
        if failed:
            own_ok = all(r["pass"] for r in t["runs"] if not r["held_out"])
            problems.append(f"{t['id']}: failed on seeds {failed}" + (" (passed only on its own seeds)" if own_ok else ""))
        copies = [r for r in idea["tests"]
                  if r["role"] == "replication" and r["replicates"] == t["id"] and r["sha256"] != t["sha256"]]
        if not copies:
            problems.append(f"{t['id']}: needs a replication with independently written code")
        for rep in copies:
            if not all(r["pass"] for r in rep["runs"]):
                problems.append(f"{rep['id']}: replication did not pass on every seed")
                continue
            theirs = _headlines(rep)
            for k, a in _headlines(t).items():
                b = theirs.get(k)
                if b is None:
                    problems.append(f"{rep['id']}: did not report '{k}'")
                elif abs(a - b) > REPLICATION_TOL * max(abs(a), abs(b), 1e-12):
                    problems.append(f"{rep['id']}: {k} is {b:.4g}, but {a:.4g} in {t['id']} (more than 10% apart)")
    return problems


def unmet(claim: dict[str, Any]) -> dict[str, list[str]]:
    """For every label, what the claim is missing (an empty list means it earns the label)."""
    is_idea = "settling_test" in claim
    out = {label: [f"{claim['id']} is {'an idea' if is_idea else 'a claim from sources'}"] for label in LABELS}
    common = quote_problems(claim) + number_problems(claim)
    if is_idea:
        grounding = grounding_problems(claim)
        out["untested"] = grounding
        out["tested"] = common + grounding + test_problems(claim)
        failed = any(r["pass"] is False for t in claim["tests"] if not is_stale(t) for r in t["runs"])
        out["refuted"] = [] if failed else ["no run has reported pass=false"]
        return out
    agree = {q["url"] for q in claim["quotes"] if not q.get("disagrees")}
    disagree = any(q.get("disagrees") for q in claim["quotes"])
    out["reported"] = (common + ([] if agree else ["no quote supports it"])
                       + (["a source disagrees: use contested"] if disagree else []))
    index = sources()
    works = count_works([index[u] for u in agree if u in index])
    out["established"] = out["reported"] + ([] if works >= 2 else [
        "needs two or more independent sources" + (" (these quotes come from one work, e.g. a preprint and its "
                                                   "published version)" if len(agree) >= 2 else "")])
    out["contested"] = common + ([] if agree and disagree else ["needs quotes on both sides"])
    return out


def reaudit() -> list[dict[str, str]]:
    """Re-run tests whose scripts were edited, then move any label no longer earned to the
    strongest one that is (a tested idea whose test now fails becomes refuted)."""
    with locked():
        return _reaudit()


def _reaudit() -> list[dict[str, str]]:
    rows, changes = claims(), []
    for c in rows:
        for t in c["tests"]:
            if is_stale(t) and (ROOT / t["script"]).is_file():
                execute(t)
        if c["label"] == "pending":
            continue
        missing = unmet(c)
        if missing[c["label"]] or (c["label"] == "tested" and not missing["refuted"]):
            order = ("refuted", "tested", "untested") if "settling_test" in c else ("established", "contested", "reported")
            new = next((label for label in order if not missing[label]), "pending")
            changes.append({"id": c["id"], "from": c["label"], "to": new})
            c.setdefault("history", []).append({"label": new, "reason": "re-check: " + "; ".join(missing[c["label"]][:2]),
                                                "at": _now()})
            c["label"] = new
    save_claims(rows)
    return changes


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    p = Parser(__doc__)
    p.add_argument("claim")
    p.add_argument("label", choices=LABELS)
    p.add_argument("--reason", required=True, help="one sentence: why the evidence earns this label")
    a = p.parse_args()
    with locked():
        claim = get_claim(a.claim)
        missing = unmet(claim)[a.label]
        if missing:
            finish({"id": claim["id"], "refused": a.label, "label": NAMES[claim["label"]], "missing": missing}, 1)
        claim.setdefault("history", []).append({"label": a.label, "reason": a.reason.strip(), "at": _now()})
        claim["label"] = a.label
        put_claim(claim)
    finish({"id": claim["id"], "label": NAMES[a.label]})


if __name__ == "__main__":
    main()
