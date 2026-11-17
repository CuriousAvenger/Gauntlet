"""Capturing sources. Gauntlet fetches and saves the text itself where it can,
so the quote check compares against what the source actually says rather than
against an agent's copy of it."""

from __future__ import annotations

import io
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "gauntlet-research/0.1 (+https://github.com/curiousavenger/gauntlet)"
MAX_BYTES = 25 * 1024 * 1024
SOURCE_KINDS = (
    "peer-reviewed", "preprint", "systematic-review", "meta-analysis", "guideline", "official",
    "official-docs", "standard", "textbook", "survey", "reference", "primary", "dataset",
    "repository", "news", "blog", "other",
)


class FetchError(Exception):
    def __init__(self, msg: str, paywalled: bool = False):
        super().__init__(msg)
        self.paywalled = paywalled


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "button"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section",
             "article", "blockquote", "pre", "dd", "dt", "figcaption", "td", "th"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip(), p.title.strip()


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError as e:
        raise FetchError("PDF needs the optional 'pypdf' package (pip install 'gauntlet[pdf]'), "
                         "or save the text yourself and use --file") from e
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()


_PAYWALL_HINTS = ("purchase this article", "buy article", "subscribe to read", "log in to access",
                  "access through your institution", "get access", "rent this article")


def fetch(url: str, timeout: int = 60) -> tuple[str, str]:
    """Fetch a URL and return (text, title). Raises FetchError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} for {url}", paywalled=e.code in (401, 402, 403)) from e
    except urllib.error.URLError as e:
        raise FetchError(f"could not reach {url}: {e.reason}") from e
    if len(data) > MAX_BYTES:
        raise FetchError(f"source larger than {MAX_BYTES // (1024 * 1024)} MB")
    if "pdf" in ctype or data[:5] == b"%PDF-":
        text, title = pdf_to_text(data), ""
    else:
        charset = "utf-8"
        m = re.search(r"charset=([\w-]+)", ctype)
        if m:
            charset = m.group(1)
        raw = data.decode(charset, errors="replace")
        if "html" in ctype or raw.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            text, title = html_to_text(raw)
        else:
            text, title = raw, ""
    if len(text) < 500 and any(h in text.lower() for h in _PAYWALL_HINTS):
        raise FetchError("page looks like a paywall; listed as unread", paywalled=True)
    if not text.strip():
        raise FetchError("no text could be extracted")
    return text, title
