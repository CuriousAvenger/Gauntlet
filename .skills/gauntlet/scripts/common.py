"""Shared by the Gauntlet scripts: the research folder's records, the checks, and test runs.

The research folder is the template copy that contains .skills/ (or $GAUNTLET_ROOT):
  AGENTS.md            the question, under "## Question"
  sources/index.json   url -> saved copy (S1.txt, ...) with its hash, or why it was unreadable
  claims.jsonl         claims and ideas, with quotes, tests and labels
  runs/                frozen test scripts and the log of every run
  report.md
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from statistics import mean
from typing import Any, NoReturn

ROOT = Path(os.environ.get("GAUNTLET_ROOT") or Path(__file__).resolve().parents[3])
INDEX = ROOT / "sources" / "index.json"
CLAIMS = ROOT / "claims.jsonl"

LABELS = ("established", "reported", "contested", "tested", "refuted", "untested")
NAMES = {"established": "Established", "reported": "Reported", "contested": "Contested",
         "tested": "New idea: tested", "refuted": "New idea: refuted", "untested": "New idea: untested",
         "pending": "Pending"}
REPLICATION_TOL = 0.10
HELD_OUT_SEEDS = 3
TIMEOUT_S = 120


# ---- output -----------------------------------------------------------------------

def finish(result: dict[str, Any], code: int = 0) -> NoReturn:
    """Print one JSON object and exit: 0 = done, 1 = refused, 2 = misuse."""
    print(json.dumps(result, indent=1, ensure_ascii=False))
    sys.exit(code)


def fail(message: str, code: int = 2) -> NoReturn:
    finish({"error": message}, code)


# ---- records ----------------------------------------------------------------------

def write_file(path: Path, text: str) -> None:
    """Atomic write, so a crash never leaves a half-written record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources() -> dict[str, dict[str, Any]]:
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def source_text(src: dict[str, Any]) -> str:
    return (ROOT / src["file"]).read_text(encoding="utf-8", errors="replace")


def claims() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CLAIMS.read_text().splitlines() if line.strip()] if CLAIMS.exists() else []


def save_claims(rows: list[dict[str, Any]]) -> None:
    rows = sorted(rows, key=lambda c: (c["id"][0], int(c["id"][1:])))
    write_file(CLAIMS, "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in rows))


def get_claim(cid: str) -> dict[str, Any]:
    found = next((c for c in claims() if c["id"] == cid), None)
    if found is None:
        fail(f"no claim {cid} (see claims.jsonl)")
    return found


def put_claim(claim: dict[str, Any]) -> None:
    save_claims([c for c in claims() if c["id"] != claim["id"]] + [claim])


def question() -> str:
    """The first line under '## Question' in AGENTS.md, unless it is still the placeholder."""
    path = ROOT / "AGENTS.md"
    match = re.search(r"^## Question\s*$(.*?)(?=^## |\Z)", path.read_text(), re.M | re.S) if path.exists() else None
    text = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.S) if match else ""
    line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return "" if line == "Write your research question here." else line


# ---- quote and number checks ---------------------------------------------------------

_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                        "−": "-", " ": " "})


def normalize(text: str) -> str:
    """Case, whitespace, curly quotes, dashes and hyphenated line breaks; never drops words."""
    text = unicodedata.normalize("NFKC", text).translate(_CHARS)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    """Word for word after normalising; '...' skips text, and the pieces must appear in order."""
    hay, pos, found = normalize(text), 0, False
    for piece in re.split(r"\.\.\.|…", quote):
        piece = normalize(piece).strip(" .")
        if piece:
            pos = hay.find(piece, pos)
            if pos < 0:
                return False
            pos, found = pos + len(piece), True
    return found


def numbers(text: str) -> list[tuple[float, int]]:
    """(value, decimals shown) for each number; '1,000' is one thousand; ids like C12 are ignored."""
    out = []
    for tok in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?", unicodedata.normalize("NFKC", text)):
        tok = tok.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", tok) else tok.split(",")[0]
        mantissa = tok.lower().split("e")[0]
        out.append((float(tok), len(mantissa.split(".")[1]) if "." in mantissa else 0))
    return out


def quote_problems(claim: dict[str, Any]) -> list[str]:
    problems, index = [], sources()
    for q in claim["quotes"]:
        src = index.get(q["url"])
        if not src or src["status"] != "read":
            problems.append(f"{q['source']}: source was not read")
        elif sha256(ROOT / src["file"]) != src["sha256"]:
            problems.append(f"{q['source']}: saved copy was edited after it was fetched")
        elif len(normalize(q["quote"])) < 20:
            problems.append(f"{q['source']}: quote a full sentence, not a fragment")
        elif not quote_in(q["quote"], source_text(src)):
            problems.append(f"{q['source']}: quote not found word for word in the saved copy")
    return problems


def number_problems(claim: dict[str, Any]) -> list[str]:
    """Each number in the statement must appear in a quote or a test log, allowing rounding to
    the precision the statement shows (a log value 8.14 supports "8", not "8.0")."""
    evidence = " ".join(q["quote"] for q in claim["quotes"])
    for run in (r for t in claim["tests"] for r in t["runs"]):
        log = ROOT / run["log"]
        evidence += "\n" + (log.read_text(errors="replace") if log.exists() else "")
    known = [v for v, _ in numbers(evidence)]
    return [f"the number {v:g} is not in any quote or test log"
            for v, places in numbers(claim["statement"]) if not any(round(k, places) == round(v, places) for k in known)]


# ---- test runs ------------------------------------------------------------------------

def is_stale(test: dict[str, Any]) -> bool:
    """The frozen script was edited (or removed) after it ran."""
    path = ROOT / test["script"]
    return not path.is_file() or sha256(path) != test["sha256"]


def _run(test: dict[str, Any], seed: int, held_out: bool) -> dict[str, Any]:
    cmd = [sys.executable, str(ROOT / test["script"]), "--seed", str(seed)]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S)
        output, ok = proc.stdout + proc.stderr, proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, ok = f"timed out after {TIMEOUT_S}s", False
    log = f"runs/{test['id']}-seed{seed}.log"
    write_file(ROOT / log, output)
    result = None
    lines = [l.strip() for l in output.splitlines() if l.strip().startswith("GAUNTLET_RESULT")]
    if ok and lines:
        try:
            result = json.loads(lines[-1][len("GAUNTLET_RESULT"):])
        except json.JSONDecodeError:
            pass
    result = result if isinstance(result, dict) else None
    return {"seed": seed, "held_out": held_out, "log": log, "pass": None if result is None else bool(result.get("pass")),
            "headline": (result or {}).get("headline") or {}}


def execute(test: dict[str, Any]) -> dict[str, Any]:
    """(Re-)run a test in place: the author's seeds, then held-out seeds drawn at random."""
    test["sha256"] = sha256(ROOT / test["script"])
    held_out: list[int] = []
    while test["role"] != "counterexample" and len(held_out) < HELD_OUT_SEEDS:
        seed = random.SystemRandom().randrange(1000, 10**9)
        if seed not in test["seeds"] and seed not in held_out:
            held_out.append(seed)
    test["runs"] = [_run(test, s, False) for s in test["seeds"]] + [_run(test, s, True) for s in held_out]
    return test


# ---- labels ---------------------------------------------------------------------------

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
    wrong = [f"{claim['id']} is {'an idea' if is_idea else 'a claim from sources'}"]
    out = {label: list(wrong) for label in LABELS}
    common = quote_problems(claim) + number_problems(claim)
    if is_idea:
        out["untested"] = []
        out["tested"] = common + test_problems(claim)
        failed = any(r["pass"] is False for t in claim["tests"] if not is_stale(t) for r in t["runs"])
        out["refuted"] = [] if failed else ["no run has reported pass=false"]
        return out
    agree = {q["url"] for q in claim["quotes"] if not q.get("disagrees")}
    disagree = any(q.get("disagrees") for q in claim["quotes"])
    out["reported"] = common + ([] if agree else ["no quote supports it"]) + (["a source disagrees: use contested"] if disagree else [])
    out["established"] = out["reported"] + ([] if len(agree) >= 2 else ["needs two or more independent sources"])
    out["contested"] = common + ([] if agree and disagree else ["needs quotes on both sides"])
    return out


def reaudit() -> list[dict[str, str]]:
    """Re-run tests whose scripts were edited, then move any label no longer earned to the
    strongest one that is (a tested idea whose test now fails becomes refuted)."""
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
            c["label"] = new
    save_claims(rows)
    return changes
