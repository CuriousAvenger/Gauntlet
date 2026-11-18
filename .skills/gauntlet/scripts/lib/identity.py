"""Which saved sources are the same work, so one paper read twice (a preprint and its
journal version, or two arXiv versions) never counts as two independent sources."""
from __future__ import annotations

import re
from typing import Any

from .similarity import similarity

ARXIV = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv[:.]\s*)([a-z\-]+(?:\.[a-z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?",
                   re.I)
DOI = re.compile(r"(10\.\d{4,9}/[^\s\"'<>?#]+)", re.I)
SAME_TITLE = 0.9


def arxiv_id(text: str) -> tuple[str, str] | None:
    """(id without version, version or '') from an arXiv URL or 'arXiv:ID' text."""
    m = ARXIV.search(text)
    return (m.group(1).lower(), (m.group(2) or "").lower()) if m else None


def keys(url: str, meta: dict[str, str] | None = None) -> list[str]:
    """Identity keys for a source: arxiv:<id> and doi:<doi>, from its URL and page metadata."""
    meta = meta or {}
    found = set()
    for text in (url, meta.get("citation_arxiv_id", ""), meta.get("arxiv_id", "")):
        a = arxiv_id(text) or (arxiv_id("arxiv:" + text) if text else None)
        if a:
            found.add(f"arxiv:{a[0]}")
    for text in (url, meta.get("citation_doi", ""), meta.get("doi", "")):
        m = DOI.search(text)
        if m:
            doi = m.group(1).lower().rstrip(".,;)")
            a = arxiv_id(doi.replace("10.48550/arxiv.", "arxiv:"))  # arXiv's own DOIs name the preprint
            found.add(f"arxiv:{a[0]}" if doi.startswith("10.48550/") and a else f"doi:{doi}")
    return sorted(found)


def same_work(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if set(a.get("ids", [])) & set(b.get("ids", [])):
        return True
    ta, tb = a.get("title", ""), b.get("title", "")
    real = ta and tb and ta != a.get("url") and tb != b.get("url")
    return bool(real and similarity(ta, tb) >= SAME_TITLE)


def count_works(sources: list[dict[str, Any]]) -> int:
    """How many distinct works the given sources represent."""
    groups: list[list[dict[str, Any]]] = []
    for s in sources:
        joined = [g for g in groups if any(same_work(s, t) for t in g)]
        merged = [s] + [t for g in joined for t in g]
        groups = [g for g in groups if g not in joined] + [merged]
    return len(groups)
