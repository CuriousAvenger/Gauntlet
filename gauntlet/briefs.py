"""Compose self-contained briefs for the orchestrator and each role.

A brief is everything one agent needs, with no file access and no knowledge of
the conversation: the trust rules, the role's instructions, its agent name and
task, and the project context (question, depth, topic profile, expert pack).
Any harness can hand it to a subagent, or one agent can follow it itself.
"""

from __future__ import annotations

import re
from importlib import resources
from typing import Any

from .config import ROLE_TIERS

ROLES = tuple(ROLE_TIERS)  # orchestrator first, then the seven working roles
TIER_HINT = {"strong": "your strongest model", "mid": "a mid-tier model", "cheap": "a fast, inexpensive model"}
PACK_CHARS = 8000


def _read(*parts: str) -> str:
    return resources.files("gauntlet").joinpath("briefs", *parts).read_text(encoding="utf-8")


def _strip_front(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}, text
    meta = dict((k.strip(), v.strip()) for k, v in (l.split(":", 1) for l in m.group(1).splitlines() if ":" in l))
    return meta, text[m.end():]


def role_meta(role: str) -> dict[str, str]:
    return _strip_front(_read("roles", f"{role}.md"))[0] if role != "orchestrator" else {
        "description": "Runs the Gauntlet research loop", "tier": "strong"}


def project_context(project) -> str:
    s = project.state()
    lines = [
        "## Project",
        f"- Slug: `{project.slug}` (pass it as `project` if you work on several)",
        f"- Question (round {len(s['rounds'])}): {s['rounds'][-1]['question']}",
        f"- Depth: {s['depth']}; source target {s['targets']['sources']}; ideas tested per cycle "
        f"{s['targets']['test_ideas']}; max cycles {s['targets']['max_cycles']}; budget ${s['budget_usd']:.2f}",
        "",
        "## Topic profile",
        project.profile_path.read_text().split("---", 2)[-1].strip(),
    ]
    if project.pack_dir.exists():
        pack = "\n\n".join(p.read_text() for p in sorted(project.pack_dir.glob("*.md")))
        if len(pack) > PACK_CHARS:
            pack = pack[:PACK_CHARS] + "\n\n[pack truncated]"
        lines += ["", "## Expert pack", pack]
    return "\n".join(lines)


def compose(role: str, project=None, agent: str | None = None, task: str | None = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; roles: {', '.join(ROLES)}")
    if role == "orchestrator":
        parts = [_read("orchestrator.md").strip()]
    else:
        meta, body = _strip_front(_read("roles", f"{role}.md"))
        tier = meta.get("tier", ROLE_TIERS[role])
        parts = [body.strip(), _read("rules.md").strip()]
        assign = ["## Your assignment",
                  f"- Sign every tool call with `agent: \"{agent}\"`." if agent else
                  "- Sign every tool call with the agent name you were given.",
                  f"- Recommended model: {TIER_HINT.get(tier, tier)} ({tier} tier)."]
        if task:
            assign += ["", "### Task", task.strip()]
        parts.append("\n".join(assign))
    if project is not None:
        parts.append(project_context(project))
    return "\n\n".join(parts) + "\n"
