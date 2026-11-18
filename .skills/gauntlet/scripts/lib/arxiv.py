"""arXiv: metadata from the arXiv API, full text pinned to one version.

Quotes must point at the exact text they came from, and arXiv papers change between
versions, so a paper read without a version is pinned to the version current at the time.
Full text comes from arXiv's HTML version when it exists, then the PDF (needs pypdf),
and otherwise the abstract alone, which is marked as such.
"""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

from . import web
from .identity import arxiv_id

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def parse_feed(xml: bytes) -> list[dict[str, Any]]:
    """Entries of an arXiv API Atom feed (error entries are skipped)."""
    out = []
    for e in ET.fromstring(xml).findall("a:entry", NS):
        found = arxiv_id(e.findtext("a:id", "", NS))
        if not found:
            continue  # the API reports errors as an entry without a paper id
        def text(path):
            return " ".join((e.findtext(path, "", NS) or "").split())
        out.append({"id": found[0], "version": found[1], "title": text("a:title"), "abstract": text("a:summary"),
                    "authors": [a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)],
                    "published": text("a:published")[:10], "doi": text("x:doi"), "comment": text("x:comment"),
                    "journal_ref": text("x:journal_ref"), "url": f"https://arxiv.org/abs/{found[0]}{found[1]}"})
    return out


def metadata(paper: str) -> dict[str, Any]:
    entries = parse_feed(web.get(f"{API}?id_list={urllib.parse.quote(paper)}")[0])
    if not entries:
        raise web.FetchError(f"arXiv has no paper {paper}")
    return entries[0]


def search(query: str, n: int = 10) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"search_query": f"all:{query}", "max_results": n, "sortBy": "relevance"})
    return parse_feed(web.get(f"{API}?{params}")[0])


def read(paper: str, version: str = "") -> tuple[str, dict[str, Any]]:
    """(text, metadata) for one pinned version of a paper."""
    meta = metadata(paper)
    meta["version"] = version or meta["version"]
    pinned = f"{paper}{meta['version']}"
    meta["url"] = f"https://arxiv.org/abs/{pinned}"
    meta["withdrawn"] = "withdrawn" in meta["comment"].lower()
    for url, kind in ((f"https://arxiv.org/html/{pinned}", "html"), (f"https://arxiv.org/pdf/{pinned}", "pdf")):
        try:
            text = web.page(url)[0]
        except web.FetchError:
            continue
        if len(text) > 2000:
            meta["text_from"] = kind
            return text, meta
    meta["text_from"] = "abstract only"
    return f"{meta['title']}\n\n{meta['abstract']}", meta
