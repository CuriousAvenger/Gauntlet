"""Gauntlet's MCP tools: the only way agents read and write research records.

Design notes (tools are written for models, not people):
- Few, task-shaped tools whose results carry what the caller needs next (ids,
  failures, what to fix), never raw file dumps.
- Nothing needs filesystem access: briefs, profile, evidence map and test
  scripts all travel through tools, so chat-only MCP clients work too.
- `project` is optional everywhere and defaults to the active project.
- Writes are signed with `agent` for separation of duties (an author cannot
  referee its own claim; a replication needs another agent and its own code).
- Errors are ToolErrors phrased as instructions.
- Every call verifies, then re-seals, the project's records (integrity.py).
"""

from __future__ import annotations

import re
from typing import Any

from . import __version__, briefs, cost, integrity, labels, profiles, report, testing
from .checks import provenance, quote_check, wording
from .config import load_config
from .project import Project, ProjectError, projects_dir
from .protocol import Server, ToolError
from .sources import SOURCE_KINDS, FetchError, fetch
from .util import atomic_write, now_iso

INSTRUCTIONS = """Gauntlet is a research harness: answers where every claim shows how it was checked.
When the user asks a research question (what the evidence says, whether something is true, a literature
review, comparing findings), call get_brief with role "orchestrator" and follow it.
The tools enforce the trust rules: labels are refused unless earned, sources are fetched and stored by
the harness, tests are executed by the harness on held-out seeds, and the report cannot overstate."""

server = Server("gauntlet", __version__, INSTRUCTIONS)

STAGES = ("scope", "survey", "synthesize", "explore", "check", "report")
SOURCE_CAP_FACTOR = 2      # save_source refuses beyond 2x the depth's source target
TESTS_PER_IDEA_CAP = 12
UNGATED_ROLES = ("orchestrator", "writer")  # may always run, so a report can be finished

_P = {"project": {"type": "string", "description": "Project slug. Defaults to the active project."}}
_AGENT = {"agent": {"type": "string", "minLength": 1,
                    "description": "Your agent name from your brief, e.g. reader-2. It signs your work."}}
_EVIDENCE = {
    "type": "array", "minItems": 1,
    "items": {"type": "object", "required": ["source_id", "passage"], "additionalProperties": False,
              "properties": {
                  "source_id": {"type": "string", "description": "S-id from save_source"},
                  "passage": {"type": "string", "description": "Exact words from the saved source; '...' skips text"},
                  "side": {"type": "string", "enum": ["for", "against"],
                           "description": "'against' if the passage contradicts the claim (default for)"}}},
}
_COMPARISON = {
    "type": "array",
    "description": "Required when the statement compares numbers (x-fold, faster, fewer). a and b must share unit, baseline and scale.",
    "items": {"type": "object", "required": ["a", "b"], "additionalProperties": False,
              "properties": {k: {"type": "object", "required": ["value", "unit", "baseline", "scale"],
                                 "properties": {"value": {"type": "number"}, "unit": {"type": "string"},
                                                "baseline": {"type": "string"}, "scale": {"type": "string"}}}
                             for k in ("a", "b")}},
}


# ---- per-call integrity ---------------------------------------------------------------

_touched: dict[str, Project] = {}


def _open(project: str | None) -> Project:
    """Open a project and, once per tool call, verify its records were not edited
    outside Gauntlet. An out-of-band edit is recorded, every claim is re-checked,
    and the call is refused so the agent sees what happened."""
    try:
        p = Project.open(projects_dir(), project, load_config())
    except ProjectError as e:
        raise ToolError(f"{e}. Call start_research first, or pass `project`.") from e
    key = str(p.root)
    if key not in _touched:
        _touched[key] = p
        changed = integrity.verify(p)
        if changed:
            ev = integrity.record_tampering(p, changed)
            raise ToolError(
                "Evidence records were edited outside Gauntlet: " + ", ".join(changed[:8])
                + f". The edit is recorded in the report and every claim was re-checked "
                f"({len(ev['relabelled'])} label(s) changed). Change records only through these tools, "
                "then retry your call.")
    return p


def _around(name: str, call):
    _touched.clear()
    try:
        return call()
    finally:
        for p in list(_touched.values()):
            if p.state_path.exists():
                integrity.seal(p)
        _touched.clear()


server.around = _around


# ---- helpers ------------------------------------------------------------------------

def _claim(p: Project, cid: str) -> dict[str, Any]:
    try:
        return p.claim(cid)
    except ProjectError:
        ids = [c["id"] for c in p.claims()]
        raise ToolError(f"no claim {cid}; existing ids: {', '.join(ids[-30:]) or 'none'}") from None


def _lint(text: str) -> None:
    hits = wording.lint(text)
    if hits:
        raise ToolError("Wording not allowed: " + "; ".join(f"'{w}' ({hint})" for w, hint, _ in hits)
                        + ". Rephrase and call again.")


def _check_evidence(p: Project, evidence: list[dict]) -> list[dict]:
    out = []
    for e in evidence:
        src = p.source(e["source_id"])
        if src is None:
            raise ToolError(f"unknown source {e['source_id']}; save it with save_source first")
        if src["status"] != "read":
            raise ToolError(f"{e['source_id']} is unread ({src.get('unread_reason')}); unread sources cannot be cited")
        out.append({"source_id": e["source_id"], "passage": e["passage"].strip(), "side": e.get("side", "for")})
    return out


def _quick_feedback(p: Project, claim: dict) -> list[str]:
    """Problems an author can fix immediately: misquotes and unlinked numbers."""
    notes = []
    q = quote_check.check(p, claim)
    if not q.passed:
        notes += [f"quote {d}" for d in q.details if d.split(": ", 1)[-1] != "found"]
    pr = provenance.check(p, claim)
    if not pr.passed:
        notes += [d for d in pr.details if "appears in no" in d]
    return notes


def _compact(c: dict) -> dict:
    out = {"id": c["id"], "label": c["label"], "statement": c["statement"]}
    if c["kind"] == "idea":
        out["gap"] = c.get("gap")
        out["tests"] = [f"{t['id']}:{t['role']}:{sum(1 for r in testing.runs(t) if r['pass'])}/{len(testing.runs(t))}"
                        for t in c.get("tests", [])]
    else:
        out["sources"] = [e["source_id"] + ("(against)" if e.get("side") == "against" else "") for e in c["sources"]]
    failed = [k for k, v in c.get("checks", {}).items() if not v["passed"]]
    if failed:
        out["failing_checks"] = failed
    return out


# ---- briefs ---------------------------------------------------------------------------

@server.tool(
    "get_brief",
    """Get the self-contained instructions for a Gauntlet role. Call it with role "orchestrator" when the user asks
a research question, then follow that brief. For each piece of delegated work, get the role's brief with the
agent name and task filled in, and give it to a subagent (or follow it yourself if you cannot start subagents).
Roles: orchestrator, reader, synthesizer, ideator, prover, breaker, referee, writer. Research roles are refused
once the project's budget is spent; the writer is always available to finish the report.""",
    {**_P, "role": {"type": "string", "enum": list(briefs.ROLES)},
     "agent": {"type": "string", "description": "Agent name to assign, e.g. reader-3 (unique per instance)"},
     "task": {"type": "string", "description": "The specific task: sub-questions, claim ids, idea id, test id..."}},
    ["role"],
)
def get_brief(role: str, agent: str | None = None, task: str | None = None, project: str | None = None) -> str:
    p = None
    try:
        p = _open(project)
    except ToolError:
        if role != "orchestrator" or project:
            raise
    if p is not None and role not in UNGATED_ROLES:
        sp = cost.spend(p)
        if sp["total_usd"] >= sp["budget_usd"]:
            raise ToolError(f"Budget spent (${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f}): no new research "
                            "work. Go to the Report stage with what you have and tell the user.")
        s = p.state()
        s.setdefault("dispatches", []).append({"role": role, "agent": agent, "at": now_iso()})
        p.save_state(s)
    return briefs.compose(role, p, agent, task)


@server.prompt(
    "research",
    "Research a question with Gauntlet: a sourced answer where every claim shows how it was checked.",
    [{"name": "question", "description": "The research question", "required": True},
     {"name": "depth", "description": "quick | standard | deep", "required": False}],
)
def research_prompt(question: str, depth: str = "standard") -> str:
    return (briefs.compose("orchestrator") + f"\n## The user's request\n\nQuestion: {question}\nDepth: {depth}\n")


# ---- lifecycle ------------------------------------------------------------------------

@server.tool(
    "start_research",
    """Create a research project for a question (or start a follow-up round on an existing one) and make it active.
Returns the slug, the drafted topic profile (field, reader level, high-stakes flag, test mode), depth targets and a cost
estimate to show the user before spending anything. Get the orchestrator brief (get_brief) first if you have not.""",
    {"question": {"type": "string", "minLength": 3},
     "depth": {"type": "string", "enum": ["quick", "standard", "deep"],
               "description": "quick ~10 sources, ideas untested; standard ~30 sources, top ideas tested once; deep 50+ sources, repeated cycles"},
     "pack": {"type": "string", "description": f"Optional expert pack: {', '.join(profiles.available_packs())}, or a directory path"},
     "reader_level": {"type": "string", "enum": ["general", "student", "expert"]},
     "budget_usd": {"type": "number", "description": "Hard budget; defaults per depth"},
     "follow_up_on": {"type": "string", "description": "Slug of an existing project: starts a new round on the same notes"}},
    ["question"],
)
def start_research(question: str, depth: str = "standard", pack: str | None = None, reader_level: str | None = None,
                   budget_usd: float | None = None, follow_up_on: str | None = None) -> dict:
    cfg = load_config()
    if follow_up_on:
        p = _open(follow_up_on)
        s = p.state()
        s["rounds"].append({"n": len(s["rounds"]) + 1, "question": question, "started": now_iso()})
        s["status"] = "scope"
        p.save_state(s)
        return {"project": p.slug, "round": len(s["rounds"]), "question": question,
                "kept": {"sources": len(p.sources()), "claims": len(p.claims())},
                "next": "Scope the follow-up, then survey only what the existing sources do not cover."}
    try:
        p = Project.create(projects_dir(), question, depth=depth, pack=pack, budget_usd=budget_usd,
                           reader_level=reader_level, config=cfg)
    except (ProjectError, ValueError) as e:
        raise ToolError(str(e)) from e
    _touched[str(p.root)] = p
    prof = p.profile()
    est = cost.estimate(cfg, depth)
    return {
        "project": p.slug,
        "folder": str(p.root),
        "profile": {k: prof.get(k) for k in ("field", "reader_level", "high_stakes", "test_mode")},
        "targets": p.state()["targets"],
        "budget_usd": p.state()["budget_usd"],
        "estimate_usd": est["total_usd"],
        "estimate_by_stage": {r["stage"]: round(r["usd"] or 0, 2) for r in est["rows"]},
        "pack": pack,
        "next": "Tell the user the profile and estimate; fix the profile with update_profile if wrong; plan "
                "sub-questions; set_stage('survey').",
    }


@server.tool(
    "update_profile",
    """Correct the topic profile: field family (re-drafts where to look and how ideas are tested), reader level, or
free-text notes the user gave (appended under 'Notes from the user'). Every brief issued afterwards uses it.""",
    {**_P, "field": {"type": "string", "enum": list(profiles.FIELDS)},
     "reader_level": {"type": "string", "enum": ["general", "student", "expert"]},
     "notes": {"type": "string"}},
)
def update_profile(field: str | None = None, reader_level: str | None = None, notes: str | None = None,
                   project: str | None = None) -> dict:
    p = _open(project)
    cur = p.profile()
    text = p.profile_path.read_text()
    if field or reader_level:
        text = profiles.draft_profile(p.state()["question"], field=field or cur.get("field"),
                                      pack=p.state().get("pack"), reader_level=reader_level or cur.get("reader_level"))
        old_notes = p.profile_path.read_text().partition("\n## Notes from the user\n")[2]
        if old_notes:
            text += "\n## Notes from the user\n" + old_notes
    if notes:
        if "\n## Notes from the user\n" not in text:
            text += "\n## Notes from the user\n"
        text = text.rstrip() + f"\n- {notes.strip()}\n"
    atomic_write(p.profile_path, text)
    new = p.profile()
    return {k: new.get(k) for k in ("field", "reader_level", "high_stakes", "test_mode")}


@server.tool(
    "status",
    """Where the project stands: stage, sources read vs target, claims by label, open gaps, spend vs budget, whether a
stop condition holds. Options add the compact claim list, the evidence map, or the topic profile.""",
    {**_P, "include_claims": {"type": "boolean"}, "include_evidence_map": {"type": "boolean"},
     "include_profile": {"type": "boolean"}},
    read_only=True,
)
def status(project: str | None = None, include_claims: bool = False, include_evidence_map: bool = False,
           include_profile: bool = False) -> dict:
    p = _open(project)
    s = p.state()
    claims = p.claims()
    srcs = p.sources()
    by_label: dict[str, int] = {}
    for c in claims:
        by_label[c["label"]] = by_label.get(c["label"], 0) + 1
    sp = cost.spend(p)
    stop, why = cost.should_stop(p)
    out = {
        "project": p.slug, "round": len(s["rounds"]), "question": s["rounds"][-1]["question"], "depth": s["depth"],
        "stage": s["status"],
        "sources": {"read": sum(1 for x in srcs if x["status"] == "read"),
                    "unread": sum(1 for x in srcs if x["status"] != "read"), "target": s["targets"]["sources"]},
        "claims_by_label": by_label, "open_gaps": p.gaps(),
        "cycles_done": sum(1 for c in s["cycles"] if c.get("ended")), "max_cycles": s["targets"]["max_cycles"],
        "spend_usd": round(sp["total_usd"], 2), "budget_usd": sp["budget_usd"],
        "stop": stop, "stop_reason": why, "report_written": p.report_path.exists(),
        "integrity_events": len(s.get("integrity_events", [])),
    }
    if include_claims:
        out["claims"] = [_compact(c) for c in claims]
    if include_evidence_map and p.evidence_map_path.exists():
        out["evidence_map"] = p.evidence_map_path.read_text()
    if include_profile:
        out["profile"] = p.profile_path.read_text()
    return out


@server.tool(
    "set_stage",
    """Record the loop stage: scope, survey, synthesize, explore, check, report. Entering explore opens a cycle; leaving
check (to explore or report) closes it and returns whether a stop condition holds (cycles used, budget spent, or
repeated cycles with no new evidence).""",
    {**_P, "stage": {"type": "string", "enum": list(STAGES)}},
    ["stage"],
)
def set_stage(stage: str, project: str | None = None) -> dict:
    p = _open(project)
    s = p.state()
    prev = s["status"]
    out: dict[str, Any] = {"stage": stage, "previous": prev}
    open_cycle = bool(s["cycles"]) and not s["cycles"][-1].get("ended")
    if prev == "check" and stage in ("explore", "report") and open_cycle:
        out["cycle"] = {k: v for k, v in cost.end_cycle(p).items() if k != "before"}
    if stage == "explore":
        out["cycle_started"] = cost.start_cycle(p)["n"]
    p.update_state(status=stage)
    stop, why = cost.should_stop(p)
    out.update(stop=stop, stop_reason=why)
    return out


# ---- sources ---------------------------------------------------------------------------

@server.tool(
    "save_source",
    """Save a source so it can be cited. Give `url`: the harness fetches and stores the text itself, so quotes are checked
against what the source actually says (use the most text-rich URL: arXiv abs/HTML, PubMed Central, the docs page).
Only if the harness cannot fetch a page you can read, pass its verbatim text in `text` (flagged as weaker provenance).
If a source is paywalled or unreadable, pass `unread_reason`; it is listed but can never be cited.""",
    {**_P, **_AGENT, "url": {"type": "string"}, "title": {"type": "string"},
     "kind": {"type": "string", "enum": list(SOURCE_KINDS)},
     "text": {"type": "string", "description": "Verbatim source text, only when fetching fails"},
     "unread_reason": {"type": "string"}},
    ["agent", "kind"],
)
def save_source(agent: str, kind: str, url: str | None = None, title: str | None = None, text: str | None = None,
                unread_reason: str | None = None, project: str | None = None) -> dict:
    p = _open(project)
    if not url and not text and not unread_reason:
        raise ToolError("give `url` (preferred), or `text`, or `unread_reason`")
    cap = p.state()["targets"]["sources"] * SOURCE_CAP_FACTOR
    if len(p.sources()) >= cap:
        raise ToolError(f"source limit for this depth reached ({cap}); work with the sources saved, "
                        "or ask the user to rerun at a deeper depth")
    captured = "agent-text" if text else "gauntlet-fetch"
    if url and not text and not unread_reason:
        try:
            text, fetched_title = fetch(url)
            title = title or fetched_title
        except FetchError as e:
            unread_reason = ("paywalled: " if e.paywalled else "fetch failed: ") + str(e)
    try:
        row = p.add_source(title or url or "untitled", url, text, kind=kind, captured_by=captured,
                           unread_reason=unread_reason, agent=agent)
    except ProjectError as e:
        raise ToolError(str(e)) from e
    if row["status"] != "read":
        return {"source_id": row["id"], "status": "unread", "reason": row["unread_reason"],
                "hint": "Not citable. Look for an open copy (preprint, author page) and save that URL, "
                        "or pass the page's verbatim text if you can read it."}
    return {"source_id": row["id"], "status": "read", "chars": len(text or ""), "title": row["title"],
            "captured_by": captured, "opening": (text or "")[:400].strip()}


@server.tool(
    "search_sources",
    """Find exact lines in saved sources (case-insensitive regex). Use it to copy passages word for word before
record_claim, to read a passage in context, and to check whether an idea already appears in the sources read.""",
    {**_P, "pattern": {"type": "string", "minLength": 2},
     "source_id": {"type": "string", "description": "Limit to one source; default all"},
     "context": {"type": "integer", "description": "Lines of context around each hit (default 1)"},
     "max_hits": {"type": "integer", "description": "Default 15"}},
    ["pattern"], read_only=True,
)
def search_sources(pattern: str, source_id: str | None = None, context: int = 1, max_hits: int = 15,
                   project: str | None = None) -> dict:
    p = _open(project)
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        raise ToolError(f"invalid regex: {e}") from e
    srcs = [p.source(source_id)] if source_id else p.sources()
    if source_id and srcs[0] is None:
        raise ToolError(f"no source {source_id}")
    hits = []
    for src in srcs:
        text = p.source_text(src) if src["status"] == "read" else None
        if not text:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if rx.search(line):
                lo, hi = max(0, i - context), min(len(lines), i + context + 1)
                hits.append({"source_id": src["id"], "line": i + 1, "text": "\n".join(lines[lo:hi])})
                if len(hits) >= max_hits:
                    return {"hits": hits, "truncated": True}
    return {"hits": hits, "truncated": False}


# ---- claims -----------------------------------------------------------------------------

@server.tool(
    "record_claim",
    """Record one claim from sources with its quoted evidence. The statement must say no more than the passages (keep
their hedges and scope); every number in it must appear in a passage. Returns the claim id plus any quote or number
problems to fix now. Claims start as pending; only a referee labels them. If the same claim already exists,
use add_evidence instead.""",
    {**_P, **_AGENT, "statement": {"type": "string", "minLength": 10}, "evidence": _EVIDENCE,
     "comparisons": _COMPARISON},
    ["agent", "statement", "evidence"],
)
def record_claim(agent: str, statement: str, evidence: list[dict], comparisons: list[dict] | None = None,
                 project: str | None = None) -> dict:
    p = _open(project)
    _lint(statement)
    ev = _check_evidence(p, evidence)
    c = p.new_claim(statement, "sourced", agent=agent)
    c["sources"] = ev
    c["comparisons"] = comparisons or []
    p.put_claim(c)
    problems = _quick_feedback(p, c)
    out = {"claim_id": c["id"], "label": "pending"}
    if problems:
        out["fix_now"] = problems
        out["hint"] = "Copy passages exactly via search_sources, then add corrected evidence with add_evidence."
    return out


@server.tool(
    "add_evidence",
    """Attach more quoted passages (or a comparison record) to an existing claim or idea: a second independent source
that agrees, or a passage that contradicts it (side='against', which makes it a candidate for 'contested').""",
    {**_P, **_AGENT, "claim_id": {"type": "string"}, "evidence": _EVIDENCE, "comparisons": _COMPARISON},
    ["agent", "claim_id"],
)
def add_evidence(agent: str, claim_id: str, evidence: list[dict] | None = None, comparisons: list[dict] | None = None,
                 project: str | None = None) -> dict:
    p = _open(project)
    c = _claim(p, claim_id)
    if not evidence and not comparisons:
        raise ToolError("give `evidence` and/or `comparisons`")
    start = len(c["sources"])
    c["sources"] += _check_evidence(p, evidence or [])
    c["comparisons"] = c.get("comparisons", []) + (comparisons or [])
    c["history"].append({"at": now_iso(), "event": "evidence", "by": agent})
    p.put_claim(c)
    out = {"claim_id": claim_id, "evidence_indexes": list(range(start, len(c["sources"])))}
    problems = _quick_feedback(p, c) if c["sources"] else []
    if problems:
        out["fix_now"] = problems
    return out


@server.tool(
    "list_claims",
    "Compact list of claims (id, label, statement, sources or tests, failing checks). Filter by label, kind or ids.",
    {**_P, "label": {"type": "string", "enum": list(labels.LABELS) + ["pending"]},
     "kind": {"type": "string", "enum": ["sourced", "idea"]},
     "ids": {"type": "array", "items": {"type": "string"}},
     "full": {"type": "boolean", "description": "Return complete records (evidence passages, runs, verdicts)"}},
    read_only=True,
)
def list_claims(label: str | None = None, kind: str | None = None, ids: list[str] | None = None, full: bool = False,
                project: str | None = None) -> dict:
    p = _open(project)
    rows = [c for c in p.claims() if (not label or c["label"] == label) and (not kind or c["kind"] == kind)
            and (not ids or c["id"] in ids)]
    if full:
        return {"claims": [{k: v for k, v in c.items() if k != "history"} for c in rows]}
    return {"claims": [_compact(c) for c in rows]}


@server.tool(
    "record_evidence_map",
    """Write the evidence map: what sources agree on, where they disagree, and the open gaps. Cite claims by id in the
markdown. Gaps feed the ideator: make each specific enough that an idea could address it. A gap re-sent with the
same text keeps its id; gaps not re-sent are closed.""",
    {**_P, **_AGENT, "agree": {"type": "string"}, "disagree": {"type": "string"},
     "gaps": {"type": "array", "items": {"type": "string"}}},
    ["agent", "agree", "disagree", "gaps"],
)
def record_evidence_map(agent: str, agree: str, disagree: str, gaps: list[str], project: str | None = None) -> dict:
    p = _open(project)
    _lint(agree + "\n" + disagree + "\n" + "\n".join(gaps))
    return {"open_gaps": p.set_evidence_map(agree, disagree, gaps, agent)}


# ---- ideas and tests ------------------------------------------------------------------------

@server.tool(
    "propose_idea",
    """Propose an idea that addresses an open gap. It is recorded as 'New idea: untested' with the concrete test that
would settle it (instances, metric, pass condition).""",
    {**_P, **_AGENT, "statement": {"type": "string", "minLength": 10},
     "gap": {"type": "string", "description": "Gap id, e.g. G2"},
     "rationale": {"type": "string", "description": "Why it might hold, citing claim ids; note any prior work"},
     "settling_test": {"type": "string", "minLength": 10}},
    ["agent", "statement", "gap", "settling_test"],
)
def propose_idea(agent: str, statement: str, gap: str, settling_test: str, rationale: str = "",
                 project: str | None = None) -> dict:
    p = _open(project)
    gaps = p.gaps()
    if gap not in gaps:
        raise ToolError(f"unknown or closed gap {gap}; open gaps: {gaps or 'none (run record_evidence_map first)'}")
    _lint(statement + "\n" + rationale)
    c = p.new_claim(statement, "idea", agent=agent, gap=gap, rationale=rationale, settling_test=settling_test)
    labels.set_label(p, c["id"], "untested", by=agent, reason="proposed")
    return {"idea_id": c["id"], "label": labels.display("untested")}


@server.tool(
    "run_test",
    """Run a Python test script for an idea. Pass the source as `code` (the harness saves it under runs/<agent>/), or
`script`, a path to a file you already wrote inside the project folder. The harness executes it: first on your
development seeds, then (for support and replication) on held-out seeds it draws at random, and keeps every log.
The script must accept `--seed N` and print `GAUNTLET_RESULT {"pass": true|false, "headline": {"name": number}}`.
Roles: support (prover's test), counterexample (breaker's attack: pass=false means the idea broke), replication
(a second prover's independent script for test `replicates`). Each call adds a new test record.""",
    {**_P, **_AGENT, "idea_id": {"type": "string"},
     "role": {"type": "string", "enum": list(testing.ROLES)},
     "code": {"type": "string", "description": "Python source of the test script"},
     "name": {"type": "string", "description": "File name for `code`, e.g. heldout_test.py (default test.py)"},
     "script": {"type": "string", "description": "Instead of code: path relative to the project folder"},
     "dev_seeds": {"type": "array", "items": {"type": "integer"}, "description": "Seeds you used while writing it (default [0])"},
     "args": {"type": "array", "items": {"type": "string"}, "description": "Extra CLI args before --seed"},
     "replicates": {"type": "string", "description": "For role=replication: the support test id, e.g. T1"}},
    ["agent", "idea_id", "role"],
)
def run_test(agent: str, idea_id: str, role: str, code: str | None = None, name: str | None = None,
             script: str | None = None, dev_seeds: list[int] | None = None, args: list[str] | None = None,
             replicates: str | None = None, project: str | None = None) -> dict:
    p = _open(project)
    c = _claim(p, idea_id)
    if bool(code) == bool(script):
        raise ToolError("give exactly one of `code` (script source) or `script` (path)")
    if len(c.get("tests", [])) >= TESTS_PER_IDEA_CAP:
        raise ToolError(f"{idea_id} already has {TESTS_PER_IDEA_CAP} tests; decide with what has been run")
    if code:
        safe_agent = re.sub(r"[^A-Za-z0-9_.-]", "_", agent)
        fname = re.sub(r"[^A-Za-z0-9_.-]", "_", name or "test.py")
        if not fname.endswith(".py"):
            fname += ".py"
        rel = f"runs/{safe_agent}/{idea_id}-{fname}"
        atomic_write(p.root / rel, code)
        script = rel
    try:
        t = testing.new_test(p, c, agent, script, role, dev_seeds or [0], args, replicates)
    except testing.TestError as e:
        raise ToolError(str(e)) from e
    c["tests"].append(t)
    c["history"].append({"at": now_iso(), "event": "test", "test": t["id"], "by": agent})
    p.put_claim(c)
    out = testing.summary(t)
    rs = testing.runs(t)
    out["all_passed"] = all(r["pass"] for r in rs)
    errors = [r for r in rs if r["error"]]
    if errors:
        log = (p.root / errors[0]["log"]).read_text(errors="replace")
        out["first_error_log_tail"] = log[-1500:]
    return out


# ---- refereeing -------------------------------------------------------------------------

@server.tool(
    "judge_evidence",
    """Referee verdicts: for each evidence entry (0-based index) of a claim, does the passage, read in context, support
the statement as written (scope, population, scale, hedges)? Use 'partial' when it supports only a narrower
statement and say which in the note. For side='against' entries, 'supports' means it genuinely contradicts the
claim. You cannot judge claims you authored.""",
    {**_P, **_AGENT, "claim_id": {"type": "string"},
     "verdicts": {"type": "array", "minItems": 1, "items": {
         "type": "object", "required": ["index", "verdict"], "additionalProperties": False,
         "properties": {"index": {"type": "integer"},
                        "verdict": {"type": "string", "enum": ["supports", "partial", "does-not-support"]},
                        "note": {"type": "string"}}}}},
    ["agent", "claim_id", "verdicts"],
)
def judge_evidence(agent: str, claim_id: str, verdicts: list[dict], project: str | None = None) -> dict:
    p = _open(project)
    c = _claim(p, claim_id)
    if c.get("agent") == agent:
        raise ToolError(f"{claim_id} was written by {agent}; a different agent must referee it")
    for v in verdicts:
        if not 0 <= v["index"] < len(c["sources"]):
            raise ToolError(f"{claim_id} has evidence indexes 0..{len(c['sources']) - 1}")
        c["referee"].append({"source_index": v["index"], "verdict": v["verdict"], "by": agent,
                             "note": v.get("note", ""), "at": now_iso()})
    _, reqs = labels.evaluate(p, c)
    p.put_claim(c)
    return {"claim_id": claim_id, "labels_earned": [k for k, u in reqs.items() if not u]}


@server.tool(
    "check_claim",
    "Run every applicable check on a claim and report each result plus the labels it currently earns.",
    {**_P, "claim_id": {"type": "string"}},
    ["claim_id"], read_only=True,
)
def check_claim(claim_id: str, project: str | None = None) -> dict:
    p = _open(project)
    c = _claim(p, claim_id)
    results, reqs = labels.evaluate(p, c)
    p.put_claim(c)
    return {"claim_id": claim_id, "label": c["label"],
            "checks": {k: {"passed": r.passed, "details": r.details} for k, r in results.items()},
            "labels_earned": [k for k, u in reqs.items() if not u]}


@server.tool(
    "set_label",
    """Set a claim's label. The harness re-runs the checks and refuses any label the evidence does not earn, returning
what is missing. Sourced: established (2+ independent sources agree), reported (1 source), contested (both sides
quoted). Ideas: tested (support test passed held-out runs and an independent replication), refuted (a run failed),
untested. If refused, set a weaker label or leave it pending; never alter evidence to get it through.""",
    {**_P, **_AGENT, "claim_id": {"type": "string"}, "label": {"type": "string", "enum": list(labels.LABELS)},
     "reason": {"type": "string"}},
    ["agent", "claim_id", "label"],
)
def set_label(agent: str, claim_id: str, label: str, reason: str = "", project: str | None = None) -> dict:
    p = _open(project)
    _claim(p, claim_id)
    ok, unmet, c = labels.set_label(p, claim_id, label, by=agent, reason=reason)
    if ok:
        return {"claim_id": claim_id, "label": labels.display(label)}
    raise ToolError(f"Label '{label}' refused for {claim_id} (stays {labels.display(c['label'])}). Missing:\n- "
                    + "\n- ".join(unmet))


@server.tool(
    "audit",
    """Re-check every labelled claim: tests whose scripts changed are re-run on fresh held-out seeds, and any label no
longer earned is moved to the strongest one that is (e.g. a tested idea whose test now fails becomes refuted).
Run it after the Check stage in every cycle.""",
    _P,
)
def audit(project: str | None = None) -> dict:
    p = _open(project)
    changes = labels.audit(p)
    return {"changes": changes, "all_hold": not changes}


# ---- report and usage -------------------------------------------------------------------------

@server.tool(
    "write_report",
    """Save the plain-language answer and assemble report.md. The harness adds findings by label, new ideas, what was
not checked and the expert appendix from the claim records. Cite claims as [C3] or [C3, C7]; it shows each label
beside the citation. Refused if the answer cites a pending claim or an idea that is not tested, states a number in
a paragraph without a citation, or uses banned wording; fix and call again. draft=true writes it anyway, marked
DRAFT. Returns the report text so you can show it even without file access.""",
    {**_P, **_AGENT, "answer": {"type": "string", "minLength": 20}, "draft": {"type": "boolean"}},
    ["agent", "answer"],
)
def write_report(agent: str, answer: str, draft: bool = False, project: str | None = None) -> dict:
    p = _open(project)
    ok, problems = report.write(p, answer=answer, draft=draft)
    if not ok:
        raise ToolError("Report not written. Fix the answer:\n- " + "\n- ".join(problems))
    return {"report_path": str(p.report_path), "draft": bool(problems), "problems": problems,
            "report": p.report_path.read_text()}


@server.tool(
    "log_usage",
    """Record a finished agent's token usage against the project's budget. Call it after each subagent if your
environment reports token counts; get_brief refuses new research work once the budget is spent.""",
    {**_P, **_AGENT, "input_tokens": {"type": "integer"}, "output_tokens": {"type": "integer"},
     "model": {"type": "string", "description": "Model id, for pricing (default: the role's configured tier)"}},
    ["agent", "input_tokens", "output_tokens"],
)
def log_usage(agent: str, input_tokens: int, output_tokens: int, model: str | None = None,
              project: str | None = None) -> dict:
    p = _open(project)
    stage = p.state()["status"]
    p.log_cost(cost.ledger_row(p.config, stage, agent, None, model, input_tokens, output_tokens))
    sp = cost.spend(p)
    return {"spend_usd": round(sp["total_usd"], 4), "budget_usd": sp["budget_usd"]}


def serve() -> None:
    """Run the server on stdio (console entry point `gauntlet-mcp`)."""
    server.serve()
