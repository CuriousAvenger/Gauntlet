"""The research folder's records, as plain files the agent can read directly.

The research folder is the copy of the Gauntlet template that contains `skills/`
(override with $GAUNTLET_ROOT):

  QUESTION.md          the problem, written by the user
  sources/index.json   url -> saved copy (S1.txt, ...) with its hash, or why it was unreadable
  sources/S1.txt ...   exact text Gauntlet fetched
  claims.jsonl         claims and ideas: quotes, tests, labels
  runs/                test scripts (frozen copies) and the log of every run
  report.md
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .fetch import FetchError, fetch


def write_file(path: Path, text: str) -> None:
    """Atomic write, so a crash never leaves a half-written record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


TEMPLATE_ROOT = Path(__file__).resolve().parents[4]  # lib -> scripts -> gauntlet -> skills -> root


class Project:
    def __init__(self):
        self.root = Path(os.environ.get("GAUNTLET_ROOT") or TEMPLATE_ROOT)
        self.question_path = self.root / "QUESTION.md"
        self.report_path = self.root / "report.md"
        self._index = self.root / "sources" / "index.json"
        self._claims = self.root / "claims.jsonl"

    def question(self) -> str:
        """The first line of QUESTION.md that is not a heading or the template's placeholder."""
        if self.question_path.exists():
            for line in self.question_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith(("#", ">")) and line != "Write your research question here.":
                    return line
        return ""

    # ---- sources -------------------------------------------------------------
    def sources(self) -> dict[str, dict[str, Any]]:
        return json.loads(self._index.read_text()) if self._index.exists() else {}

    def source(self, url: str, page_text: str | None = None) -> dict[str, Any]:
        """The saved copy of `url`, fetched on first use. `page_text` saves text the agent
        supplies for a page Gauntlet cannot fetch. Raises FetchError if unreadable."""
        index = self.sources()
        src = index.get(url)
        if src and src["status"] == "read":
            return src
        if src and page_text is None:
            raise FetchError(src["reason"])
        sid = src["id"] if src else f"S{len(index) + 1}"
        try:
            text, title = (page_text, "") if page_text else fetch(url)
        except FetchError as e:
            index[url] = {"id": sid, "url": url, "status": "unreadable", "reason": str(e)}
            write_file(self._index, json.dumps(index, indent=1))
            raise
        path = self.root / "sources" / f"{sid}.txt"
        write_file(path, text)
        index[url] = {"id": sid, "url": url, "title": title or url, "status": "read", "file": f"sources/{sid}.txt",
                      "sha256": sha256(path), "supplied_by_agent": page_text is not None}
        write_file(self._index, json.dumps(index, indent=1))
        return index[url]

    def text(self, src: dict[str, Any]) -> str:
        return (self.root / src["file"]).read_text(encoding="utf-8", errors="replace")

    # ---- claims ----------------------------------------------------------------
    def claims(self) -> list[dict[str, Any]]:
        if not self._claims.exists():
            return []
        return [json.loads(line) for line in self._claims.read_text().splitlines() if line.strip()]

    def save_claims(self, claims: list[dict[str, Any]]) -> None:
        write_file(self._claims, "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims))

    def claim(self, cid: str) -> dict[str, Any]:
        for c in self.claims():
            if c["id"] == cid:
                return c
        raise KeyError(f"no claim {cid} (see claims.jsonl)")

    def put(self, claim: dict[str, Any]) -> None:
        claims = [c for c in self.claims() if c["id"] != claim["id"]] + [claim]
        self.save_claims(sorted(claims, key=lambda c: (c["id"][0], int(c["id"][1:]))))

    def next_id(self, prefix: str) -> str:
        return f"{prefix}{1 + sum(c['id'].startswith(prefix) for c in self.claims())}"
