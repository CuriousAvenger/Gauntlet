#!/usr/bin/env python3
"""Re-check every label, then write report.md around your answer.

  report.py --answer answer.md [--high-stakes] [--draft]

The title is the question in AGENTS.md (or pass --question). Cite claims in the answer as
[C3] or [C3, C7]. Refused if the answer cites a claim with no label or an idea that is not
tested, or states a number without citing a claim. --draft writes it anyway, marked as a
draft. --high-stakes adds a not-advice notice.
"""
import argparse
import re

from common import NAMES, ROOT, claims, fail, finish, question, reaudit, sources, write_file

CITE = re.compile(r"\[((?:[CI]\d+)(?:\s*,\s*[CI]\d+)*)\]")
MEANINGS = {"established": "Independent sources agree", "reported": "One source says so",
            "contested": "Sources disagree", "tested": "Proposed here, passed a test",
            "refuted": "Proposed here, failed a test", "untested": "Proposed here, not tested"}


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
    out += section("New ideas", ("tested", "refuted", "untested"),
                   lambda c: f"\n  - Would be settled by: {c['settling_test']}" if c["label"] == "untested" else "")

    out += ["## What was not checked", ""]
    pending = [c["id"] for c in rows if c["label"] == "pending"]
    if pending:
        out.append(f"- Claims that earned no label, left out above: {', '.join(pending)}.")
    out += [f"- {s['id']} could not be read ({s['reason']}): {s['url']}" for s in srcs if s["status"] != "read"]
    out += [f"- {s['id']} was supplied by the agent, not fetched by Gauntlet." for s in srcs if s.get("supplied_by_agent")]
    out += [f"- {ch['id']} moved from {NAMES[ch['from']]} to {NAMES[ch['to']]} when re-checked." for ch in changes]
    out += ["- Gauntlet checks that quotes exist word for word and that numbers trace to evidence; whether a quote "
            "supports its claim is the referee's judgement.",
            "- Anything absent was not found in the sources read, which does not mean it does not exist.", ""]

    out += ["## Evidence", ""]
    for c in rows:
        out += [f"**{c['id']}** ({NAMES[c['label']]}) {c['statement']}", ""]
        out += [f"- {q['source']}{' (disagrees)' if q.get('disagrees') else ''}: \"{q['quote']}\"" for q in c["quotes"]]
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


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
