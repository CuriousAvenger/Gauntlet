#!/usr/bin/env python3
"""Read a source. Gauntlet fetches the page itself and keeps an exact copy; quotes are later
checked word for word against this copy.

  source.py URL                    first 8000 characters of the saved text
  source.py URL --from 8000        the next part
  source.py URL --find REGEX       matching lines, to copy quotes word for word
  source.py URL --text-file F      save text you read yourself, for a page Gauntlet cannot fetch
                [--title T]        (give the paper's title, so duplicates can be recognised)

arXiv links are read through the arXiv API and pinned to one version (an unversioned link
is pinned to the current version). Each source records its identity (arXiv id, DOI), so a
preprint and its journal version count as one work.

This file also owns the research folder's location and the JSON output the other scripts use.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator, NoReturn

from lib import arxiv, identity, search, web

# The research folder: the template copy that contains .skills/ (or $GAUNTLET_ROOT).
ROOT = Path(os.environ.get("GAUNTLET_ROOT") or Path(__file__).resolve().parents[3])
INDEX = ROOT / "sources" / "index.json"  # url -> saved copy (S1.txt, ...), its identity and hash, or why unreadable
CHUNK = 8000


def finish(result: dict[str, Any], code: int = 0) -> NoReturn:
    """Print one JSON object and exit: 0 = done, 1 = refused, 2 = misuse."""
    print(json.dumps(result, indent=1, ensure_ascii=False))
    sys.exit(code)


def fail(message: str, code: int = 2) -> NoReturn:
    finish({"error": message}, code)


class Parser(argparse.ArgumentParser):
    """Command-line parser whose usage errors follow the JSON contract (exit 2 = misuse)."""

    def __init__(self, doc: str | None = None, **kwargs: Any):
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(description=doc, **kwargs)  # subcommand parsers arrive with their own kwargs

    def error(self, message: str) -> NoReturn:
        fail(f"{message} (see --help)")


def write_file(path: Path, text: str) -> None:
    """Atomic write, so a crash never leaves a half-written record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_lock: dict[str, Any] = {"depth": 0, "file": None}


@contextlib.contextmanager
def locked() -> Iterator[None]:
    """Hold the research folder's lock while reading and rewriting records, so agents working
    in parallel never lose each other's writes or reuse an id. Re-entrant within a process."""
    if _lock["depth"] == 0:
        ROOT.mkdir(parents=True, exist_ok=True)
        f = open(ROOT / ".gauntlet.lock", "a+")
        try:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        except ImportError:  # Windows
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        _lock["file"] = f
    _lock["depth"] += 1
    try:
        yield
    finally:
        _lock["depth"] -= 1
        if _lock["depth"] == 0:
            _lock["file"].close()  # closing the file releases the lock
            _lock["file"] = None


def sources() -> dict[str, dict[str, Any]]:
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def source_text(src: dict[str, Any]) -> str:
    return (ROOT / src["file"]).read_text(encoding="utf-8", errors="replace")


def _read(url: str) -> tuple[str, str, dict[str, Any]]:
    """(text, title, extra metadata) fetched by Gauntlet."""
    found = identity.arxiv_id(url)
    if found:
        text, meta = arxiv.read(*found)
        extra = {k: meta[k] for k in ("authors", "published", "version", "text_from", "withdrawn", "journal_ref")}
        extra.update(pinned=meta["url"], meta={"citation_arxiv_id": found[0], "citation_doi": meta["doi"]})
        return text, meta["title"], extra
    text, title, meta = web.page(url)
    return text, title, {"meta": meta}


def save(url: str, page_text: str | None, title: str | None = None) -> dict[str, Any]:
    """Saved copy of `url`, fetching it on first use; failures are recorded as unreadable.
    The fetch happens outside the lock; only the bookkeeping holds it."""
    src = sources().get(url)
    if src and src["status"] == "read":
        return src
    if src and page_text is None:
        fail(f"unreadable, so it cannot be cited: {src['reason']}. If you can read it, use --text-file.", 1)
    doi = next((k[4:] for k in identity.keys(url) if k.startswith("doi:")), "")
    try:
        text, fetched_title, extra = (page_text, "", {}) if page_text is not None else _read(url)
    except web.FetchError as e:
        text, error = None, str(e)
        copy = (search.work(doi) or {}).get("open_copy")  # a paywalled paper may have a legal open copy
        if copy and copy != url:
            try:
                text, fetched_title, extra = _read(copy)
                extra["open_copy"] = copy
            except web.FetchError:
                pass
    if text is not None:
        doi = doi or extra.get("meta", {}).get("citation_doi", "")
        if (search.work(doi) or {}).get("retracted"):
            extra["retracted"] = True
    with locked():
        index = sources()
        src = index.get(url)
        if src and src["status"] == "read":
            return src  # another agent saved it meanwhile
        sid = src["id"] if src else f"S{len(index) + 1}"
        if text is None:
            index[url] = {"id": sid, "url": url, "status": "unreadable", "reason": error}
            write_file(INDEX, json.dumps(index, indent=1))
            fail(f"unreadable, so it cannot be cited: {error}. If you can read the page, use --text-file.", 1)
        path = ROOT / "sources" / f"{sid}.txt"
        write_file(path, text)
        meta = extra.pop("meta", {})
        row = {"id": sid, "url": url, "title": title or fetched_title or url, "status": "read",
               "file": f"sources/{sid}.txt", "sha256": sha256(path), "ids": identity.keys(url, meta),
               "supplied_by_agent": page_text is not None, **extra}
        same = [s["id"] for s in index.values() if s["status"] == "read" and identity.same_work(row, s)]
        if same:
            row["same_work_as"] = same
        index[url] = row
        write_file(INDEX, json.dumps(index, indent=1))
    return row


if __name__ == "__main__":
    p = Parser(__doc__)
    p.add_argument("url")
    p.add_argument("--from", dest="start", type=int, default=0)
    p.add_argument("--find")
    p.add_argument("--text-file")
    p.add_argument("--title")
    a = p.parse_args()
    src = save(a.url, open(a.text_file, encoding="utf-8").read() if a.text_file else None, a.title)
    text = source_text(src)
    out = {"source": src["id"], "title": src["title"], "chars": len(text)}
    for key in ("pinned", "text_from", "open_copy", "same_work_as"):
        if src.get(key):
            out[key] = src[key]
    if src.get("withdrawn") or src.get("retracted"):
        out["warning"] = "this paper was withdrawn or retracted; it cannot be cited"
    if src.get("text_from") == "abstract only":
        out["warning"] = "only the abstract could be read; quote only from it"
    if a.find:
        lines = text.splitlines()
        out["matches"] = [{"line": i + 1, "text": " ".join(lines[max(0, i - 1):i + 2])}
                          for i, line in enumerate(lines) if re.search(a.find, line, re.I)][:20]
    else:
        out["text"] = text[a.start:a.start + CHUNK]
        if a.start + CHUNK < len(text):
            out["more"] = f"--from {a.start + CHUNK}"
    finish(out)
