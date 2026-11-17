"""Assemble report.md. The writer supplies only the plain-language answer; findings,
ideas, what was not checked and the appendix are generated from the records, after
every label has been re-audited, so nothing in the report outruns its evidence."""

from __future__ import annotations

import re
from typing import Any

from . import labels, testing
from .labels import DISPLAY, MEANING
from .util import atomic_write, now_iso

CITE = re.compile(r"\[((?:[CI]\d+)(?:\s*,\s*[CI]\d+)*)\]")
NOT_ADVICE = ("**This report is research, not advice.** It is not medical, legal or financial advice; "
              "consult a qualified professional.")


def answer_problems(answer: str, claims: dict[str, dict[str, Any]]) -> list[str]:
    problems = []
    for m in CITE.finditer(answer):
        for cid in re.split(r"\s*,\s*", m.group(1)):
            c = claims.get(cid)
            if c is None:
                problems.append(f"cites {cid}, which does not exist")
            elif c["label"] == "pending":
                problems.append(f"cites {cid}, which has not earned a label")
            elif c["kind"] == "idea" and c["label"] != "tested":
                problems.append(f"cites {cid} ({DISPLAY[c['label']]}); only tested ideas may appear in the answer")
    for para in re.split(r"\n\s*\n", answer):
        if re.search(r"(?<![\w.])\d", CITE.sub("", para)) and not CITE.search(para):
            problems.append(f"states a number without citing a claim: {para.strip()[:80]!r}")
    return problems


def _cite_with_label(answer: str, claims: dict[str, dict[str, Any]]) -> str:
    def sub(m):
        ids = re.split(r"\s*,\s*", m.group(1))
        return "[" + "; ".join(f"{i} · {DISPLAY[claims[i]['label']]}" for i in ids) + "]"
    return CITE.sub(sub, answer)


def write(project, answer: str, draft: bool = False) -> list[str]:
    """Re-audit, validate the answer and write report.md. Returns the problems; when
    there are any and draft is False, nothing is written."""
    changes = labels.reaudit(project)
    claims = project.claims()
    by_id = {c["id"]: c for c in claims}
    problems = answer_problems(answer, by_id)
    if problems and not draft:
        return problems
    state, sources = project.state(), project.sources()

    out = [f"# {state['question']}", "", f"_Gauntlet report · depth {state['depth']} · {now_iso()[:10]}_", ""]
    if draft and problems:
        out += ["> **DRAFT: failed report checks** (listed at the end). Do not share.", ""]
    if state["high_stakes"]:
        out += [f"> {NOT_ADVICE}", ""]
    out += ["Every claim carries a label showing the evidence behind it.", "", "| Label | Meaning |", "|---|---|"]
    out += [f"| {DISPLAY[k]} | {v} |" for k, v in MEANING.items()]
    out += ["", "## Answer", "", _cite_with_label(answer.strip(), by_id), "", "## Findings", ""]
    for lab in ("established", "reported", "contested"):
        group = [c for c in claims if c["label"] == lab]
        if group:
            out += [f"### {DISPLAY[lab]}", ""] + [
                f"- **{c['id']}** {c['statement']} _({', '.join(e['source_id'] for e in c['sources'])})_" for c in group] + [""]

    out += ["## New ideas", "", "Proposed during the research; only tested ideas appear in the answer.", ""]
    for lab in ("tested", "refuted", "untested"):
        group = [c for c in claims if c["label"] == lab]
        if group:
            out += [f"### {DISPLAY[lab]}", ""]
            for c in group:
                out.append(f"- **{c['id']}** {c['statement']}")
                if lab == "untested":
                    out.append(f"  - Test that would settle it: {c['settling_test']}")
            out.append("")

    pending = [c for c in claims if c["label"] == "pending"]
    unread = [s for s in sources if s["status"] != "read"]
    read = len(sources) - len(unread)
    out += ["## What was not checked", ""]
    if pending:
        out.append(f"- {len(pending)} claim(s) did not earn a label and are left out: "
                   + ", ".join(c["id"] for c in pending))
    if unread:
        out.append(f"- {len(unread)} source(s) found but not read: "
                   + "; ".join(f"{s['id']} {s['title']} ({s['unread_reason']})" for s in unread))
    if read < state["targets"]["sources"]:
        out.append(f"- {read} of the ~{state['targets']['sources']} sources planned for this depth were read.")
    if any(s.get("captured_by") == "agent" for s in sources):
        out.append("- Some source text was supplied by an agent rather than fetched by Gauntlet (marked in the appendix).")
    for ch in changes:
        out.append(f"- {ch['id']} was downgraded from {DISPLAY[ch['from']]} to {DISPLAY[ch['to']]} on re-audit.")
    out += ["- Whether a passage supports its claim is a referee model's judgement; Gauntlet checks the passage "
            "exists verbatim and that numbers trace to evidence.",
            "- Anything absent here was not found in the sources read, which is not the same as not existing.", ""]

    out += ["## Appendix: evidence", ""]
    for c in claims:
        out += [f"**{c['id']}** ({DISPLAY[c['label']]}) {c['statement']}", ""]
        out += [f"- {e['source_id']}{' (against)' if e.get('side') == 'against' else ''}: \"{e['passage']}\""
                for e in c["sources"]]
        for t in c["tests"]:
            seeds = ", ".join(f"{r['seed']} {'pass' if r['pass'] else 'fail' if r['pass'] is False else 'error'}"
                              for r in testing.runs(t))
            out.append(f"- {t['id']} {t['role']}{' of ' + t['replicates'] if t['replicates'] else ''}: "
                       f"`{t['script']}` — {seeds}")
        out.append("")
    out += ["| Source | Title | Kind | Status | URL |", "|---|---|---|---|---|"]
    out += [f"| {s['id']} | {s['title']} | {s['kind']} | {s['status']}{' (agent text)' if s.get('captured_by') == 'agent' else ''}"
            f" | {s.get('url') or ''} |" for s in sources]
    if draft and problems:
        out += ["", "## Report check failures", ""] + [f"- {p}" for p in problems]
    atomic_write(project.report_path, "\n".join(out) + "\n")
    return problems
