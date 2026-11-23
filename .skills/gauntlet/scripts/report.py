#!/usr/bin/env python3
"""Re-check every label, then write report.md around your answer.

  report.py --answer answer.md [--high-stakes] [--draft]

The title is the question in AGENTS.md (or pass --question). Cite claims in the answer as
[C3] or [C3, C7]. Refused if the answer cites a claim with no label or an idea that is not
tested, or states a number without citing a claim. --draft writes it anyway, marked as a
draft. --high-stakes adds a not-advice notice.
"""
from __future__ import annotations

import re

from claim import claims
from label import NAMES, reaudit
from rank import diverse_top, ratings
from source import ROOT, Parser, fail, finish, sources, write_file

FRONTIER = 5
CITE = re.compile(r"\[((?:[CI]\d+)(?:\s*,\s*[CI]\d+)*)\]")
MEANINGS = {"established": "Independent sources agree", "reported": "One source says so",
            "contested": "Sources disagree", "tested": "Proposed here, passed a test",
            "refuted": "Proposed here, failed a test", "untested": "Proposed here, not tested"}


def question() -> str:
    """The first line under '## Question' in AGENTS.md, unless it is still the placeholder."""
    path = ROOT / "AGENTS.md"
    match = re.search(r"^## Question\s*$(.*?)(?=^## |\Z)", path.read_text(), re.M | re.S) if path.exists() else None
    text = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.S) if match else ""
    line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return "" if line == "Write your research question here." else line


def answer_problems(answer, by_id):
    problems = []
    for match in CITE.finditer(answer):
        for cid in re.split(r"\s*,\s*", match.group(1)):
            c = by_id.get(cid)
            if c is None:
                problems.append(f"cites {cid}, which does not exist")
            elif c["label"] == "pending":
                problems.append(f"cites {cid}, which has no label")
            elif c["label"] in ("refuted", "untested"):
                problems.append(f"cites {cid} ({NAMES[c['label']]}); the answer may cite only tested ideas")
    for para in re.split(r"\n\s*\n", answer):
        if re.search(r"(?<![\w.])\d", CITE.sub("", para)) and not CITE.search(para):
            problems.append(f"a paragraph states a number without citing a claim: {para.strip()[:70]!r}")
    return problems


def render(title, answer, rows, changes, high_stakes, problems):
    by_id = {c["id"]: c for c in rows}

    def cited(match):
        return "[" + "; ".join(f"{i} · {NAMES[by_id[i]['label']]}" if i in by_id else i
                               for i in re.split(r"\s*,\s*", match.group(1))) + "]"

    def section(heading, labels, extra=lambda c: ""):
        lines = [f"## {heading}", ""]
        for label in labels:
            group = [c for c in rows if c["label"] == label]
            if group:
                lines += [f"### {NAMES[label]}", ""] + [f"- **{c['id']}** {c['statement']}{extra(c)}" for c in group] + [""]
        return lines if len(lines) > 2 else lines + ["None.", ""]

    srcs = list(sources().values())
    out = [f"# {title}", ""]
    if problems:
        out += ["> **Draft: this report failed its checks** (listed at the end).", ""]
    if high_stakes:
        out += ["> **This is research, not advice.** It is not medical, legal or financial advice.", ""]
    out += ["| Label | Meaning |", "|---|---|"] + [f"| {NAMES[k]} | {v} |" for k, v in MEANINGS.items()]
    out += ["", "## Answer", "", CITE.sub(cited, answer.strip()), ""]
    out += section("Findings", ("established", "reported", "contested"),
                   lambda c: f" _({', '.join(q['source'] for q in c['quotes'])})_")
    elo, _ = ratings()
    out += section("New ideas", ("tested", "refuted", "untested"),
                   lambda c: f" _(Elo {round(elo[c['id']])})_" if c["id"] in elo else "")

    frontier = [by_id[r["id"]] for r in diverse_top(FRONTIER) if r["label"] == "untested"]
    out += ["## Frontier", "", "The strongest untested ideas, one per cluster of similar ideas, with the closest "
            "work found in the sources read. Each is a lead, not a finding.", ""]
    for c in frontier:
        out += [f"### {c['id']}: {c['statement']}", ""]
        out += [f"- Closest prior work: {q['source']}, \"{q['quote']}\"" for q in c.get("prior_work", [])]
        out += [f"- What it adds: {c.get('difference', '')}", f"- Would be settled by: {c['settling_test']}", ""]
    if not frontier:
        out += ["None.", ""]

    out += ["## What was not checked", ""]
    pending = [c["id"] for c in rows if c["label"] == "pending"]
    if pending:
        out.append(f"- Claims that earned no label, left out above: {', '.join(pending)}.")
    out += [f"- {s['id']} could not be read ({s['reason']}): {s['url']}" for s in srcs if s["status"] != "read"]
    out += [f"- {s['id']} was supplied by the agent, not fetched by Gauntlet." for s in srcs if s.get("supplied_by_agent")]
    out += [f"- {ch['id']} moved from {NAMES[ch['from']]} to {NAMES[ch['to']]} when re-checked: {ch['why']}."
            for ch in changes]
    out += ["- Gauntlet checks that quotes exist word for word and that numbers trace to evidence; whether a quote "
            "supports its claim is the referee's judgement.",
            "- Anything absent was not found in the sources read, which does not mean it does not exist.", ""]

    out += ["## Evidence", ""]
    for c in rows:
        out += [f"**{c['id']}** ({NAMES[c['label']]}) {c['statement']}", ""]
        out += [f"- {q['source']}{' (disagrees)' if q.get('disagrees') else ''}: \"{q['quote']}\"" for q in c["quotes"]]
        out += [f"- Prior work, {q['source']}: \"{q['quote']}\"" for q in c.get("prior_work", [])]
        if c.get("difference"):
            out.append(f"- Difference claimed: {c['difference']}")
        for t in c["tests"]:
            seeds = ", ".join(f"{r['seed']}{'*' if r['held_out'] else ''} "
                              f"{'pass' if r['pass'] else 'fail' if r['pass'] is False else 'error'}" for r in t["runs"])
            out.append(f"- {t['id']} ({t['role']}): {seeds}  (* = held-out seed)")
        out.append("")
    out += ["| Source | Title | URL |", "|---|---|---|"]
    out += [f"| {s['id']} | {s.get('title', '')} | {s['url']} |" for s in srcs if s["status"] == "read"]
    if problems:
        out += ["", "## Check failures", ""] + [f"- {p}" for p in problems]
    return "\n".join(out) + "\n"


def main() -> None:
    p = Parser(__doc__)
    p.add_argument("--answer", required=True)
    p.add_argument("--question")
    p.add_argument("--high-stakes", action="store_true")
    p.add_argument("--draft", action="store_true")
    a = p.parse_args()

    title = a.question or question()
    if not title:
        fail("write the question under '## Question' in AGENTS.md (or pass --question)")
    answer = open(a.answer, encoding="utf-8").read()
    changes = reaudit()
    rows = claims()
    problems = answer_problems(answer, {c["id"]: c for c in rows})
    if problems and not a.draft:
        finish({"refused": "report not written", "fix": problems}, 1)
    write_file(ROOT / "report.md", render(title, answer, rows, changes, a.high_stakes, problems))
    finish({"report": str(ROOT / "report.md"), **({"draft_problems": problems} if problems else {})})


if __name__ == "__main__":
    main()
