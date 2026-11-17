#!/usr/bin/env python3
"""Read a source. Gauntlet fetches the page itself and keeps an exact copy; quotes are later
checked word for word against this copy.

  source.py URL                    first 8000 characters of the saved text
  source.py URL --from 8000        the next part
  source.py URL --find REGEX       matching lines, to copy quotes word for word
  source.py URL --text-file F      save text you read yourself, for a page Gauntlet cannot fetch
"""
from __future__ import annotations

import argparse
import io
import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

from common import INDEX, ROOT, fail, finish, sha256, source_text, sources, write_file

CHUNK = 8000
MAX_BYTES = 25 * 1024 * 1024


class FetchError(Exception):
    pass


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article", "blockquote", "pre", "td"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        self._skip += tag in self.SKIP
        self._in_title |= tag == "title"
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        self._skip -= tag in self.SKIP and self._skip > 0
        self._in_title &= tag != "title"
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def fetch(url: str, timeout: int = 60) -> tuple[str, str]:
    """Return (text, title). Raises FetchError, including for paywalls."""
    req = urllib.request.Request(url, headers={"User-Agent": "gauntlet/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype, data = resp.headers.get("Content-Type", ""), resp.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}" + (" (likely paywalled)" if e.code in (401, 402, 403) else "")) from e
    except urllib.error.URLError as e:
        raise FetchError(f"could not reach {url}: {e.reason}") from e
    if "pdf" in ctype or data[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader  # optional
        except ImportError as e:
            raise FetchError("PDF needs the optional pypdf package; pass the text instead") from e
        return "\n\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages), ""
    m = re.search(r"charset=([\w-]+)", ctype)
    raw = data.decode(m.group(1) if m else "utf-8", errors="replace")
    if "html" not in ctype and not raw.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        return raw, ""
    parser = _Text()
    parser.feed(raw)
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))).strip()
    if len(text) < 500 and re.search(r"subscribe|purchase|log in to|get access", text, re.I):
        raise FetchError("page looks like a paywall")
    if not text:
        raise FetchError("no text could be extracted")
    return text, parser.title.strip()


def save(url: str, page_text: str | None) -> dict:
    """Saved copy of `url`, fetching it on first use; failures are recorded as unreadable."""
    index = sources()
    src = index.get(url)
    if src and src["status"] == "read":
        return src
    if src and page_text is None:
        fail(f"unreadable, so it cannot be cited: {src['reason']}. If you can read it, use --text-file.", 1)
    sid = src["id"] if src else f"S{len(index) + 1}"
    try:
        text, title = (page_text, "") if page_text is not None else fetch(url)
    except FetchError as e:
        index[url] = {"id": sid, "url": url, "status": "unreadable", "reason": str(e)}
        write_file(INDEX, json.dumps(index, indent=1))
        fail(f"unreadable, so it cannot be cited: {e}. If you can read the page, use --text-file.", 1)
    write_file(ROOT / "sources" / f"{sid}.txt", text)
    index[url] = {"id": sid, "url": url, "title": title or url, "status": "read", "file": f"sources/{sid}.txt",
                  "sha256": sha256(ROOT / "sources" / f"{sid}.txt"), "supplied_by_agent": page_text is not None}
    write_file(INDEX, json.dumps(index, indent=1))
    return index[url]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--from", dest="start", type=int, default=0)
    p.add_argument("--find")
    p.add_argument("--text-file")
    a = p.parse_args()
    src = save(a.url, open(a.text_file, encoding="utf-8").read() if a.text_file else None)
    text = source_text(src)
    out = {"source": src["id"], "title": src["title"], "chars": len(text)}
    if a.find:
        lines = text.splitlines()
        out["matches"] = [{"line": i + 1, "text": " ".join(lines[max(0, i - 1):i + 2])}
                          for i, line in enumerate(lines) if re.search(a.find, line, re.I)][:20]
    else:
        out["text"] = text[a.start:a.start + CHUNK]
        if a.start + CHUNK < len(text):
            out["more"] = f"--from {a.start + CHUNK}"
    finish(out)
