#!/usr/bin/env python3
"""Re-check every label, then write report.md around your answer.

  report.py --answer answer.md [--high-stakes] [--draft]

The report's title is the question in AGENTS.md (or pass --question).

Cite claims in the answer as [C3] or [C3, C7]. Refused if the answer cites a claim with no
label or an idea that is not tested, or states a number without citing a claim. --draft
writes it anyway, marked as a draft. --high-stakes adds a not-advice notice.
"""
import argparse

from lib.cli import fail, finish
from lib.report import build
from lib.store import Project

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--answer", required=True); p.add_argument("--question")
p.add_argument("--high-stakes", action="store_true"); p.add_argument("--draft", action="store_true")
a = p.parse_args()

project = Project()
question = a.question or project.question()
if not question:
    fail("write the question under '## Question' in AGENTS.md (or pass --question)")
problems = build(project, question, open(a.answer, encoding="utf-8").read(), a.high_stakes, a.draft)
if problems and not a.draft:
    finish({"refused": "report not written", "fix": problems}, 1)
finish({"report": str(project.report_path), **({"draft_problems": problems} if problems else {})})
