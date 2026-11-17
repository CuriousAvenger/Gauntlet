"""The checks a model cannot reliably do for itself, and the label rules built on them.

Judgement (does a passage *support* the claim, is a comparison fair) is the referee's job.
Code checks only facts: the quote is in the saved source, every number traces to a quote
or a test log, and the harness's own test runs passed.
"""

from __future__ import annotations

import re
import unicodedata
from statistics import mean
from typing import Any

from .runner import is_stale
from .store import sha256

LABELS = ("established", "reported", "contested", "tested", "refuted", "untested")
SOURCED, IDEA = ("established", "contested", "reported"), ("refuted", "tested", "untested")
NAMES = {"established": "Established", "reported": "Reported", "contested": "Contested",
         "tested": "New idea: tested", "refuted": "New idea: refuted", "untested": "New idea: untested",
         "pending": "Pending"}
MEANINGS = {"established": "Independent sources agree", "reported": "One source says so",
            "contested": "Sources disagree", "tested": "Proposed here, passed a test",
            "refuted": "Proposed here, failed a test", "untested": "Proposed here, not tested"}
REPLICATION_TOL = 0.10
MIN_QUOTE_CHARS = 20

_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                        "−": "-", " ": " "})
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def normalize(text: str) -> str:
    """Case, whitespace, curly quotes, dashes and hyphenated line breaks; never drops words."""
    text = unicodedata.normalize("NFKC", text).translate(_CHARS)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    """Verbatim after normalising; '...' skips text, and the pieces must appear in order."""
    hay, pos, found = normalize(text), 0, False
    for piece in re.split(r"\.\.\.|…", quote):
        piece = normalize(piece).strip(" .")
        if piece:
            idx = hay.find(piece, pos)
            if idx < 0:
                return False
            pos, found = idx + len(piece), True
    return found


def numbers(text: str) -> list[tuple[float, int]]:
    """(value, decimals shown) for each number; '1,000' is one thousand; C12 or S3 are ignored."""
    out = []
    for tok in _NUMBER.findall(unicodedata.normalize("NFKC", text).replace("−", "-")):
        tok = tok.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", tok) else tok.split(",")[0]
        mantissa = tok.lower().split("e")[0]
        out.append((float(tok), len(mantissa.split(".")[1]) if "." in mantissa else 0))
    return out


def quote_problems(project, claim: dict[str, Any]) -> list[str]:
    problems, sources = [], project.sources()
    for q in claim["quotes"]:
        src, tag = sources.get(q["url"]), q.get("source", q["url"])
        if not src or src["status"] != "read":
            problems.append(f"{tag}: source was not read")
        elif sha256(project.root / src["file"]) != src["sha256"]:
            problems.append(f"{tag}: saved copy was edited after it was fetched")
        elif len(normalize(q["quote"])) < MIN_QUOTE_CHARS:
            problems.append(f"{tag}: quote a full sentence, not a fragment")
        elif not quote_in(q["quote"], project.text(src)):
            problems.append(f"{tag}: quote not found word for word in the saved copy")
    return problems


def number_problems(project, claim: dict[str, Any]) -> list[str]:
    """Each number in the statement must appear in a quote or a test log, allowing rounding
    to the precision the statement shows (a log value 8.14 supports "8", not "8.0")."""
    evidence = " ".join(q["quote"] for q in claim["quotes"])
    for t in claim["tests"]:
        for r in t["runs"]:
            log = project.root / r["log"]
            evidence += "\n" + (log.read_text(errors="replace") if log.exists() else "")
    known = [v for v, _ in numbers(evidence)]
    return [f"the number {v:g} is not in any quote or test log"
            for v, places in numbers(claim["statement"]) if not any(round(k, places) == round(v, places) for k in known)]


def _headlines(test: dict[str, Any]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for r in test["runs"]:
        for k, v in r["headline"].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                values.setdefault(k, []).append(float(v))
    return {k: mean(v) for k, v in values.items()}


def test_problems(project, idea: dict[str, Any]) -> list[str]:
    support = [t for t in idea["tests"] if t["role"] == "support"]
    if not support:
        return ["no support test has been run"]
    problems = []
    for t in idea["tests"]:
        if is_stale(project, t):
            problems.append(f"{t['id']}: its script was edited after it ran")
        elif t["role"] == "counterexample" and any(r["pass"] is False for r in t["runs"]):
            problems.append(f"{t['id']}: a counterexample broke the idea")
    for t in support:
        failed = [r["seed"] for r in t["runs"] if not r["pass"]]
        if failed:
            fitted = all(r["pass"] for r in t["runs"] if not r["held_out"])
            problems.append(f"{t['id']}: failed on seeds {failed}" + (" (passed only on its own seeds)" if fitted else ""))
        copies = [r for r in idea["tests"] if r["role"] == "replication" and r["replicates"] == t["id"]
                  and r["sha256"] != t["sha256"]]
        if not copies:
            problems.append(f"{t['id']}: needs a replication with independently written code")
        for rep in copies:
            if not all(r["pass"] for r in rep["runs"]):
                problems.append(f"{rep['id']}: replication did not pass on every seed")
                continue
            ours, theirs = _headlines(t), _headlines(rep)
            for k, a in ours.items():
                b = theirs.get(k)
                if b is None:
                    problems.append(f"{rep['id']}: did not report '{k}'")
                elif abs(a - b) > REPLICATION_TOL * max(abs(a), abs(b), 1e-12):
                    problems.append(f"{rep['id']}: {k} is {b:.4g}, but {a:.4g} in {t['id']} (more than 10% apart)")
    return problems


def unmet(project, claim: dict[str, Any]) -> dict[str, list[str]]:
    """For every label, what the claim is missing (an empty list means it earns the label)."""
    is_idea = "settling_test" in claim
    wrong = [f"{claim['id']} is {'an idea' if is_idea else 'a claim from sources'}"]
    out = {label: list(wrong) for label in (SOURCED if is_idea else IDEA)}
    common = quote_problems(project, claim) + number_problems(project, claim)
    if is_idea:
        out["untested"] = []
        out["tested"] = common + test_problems(project, claim)
        refuted = any(r["pass"] is False for t in claim["tests"] if not is_stale(project, t) for r in t["runs"])
        out["refuted"] = [] if refuted else ["no run has reported pass=false"]
        return out
    agree = {q["url"] for q in claim["quotes"] if not q.get("disagrees")}
    disagree = any(q.get("disagrees") for q in claim["quotes"])
    out["reported"] = common + ([] if agree else ["no quote supports it"]) + (["a source disagrees: use contested"] if disagree else [])
    out["established"] = out["reported"] + ([] if len(agree) >= 2 else ["needs two or more independent sources"])
    out["contested"] = common + ([] if agree and disagree else ["needs quotes on both sides"])
    return out


def reaudit(project) -> list[dict[str, str]]:
    """Re-run tests whose scripts were edited, then move any label that is no longer earned
    to the strongest one that is (a tested idea whose test now fails becomes refuted)."""
    from .runner import execute

    claims, changes = project.claims(), []
    for c in claims:
        for t in c["tests"]:
            if is_stale(project, t) and (project.root / t["script"]).is_file():
                execute(project, t)
        if c["label"] == "pending":
            continue
        missing = unmet(project, c)
        refuted_now = c["label"] == "tested" and not missing["refuted"]
        if missing[c["label"]] or refuted_now:
            order = IDEA if "settling_test" in c else SOURCED
            new = next((label for label in order if not missing[label]), "pending")
            changes.append({"id": c["id"], "from": c["label"], "to": new})
            c["label"] = new
    project.save_claims(claims)
    return changes
