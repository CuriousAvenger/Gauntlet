#!/usr/bin/env python3
"""Record a claim or an idea. Reads one JSON object on stdin:

  claim from sources:  {"statement": "...", "quotes": [{"url": "...", "quote": "exact words", "disagrees": false}]}
  new idea:            {"statement": "...", "settling_test": "the test that would settle it"}
  more quotes:         {"add_to": "C3", "quotes": [...]}

  claim.py <<'EOF'
  {...}
  EOF

Read each URL with source.py first. Quotes are checked word for word against the saved copy,
and every number in the statement must appear in a quote. Problems come back under "fix";
the claim stays pending until a referee labels it.
"""
import json
import sys

from common import claims, fail, finish, get_claim, number_problems, put_claim, quote_problems, sources

if sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    sys.exit(0)
try:
    req = json.load(sys.stdin)
except json.JSONDecodeError as e:
    fail(f"stdin is not valid JSON: {e}")

index, quotes = sources(), []
for q in req.get("quotes", []):
    src = index.get(q.get("url"))
    if not q.get("quote"):
        fail("each quote needs a url and a quote")
    if not src:
        fail(f"read {q.get('url')} with source.py first, then quote from it", 1)
    if src["status"] != "read":
        fail(f"{q['url']} could not be read ({src['reason']}), so it cannot be cited", 1)
    quotes.append({"source": src["id"], "url": q["url"], "quote": q["quote"].strip(), "disagrees": bool(q.get("disagrees"))})


def new_id(prefix):
    return f"{prefix}{1 + sum(c['id'].startswith(prefix) for c in claims())}"


if req.get("add_to"):
    claim = get_claim(req["add_to"])
    claim["quotes"] += quotes
elif req.get("settling_test"):
    claim = {"id": new_id("I"), "statement": req.get("statement", "").strip(), "quotes": quotes,
             "settling_test": req["settling_test"].strip(), "tests": [], "label": "untested"}
elif quotes:
    claim = {"id": new_id("C"), "statement": req.get("statement", "").strip(), "quotes": quotes,
             "tests": [], "label": "pending"}
else:
    fail("give quotes (a claim from sources), settling_test (an idea), or add_to with quotes")
if not claim["statement"]:
    fail("the statement is empty")
put_claim(claim)
problems = quote_problems(claim) + number_problems(claim)
finish({"id": claim["id"], "label": claim["label"], **({"fix": problems} if problems else {})})
