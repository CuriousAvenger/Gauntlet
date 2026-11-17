"""The tools agents call. They work on the active project (set by start_research)
and need no file access, so any MCP client can drive a full run."""

from __future__ import annotations

import re
from typing import Any

from . import __version__, briefs, labels, report, testing
from .labels import DISPLAY
from .project import DEPTHS, Project, ProjectError, available_packs
from .protocol import Server, ToolError
from .sources import KINDS, FetchError, fetch
from .util import now_iso

server = Server("gauntlet", __version__, (
    "Gauntlet researches questions so that every claim in the answer shows how it was checked. "
    "When the user asks a research question, call get_brief with role 'orchestrator' and follow it."))

EVIDENCE = {"type": "array", "minItems": 1, "items": {
    "type": "object", "required": ["source_id", "passage"], "additionalProperties": False,
    "properties": {"source_id": {"type": "string"},
                   "passage": {"type": "string", "description": "Exact words from the saved source; '...' skips text"},
                   "side": {"type": "string", "enum": ["for", "against"], "description": "Default 'for'"}}}}


def _project() -> Project:
    try:
        return Project.open()
    except ProjectError as e:
        raise ToolError(str(e)) from e


def _claim(p: Project, cid: str) -> dict[str, Any]:
    try:
        return p.claim(cid)
    except ProjectError as e:
        raise ToolError(f"{e}; list_claims shows the ids") from e


def _evidence(p: Project, evidence: list[dict]) -> list[dict]:
    for e in evidence:
        src = p.source(e["source_id"])
        if src is None or src["status"] != "read":
            raise ToolError(f"{e['source_id']} is not a saved, readable source; it cannot be cited")
    return [{"source_id": e["source_id"], "passage": e["passage"].strip(), "side": e.get("side", "for")}
            for e in evidence]


def _summary(c: dict[str, Any]) -> dict[str, Any]:
    out = {"id": c["id"], "label": c["label"], "statement": c["statement"]}
    if c["kind"] == "sourced":
        out["sources"] = [e["source_id"] + (" (against)" if e["side"] == "against" else "") for e in c["sources"]]
    else:
        out["tests"] = [f"{t['id']} {t['role']}: {sum(bool(r['pass']) for r in testing.runs(t))}/"
                        f"{len(testing.runs(t))} passed" for t in c["tests"]]
    return out


@server.tool("get_brief", """Instructions for a Gauntlet role. Call with role 'orchestrator' when the user asks a
research question and follow it. For delegated work, get the role's brief with its task and give it to a subagent,
or follow it yourself if you cannot start subagents.""",
             {"role": {"type": "string", "enum": list(briefs.ROLES)},
              "task": {"type": "string", "description": "The specific task for this role"}}, ["role"])
def get_brief(role: str, task: str | None = None) -> str:
    try:
        project = Project.open()
    except ProjectError:
        project = None
    return briefs.compose(role, project, task)


@server.prompt("research", "Research a question; every claim in the answer shows how it was checked.",
               [{"name": "question", "required": True}, {"name": "depth", "required": False}])
def research_prompt(question: str, depth: str = "standard") -> str:
    return briefs.compose("orchestrator") + f"\n## Request\n\nQuestion: {question}\nDepth: {depth}\n"


@server.tool("start_research", """Create a research project and make it active, or start a follow-up round on an
existing one. Depth: quick (~10 sources, ideas untested), standard (~30 sources, top ideas tested), deep (50+ sources,
repeated cycles). Set high_stakes for medical, legal or financial questions.""",
             {"question": {"type": "string", "minLength": 3},
              "depth": {"type": "string", "enum": list(DEPTHS)},
              "high_stakes": {"type": "boolean"},
              "reader_level": {"type": "string", "enum": ["general", "student", "expert"]},
              "pack": {"type": "string", "description": f"Expert pack: {', '.join(available_packs())}, or a directory"},
              "follow_up_on": {"type": "string", "description": "Slug of an existing project"}}, ["question"])
def start_research(question: str, depth: str = "standard", high_stakes: bool = False, reader_level: str = "general",
                   pack: str | None = None, follow_up_on: str | None = None) -> dict:
    try:
        if follow_up_on:
            p = Project.open(follow_up_on)
            s = p.state()
            s["rounds"].append({"n": len(s["rounds"]) + 1, "question": question, "started": now_iso()})
            p.save_state(s)
        else:
            p = Project.create(question, depth, high_stakes, reader_level, pack)
    except ProjectError as e:
        raise ToolError(str(e)) from e
    return {"project": p.slug, "folder": str(p.root), "round": len(p.state()["rounds"]), **p.state()["targets"]}


@server.tool("status", "Counts of sources and claims by label, open gaps, and optionally the evidence map.",
             {"include_evidence_map": {"type": "boolean"}}, read_only=True)
def status(include_evidence_map: bool = False) -> dict:
    p = _project()
    s, srcs, labelled = p.state(), p.sources(), {}
    for c in p.claims():
        labelled[c["label"]] = labelled.get(c["label"], 0) + 1
    out = {"project": p.slug, "question": s["rounds"][-1]["question"], "depth": s["depth"], "targets": s["targets"],
           "reader_level": s["reader_level"], "high_stakes": s["high_stakes"],
           "sources_read": sum(x["status"] == "read" for x in srcs), "sources_unread": sum(x["status"] != "read" for x in srcs),
           "claims_by_label": labelled, "open_gaps": p.gaps()}
    if include_evidence_map and p.evidence_map_path.exists():
        out["evidence_map"] = p.evidence_map_path.read_text()
    return out


@server.tool("save_source", """Save a source so it can be cited. Give `url`: Gauntlet fetches and stores the text itself,
so quotes are checked against what the source really says. Pass `text` (verbatim) only for a page Gauntlet cannot
fetch but you can read. Pass `unread_reason` for a paywalled or unreadable source: listed, never citable.""",
             {"kind": {"type": "string", "enum": list(KINDS)}, "url": {"type": "string"}, "title": {"type": "string"},
              "text": {"type": "string"}, "unread_reason": {"type": "string"}}, ["kind"])
def save_source(kind: str, url: str | None = None, title: str | None = None, text: str | None = None,
                unread_reason: str | None = None) -> dict:
    p = _project()
    if not (url or text or unread_reason):
        raise ToolError("give url, text or unread_reason")
    captured_by = "agent" if text else "gauntlet"
    if url and not text and not unread_reason:
        try:
            text, fetched_title = fetch(url)
            title = title or fetched_title
        except FetchError as e:
            unread_reason = str(e)
    try:
        row = p.add_source(title or url or "untitled", url, kind, text, unread_reason, captured_by)
    except ProjectError as e:
        raise ToolError(str(e)) from e
    if row["status"] != "read":
        return {"source_id": row["id"], "status": "unread", "reason": row["unread_reason"],
                "hint": "Not citable. Find an open copy, or pass the page text verbatim if you can read it."}
    return {"source_id": row["id"], "status": "read", "title": row["title"], "opening": text[:300]}


@server.tool("search_sources", "Exact lines from saved sources matching a regex (case-insensitive), for quoting verbatim.",
             {"pattern": {"type": "string", "minLength": 2}, "source_id": {"type": "string"},
              "context": {"type": "integer", "description": "Lines around each hit (default 1)"}}, ["pattern"],
             read_only=True)
def search_sources(pattern: str, source_id: str | None = None, context: int = 1) -> dict:
    p = _project()
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        raise ToolError(f"invalid regex: {e}") from e
    hits = []
    for src in p.sources():
        text = p.source_text(src) if not source_id or src["id"] == source_id else None
        lines = text.splitlines() if text else []
        for i, line in enumerate(lines):
            if rx.search(line):
                hits.append({"source_id": src["id"], "line": i + 1,
                             "text": "\n".join(lines[max(0, i - context):i + context + 1])})
                if len(hits) == 15:
                    return {"hits": hits, "more": True}
    return {"hits": hits, "more": False}


@server.tool("record_claim", """Record a claim from sources with quoted evidence. Say no more than the passages
(keep their hedges and scope); every number must appear in a passage. Returns problems to fix now, if any.""",
             {"statement": {"type": "string", "minLength": 10}, "evidence": EVIDENCE}, ["statement", "evidence"])
def record_claim(statement: str, evidence: list[dict]) -> dict:
    p = _project()
    c = p.new_claim("sourced", statement, sources=_evidence(p, evidence))
    problems = labels.quote_problems(p, c) + labels.provenance_problems(p, c)
    return {"claim_id": c["id"], **({"fix": problems} if problems else {})}


@server.tool("add_evidence", """Add quoted passages to a claim: another source that agrees, or one that contradicts it
(side 'against').""", {"claim_id": {"type": "string"}, "evidence": EVIDENCE}, ["claim_id", "evidence"])
def add_evidence(claim_id: str, evidence: list[dict]) -> dict:
    p = _project()
    c = _claim(p, claim_id)
    c["sources"] += _evidence(p, evidence)
    p.put_claim(c)
    problems = labels.quote_problems(p, c)
    return {"claim_id": claim_id, "evidence_count": len(c["sources"]), **({"fix": problems} if problems else {})}


@server.tool("list_claims", "Claims and ideas, filtered by ids or label. `full` returns passages and test runs.",
             {"ids": {"type": "array", "items": {"type": "string"}},
              "label": {"type": "string", "enum": list(labels.LABELS) + ["pending"]},
              "full": {"type": "boolean"}}, read_only=True)
def list_claims(ids: list[str] | None = None, label: str | None = None, full: bool = False) -> dict:
    rows = [c for c in _project().claims() if (not ids or c["id"] in ids) and (not label or c["label"] == label)]
    return {"claims": rows if full else [_summary(c) for c in rows]}


@server.tool("record_evidence_map", """Record what sources agree on, where they disagree (markdown citing claim ids)
and the open gaps. A gap re-sent with the same text keeps its id; gaps not re-sent are closed.""",
             {"agree": {"type": "string"}, "disagree": {"type": "string"},
              "gaps": {"type": "array", "items": {"type": "string"}}}, ["agree", "disagree", "gaps"])
def record_evidence_map(agree: str, disagree: str, gaps: list[str]) -> dict:
    return {"open_gaps": _project().set_evidence_map(agree, disagree, gaps)}


@server.tool("propose_idea", "Propose an idea from an open gap, with the concrete test that would settle it.",
             {"statement": {"type": "string", "minLength": 10}, "gap": {"type": "string"},
              "settling_test": {"type": "string", "minLength": 10}, "rationale": {"type": "string"}},
             ["statement", "gap", "settling_test"])
def propose_idea(statement: str, gap: str, settling_test: str, rationale: str = "") -> dict:
    p = _project()
    if gap not in p.gaps():
        raise ToolError(f"unknown or closed gap {gap}; open gaps: {p.gaps() or 'none yet'}")
    c = p.new_claim("idea", statement, gap=gap, settling_test=settling_test, rationale=rationale, label="untested")
    return {"idea_id": c["id"], "label": DISPLAY["untested"]}


@server.tool("run_test", """Run a Python test for an idea. Gauntlet saves `code` and runs it on your dev_seeds, then
(support and replication) on held-out seeds it picks at random. The script takes `--seed N` and prints
`GAUNTLET_RESULT {"pass": true|false, "headline": {"name": number}}`. Roles: support (the prover's test),
counterexample (an attack; pass=false means the idea broke), replication (independent code for test `replicates`).""",
             {"idea_id": {"type": "string"}, "code": {"type": "string", "minLength": 20},
              "role": {"type": "string", "enum": list(testing.ROLES)},
              "dev_seeds": {"type": "array", "items": {"type": "integer"}},
              "replicates": {"type": "string", "description": "Support test id, for role replication"}},
             ["idea_id", "code", "role"])
def run_test(idea_id: str, code: str, role: str, dev_seeds: list[int] | None = None,
             replicates: str | None = None) -> dict:
    p = _project()
    idea = _claim(p, idea_id)
    try:
        test = testing.new_test(p, idea, code, role, dev_seeds or [0], replicates)
    except testing.TestError as e:
        raise ToolError(str(e)) from e
    idea["tests"].append(test)
    p.put_claim(idea)
    out = {"test_id": test["id"], "runs": [{k: r[k] for k in ("seed", "pass", "headline", "error") if r[k] is not None}
                                           for r in testing.runs(test)]}
    failed = next((r for r in testing.runs(test) if r["error"]), None)
    if failed:
        out["log_tail"] = (p.root / failed["log"]).read_text(errors="replace")[-1200:]
    return out


@server.tool("set_label", """Set a label if the evidence earns it; otherwise get back what is missing. Sourced claims:
established (2+ independent sources agree), reported (1 source), contested (both sides quoted). Ideas: tested
(support test passed held-out seeds and an independent replication agrees), refuted (a run failed), untested.""",
             {"claim_id": {"type": "string"}, "label": {"type": "string", "enum": list(labels.LABELS)}},
             ["claim_id", "label"])
def set_label(claim_id: str, label: str) -> dict:
    p = _project()
    _claim(p, claim_id)
    unmet = labels.set_label(p, claim_id, label)
    if unmet:
        raise ToolError(f"{label} refused for {claim_id}:\n- " + "\n- ".join(unmet))
    return {"claim_id": claim_id, "label": DISPLAY[label]}


@server.tool("write_report", """Re-audit every label, then write report.md from the records with your plain-language
answer on top. Cite claims as [C3] or [C3, C7]. Refused if the answer cites an unlabelled claim or an idea that is
not tested, or states a number without a citation; draft=true writes it anyway, marked DRAFT.""",
             {"answer": {"type": "string", "minLength": 20}, "draft": {"type": "boolean"}}, ["answer"])
def write_report(answer: str, draft: bool = False) -> dict:
    p = _project()
    problems = report.write(p, answer, draft)
    if problems and not draft:
        raise ToolError("Report not written; fix the answer:\n- " + "\n- ".join(problems))
    return {"report_path": str(p.report_path), "report": p.report_path.read_text()}
