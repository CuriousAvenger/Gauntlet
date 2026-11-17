"""`gauntlet` command line.

User commands:   ask, continue, status, report, estimate, packs
Agent commands:  source, claim, idea, test, audit, lint, cost, cycle, should-stop, brief
Setup:           install (write runner agent files), eval
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import __version__, cost, labels, profiles, report, runners
from ..checks import wording
from ..config import load_config
from ..project import Project, ProjectError, projects_dir
from ..sources import SOURCE_KINDS, FetchError, fetch
from ..util import now_iso, parse_result_line


def _open(args) -> Project:
    return Project.open(projects_dir(args.projects_dir), args.project, load_config(args.config))


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


# ---- user commands -------------------------------------------------------------

def cmd_ask(args) -> int:
    cfg = load_config(args.config)
    proj = Project.create(projects_dir(args.projects_dir), args.question, depth=args.depth, pack=args.pack,
                          budget_usd=args.budget, reader_level=args.level, config=cfg)
    prof = proj.profile()
    est = cost.estimate(cfg, args.depth)
    print(f"Created project: {proj.root}")
    print(f"Field (draft): {prof.get('field')}  ·  reader level: {prof.get('reader_level')}  ·  "
          f"high-stakes: {prof.get('high_stakes')}")
    print(f"Edit the topic profile in plain words if it is wrong: {proj.profile_path}\n")
    print(cost.format_estimate(est))
    if args.budget is not None:
        print(f"Budget override: ${args.budget:.2f}")
    print("\nNext: run the research loop in your agent runner, e.g. in Claude Code:")
    print(f"  /gauntlet {proj.slug}")
    print("or print the orchestrator brief for any runner:")
    print(f"  gauntlet brief orchestrator -p {proj.slug}")
    return 0


def cmd_continue(args) -> int:
    proj = _open(args)
    s = proj.state()
    s["rounds"].append({"n": len(s["rounds"]) + 1, "question": args.followup, "started": now_iso()})
    s["status"] = "scope"
    proj.save_state(s)
    print(f"Round {len(s['rounds'])} started on {proj.slug}: {args.followup}")
    print("Existing sources, claims and ideas are kept; the loop resumes at Scope for the follow-up.")
    return 0


def cmd_status(args) -> int:
    proj = _open(args)
    s = proj.state()
    claims = proj.claims()
    srcs = proj.sources()
    sp = cost.spend(proj)
    stop, why = cost.should_stop(proj)
    counts: dict[str, int] = {}
    for c in claims:
        counts[c["label"]] = counts.get(c["label"], 0) + 1
    info = {
        "project": proj.slug,
        "question": s["question"],
        "round": len(s["rounds"]),
        "current_question": s["rounds"][-1]["question"],
        "depth": s["depth"],
        "status": s["status"],
        "sources": {"read": sum(1 for x in srcs if x.get("status") == "read"),
                    "unread": sum(1 for x in srcs if x.get("status") != "read"),
                    "target": s["targets"]["sources"]},
        "claims_by_label": counts,
        "gaps": list(proj.gaps()),
        "cycles_done": len([c for c in s["cycles"] if c.get("ended")]),
        "spend_usd": sp["total_usd"],
        "budget_usd": sp["budget_usd"],
        "should_stop": stop,
        "stop_reason": why,
        "report": proj.report_path.exists(),
    }
    if args.json:
        _print_json(info)
        return 0
    print(f"{info['project']}  [{info['status']}]  depth={info['depth']}  round {info['round']}")
    print(f"Q: {info['current_question']}")
    print(f"Sources: {info['sources']['read']} read / {info['sources']['target']} target, {info['sources']['unread']} unread")
    print("Claims: " + (", ".join(f"{labels.display(k)}={v}" for k, v in sorted(counts.items())) or "none"))
    print(f"Gaps: {', '.join(info['gaps']) or 'none listed'}")
    print(f"Cycles: {info['cycles_done']}/{s['targets']['max_cycles']}   Spend: ${sp['total_usd']:.2f} / ${sp['budget_usd']:.2f}")
    print(f"Stop? {'yes' if stop else 'no'} — {why}")
    return 0


def cmd_set_status(args) -> int:
    proj = _open(args)
    proj.update_state(status=args.stage)
    print(f"status = {args.stage}")
    return 0


def cmd_report(args) -> int:
    proj = _open(args)
    ok, problems = report.write(proj, draft=args.draft)
    if not ok:
        print("Report NOT written; fix these first (or use --draft):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2
    print(f"Wrote {proj.report_path}" + (f" (DRAFT, {len(problems)} problem(s))" if problems else ""))
    return 0


def cmd_estimate(args) -> int:
    cfg = load_config(args.config)
    depths = [args.depth] if args.depth else list(cfg.depths)
    for d in depths:
        print(cost.format_estimate(cost.estimate(cfg, d)))
        print()
    return 0


def cmd_packs(args) -> int:
    for p in profiles.available_packs():
        print(p)
    return 0


def cmd_profile(args) -> int:
    proj = _open(args)
    if args.field or args.level:
        cur = proj.profile()
        text = profiles.draft_profile(proj.state()["question"], field=args.field or cur.get("field"),
                                      pack=proj.state().get("pack"), reader_level=args.level or cur.get("reader_level"))
        proj.profile_path.write_text(text)
        print(f"Re-drafted {proj.profile_path}")
    if args.json:
        _print_json(proj.profile())
    else:
        print(proj.profile_path.read_text())
    return 0


# ---- sources ---------------------------------------------------------------------

def cmd_source_add(args) -> int:
    proj = _open(args)
    text, title, captured, unread = None, args.title, "gauntlet-fetch", args.unread
    if not unread:
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8", errors="replace")
            captured = "agent-file"
        elif args.url:
            try:
                text, fetched_title = fetch(args.url)
                title = title or fetched_title
            except FetchError as e:
                unread = ("paywalled: " if e.paywalled else "fetch failed: ") + str(e)
        else:
            print("give --url, --file, or --unread REASON", file=sys.stderr)
            return 2
    row = proj.add_source(title or args.url or "untitled", args.url, text, kind=args.kind,
                          captured_by=captured, unread_reason=unread, agent=args.agent)
    if row["status"] == "read":
        print(f"{row['id']} saved ({len(text):,} chars) -> {row['file']}")
    else:
        print(f"{row['id']} listed as UNREAD ({row['unread_reason']}); it cannot be cited")
    return 0 if row["status"] == "read" else 3


def cmd_source_list(args) -> int:
    proj = _open(args)
    rows = proj.sources()
    if args.json:
        _print_json(rows)
        return 0
    for s in rows:
        print(f"{s['id']:<5} {s['status']:<7} {s.get('kind', ''):<16} {s.get('title', '')[:70]}")
    return 0


def cmd_source_grep(args) -> int:
    """Print exact lines from a saved source so agents can quote verbatim."""
    import re
    proj = _open(args)
    targets = [proj.source(args.id)] if args.id != "all" else proj.sources()
    pat = re.compile(args.pattern, re.I)
    hits = 0
    for src in targets:
        if src is None:
            print(f"no source {args.id}", file=sys.stderr)
            return 2
        text = proj.source_text(src)
        if text is None:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if pat.search(line):
                lo, hi = max(0, i - args.context), min(len(lines), i + args.context + 1)
                print(f"--- {src['id']}:{i + 1}")
                print("\n".join(lines[lo:hi]))
                hits += 1
                if hits >= args.max:
                    return 0
    return 0 if hits else 1


# ---- claims ----------------------------------------------------------------------

def _evidence(pairs, side):
    return [{"source_id": sid, "passage": passage, "side": side} for sid, passage in (pairs or [])]


def cmd_claim_add(args) -> int:
    proj = _open(args)
    ev = _evidence(args.cite, "for") + _evidence(args.against, "against")
    for e in ev:
        if proj.source(e["source_id"]) is None:
            print(f"unknown source {e['source_id']}", file=sys.stderr)
            return 2
    hits = wording.lint(args.statement)
    if hits:
        for w, hint, _ in hits:
            print(f"wording: '{w}' — {hint}", file=sys.stderr)
        return 2
    c = proj.new_claim(args.statement, "sourced", agent=args.by)
    c["sources"] = ev
    if args.comparison:
        c["comparisons"] = [json.loads(x) for x in args.comparison]
    proj.put_claim(c)
    print(c["id"])
    return 0


def cmd_claim_cite(args) -> int:
    proj = _open(args)
    c = proj.claim(args.id)
    if proj.source(args.source) is None:
        print(f"unknown source {args.source}", file=sys.stderr)
        return 2
    c["sources"].append({"source_id": args.source, "passage": args.passage, "side": args.side})
    c["history"].append({"at": now_iso(), "event": "cite", "source": args.source, "by": args.by})
    proj.put_claim(c)
    print(f"{args.id}: evidence [{len(c['sources']) - 1}] added from {args.source}")
    return 0


def cmd_claim_compare(args) -> int:
    proj = _open(args)
    c = proj.claim(args.id)
    comp = json.loads(args.json_spec)
    if "a" not in comp or "b" not in comp:
        print('comparison must be {"a": {...}, "b": {...}}', file=sys.stderr)
        return 2
    c.setdefault("comparisons", []).append(comp)
    proj.put_claim(c)
    print(f"{args.id}: comparison recorded")
    return 0


def cmd_claim_referee(args) -> int:
    proj = _open(args)
    c = proj.claim(args.id)
    if args.index >= len(c["sources"]):
        print(f"{args.id} has {len(c['sources'])} evidence entries (0-based index)", file=sys.stderr)
        return 2
    c["referee"].append({"source_index": args.index, "verdict": args.verdict, "by": args.by,
                         "note": args.note or "", "at": now_iso()})
    proj.put_claim(c)
    print(f"{args.id}[{args.index}]: {args.verdict} (by {args.by})")
    return 0


def cmd_claim_label(args) -> int:
    proj = _open(args)
    ok, unmet, c = labels.set_label(proj, args.id, args.label, by=args.by, reason=args.reason or "",
                                    execute=not args.no_exec)
    if ok:
        print(f"{args.id}: {labels.display(args.label)}")
        return 0
    print(f"{args.id}: label '{args.label}' REFUSED (stays {labels.display(c['label'])}):")
    for u in unmet:
        print(f"  - {u}")
    return 4


def cmd_claim_check(args) -> int:
    proj = _open(args)
    ids = [args.id] if args.id else [c["id"] for c in proj.claims()]
    worst = 0
    for cid in ids:
        c = proj.claim(cid)
        results, reqs = labels.evaluate(proj, c, execute=not args.no_exec)
        proj.put_claim(c)
        print(f"{cid} [{labels.display(c['label'])}] {c['statement'][:80]}")
        for name, r in results.items():
            print(f"  {'PASS' if r.passed else 'FAIL'} {name}: " + "; ".join(r.details)[:300])
        allowed = [lab for lab, u in reqs.items() if not u]
        print(f"  labels earned now: {', '.join(allowed) or 'none'}")
        if c["label"] != "pending" and reqs.get(c["label"]):
            worst = 4
    return worst


def cmd_claim_show(args) -> int:
    proj = _open(args)
    _print_json(proj.claim(args.id))
    return 0


def cmd_claim_list(args) -> int:
    proj = _open(args)
    rows = [c for c in proj.claims() if not args.label or c["label"] == args.label]
    if args.kind:
        rows = [c for c in rows if c["kind"] == args.kind]
    if args.json:
        _print_json(rows)
        return 0
    for c in rows:
        print(f"{c['id']:<5} {labels.display(c['label']):<26} {c['statement'][:90]}")
    return 0


def cmd_claim_overturn(args) -> int:
    """A person (or referee) overturns a label after the fact. Tracked as the
    most important evaluation number."""
    proj = _open(args)
    c = proj.claim(args.id)
    old = c["label"]
    c["label"] = "pending"
    c["history"].append({"at": now_iso(), "event": "overturned", "from": old, "to": "pending",
                         "by": args.by, "reason": args.reason})
    proj.put_claim(c)
    print(f"{args.id}: {old} overturned -> pending")
    return 0


# ---- ideas and tests ---------------------------------------------------------------

def cmd_idea_add(args) -> int:
    proj = _open(args)
    gaps = proj.gaps()
    if args.gap and gaps and args.gap not in gaps:
        print(f"unknown gap {args.gap}; evidence_map.md lists {', '.join(gaps)}", file=sys.stderr)
        return 2
    hits = wording.lint(args.statement)
    if hits:
        for w, hint, _ in hits:
            print(f"wording: '{w}' — {hint}", file=sys.stderr)
        return 2
    c = proj.new_claim(args.statement, "idea", agent=args.by, gap=args.gap, rationale=args.rationale,
                       settling_test=args.settling_test)
    if c.get("settling_test"):
        labels.set_label(proj, c["id"], "untested", by=args.by, reason="proposed")
        c = proj.claim(c["id"])
    print(f"{c['id']} ({labels.display(c['label'])})")
    return 0


def _next_test_id(c) -> str:
    return f"T{len(c.get('tests', [])) + 1}"


def cmd_test_add(args) -> int:
    proj = _open(args)
    c = proj.claim(args.id)
    if c["kind"] != "idea":
        print("tests attach to ideas (I-ids)", file=sys.stderr)
        return 2
    for rel in (args.script, args.log):
        if rel and not (proj.root / rel).exists():
            print(f"file not found (paths are relative to the project root): {rel}", file=sys.stderr)
            return 2
    res = parse_result_line((proj.root / args.log).read_text(errors="replace"))
    t = {"id": _next_test_id(c), "role": args.role, "script": args.script, "log": args.log,
         "agent": args.agent, "brief": args.brief, "result": res, "added": now_iso()}
    if args.held_out_cmd:
        t["held_out"] = {
            "cmd": args.held_out_cmd,
            "seeds": [int(x) for x in args.seeds.split(",")] if args.seeds else None,
            "dev_seeds": [int(x) for x in args.dev_seeds.split(",")] if args.dev_seeds else [],
        }
    c["tests"].append(t)
    proj.put_claim(c)
    outcome = "no GAUNTLET_RESULT line" if res is None else f"pass={res.get('pass')}"
    print(f"{args.id}/{t['id']} recorded ({outcome})")
    return 0


def cmd_test_replica(args) -> int:
    proj = _open(args)
    c = proj.claim(args.id)
    t = next((t for t in c["tests"] if t["id"] == args.test), None)
    if t is None:
        print(f"no test {args.test} on {args.id}", file=sys.stderr)
        return 2
    if not (proj.root / args.log).exists():
        print(f"log not found: {args.log}", file=sys.stderr)
        return 2
    t["replica"] = {"log": args.log, "agent": args.agent, "brief": args.brief, "script": args.script,
                    "added": now_iso()}
    proj.put_claim(c)
    print(f"{args.id}/{args.test}: replica recorded from {args.agent}")
    return 0


# ---- audit, lint, cost, cycles ----------------------------------------------------

def cmd_audit(args) -> int:
    proj = _open(args)
    changes = labels.audit(proj, execute=not args.no_exec)
    if not changes:
        print("audit: every label still holds")
        return 0
    for ch in changes:
        print(f"{ch['id']}: {ch['from']} -> {ch['to']}  ({ch['reason'][:200]})")
    return 5


def cmd_lint(args) -> int:
    if args.file:
        text = Path(args.file).read_text()
    else:
        proj = _open(args)
        text = proj.answer_path.read_text() if proj.answer_path.exists() else ""
    hits = wording.lint(text)
    for w, hint, ctx in hits:
        print(f"'{w}': {hint}\n   ...{ctx}...")
    return 6 if hits else 0


def cmd_cost_log(args) -> int:
    proj = _open(args)
    row = cost.ledger_row(proj.config, args.stage, args.agent, args.tier, args.model,
                          args.input_tokens, args.output_tokens, args.usd)
    proj.log_cost(row)
    sp = cost.spend(proj)
    print(f"logged ${row['usd']:.4f}; total ${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f}")
    return 0


def cmd_cost_show(args) -> int:
    proj = _open(args)
    _print_json(cost.spend(proj))
    return 0


def cmd_budget_check(args) -> int:
    proj = _open(args)
    sp = cost.spend(proj)
    if sp["remaining_usd"] <= 0:
        print(f"OVER BUDGET: ${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f}")
        return 7
    print(f"ok: ${sp['remaining_usd']:.2f} remaining")
    return 0


def cmd_cycle(args) -> int:
    proj = _open(args)
    if args.action == "start":
        c = cost.start_cycle(proj)
        print(f"cycle {c['n']} started")
    else:
        c = cost.end_cycle(proj)
        print(f"cycle {c['n']} ended: {c['new_sources']} new source(s), {c['new_claims']} new claim(s), "
              f"{c['relabelled']} relabelled")
        stop, why = cost.should_stop(proj)
        print(("STOP: " if stop else "CONTINUE: ") + why)
    return 0


def cmd_should_stop(args) -> int:
    proj = _open(args)
    stop, why = cost.should_stop(proj)
    print(("STOP: " if stop else "CONTINUE: ") + why)
    return 0 if stop else 1


# ---- runners, briefs, eval ----------------------------------------------------------

def cmd_brief(args) -> int:
    proj = None
    if args.project or (projects_dir(args.projects_dir) / ".current").exists():
        try:
            proj = _open(args)
        except ProjectError:
            proj = None
    print(runners.brief(args.role, proj))
    return 0


def cmd_install(args) -> int:
    cfg = load_config(args.config)
    written = runners.install(args.runner, Path(args.dir), cfg)
    for p in written:
        print(f"wrote {p}")
    return 0


def cmd_eval(args) -> int:
    from .. import evaluation
    if args.action == "planted":
        res = evaluation.planted_errors(verbose=True)
        print(f"\nPlanted errors caught: {res['caught']}/{res['planted']} (pass threshold {res['threshold']})")
        return 0 if res["passed"] else 8
    proj = _open(args)
    out = evaluation.sample_claims(proj, n=args.n, seed=args.seed)
    print(f"wrote review sheet {out}")
    return 0


# ---- parser -------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gauntlet", description="Research where every claim shows how it was checked.")
    p.add_argument("--version", action="version", version=f"gauntlet {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-p", "--project", help="project slug (default: the current project)")
    common.add_argument("--projects-dir", help="where projects live (default ./projects or $GAUNTLET_PROJECTS)")
    common.add_argument("--config", help="path to gauntlet.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, parents=(common,)):
        sp = sub.add_parser(name, help=help_, parents=list(parents))
        sp.set_defaults(fn=fn)
        return sp

    a = add("ask", cmd_ask, "start a project from a question")
    a.add_argument("question")
    a.add_argument("--depth", default="standard", help="quick | standard | deep")
    a.add_argument("--pack", help="expert pack name or directory")
    a.add_argument("--budget", type=float, help="hard budget in USD (default: per depth)")
    a.add_argument("--level", choices=["general", "student", "expert"], help="reader level")

    a = add("continue", cmd_continue, "ask a follow-up on the same notes")
    a.add_argument("followup")
    a = add("status", cmd_status, "show project status")
    a.add_argument("--json", action="store_true")
    a = add("stage", cmd_set_status, "record the stage the orchestrator is in")
    a.add_argument("stage", choices=["scope", "survey", "synthesize", "explore", "check", "report", "reported"])
    a = add("report", cmd_report, "assemble report.md (refuses if report checks fail)")
    a.add_argument("--draft", action="store_true", help="write anyway, marked DRAFT, with the problems listed")
    a = add("estimate", cmd_estimate, "show cost estimates per depth mode")
    a.add_argument("--depth")
    add("packs", cmd_packs, "list built-in expert packs")
    a = add("profile", cmd_profile, "show or re-draft the topic profile")
    a.add_argument("--field", choices=profiles.FIELDS)
    a.add_argument("--level", choices=["general", "student", "expert"])
    a.add_argument("--json", action="store_true")

    src = sub.add_parser("source", help="save and search sources").add_subparsers(dest="sub", required=True)
    s = src.add_parser("add", parents=[common], help="save a source (fetched by Gauntlet when --url is given)")
    s.add_argument("--url")
    s.add_argument("--file", help="text file saved by the agent (weaker provenance; flagged in the report)")
    s.add_argument("--title")
    s.add_argument("--kind", default="other", choices=SOURCE_KINDS)
    s.add_argument("--unread", metavar="REASON", help="list the source as found but not read (e.g. paywalled)")
    s.add_argument("--agent")
    s.set_defaults(fn=cmd_source_add)
    s = src.add_parser("list", parents=[common])
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_source_list)
    s = src.add_parser("grep", parents=[common], help="find exact lines in saved sources to quote")
    s.add_argument("id", help="source id or 'all'")
    s.add_argument("pattern", help="regular expression (case-insensitive)")
    s.add_argument("-C", "--context", type=int, default=1)
    s.add_argument("--max", type=int, default=20)
    s.set_defaults(fn=cmd_source_grep)

    cl = sub.add_parser("claim", help="record and label claims").add_subparsers(dest="sub", required=True)
    s = cl.add_parser("add", parents=[common], help="add a claim from sources")
    s.add_argument("statement")
    s.add_argument("--cite", nargs=2, action="append", metavar=("SOURCE", "PASSAGE"))
    s.add_argument("--against", nargs=2, action="append", metavar=("SOURCE", "PASSAGE"),
                   help="a passage that disagrees (makes the claim contested)")
    s.add_argument("--comparison", action="append", help='JSON {"a": {value,unit,baseline,scale}, "b": {...}}')
    s.add_argument("--by", help="agent name")
    s.set_defaults(fn=cmd_claim_add)
    s = cl.add_parser("cite", parents=[common], help="add evidence to a claim")
    s.add_argument("id"); s.add_argument("--source", required=True); s.add_argument("--passage", required=True)
    s.add_argument("--side", default="for", choices=["for", "against"]); s.add_argument("--by")
    s.set_defaults(fn=cmd_claim_cite)
    s = cl.add_parser("compare", parents=[common], help="record a like-for-like comparison")
    s.add_argument("id"); s.add_argument("json_spec", metavar="JSON")
    s.set_defaults(fn=cmd_claim_compare)
    s = cl.add_parser("referee", parents=[common], help="record whether a passage supports the claim")
    s.add_argument("id"); s.add_argument("--index", type=int, required=True)
    s.add_argument("--verdict", required=True, choices=["supports", "partial", "does-not-support"])
    s.add_argument("--by", required=True); s.add_argument("--note")
    s.set_defaults(fn=cmd_claim_referee)
    s = cl.add_parser("label", parents=[common], help="set a label (refused unless its checks pass)")
    s.add_argument("id"); s.add_argument("label", choices=labels.LABELS)
    s.add_argument("--by"); s.add_argument("--reason")
    s.add_argument("--no-exec", action="store_true", help="do not execute held-out commands")
    s.set_defaults(fn=cmd_claim_label)
    s = cl.add_parser("check", parents=[common], help="run checks on one or all claims")
    s.add_argument("id", nargs="?")
    s.add_argument("--no-exec", action="store_true")
    s.set_defaults(fn=cmd_claim_check)
    s = cl.add_parser("show", parents=[common]); s.add_argument("id"); s.set_defaults(fn=cmd_claim_show)
    s = cl.add_parser("list", parents=[common])
    s.add_argument("--label"); s.add_argument("--kind", choices=["sourced", "idea"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_claim_list)
    s = cl.add_parser("overturn", parents=[common], help="record that a person overturned a label")
    s.add_argument("id"); s.add_argument("--by", required=True); s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_claim_overturn)

    idea = sub.add_parser("idea", help="propose ideas").add_subparsers(dest="sub", required=True)
    s = idea.add_parser("add", parents=[common], help="propose an idea (labelled untested)")
    s.add_argument("statement"); s.add_argument("--gap", help="gap id from evidence_map.md (G1, ...)")
    s.add_argument("--rationale"); s.add_argument("--settling-test", required=True,
                                                  help="the test that would settle the idea")
    s.add_argument("--by")
    s.set_defaults(fn=cmd_idea_add)

    tst = sub.add_parser("test", help="record tests of ideas").add_subparsers(dest="sub", required=True)
    s = tst.add_parser("add", parents=[common], help="attach a test script and its log to an idea")
    s.add_argument("id"); s.add_argument("--script", required=True); s.add_argument("--log", required=True)
    s.add_argument("--agent", required=True); s.add_argument("--brief")
    s.add_argument("--role", default="support", choices=["support", "counterexample"])
    s.add_argument("--held-out-cmd", help="command with {seed}, run from the project root")
    s.add_argument("--seeds", help="comma-separated held-out seeds")
    s.add_argument("--dev-seeds", help="comma-separated seeds used while writing the test")
    s.set_defaults(fn=cmd_test_add)
    s = tst.add_parser("replica", parents=[common], help="attach an independent replication of a test")
    s.add_argument("id"); s.add_argument("test"); s.add_argument("--log", required=True)
    s.add_argument("--agent", required=True); s.add_argument("--brief"); s.add_argument("--script")
    s.set_defaults(fn=cmd_test_replica)

    a = add("audit", cmd_audit, "re-check every label; downgrade any that no longer hold")
    a.add_argument("--no-exec", action="store_true")
    a = add("lint", cmd_lint, "wording lint on answer.md or a file")
    a.add_argument("file", nargs="?")

    cst = sub.add_parser("cost", help="spend ledger").add_subparsers(dest="sub", required=True)
    s = cst.add_parser("log", parents=[common])
    s.add_argument("--stage", required=True, choices=list(cost.STAGE_TIERS))
    s.add_argument("--agent", required=True); s.add_argument("--tier", choices=["strong", "mid", "cheap"])
    s.add_argument("--model"); s.add_argument("--input-tokens", type=int, required=True)
    s.add_argument("--output-tokens", type=int, required=True); s.add_argument("--usd", type=float)
    s.set_defaults(fn=cmd_cost_log)
    s = cst.add_parser("show", parents=[common]); s.set_defaults(fn=cmd_cost_show)
    add("budget-check", cmd_budget_check, "exit 7 if the budget is spent")

    a = add("cycle", cmd_cycle, "mark the start/end of an Explore-Check cycle")
    a.add_argument("action", choices=["start", "end"])
    add("should-stop", cmd_should_stop, "exit 0 if a stop condition holds, 1 to continue")

    a = add("brief", cmd_brief, "print a role brief (with the trust rules) for any runner")
    a.add_argument("role", choices=runners.ROLES)
    a = add("install", cmd_install, "write agent files for a runner")
    a.add_argument("--runner", required=True, choices=list(runners.RUNNERS))
    a.add_argument("--dir", default=".")
    a = add("eval", cmd_eval, "evaluation helpers")
    a.add_argument("action", choices=["planted", "sample"])
    a.add_argument("--n", type=int, default=100)
    a.add_argument("--seed", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.fn(args) or 0
    except (ProjectError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
