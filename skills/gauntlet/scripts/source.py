#!/usr/bin/env python3
"""Fetch a page and keep an exact copy; quotes are later checked against this copy.

  source.py PROJECT URL                    first 8000 characters of the saved text
  source.py PROJECT URL --from 8000        the next part
  source.py PROJECT URL --find REGEX       matching lines, to copy quotes word for word
  source.py PROJECT URL --text-file F      save text you read yourself, for a page Gauntlet cannot fetch
"""
import argparse
import re

from gauntlet.cli import fail, finish
from gauntlet.fetch import FetchError
from gauntlet.store import Project

CHUNK = 8000

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("project"); p.add_argument("url")
p.add_argument("--from", dest="start", type=int, default=0)
p.add_argument("--find"); p.add_argument("--text-file")
a = p.parse_args()

project = Project(a.project)
try:
    page = open(a.text_file, encoding="utf-8").read() if a.text_file else None
    src = project.source(a.url, page)
except FetchError as e:
    fail(f"unreadable, so it cannot be cited: {e}. If you can read the page, save it with --text-file.", 1)
text = project.text(src)
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
