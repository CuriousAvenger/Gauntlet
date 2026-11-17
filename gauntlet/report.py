"""Assemble report.md: the writer's answer on top, then findings by label, new
ideas, what was not checked, and the expert appendix. The structured sections
are generated from claims.jsonl so no label can be overstated in prose."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import cost, testing
from .checks.wording import lint
from .labels import DISPLAY, IDEA_LABELS, MEANING, PENDING, SOURCED_LABELS, display
from .util import atomic_write, now_iso

CITE_RE = re.compile(r"\[((?:[CI]\d+)(?:\s*,\s*[CI]\d+)*)\]")
NOT_ADVICE = ("**This report is research, not advice.** It summarises what sources say and what "
              "was tested. It is not medical, legal or financial advice; consult a qualified professional.")
DISCLOSURE = ("Prepared with Gauntlet, an AI research assistant. Every claim carries a label showing "
              "how it was checked; labels and quotes should be read before relying on any claim.")


def validate_answer(project, answer: str, claims: dict[str, dict]) -> list[str]:
    problems = []
    if not answer.strip():
        return ["answer.md is empty or missing: the writer must draft the plain-language answer first"]
    cited = set()
    for m in CITE_RE.finditer(answer):
        for cid in re.split(r"\s*,\s*", m.group(1)):
            cited.add(cid)
    for cid in sorted(cited):
        c = claims.get(cid)
        if c is None:
            problems.append(f"answer cites {cid}, which does not exist")
        elif c["label"] == PENDING:
            problems.append(f"answer cites {cid}, which has not passed its checks (pending)")
        elif c["kind"] == "idea" and c["label"] != "tested":
            problems.append(f"answer cites {cid} ({display(c['label'])}); only tested ideas may appear in the answer")
    for para in re.split(r"\n\s*\n", answer):
        body = CITE_RE.sub("", para)
        if re.search(r"(?<![\w.#])\d", body) and not CITE_RE.search(para) and not para.lstrip().startswith("#"):
            problems.append(f"paragraph states a number without citing a claim: {para.strip()[:80]!r}")
    for word, hint, ctx in lint(answer):
        problems.append(f"wording: '{word}' ({hint}) in: ...{ctx}...")
    return problems


def validate_claims(claims: list[dict]) -> list[str]:
    problems = []
    for c in claims:
        if c["label"] == PENDING:
            continue
        for word, hint, _ in lint(c["statement"]):
            problems.append(f"wording in {c['id']}: '{word}' ({hint})")
    return problems


def _annotate(answer: str, claims: dict[str, dict]) -> str:
    def rep(m):
        ids = re.split(r"\s*,\s*", m.group(1))
        return "[" + "; ".join(f"{i} · {display(claims[i]['label'])}" if i in claims else i for i in ids) + "]"
    return CITE_RE.sub(rep, answer)


def _src_title(project, sid: str) -> str:
    s = project.source(sid) or {}
    return s.get("title") or sid


def build(project, draft: bool = False) -> tuple[str, list[str]]:
    state = project.state()
    profile = project.profile()
    claims = project.claims()
    by_id = {c["id"]: c for c in claims}
    answer = project.answer_path.read_text() if project.answer_path.exists() else ""
    problems = validate_answer(project, answer, by_id) + validate_claims(claims)

    L: list[str] = []
    L.append(f"# {state['question']}\n")
    L.append(f"_Gauntlet report · depth: {state['depth']} · round {len(state['rounds'])} · {now_iso()[:10]}_\n")
    if draft and problems:
        L.append("> **DRAFT — failed report checks.** See the list at the end. Do not share.\n")
    if profile.get("high_stakes"):
        L.append(f"> {NOT_ADVICE}\n")
    events = state.get("integrity_events", [])
    if events:
        L.append(f"> **Integrity:** evidence records were edited outside Gauntlet {len(events)} time(s) "
                 f"(first {events[0]['at'][:16]}). Every claim was re-checked after each edit; see the appendix.\n")
    L.append("**How to read this report.** Every claim carries a label that shows what evidence stands "
             "behind it. Nothing is shown as more certain than its evidence.\n")
    L.append("| Label | Meaning |\n|---|---|")
    for lab in SOURCED_LABELS + IDEA_LABELS:
        L.append(f"| {DISPLAY[lab]} | {MEANING[lab]} |")
    L.append("")

    L.append("## Answer\n")
    L.append(_annotate(answer.strip(), by_id) if answer.strip() else "_The writer has not drafted an answer yet._")
    L.append("")

    L.append("## Findings\n")
    for lab in SOURCED_LABELS:
        group = [c for c in claims if c["label"] == lab]
        if not group:
            continue
        L.append(f"### {DISPLAY[lab]}\n")
        for c in group:
            srcs = ", ".join(f"{e['source_id']}" + (f" ({e.get('side')})" if lab == "contested" else "")
                             for e in c["sources"])
            L.append(f"- **{c['id']}** {c['statement']} — _sources: {srcs}_")
        L.append("")
    if not any(c["label"] in SOURCED_LABELS for c in claims):
        L.append("_No claims from sources have passed their checks yet._\n")

    L.append("## New ideas\n")
    L.append("Ideas proposed during the research. None of these appear in the answer above unless tested.\n")
    any_idea = False
    for lab in ("tested", "refuted", "untested"):
        group = [c for c in claims if c["label"] == lab]
        if not group:
            continue
        any_idea = True
        L.append(f"### {DISPLAY[lab]}\n")
        for c in group:
            line = f"- **{c['id']}** {c['statement']}"
            if lab == "untested":
                line += f"\n  - _Test that would settle it:_ {c.get('settling_test')}"
            elif lab == "tested":
                line += "\n  - _Passed:_ " + ", ".join(c.get("checks_passed", []))
            else:
                fails = sorted({t["id"] for t in c.get("tests", []) for r in testing.runs(t) if r["pass"] is False})
                line += f"\n  - _Failed in:_ {', '.join(fails) or 'see appendix'}"
            L.append(line)
        L.append("")
    if not any_idea:
        L.append("_No ideas were proposed in this run._\n")

    L.append("## What was not checked\n")
    L += not_checked(project, claims, state)
    L.append("")

    L.append("## Expert appendix\n")
    L += appendix(project, claims, state)

    L.append("\n---\n")
    L.append(f"_{DISCLOSURE}_")
    if draft and problems:
        L.append("\n## Report check failures\n")
        L += [f"- {p}" for p in problems]
    return "\n".join(L) + "\n", problems


def not_checked(project, claims, state) -> list[str]:
    out = []
    pending = [c for c in claims if c["label"] == PENDING]
    if pending:
        out.append(f"- **{len(pending)} claim(s) did not pass their checks** and are left out of the findings:")
        for c in pending:
            failed = [k for k, v in c.get("checks", {}).items() if not v["passed"]]
            out.append(f"  - {c['id']}: {c['statement'][:120]}" + (f" (failed: {', '.join(failed)})" if failed else " (not checked)"))
    unread = [s for s in project.sources() if s.get("status") != "read"]
    if unread:
        out.append(f"- **{len(unread)} source(s) found but not read** (never cited):")
        for s in unread:
            out.append(f"  - {s['id']} {s.get('title')}: {s.get('unread_reason')}")
    untested = [c for c in claims if c["label"] == "untested"]
    if untested:
        out.append(f"- **{len(untested)} idea(s) not tested.** Each lists the test that would settle it.")
    read = sum(1 for s in project.sources() if s.get("status") == "read")
    target = state["targets"]["sources"]
    if read < target:
        out.append(f"- Only {read} of the ~{target} sources planned for this depth were read.")
    agent_cap = [s["id"] for s in project.sources() if s.get("captured_by") == "agent-file" and s.get("status") == "read"]
    if agent_cap:
        out.append(f"- Source text for {', '.join(agent_cap)} was saved by an agent, not fetched by Gauntlet; "
                   "quotes from these were matched against the agent's copy.")
    out.append("- Whether a quoted passage *supports* a claim is a referee model's judgement; the quote check only "
               "confirms the passage exists in the saved source.")
    out.append("- Sources not read at all may say something different. Absence from this report means "
               "\"not found in the sources read\", not \"does not exist\".")
    return out


def appendix(project, claims, state) -> list[str]:
    out = ["### Claims and evidence\n"]
    for c in claims:
        out.append(f"#### {c['id']} — {display(c['label'])}\n")
        out.append(f"{c['statement']}\n")
        for i, e in enumerate(c.get("sources", [])):
            side = f" ({e['side']})" if e.get("side") and e["side"] != "for" else ""
            out.append(f"- {e['source_id']}{side}, _{_src_title(project, e['source_id'])}_: \"{e.get('passage', '').strip()}\"")
        for t in c.get("tests", []):
            rs = testing.runs(t)
            seeds = ", ".join(f"{r['seed']}:{'pass' if r['pass'] else ('fail' if r['pass'] is False else 'error')}"
                              for r in rs)
            rep = f", replicates {t['replicates']}" if t.get("replicates") else ""
            out.append(f"- Test {t['id']} ({t['role']}{rep}, by {t['agent']}): `{t['script']}` — runs {seeds}; "
                       f"logs under `runs/_harness/{c['id']}/`")
        for comp in c.get("comparisons", []):
            a, b = comp.get("a", {}), comp.get("b", {})
            out.append(f"- Comparison: {a.get('value')} vs {b.get('value')} {a.get('unit')}, baseline {a.get('baseline')}, scale {a.get('scale')}")
        checks = c.get("checks", {})
        if checks:
            out.append("- Checks: " + ", ".join(f"{k} {'✓' if v['passed'] else '✗'}" for k, v in checks.items()))
        downgrades = [h for h in c.get("history", []) if h.get("event") == "downgrade"]
        for h in downgrades:
            out.append(f"- Downgraded {h['from']} → {h['to']} on {h['at'][:10]}: {h.get('reason', '')[:200]}")
        out.append("")
    out.append("### Sources\n")
    out.append("| Id | Title | Kind | Status | URL |\n|---|---|---|---|---|")
    for s in project.sources():
        out.append(f"| {s['id']} | {s.get('title', '')} | {s.get('kind', '')} | {s.get('status')} | {s.get('url') or ''} |")
    out.append("\n### Run record\n")
    counts = Counter(c["label"] for c in claims)
    out.append("- Claims by label: " + (", ".join(f"{display(k)}: {v}" for k, v in sorted(counts.items())) or "none"))
    sp = cost.spend(project)
    out.append(f"- Spend: ${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f} budget"
               + ("".join(f"; {t} ${u:.2f}" for t, u in sp["by_tier"].items())))
    out.append(f"- Cycles: {len([c for c in state['cycles'] if c.get('ended')])}; rounds: {len(state['rounds'])}")
    overturned = sum(1 for c in claims for h in c.get("history", []) if h.get("event") in ("downgrade", "overturned"))
    out.append(f"- Labels later overturned: {overturned}")
    for ev in state.get("integrity_events", []):
        out.append(f"- Integrity event {ev['at'][:16]}: edited outside Gauntlet: {', '.join(ev['files'][:8])}; "
                   f"{len(ev.get('relabelled', []))} label(s) changed on re-check")
    out.append(f"- Models: " + ", ".join(f"{k}={v}" for k, v in state.get("models", {}).items()))
    return out


def write(project, answer: str | None = None, draft: bool = False) -> tuple[bool, list[str]]:
    """Save the writer's answer (if given) and assemble report.md. Refuses, unless
    draft=True, when the answer or any labelled claim fails the report checks."""
    if answer is not None:
        atomic_write(project.answer_path, answer.strip() + "\n")
    text, problems = build(project, draft=draft)
    if problems and not draft:
        return False, problems
    atomic_write(project.report_path, text)
    if not problems:
        project.update_state(status="reported")
    return True, problems
