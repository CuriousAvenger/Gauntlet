"""Runner adapters. Roles are plain markdown briefs; any agent runner that can
spawn subagents with a system prompt and a shell can run Gauntlet. Adapters
write those briefs in the runner's own agent format with the configured model
for each tier."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Any

from .config import ROLE_TIERS, Config
from .util import atomic_write

ROLES = tuple(ROLE_TIERS)
RUNNERS = {"claude-code": "Claude Code (.claude/agents, .claude/commands)",
           "opencode": "opencode (.opencode/agent, .opencode/command)"}


def _read(*parts: str) -> str:
    return resources.files("gauntlet").joinpath(*parts).read_text(encoding="utf-8")


def role_source(role: str) -> tuple[dict[str, Any], str]:
    text = _read("core", "orchestrator.md") if role == "orchestrator" else _read("core", "roles", f"{role}.md")
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    meta: dict[str, Any] = {}
    body = text
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta, body


def rules() -> str:
    return _read("core", "rules.md")


def brief(role: str, project=None) -> str:
    """The full brief for a role: trust rules + role instructions (+ project context)."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; choose from {ROLES}")
    _, body = role_source(role)
    parts = [rules().strip(), body.strip()]
    if project is not None:
        s = project.state()
        parts.append(
            "## This project\n\n"
            f"- Project: `{project.slug}` (folder `{project.root}`)\n"
            f"- Question (round {len(s['rounds'])}): {s['rounds'][-1]['question']}\n"
            f"- Depth: {s['depth']} · source target {s['targets']['sources']} · ideas to test per cycle "
            f"{s['targets']['test_ideas']} · max cycles {s['targets']['max_cycles']} · budget ${s['budget_usd']:.2f}\n"
            f"- Topic profile: `{project.profile_path}`\n"
            + (f"- Expert pack: `{project.pack_dir}`\n" if project.pack_dir.exists() else "")
        )
    return "\n\n".join(parts) + "\n"


def _claude_alias(model: str) -> str:
    for fam in ("opus", "sonnet", "haiku"):
        if model.startswith(f"claude-{fam}"):
            return fam
    return model


def install(runner: str, dest: Path, cfg: Config) -> list[Path]:
    if runner not in RUNNERS:
        raise ValueError(f"unknown runner {runner!r}; choose from {list(RUNNERS)}")
    written = []
    sub_roles = [r for r in ROLES if r != "orchestrator"]
    for role in sub_roles:
        meta, _ = role_source(role)
        model = cfg.model_for(ROLE_TIERS[role])
        desc = meta.get("description", f"Gauntlet {role}")
        body = brief(role)
        if runner == "claude-code":
            fm = [f"name: gauntlet-{role}", f"description: {desc}", f"model: {_claude_alias(model)}"]
            if meta.get("tools"):
                fm.append(f"tools: {meta['tools']}")
            path = dest / ".claude" / "agents" / f"gauntlet-{role}.md"
        else:
            fm = [f"description: {desc}", "mode: subagent", f"model: anthropic/{model}"]
            path = dest / ".opencode" / "agent" / f"gauntlet-{role}.md"
        atomic_write(path, "---\n" + "\n".join(fm) + "\n---\n\n" + body)
        written.append(path)

    _, orch = role_source("orchestrator")
    orch_body = rules().strip() + "\n\n" + orch.strip() + "\n\n## Arguments\n\n$ARGUMENTS\n"
    if runner == "claude-code":
        fm = ["description: Research a question with Gauntlet (every claim shows how it was checked)",
              'argument-hint: "<question> [--depth quick|standard|deep]" | <project-slug> [follow-up]']
        path = dest / ".claude" / "commands" / "gauntlet.md"
    else:
        fm = ["description: Research a question with Gauntlet (every claim shows how it was checked)",
              f"model: anthropic/{cfg.model_for('strong')}"]
        path = dest / ".opencode" / "command" / "gauntlet.md"
    atomic_write(path, "---\n" + "\n".join(fm) + "\n---\n\n" + orch_body)
    written.append(path)
    return written
