"""Self-contained briefs: role instructions + trust rules + task + project context.
Any harness can hand one to a subagent, or one agent can follow it itself."""

from __future__ import annotations

import re
from importlib import resources

ROLES = ("orchestrator", "reader", "synthesizer", "ideator", "prover", "breaker", "referee", "writer")


def _read(name: str) -> str:
    return resources.files("gauntlet").joinpath("briefs", name).read_text(encoding="utf-8")


def compose(role: str, project=None, task: str | None = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    parts = [_read(f"{role}.md").strip()]
    if role != "orchestrator":
        parts.append(_read("rules.md").strip())
    if task:
        parts.append(f"## Your task\n\n{task.strip()}")
    if project is not None:
        s = project.state()
        parts.append(f"## Project\n\n- Question: {s['rounds'][-1]['question']}\n- Depth: {s['depth']} "
                     f"(source target {s['targets']['sources']}, ideas tested per cycle {s['targets']['test_ideas']}, "
                     f"max cycles {s['targets']['max_cycles']})\n- Reader level: {s['reader_level']}"
                     + ("\n- High-stakes topic: the report is research, not advice" if s["high_stakes"] else ""))
        if project.pack_dir.exists():
            pack = "\n\n".join(p.read_text() for p in sorted(project.pack_dir.glob("*.md")))
            parts.append("## Expert pack\n\n" + re.sub(r"^#", "###", pack, flags=re.M))
    return "\n\n".join(parts) + "\n"
