"""Small shared helpers: time, slugs, JSONL storage, text normalisation."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable

RESULT_MARKER = "GAUNTLET_RESULT"


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0] or text[:max_len]
    return text or "question"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON: {e}") from e
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


_QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
}


def normalize_text(text: str) -> str:
    """Normalise for quote matching: unicode forms, quotes/dashes, hyphenated
    line breaks, whitespace and case. Does NOT drop words or punctuation."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(_QUOTE_MAP.get(c, c) for c in text)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)  # re-join hyphenated line breaks
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


_NUM_RE = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def extract_numbers(text: str) -> list[str]:
    """Numbers as canonical strings ('1,000' -> '1000', '8.50' -> '8.5').
    Tokens attached to letters on the left (C12, S3, arXiv IDs inside words) are skipped."""
    return [canonical_number(tok) for tok in _number_tokens(text)]


def extract_number_values(text: str) -> list[tuple[str, float, int]]:
    """(canonical, value, decimals shown) for each number in the text."""
    out = []
    for tok in _number_tokens(text):
        try:
            val = float(tok)
        except ValueError:
            continue
        mant = tok.lower().split("e")[0]
        decimals = len(mant.split(".")[1]) if "." in mant else 0
        out.append((canonical_number(tok), val, decimals))
    return out


def _number_tokens(text: str) -> list[str]:
    out = []
    for m in _NUM_RE.finditer(unicodedata.normalize("NFKC", text)):
        tok = m.group(0).replace("−", "-").lstrip("+")
        # a comma followed by exactly three digits is a thousands separator
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?([eE][-+]?\d+)?", tok):
            tok = tok.replace(",", "")
        else:
            tok = tok.split(",")[0]
        out.append(tok)
    return out


def canonical_number(tok: str) -> str:
    try:
        val = float(tok)
    except ValueError:
        return tok
    if val == int(val) and abs(val) < 1e15 and "e" not in tok.lower():
        return str(int(val))
    return repr(val)


def parse_result_line(text: str) -> dict[str, Any] | None:
    """Return the last `GAUNTLET_RESULT {json}` object printed in a log."""
    found = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(RESULT_MARKER):
            payload = line[len(RESULT_MARKER):].strip()
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                found = obj
    return found
