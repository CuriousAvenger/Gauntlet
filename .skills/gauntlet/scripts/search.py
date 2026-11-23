#!/usr/bin/env python3
"""Search the literature beyond the sources already read: to find the closest prior work for
an idea, or papers in another field to borrow from.

  search.py "QUERY" [--n 10] [--where arxiv|openalex|all]

arXiv needs no key; OpenAlex (journals in every field) needs a free API key in
$OPENALEX_API_KEY and is skipped without one. Results are cached in sources/search_cache/.
A result is only a lead: read it with source.py before quoting it.
"""
import argparse

from lib.identity import keys, same_work
from lib.search import search
from source import ROOT, Parser, finish, sources

p = Parser(__doc__)
p.add_argument("query")
p.add_argument("--n", type=int, default=10)
p.add_argument("--where", choices=("arxiv", "openalex", "all"), default="all")
a = p.parse_args()

found = search(a.query, a.n, a.where, ROOT / "sources" / "search_cache")
read = [s for s in sources().values() if s["status"] == "read"]
for r in found["results"]:
    r["abstract"] = r["abstract"][:600]
    me = {"ids": keys(r["url"], {"citation_doi": r.get("doi", "")}), "title": r["title"], "url": r["url"]}
    hit = next((s["id"] for s in read if same_work(me, s)), None)
    if hit:
        r["already_read_as"] = hit
finish(found, 0 if found["results"] or not found["unavailable"] else 1)
