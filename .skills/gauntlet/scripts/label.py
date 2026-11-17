#!/usr/bin/env python3
"""Give a claim a label; refused, with what is missing, unless the evidence earns it.

  label.py CLAIM_ID LABEL

Claims from sources: established (2+ independent sources agree), reported (one source),
contested (quotes on both sides). Ideas: tested (support test passed on held-out seeds and
an independent replication agrees), refuted (a run failed), untested.
"""
import sys

from common import LABELS, NAMES, fail, finish, get_claim, put_claim, unmet

if sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    sys.exit(0)
if len(sys.argv) != 3 or sys.argv[2] not in LABELS:
    fail(f"usage: label.py CLAIM_ID LABEL, where LABEL is one of {', '.join(LABELS)}")
claim, label = get_claim(sys.argv[1]), sys.argv[2]
missing = unmet(claim)[label]
if missing:
    finish({"id": claim["id"], "refused": label, "label": NAMES[claim["label"]], "missing": missing}, 1)
claim["label"] = label
put_claim(claim)
finish({"id": claim["id"], "label": NAMES[label]})
