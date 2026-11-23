"""Source identity, the arXiv reader and literature search. The services are replaced by
recorded sample responses, so these tests run offline."""
import json

import pytest
from conftest import PAGE, QUOTE

from lib import arxiv, identity, search, web

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2106.09685v2</id>
    <published>2021-06-17T17:37:18Z</published>
    <title>LoRA: Low-Rank Adaptation of
      Large Language Models</title>
    <summary>  An important paradigm of natural language processing.  </summary>
    <author><name>Edward J. Hu</name></author>
    <author><name>Yelong Shen</name></author>
    <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1234/example.5678</arxiv:doi>
    <arxiv:comment xmlns:arxiv="http://arxiv.org/schemas/atom">Draft V2</arxiv:comment>
    <link href="http://arxiv.org/abs/2106.09685v2" rel="alternate" type="text/html"/>
  </entry>
  <entry><id>http://arxiv.org/api/errors#incorrect_id</id><title>Error</title></entry>
</feed>"""

OPENALEX = {"results": [{
    "display_name": "Predicting many properties of a quantum system from very few measurements",
    "publication_year": 2020, "doi": "https://doi.org/10.1038/s41567-020-0932-7", "is_retracted": False,
    "abstract_inverted_index": {"Predicting": [0], "properties": [2], "many": [1]},
    "authorships": [{"author": {"display_name": "Hsin-Yuan Huang"}}],
    "primary_location": {"landing_page_url": "https://www.nature.com/articles/s41567-020-0932-7"},
    "open_access": {"is_oa": True, "oa_url": "https://arxiv.org/pdf/2002.08953"}}]}


def test_identity_keys():
    assert identity.keys("https://arxiv.org/pdf/2106.09685v3.pdf") == ["arxiv:2106.09685"]
    assert identity.keys("https://doi.org/10.48550/arXiv.2106.09685") == ["arxiv:2106.09685"]
    assert identity.keys("https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.1",
                         {"citation_arxiv_id": "2106.09685"}) == ["arxiv:2106.09685", "doi:10.1103/physrevlett.1"]
    a = {"ids": [], "title": "Efficient readout of linear systems", "url": "u1"}
    b = {"ids": [], "title": "Efficient Readout of Linear Systems", "url": "u2"}
    assert identity.same_work(a, b) and identity.count_works([a, b]) == 1


def test_parsers():
    paper = arxiv.parse_feed(FEED)
    assert len(paper) == 1  # the error entry is skipped
    assert paper[0] == {**paper[0], "id": "2106.09685", "version": "v2", "doi": "10.1234/example.5678",
                        "title": "LoRA: Low-Rank Adaptation of Large Language Models", "authors": ["Edward J. Hu", "Yelong Shen"],
                        "published": "2021-06-17", "url": "https://arxiv.org/abs/2106.09685v2"}
    work = search.parse_openalex(OPENALEX)[0]
    assert work["abstract"] == "Predicting many properties" and work["url"] == "https://arxiv.org/pdf/2002.08953"
    assert work["doi"] == "10.1038/s41567-020-0932-7" and work["authors"] == ["Hsin-Yuan Huang"]


def test_arxiv_read_pins_version_and_falls_back(monkeypatch):
    monkeypatch.setattr(web, "get", lambda url, timeout=60: (FEED, "application/atom+xml"))
    monkeypatch.setattr(web, "page", lambda url: ("Full text. " * 300, "", {}))
    text, meta = arxiv.read("2106.09685")
    assert meta["url"].endswith("2106.09685v2") and meta["text_from"] == "html" and text.startswith("Full text")
    text, meta = arxiv.read("2106.09685", "v1")
    assert meta["url"].endswith("2106.09685v1")

    def unreachable(url):
        raise web.FetchError("no html or pdf")
    monkeypatch.setattr(web, "page", unreachable)
    text, meta = arxiv.read("2106.09685")
    assert meta["text_from"] == "abstract only" and "important paradigm" in text


def test_search_is_cached_and_reports_missing_services(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(arxiv, "search", lambda q, n: arxiv.parse_feed(FEED))
    first = search.search("low rank", 5, "all", tmp_path)
    assert first["results"][0]["from"] == "arxiv" and "OPENALEX_API_KEY" in first["unavailable"]["openalex"]
    monkeypatch.setattr(arxiv, "search", lambda q, n: pytest.fail("should come from the cache"))
    assert search.search("low rank", 5, "all", tmp_path) == first


def test_two_versions_of_one_paper_are_one_source(run, tmp_path):
    (tmp_path / "page.txt").write_text(PAGE)
    run("source.py", "https://arxiv.org/abs/2106.09685v1", "--text-file", "page.txt")
    code, out = run("source.py", "https://arxiv.org/abs/2106.09685v2", "--text-file", "page.txt")
    assert out["same_work_as"] == ["S1"]
    cid = run("claim.py", stdin={"statement": "Shots fell 8.0-fold.", "quotes": [
        {"url": "https://arxiv.org/abs/2106.09685v1", "quote": QUOTE},
        {"url": "https://arxiv.org/abs/2106.09685v2", "quote": QUOTE}]})[1]["id"]
    code, out = run("label.py", cid, "established", "--reason", "test")
    assert code == 1 and "one work" in out["missing"][0]
    assert run("label.py", cid, "reported", "--reason", "test")[0] == 0
