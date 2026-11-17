"""Build report.md around the writer's answer. Every label is re-audited first; the findings,
ideas, what was not checked and the evidence come from the records, not from the model."""

from __future__ import annotations

import re
from typing import Any

from .checks import MEANINGS, NAMES, reaudit
from .store import write_file

CITE = re.compile(r"\[((?:[CI]\d+)(?:\s*,\s*[CI]\d+)*)\]")
NOT_ADVICE = "**This is research, not advice.** It is not medical, legal or financial advice."


def answer_problems(answer: str, claims: dict[str, dict[str, Any]]) -> list[str]:
    problems = []
    for match in CITE.finditer(answer):
        for cid in re.split(r"\s*,\s*", match.group(1)):
            c = claims.get(cid)
            if c is None:
                problems.append(f"cites {cid}, which does not exist")
            elif c["label"] == "pending":
                problems.append(f"cites {cid}, which has no label")
            elif c["label"] in ("refuted", "untested"):
                problems.append(f"cites {cid} ({NAMES[c['label']]}); the answer may cite only tested ideas")
    for para in re.split(r"\n\s*\n", answer):
        if re.search(r"(?<![\w.])\d", CITE.sub("", para)) and not CITE.search(para) and not para.lstrip().startswith("#"):
            problems.append(f"a paragraph states a number without citing a claim: {para.strip()[:70]!r}")
    return problems


def build(project, question: str, answer: str, high_stakes: bool = False, draft: bool = False) -> list[str]:
    """Write report.md and return the problems with the answer. With problems and no
    `draft`, nothing is written."""
    changes = reaudit(project)
    claims = project.claims()
    by_id = {c["id"]: c for c in claims}
    problems = answer_problems(answer, by_id)
    if problems and not draft:
        return problems

    def cited(match):
        return "[" + "; ".join(f"{i} · {NAMES[by_id[i]['label']]}" if i in by_id else i
                               for i in re.split(r"\s*,\s*", match.group(1))) + "]"

    def section(title, labels, extra=lambda c: ""):
        lines = []
        for label in labels:
            group = [c for c in claims if c["label"] == label]
            if group:
                lines += [f"### {NAMES[label]}", ""] + [f"- **{c['id']}** {c['statement']}{extra(c)}" for c in group] + [""]
        return [f"## {title}", ""] + (lines or ["None.", ""])

    sources = list(project.sources().values())
    out = [f"# {question}", ""]
    if draft and problems:
        out += ["> **Draft: this report failed its checks** (listed at the end).", ""]
    if high_stakes:
        out += [f"> {NOT_ADVICE}", ""]
    out += ["| Label | Meaning |", "|---|---|"] + [f"| {NAMES[k]} | {v} |" for k, v in MEANINGS.items()]
    out += ["", "## Answer", "", CITE.sub(cited, answer.strip()), ""]
    out += section("Findings", ("established", "reported", "contested"),
                   lambda c: f" _({', '.join(q['source'] for q in c['quotes'])})_")
    out += section("New ideas", ("tested", "refuted", "untested"),
                   lambda c: f"\n  - Would be settled by: {c['settling_test']}" if c["label"] == "untested" else "")

    out += ["## What was not checked", ""]
    pending = [c["id"] for c in claims if c["label"] == "pending"]
    if pending:
        out.append(f"- Claims that earned no label, left out above: {', '.join(pending)}.")
    out += [f"- {s['id']} could not be read ({s['reason']}): {s['url']}" for s in sources if s["status"] != "read"]
    out += [f"- {s['id']} was supplied by the agent, not fetched by Gauntlet." for s in sources if s.get("supplied_by_agent")]
    out += [f"- {ch['id']} moved from {NAMES[ch['from']]} to {NAMES[ch['to']]} when re-checked." for ch in changes]
    out += ["- Gauntlet checks that quotes exist word for word and that numbers trace to evidence; whether a quote "
            "supports its claim is the referee's judgement.",
            "- Anything absent was not found in the sources read, which does not mean it does not exist.", ""]

    out += ["## Evidence", ""]
    for c in claims:
        out += [f"**{c['id']}** ({NAMES[c['label']]}) {c['statement']}", ""]
        out += [f"- {q['source']}{' (disagrees)' if q.get('disagrees') else ''}: \"{q['quote']}\"" for q in c["quotes"]]
        for t in c["tests"]:
            seeds = ", ".join(f"{r['seed']}{'*' if r['held_out'] else ''} "
                              f"{'pass' if r['pass'] else 'fail' if r['pass'] is False else 'error'}" for r in t["runs"])
            out.append(f"- {t['id']} ({t['role']}): {seeds}  (* = held-out seed)")
        out.append("")
    out += ["| Source | Title | URL |", "|---|---|---|"]
    out += [f"| {s['id']} | {s.get('title', '')} | {s['url']} |" for s in sources if s["status"] == "read"]
    if draft and problems:
        out += ["", "## Check failures", ""] + [f"- {p}" for p in problems]
    write_file(project.report_path, "\n".join(out) + "\n")
    return problems
