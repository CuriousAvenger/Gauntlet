#!/usr/bin/env python3
"""Give a claim a label; refused, with what is missing, unless the evidence earns it.

  label.py PROJECT CLAIM_ID LABEL

Claims from sources: established (2+ independent sources agree), reported (one source),
contested (quotes on both sides). Ideas: tested (support test passed on held-out seeds and
an independent replication agrees), refuted (a run failed), untested.
"""
import sys

from lib.checks import LABELS, NAMES, unmet
from lib.cli import fail, finish
from lib.store import Project

if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    print(__doc__)
    sys.exit(0)

if len(sys.argv) != 4 or sys.argv[3] not in LABELS:
    fail(f"usage: label.py PROJECT CLAIM_ID LABEL, where LABEL is one of {', '.join(LABELS)}")
project, cid, label = Project(sys.argv[1]), sys.argv[2], sys.argv[3]
try:
    claim = project.claim(cid)
except KeyError as e:
    fail(str(e))
missing = unmet(project, claim)[label]
if missing:
    finish({"id": cid, "refused": label, "label": NAMES[claim["label"]], "missing": missing}, 1)
claim["label"] = label
project.put(claim)
finish({"id": cid, "label": NAMES[label]})
