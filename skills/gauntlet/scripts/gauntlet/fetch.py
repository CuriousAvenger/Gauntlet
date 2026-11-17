"""Download a page and return its plain text (HTML, plain text, or PDF if pypdf is installed)."""

from __future__ import annotations

import io
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

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
