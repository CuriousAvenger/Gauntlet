"""Fetching web pages as plain text (HTML, plain text, or PDF if pypdf is installed)."""
from __future__ import annotations

import io
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = "gauntlet/1.0 (research template)"


class FetchError(Exception):
    pass


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article", "blockquote", "pre", "td"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.meta, self._skip, self._in_title = [], "", {}, 0, False

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            a = dict(attrs)
            name = (a.get("name") or "").lower()
            if name.startswith("citation_") and a.get("content") and name not in self.meta:
                self.meta[name] = a["content"].strip()
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


def get(url: str, timeout: int = 60) -> tuple[bytes, str]:
    """Raw bytes and content type. Raises FetchError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(MAX_BYTES), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}" + (" (likely paywalled)" if e.code in (401, 402, 403) else "")) from e
    except urllib.error.URLError as e:
        raise FetchError(f"could not reach {url}: {e.reason}") from e


def html_to_text(html: str) -> tuple[str, str, dict[str, str]]:
    """(text, title, citation_* meta tags) from an HTML page."""
    parser = _Text()
    parser.feed(html)
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))).strip()
    return text, parser.title.strip(), parser.meta


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # optional
    except ImportError as e:
        raise FetchError("PDF needs the optional pypdf package; pass the text instead") from e
    return "\n\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


def page(url: str) -> tuple[str, str, dict[str, str]]:
    """(text, title, citation_* meta tags) for any URL. Raises FetchError, including for paywalls."""
    data, ctype = get(url)
    if "pdf" in ctype or data[:5] == b"%PDF-":
        return pdf_to_text(data), "", {}
    m = re.search(r"charset=([\w-]+)", ctype)
    raw = data.decode(m.group(1) if m else "utf-8", errors="replace")
    if "html" not in ctype and not raw.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        return raw, "", {}
    text, title, meta = html_to_text(raw)
    if len(text) < 500 and re.search(r"subscribe|purchase|log in to|get access", text, re.I):
        raise FetchError("page looks like a paywall")
    if not text:
        raise FetchError("no text could be extracted")
    return text, meta.get("citation_title") or title, meta
