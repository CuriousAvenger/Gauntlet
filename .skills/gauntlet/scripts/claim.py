#!/usr/bin/env python3
"""Record a claim or an idea. Reads one JSON object on stdin:

  claim from sources:  {"statement": "...", "quotes": [{"url": "...", "quote": "exact words", "disagrees": false}]}
  new idea:            {"statement": "...", "settling_test": "the test that would settle it"}
  more quotes:         {"add_to": "C3", "quotes": [...]}

  claim.py <<'EOF'
  {...}
  EOF

Read each URL with source.py first. Quotes are checked word for word against the saved copy,
and every number in the statement must appear in a quote. Problems come back under "fix";
the claim stays pending until a referee labels it.

This file also owns claims.jsonl and the quote and number checks.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from typing import Any

from source import ROOT, fail, finish, sha256, source_text, sources, write_file

CLAIMS = ROOT / "claims.jsonl"


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


# ---- quote and number checks -------------------------------------------------------------

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


# ---- the command ---------------------------------------------------------------------------

def main() -> None:
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    try:
        req = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        fail(f"stdin is not valid JSON: {e}")

    index, quotes = sources(), []
    for q in req.get("quotes", []):
        src = index.get(q.get("url"))
        if not q.get("quote"):
            fail("each quote needs a url and a quote")
        if not src:
            fail(f"read {q.get('url')} with source.py first, then quote from it", 1)
        if src["status"] != "read":
            fail(f"{q['url']} could not be read ({src['reason']}), so it cannot be cited", 1)
        quotes.append({"source": src["id"], "url": q["url"], "quote": q["quote"].strip(),
                       "disagrees": bool(q.get("disagrees"))})

    def new_id(prefix):
        return f"{prefix}{1 + sum(c['id'].startswith(prefix) for c in claims())}"

    if req.get("add_to"):
        claim = get_claim(req["add_to"])
        claim["quotes"] += quotes
    elif req.get("settling_test"):
        claim = {"id": new_id("I"), "statement": req.get("statement", "").strip(), "quotes": quotes,
                 "settling_test": req["settling_test"].strip(), "tests": [], "label": "untested"}
    elif quotes:
        claim = {"id": new_id("C"), "statement": req.get("statement", "").strip(), "quotes": quotes,
                 "tests": [], "label": "pending"}
    else:
        fail("give quotes (a claim from sources), settling_test (an idea), or add_to with quotes")
    if not claim["statement"]:
        fail("the statement is empty")
    put_claim(claim)
    problems = quote_problems(claim) + number_problems(claim)
    finish({"id": claim["id"], "label": claim["label"], **({"fix": problems} if problems else {})})


if __name__ == "__main__":
    main()
