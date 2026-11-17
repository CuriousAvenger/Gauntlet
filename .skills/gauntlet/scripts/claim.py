#!/usr/bin/env python3
"""Record a claim or an idea. Reads one JSON object on stdin:

  claim from sources:  {"statement": "...", "quotes": [{"url": "...", "quote": "exact words", "disagrees": false}]}
  new idea:            {"statement": "...", "settling_test": "the test that would settle it"}
  more quotes:         {"add_to": "C3", "quotes": [...]}

  claim.py <<'EOF'
  {...}
  EOF

Quotes are checked word for word against Gauntlet's saved copy of each URL (fetched if
needed), and every number in the statement must appear in a quote. Problems are returned
so they can be fixed now; the claim stays pending until a referee labels it.
"""
import json
import sys

from lib.checks import number_problems, quote_problems
from lib.cli import fail, finish
from lib.fetch import FetchError
from lib.store import Project

if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    print(__doc__)
    sys.exit(0)

if len(sys.argv) != 1:
    fail("usage: claim.py < request.json")
project = Project()
try:
    req = json.load(sys.stdin)
except json.JSONDecodeError as e:
    fail(f"stdin is not valid JSON: {e}")

quotes = []
for q in req.get("quotes", []):
    if not q.get("url") or not q.get("quote"):
        fail("each quote needs a url and a quote")
    try:
        src = project.source(q["url"])
    except FetchError as e:
        fail(f"{q['url']} is unreadable ({e}); it cannot be cited", 1)
    quotes.append({"source": src["id"], "url": q["url"], "quote": q["quote"].strip(), "disagrees": bool(q.get("disagrees"))})

if req.get("add_to"):
    try:
        claim = project.claim(req["add_to"])
    except KeyError as e:
        fail(str(e))
    claim["quotes"] += quotes
elif req.get("settling_test"):
    claim = {"id": project.next_id("I"), "statement": req.get("statement", "").strip(), "quotes": quotes,
             "settling_test": req["settling_test"].strip(), "tests": [], "label": "untested"}
elif quotes:
    claim = {"id": project.next_id("C"), "statement": req.get("statement", "").strip(), "quotes": quotes,
             "tests": [], "label": "pending"}
else:
    fail("give quotes (a claim from sources), settling_test (an idea), or add_to with quotes")
if not claim["statement"]:
    fail("the statement is empty")
project.put(claim)
problems = quote_problems(project, claim) + number_problems(project, claim)
finish({"id": claim["id"], "label": claim["label"], **({"fix": problems} if problems else {})})
