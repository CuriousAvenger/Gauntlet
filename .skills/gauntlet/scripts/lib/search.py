"""Searching the scholarly literature beyond the sources already read: arXiv (no key
needed) and OpenAlex (needs a free API key in $OPENALEX_API_KEY). Results are cached, since
both services limit how often they can be called."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

from . import arxiv, web

OPENALEX = "https://api.openalex.org/works"


def _abstract(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex stores abstracts as word -> positions; rebuild the text."""
    if not inverted:
        return ""
    words = sorted((pos, word) for word, positions in inverted.items() for pos in positions)
    return " ".join(word for _, word in words)


def parse_openalex(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for w in data.get("results", []):
        loc = w.get("primary_location") or {}
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        url = (w.get("open_access") or {}).get("oa_url") or loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else "")
        out.append({"title": w.get("display_name") or w.get("title") or "", "abstract": _abstract(w.get("abstract_inverted_index")),
                    "authors": [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
                    "published": str(w.get("publication_year") or ""), "doi": doi, "url": url,
                    "open_access": bool((w.get("open_access") or {}).get("is_oa")),
                    "retracted": bool(w.get("is_retracted"))})
    return out


def openalex(query: str, n: int) -> list[dict[str, Any]]:
    key = os.environ.get("OPENALEX_API_KEY")
    if not key:
        raise web.FetchError("OpenAlex needs a free API key: set OPENALEX_API_KEY")
    params = urllib.parse.urlencode({"search": query, "per-page": n, "api_key": key})
    return parse_openalex(json.loads(web.get(f"{OPENALEX}?{params}")[0]))


def search(query: str, n: int, where: str, cache: Path) -> dict[str, Any]:
    """{"results": [...], "unavailable": {service: reason}}, from cache when possible."""
    path = cache / (hashlib.sha256(f"{where}|{n}|{query}".encode()).hexdigest()[:20] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    results, unavailable = [], {}
    for name, fn in (("arxiv", arxiv.search), ("openalex", openalex)):
        if where in (name, "all"):
            try:
                results += [{"from": name, **r} for r in fn(query, n)]
            except (web.FetchError, ValueError) as e:
                unavailable[name] = str(e)
    out = {"results": results, "unavailable": unavailable}
    if results:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1))
    return out
