"""Gauntlet's agent-facing tools.

Design notes (tools are written for models, not people):
- Few, task-shaped tools. Each returns what the caller needs for its next
  decision (ids, check failures, what to fix), never raw file dumps.
- `project` is optional everywhere: it defaults to the active project, which
  start_research sets. Subagents may pass it explicitly.
- Every write is signed with `agent` so the harness can enforce separation of
  duties (a claim's author cannot referee it; a replication must come from a
  different agent with its own script).
- Errors are ToolErrors phrased as instructions.
"""

from __future__ import annotations

import re
from typing import Any

from .. import __version__, cost, labels, profiles, report, testing
from ..checks import quote_check, provenance, wording
from ..config import load_config
from ..project import Project, ProjectError, projects_dir
from ..sources import SOURCE_KINDS, FetchError, fetch
from ..util import now_iso
from .server import Server, ToolError

INSTRUCTIONS = """Gauntlet is a research harness: every claim in a report shows how it was checked.
Rules the tools enforce, and you must follow:
1. Never give a claim a stronger label than its evidence. Only set_label sets labels; it refuses unearned ones.
2. Cite only sources saved with save_source, quoting passages word for word (search_sources shows exact lines).
3. Test results come from run_test, which the harness executes itself; nobody's summary replaces a run.
4. Never soften a claim or change a test to make it pass. A refuted idea is a result.
5. Say "not found in the sources read", never new/novel/first/proved.
6. On medical, legal or financial topics the report is research, not advice.
Start with start_research. Use the gauntlet-* subagents for reading, testing and refereeing."""

server = Server("gauntlet", __version__, INSTRUCTIONS)

STAGES = ("scope", "survey", "synthesize", "explore", "check", "report")
_P = {"project": {"type": "string", "description": "Project slug. Defaults to the active project."}}
_AGENT = {"agent": {"type": "string", "minLength": 1,
                    "description": "Your agent name, e.g. reader-2. Must be unique per agent; it signs your work."}}
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


# ---- helpers ------------------------------------------------------------------------

def _open(project: str | None) -> Project:
    try:
        p = Project.open(projects_dir(), project, load_config())
    except ProjectError as e:
        raise ToolError(f"{e}. Call start_research first, or pass `project`.") from e
    return p


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
    """Checks an author can fix immediately: quotes and number provenance."""
    notes = []
    q = quote_check.check(p, claim)
    if not q.passed:
        notes += [f"quote {d}" for d in q.details if "found" != d.split(": ", 1)[-1]]
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


# ---- lifecycle ------------------------------------------------------------------------

@server.tool(
    "start_research",
    """Create a research project for a question (or start a follow-up round on an existing one) and make it active.
Returns the slug, the drafted topic profile (field, reader level, high-stakes flag, test mode), depth targets and a cost
estimate to show the user before spending anything.""",
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
    prof = p.profile()
    est = cost.estimate(cfg, depth)
    return {
        "project": p.slug,
        "folder": str(p.root),
        "profile": {k: prof.get(k) for k in ("field", "reader_level", "high_stakes", "test_mode")},
        "profile_file": str(p.profile_path),
        "targets": p.state()["targets"],
        "budget_usd": p.state()["budget_usd"],
        "estimate_usd": est["total_usd"],
        "estimate_by_stage": {r["stage"]: round(r["usd"] or 0, 2) for r in est["rows"]},
        "pack_folder": str(p.pack_dir) if pack else None,
        "next": "Show the user the profile and estimate; fix profile.md if the field or level is wrong; then plan sub-questions and set_stage('survey').",
    }


@server.tool(
    "status",
    """Where the project stands: stage, sources read vs target, claims by label, open gaps, spend vs budget, whether a
stop condition holds, and the suggested next step. Set include_claims for a compact claim list.""",
    {**_P, "include_claims": {"type": "boolean"}},
    read_only=True,
)
def status(project: str | None = None, include_claims: bool = False) -> dict:
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
    }
    if include_claims:
        out["claims"] = [_compact(c) for c in claims]
    return out


@server.tool(
    "set_stage",
    """Record the loop stage: scope, survey, synthesize, explore, check, report. Entering explore opens a cycle; leaving
check (to explore or report) closes it and returns whether a stop condition holds (cycles used, budget spent, or
repeated cycles with no new evidence). Usage is attributed to the current stage.""",
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
                "hint": "Not citable. Look for an open copy (preprint, author page) and save that URL."}
    head = (text or "")[:400].strip()
    return {"source_id": row["id"], "status": "read", "chars": len(text or ""), "title": row["title"],
            "captured_by": captured, "opening": head}


@server.tool(
    "search_sources",
    """Find exact lines in saved sources (case-insensitive regex). Use it to copy passages word for word before
record_claim, and to check whether an idea already appears in the sources read.""",
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
problems to fix now. Claims start as pending; only the referee labels them. If the same claim already exists,
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
    """Attach more quoted passages (or a comparison record) to an existing claim: a second independent source that agrees,
or a passage that contradicts it (side='against', which makes it a candidate for 'contested').""",
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
    problems = _quick_feedback(p, c)
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
        return {"claims": [{k: v for k, v in c.items() if k not in ("history",)} for c in rows]}
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
    return {"open_gaps": p.set_evidence_map(agree, disagree, gaps, agent), "file": str(p.evidence_map_path)}


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
    """Run a test script for an idea. The harness executes it: first on your development seeds, then (for support and
replication) on held-out seeds it draws at random, and keeps the logs. The script must take `--seed N` and print
`GAUNTLET_RESULT {"pass": true|false, "headline": {"name": number}}`. Write it under runs/<agent>/ in the project
folder. Roles: support (prover's test), counterexample (breaker's attack: pass=false means the idea broke),
replication (a second prover's independent script for test `replicates`). Re-running an edited script replaces
nothing: each call adds a new test record.""",
    {**_P, **_AGENT, "idea_id": {"type": "string"},
     "script": {"type": "string", "description": "Path relative to the project folder, e.g. runs/prover-1/test.py"},
     "role": {"type": "string", "enum": list(testing.ROLES)},
     "dev_seeds": {"type": "array", "items": {"type": "integer"}, "description": "Seeds you used while writing it (default [0])"},
     "args": {"type": "array", "items": {"type": "string"}, "description": "Extra CLI args before --seed"},
     "replicates": {"type": "string", "description": "For role=replication: the support test id, e.g. T1"}},
    ["agent", "idea_id", "script", "role"],
)
def run_test(agent: str, idea_id: str, script: str, role: str, dev_seeds: list[int] | None = None,
             args: list[str] | None = None, replicates: str | None = None, project: str | None = None) -> dict:
    p = _open(project)
    c = _claim(p, idea_id)
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
    if any(r["error"] for r in rs):
        out["hint"] = f"Some runs produced no result; read the logs under runs/_harness/{idea_id}/"
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
    p.put_claim(c)
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
a paragraph without a citation, or uses banned wording; fix and call again. draft=true writes it anyway, marked DRAFT.""",
    {**_P, **_AGENT, "answer": {"type": "string", "minLength": 20}, "draft": {"type": "boolean"}},
    ["agent", "answer"],
)
def write_report(agent: str, answer: str, draft: bool = False, project: str | None = None) -> dict:
    p = _open(project)
    ok, problems = report.write(p, answer=answer, draft=draft)
    if not ok:
        raise ToolError("Report not written. Fix the answer:\n- " + "\n- ".join(problems))
    return {"report": str(p.report_path), "draft": bool(problems), "problems": problems}


@server.tool(
    "log_usage",
    """Record token usage for a finished subagent. Only needed in runners that do not capture usage automatically
(Claude Code does, through Gauntlet's hooks).""",
    {**_P, **_AGENT, "input_tokens": {"type": "integer"}, "output_tokens": {"type": "integer"},
     "model": {"type": "string"}},
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
    """Console entry point (`gauntlet-mcp`) for runners that launch an installed package."""
    server.serve()
