"""Claude Code hook handlers. They make the harness automatic: nobody has to
remember to log cost, respect the budget or leave the evidence files alone.

    PreToolUse  Write|Edit|MultiEdit|NotebookEdit|Bash  -> protect harness records
    PreToolUse  Agent                                   -> budget gate for gauntlet subagents
    SubagentStop                                        -> bill the subagent's transcript
    Stop                                                -> bill the main session's research turns
    SessionStart                                        -> remind a resumed session of open research

Handlers read the hook JSON from stdin and print a JSON decision, or nothing.
They never raise: a broken hook must not break the user's session.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

PROTECTED_FILES = {"claims.jsonl", "project.json", "report.md", "answer.md", "evidence_map.md", "ideas.md"}
WRITE_RE = re.compile(
    r"(>>?|\btee\b|\bsed\b[^|;&]*\s-i|\bperl\b[^|;&]*\s-[a-z]*i|\brm\b|\bmv\b|\bcp\b|\btruncate\b|\bdd\b"
    r"|\bchmod\b|write_text|open\([^)]*['\"][wa]|\.write\()"
)


def _home(event: dict[str, Any]) -> Path:
    if os.environ.get("GAUNTLET_HOME"):
        return Path(os.environ["GAUNTLET_HOME"])
    root = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    return Path(root) / "research"


def _protected(path: Path, home: Path) -> bool:
    try:
        rel = path.resolve().relative_to(home.resolve())
    except (ValueError, OSError):
        return False
    parts = rel.parts
    if len(parts) < 2:
        return False
    inner = parts[1:]
    if len(inner) == 1 and inner[0] in PROTECTED_FILES:
        return True
    if inner[0] == "sources":
        return True
    if inner[:2] == ("runs", "_harness") or inner == ("runs", "ledger.jsonl"):
        return True
    return False


def _deny(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


GUARD_REASON = ("Gauntlet's evidence records ({}) are written only by the Gauntlet tools, so every label stays "
                "backed by checked evidence. Use the gauntlet tools (record_claim, add_evidence, judge_evidence, "
                "set_label, record_evidence_map, write_report) instead.")


def pre_tool_use(event: dict[str, Any]) -> dict[str, Any] | None:
    tool = event.get("tool_name", "")
    inp = event.get("tool_input") or {}
    home = _home(event)
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        fp = inp.get("file_path") or inp.get("notebook_path")
        if fp:
            p = Path(fp) if os.path.isabs(fp) else Path(event.get("cwd") or os.getcwd()) / fp
            if _protected(p, home):
                return _deny(GUARD_REASON.format(p.name))
        return None
    if tool == "Bash":
        cmd = inp.get("command", "")
        if WRITE_RE.search(cmd) and _bash_touches_protected(cmd, event.get("cwd") or os.getcwd(), home):
            return _deny(GUARD_REASON.format("research files") + " Reading them with cat/grep is fine.")
        return None
    if tool == "Agent":
        return _budget_gate(inp, home)
    return None


def _bash_touches_protected(cmd: str, cwd: str, home: Path) -> bool:
    """Heuristic guard (not a sandbox): a writing command that names a protected
    record and is aimed at the research folder."""
    names = any(n in cmd for n in PROTECTED_FILES) or "_harness" in cmd or "sources/" in cmd
    if not names:
        return False
    try:
        inside = Path(cwd).resolve() == home.resolve() or home.resolve() in Path(cwd).resolve().parents
    except OSError:
        inside = False
    return inside or home.name in cmd or str(home) in cmd


def _budget_gate(inp: dict[str, Any], home: Path) -> dict[str, Any] | None:
    sub = str(inp.get("subagent_type") or "")
    if "gauntlet" not in sub or "writer" in sub:
        return None  # only research subagents; the writer may always finish the report
    from .cost import spend
    from .project import active_project

    proj = active_project(home)
    if proj is None:
        return None
    sp = spend(proj)
    if sp["total_usd"] >= sp["budget_usd"]:
        return _deny(f"Gauntlet budget spent (${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f}) for "
                     f"'{proj.slug}'. Stop new research; go to the Report stage with what you have and tell the "
                     "user the budget was reached.")
    return None


def subagent_stop(event: dict[str, Any]) -> None:
    agent = str(event.get("agent_type") or "")
    path = event.get("agent_transcript_path")
    if "gauntlet" not in agent or not path:
        return None
    from .cost import record_transcript
    from .project import active_project

    proj = active_project(_home(event))
    if proj is not None and Path(path).is_file():
        record_transcript(proj, path, agent.split(":")[-1])
    return None


def stop(event: dict[str, Any]) -> None:
    """Bill the orchestrator: main-session turns since the project was created,
    until its report is written."""
    path = event.get("transcript_path")
    from .cost import record_transcript
    from .project import active_project

    proj = active_project(_home(event))
    if proj is None or not path or not Path(path).is_file() or proj.state().get("status") == "reported":
        return None
    record_transcript(proj, path, "orchestrator", since=proj.state()["created"])
    return None


def session_start(event: dict[str, Any]) -> dict[str, Any] | None:
    from .project import active_project

    proj = active_project(_home(event))
    if proj is None:
        return None
    s = proj.state()
    if s.get("status") == "reported":
        return None
    ctx = (f"Gauntlet: research project '{proj.slug}' is open at stage '{s['status']}' "
           f"(question: {s['rounds'][-1]['question']}). If the user wants to continue it, use the gauntlet "
           "research skill and call the gauntlet status tool first.")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}


HANDLERS = {"pre-tool-use": pre_tool_use, "subagent-stop": subagent_stop, "stop": stop,
            "session-start": session_start}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        event = json.load(sys.stdin)
        out = HANDLERS[argv[0]](event)
        if out:
            print(json.dumps(out))
    except Exception as e:  # never break the session
        print(f"gauntlet hook ({argv[:1]}): {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
