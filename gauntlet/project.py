"""A project folder: one per question, holding everything needed to audit or continue it.

projects/<slug>/
  project.json      state: question, depth, rounds, cycles, status
  profile.md        topic profile (editable)
  sources/          index.jsonl + S<n>.txt saved source text
  evidence_map.md   agree / disagree / gaps (synthesizer)
  ideas.md          rendered from idea claims
  claims.jsonl      every claim, its label and evidence
  runs/             scripts and logs per agent; cost ledger
  answer.md         writer's plain-language answer (input to the report)
  report.md         assembled report
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import profiles
from .config import Config, load_config, research_home
from .util import (
    append_jsonl, atomic_write, now_iso, read_jsonl, sha256_file, slugify, write_jsonl,
)

CURRENT_FILE = ".active"


class ProjectError(Exception):
    pass


def projects_dir(explicit: str | None = None) -> Path:
    return Path(explicit) if explicit else research_home()


def active_project(base: Path | None = None) -> "Project | None":
    """The project the session is working on, or None. Never raises."""
    try:
        base = base or projects_dir()
        cur = base / CURRENT_FILE
        if not cur.exists():
            return None
        return Project(base / cur.read_text().strip())
    except Exception:
        return None


class Project:
    def __init__(self, root: Path, config: Config | None = None):
        self.root = Path(root)
        if not (self.root / "project.json").exists():
            raise ProjectError(f"not a Gauntlet project: {self.root}")
        self.config = config or load_config()

    # ---- paths ---------------------------------------------------------------
    @property
    def slug(self) -> str:
        return self.root.name

    @property
    def state_path(self) -> Path: return self.root / "project.json"
    @property
    def profile_path(self) -> Path: return self.root / "profile.md"
    @property
    def sources_dir(self) -> Path: return self.root / "sources"
    @property
    def sources_index(self) -> Path: return self.sources_dir / "index.jsonl"
    @property
    def evidence_map_path(self) -> Path: return self.root / "evidence_map.md"
    @property
    def ideas_path(self) -> Path: return self.root / "ideas.md"
    @property
    def claims_path(self) -> Path: return self.root / "claims.jsonl"
    @property
    def runs_dir(self) -> Path: return self.root / "runs"
    @property
    def ledger_path(self) -> Path: return self.runs_dir / "ledger.jsonl"
    @property
    def answer_path(self) -> Path: return self.root / "answer.md"
    @property
    def report_path(self) -> Path: return self.root / "report.md"
    @property
    def pack_dir(self) -> Path: return self.root / "pack"

    # ---- creation ------------------------------------------------------------
    @classmethod
    def create(
        cls,
        base: Path,
        question: str,
        depth: str = "standard",
        pack: str | None = None,
        budget_usd: float | None = None,
        reader_level: str | None = None,
        config: Config | None = None,
    ) -> "Project":
        config = config or load_config()
        if depth not in config.depths:
            raise ProjectError(f"unknown depth {depth!r}; choose from {sorted(config.depths)}")
        base = Path(base)
        base.mkdir(parents=True, exist_ok=True)
        slug = slugify(question)
        root = base / slug
        n = 2
        while root.exists():
            root = base / f"{slug}-{n}"
            n += 1
        root.mkdir()
        for d in ("sources", "runs"):
            (root / d).mkdir()
        dcfg = config.depths[depth]
        state = {
            "question": question,
            "depth": depth,
            "created": now_iso(),
            "status": "scope",
            "budget_usd": budget_usd if budget_usd is not None else dcfg["budget_usd"],
            "targets": {k: dcfg[k] for k in ("sources", "test_ideas", "max_cycles")},
            "rounds": [{"n": 1, "question": question, "started": now_iso()}],
            "cycles": [],
            "pack": pack,
            "models": dict(config.models),
            "gaps": [],
        }
        atomic_write(root / "project.json", json.dumps(state, indent=2) + "\n")
        prof = profiles.draft_profile(question, pack=pack, reader_level=reader_level)
        atomic_write(root / "profile.md", prof)
        (root / "claims.jsonl").touch()
        (root / "sources" / "index.jsonl").touch()
        if pack:
            profiles.install_pack(pack, root / "pack")
        atomic_write(base / CURRENT_FILE, root.name + "\n")
        proj = cls(root, config)
        proj.render_ideas()
        return proj

    @classmethod
    def open(cls, base: Path, slug: str | None = None, config: Config | None = None) -> "Project":
        base = Path(base)
        if slug is None:
            cur = base / CURRENT_FILE
            if cur.exists():
                slug = cur.read_text().strip()
            else:
                existing = [p for p in base.glob("*/project.json")] if base.exists() else []
                if len(existing) == 1:
                    slug = existing[0].parent.name
                else:
                    raise ProjectError(
                        "no project selected; pass --project SLUG "
                        f"(projects in {base}: {sorted(p.parent.name for p in existing) or 'none'})"
                    )
        root = base / slug
        if not root.exists() and Path(slug).exists():
            root = Path(slug)
        proj = cls(root, config)
        if root.parent == base:
            atomic_write(base / CURRENT_FILE, proj.root.name + "\n")
        return proj

    # ---- state ---------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text())

    def save_state(self, state: dict[str, Any]) -> None:
        atomic_write(self.state_path, json.dumps(state, indent=2) + "\n")

    def update_state(self, **kw: Any) -> dict[str, Any]:
        s = self.state()
        s.update(kw)
        self.save_state(s)
        return s

    def profile(self) -> dict[str, Any]:
        return profiles.parse_profile(self.profile_path.read_text())

    @property
    def current_round(self) -> int:
        return len(self.state()["rounds"])

    # ---- sources -------------------------------------------------------------
    def sources(self) -> list[dict[str, Any]]:
        return read_jsonl(self.sources_index)

    def source(self, sid: str) -> dict[str, Any] | None:
        return next((s for s in self.sources() if s["id"] == sid), None)

    def source_text(self, src: dict[str, Any]) -> str | None:
        if not src.get("file"):
            return None
        p = self.root / src["file"]
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None

    def add_source(
        self,
        title: str,
        url: str | None,
        text: str | None,
        kind: str = "other",
        captured_by: str = "gauntlet-fetch",
        unread_reason: str | None = None,
        agent: str | None = None,
    ) -> dict[str, Any]:
        rows = self.sources()
        replace_idx = None
        if url:
            for i, r in enumerate(rows):
                if r.get("url") == url:
                    if r.get("status") == "read" or text is None or unread_reason:
                        raise ProjectError(f"source already saved as {r['id']} ({r['status']}): {url}")
                    replace_idx = i  # an earlier attempt failed; this one has text
        sid = rows[replace_idx]["id"] if replace_idx is not None else _next_id("S", (r["id"] for r in rows))
        row: dict[str, Any] = {
            "id": sid,
            "title": title,
            "url": url,
            "kind": kind,
            "retrieved": now_iso(),
            "captured_by": captured_by,
            "agent": agent,
            "round": self.current_round,
        }
        if text is None or unread_reason:
            row.update(status="unread", unread_reason=unread_reason or "no text captured", file=None)
        else:
            path = self.sources_dir / f"{sid}.txt"
            atomic_write(path, text)
            row.update(status="read", file=str(path.relative_to(self.root)), sha256=sha256_file(path))
        if replace_idx is not None:
            rows[replace_idx] = row
            write_jsonl(self.sources_index, rows)
        else:
            append_jsonl(self.sources_index, row)
        return row

    # ---- claims --------------------------------------------------------------
    def claims(self) -> list[dict[str, Any]]:
        return read_jsonl(self.claims_path)

    def claim(self, cid: str) -> dict[str, Any]:
        for c in self.claims():
            if c["id"] == cid:
                return c
        raise ProjectError(f"no claim {cid}")

    def save_claims(self, claims: list[dict[str, Any]]) -> None:
        write_jsonl(self.claims_path, claims)
        self.render_ideas()

    def put_claim(self, claim: dict[str, Any]) -> None:
        claims = self.claims()
        for i, c in enumerate(claims):
            if c["id"] == claim["id"]:
                claims[i] = claim
                break
        else:
            claims.append(claim)
        self.save_claims(claims)

    def new_claim(self, statement: str, kind: str, agent: str | None = None, **extra: Any) -> dict[str, Any]:
        if kind not in ("sourced", "idea"):
            raise ProjectError("claim kind must be 'sourced' or 'idea'")
        claims = self.claims()
        prefix = "C" if kind == "sourced" else "I"
        cid = _next_id(prefix, (c["id"] for c in claims))
        claim: dict[str, Any] = {
            "id": cid,
            "kind": kind,
            "statement": statement.strip(),
            "label": "pending",
            "sources": [],
            "tests": [],
            "comparisons": [],
            "referee": [],
            "checks": {},
            "checks_passed": [],
            "history": [{"at": now_iso(), "event": "created", "by": agent}],
            "round": self.current_round,
            "agent": agent,
        }
        claim.update({k: v for k, v in extra.items() if v is not None})
        claims.append(claim)
        self.save_claims(claims)
        return claim

    # ---- evidence map --------------------------------------------------------
    def gaps(self) -> dict[str, str]:
        """Open gaps (G1, G2, ...) recorded by the synthesizer."""
        return {g["id"]: g["text"] for g in self.state().get("gaps", []) if g.get("open", True)}

    def set_evidence_map(self, agree: str, disagree: str, gaps: list[str], agent: str | None) -> dict[str, str]:
        """Write evidence_map.md. Gap ids are stable: a gap re-sent with the same
        text keeps its id; gaps not re-sent are closed."""
        s = self.state()
        known = {g["text"].strip().lower(): g for g in s.get("gaps", [])}
        nums = [int(g["id"][1:]) for g in s.get("gaps", [])]
        for g in s.get("gaps", []):
            g["open"] = False
        for text in gaps:
            key = text.strip().lower()
            if key in known:
                known[key]["open"] = True
            else:
                nxt = max(nums, default=0) + 1
                nums.append(nxt)
                g = {"id": f"G{nxt}", "text": text.strip(), "open": True, "round": len(s["rounds"])}
                s.setdefault("gaps", []).append(g)
                known[key] = g
        self.save_state(s)
        open_gaps = self.gaps()
        md = [f"# Evidence map\n", f"Question: {s['rounds'][-1]['question']}\n",
              f"_Written by {agent or 'synthesizer'} on {now_iso()[:10]}._\n",
              "## Agree\n", agree.strip() or "_none_", "", "## Disagree\n", disagree.strip() or "_none_", "",
              "## Gaps\n"]
        md += [f"- {gid}: {text}" for gid, text in open_gaps.items()] or ["_none_"]
        atomic_write(self.evidence_map_path, "\n".join(md) + "\n")
        return open_gaps

    # ---- ideas.md ------------------------------------------------------------
    def render_ideas(self) -> None:
        from .labels import display

        ideas = [c for c in self.claims() if c["kind"] == "idea"]
        gaps = self.gaps()
        lines = [f"# Ideas\n", "Generated from claims.jsonl by `gauntlet`. Do not edit by hand.\n"]
        if not ideas:
            lines.append("_No ideas proposed yet._\n")
        for c in ideas:
            lines.append(f"## {c['id']}: {c['statement']}\n")
            gap = c.get("gap")
            lines.append(f"- **Label:** {display(c['label'])}")
            lines.append(f"- **From gap:** {gap or '—'}" + (f" ({gaps[gap]})" if gap in gaps else ""))
            if c.get("rationale"):
                lines.append(f"- **Reasoning:** {c['rationale']}")
            lines.append(f"- **Test that would settle it:** {c.get('settling_test') or '—'}")
            for t in c.get("tests", []):
                rs = t.get("dev_runs", []) + t.get("held_out_runs", [])
                passed = sum(1 for r in rs if r.get("pass"))
                lines.append(f"- **Test {t['id']}** ({t['role']}, {t['agent']}): `{t['script']}` — "
                             f"{passed}/{len(rs)} runs passed")
            lines.append("")
        atomic_write(self.ideas_path, "\n".join(lines) + "\n")

    # ---- cost ledger ---------------------------------------------------------
    def ledger(self) -> list[dict[str, Any]]:
        return read_jsonl(self.ledger_path)

    def log_cost(self, row: dict[str, Any]) -> None:
        append_jsonl(self.ledger_path, row)


def _next_id(prefix: str, ids: Any) -> str:
    nums = [int(i[len(prefix):]) for i in ids if i.startswith(prefix) and i[len(prefix):].isdigit()]
    return f"{prefix}{max(nums, default=0) + 1}"


