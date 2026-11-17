"""Small helpers shared by the store, checks and report."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

RESULT_MARKER = "GAUNTLET_RESULT"


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].rsplit("-", 1)[0] if len(text) > max_len else (text or "question")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


_CHAR_MAP = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
})


def normalize_text(text: str) -> str:
    """For quote matching: unicode form, quotes and dashes, hyphenated line breaks,
    whitespace and case. Never drops words or punctuation."""
    text = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


_NUM_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def numbers(text: str) -> list[tuple[float, int]]:
    """Numbers in the text as (value, decimals shown). '1,000' is one thousand;
    tokens glued to letters (C12, S3) are ignored."""
    out = []
    for m in _NUM_RE.finditer(unicodedata.normalize("NFKC", text).replace("−", "-")):
        tok = m.group(0)
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?([eE][-+]?\d+)?", tok):
            tok = tok.replace(",", "")
        else:
            tok = tok.split(",")[0]
        mant = tok.lower().split("e")[0]
        out.append((float(tok), len(mant.split(".")[1]) if "." in mant else 0))
    return out


def parse_result(text: str) -> dict[str, Any] | None:
    """The last `GAUNTLET_RESULT {json}` line printed by a test script."""
    found = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(RESULT_MARKER):
            try:
                obj = json.loads(line[len(RESULT_MARKER):])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                found = obj
    return found
