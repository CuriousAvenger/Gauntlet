"""A project folder per question: everything needed to audit or continue it.

research/<slug>/
  project.json       question, depth, rounds, flags, gaps
  sources/           index.jsonl + S<n>.txt (text saved by Gauntlet, hashed)
  claims.jsonl       claims and ideas with their evidence, tests and labels
  evidence_map.md    agree / disagree / gaps
  runs/              test scripts and the harness's logs
  report.md
"""

from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from .util import atomic_write, now_iso, read_jsonl, sha256_file, slugify, write_jsonl

DEPTHS = {
    "quick": {"sources": 10, "test_ideas": 0, "max_cycles": 1},
    "standard": {"sources": 30, "test_ideas": 3, "max_cycles": 1},
    "deep": {"sources": 50, "test_ideas": 5, "max_cycles": 6},
}
ACTIVE = ".active"


class ProjectError(Exception):
    pass


def research_home() -> Path:
    return Path(os.environ.get("GAUNTLET_HOME") or Path.cwd() / "research")


def available_packs() -> list[str]:
    root = resources.files("gauntlet").joinpath("packs")
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        if not (self.root / "project.json").exists():
            raise ProjectError(f"not a Gauntlet project: {self.root}")
        self.state_path = self.root / "project.json"
        self.sources_dir = self.root / "sources"
        self.claims_path = self.root / "claims.jsonl"
        self.evidence_map_path = self.root / "evidence_map.md"
        self.report_path = self.root / "report.md"
        self.pack_dir = self.root / "pack"

    @property
    def slug(self) -> str:
        return self.root.name

    # ---- lifecycle -------------------------------------------------------------
    @classmethod
    def create(cls, question: str, depth: str = "standard", high_stakes: bool = False,
               reader_level: str = "general", pack: str | None = None, base: Path | None = None) -> "Project":
        if depth not in DEPTHS:
            raise ProjectError(f"depth must be one of {list(DEPTHS)}")
        base = base or research_home()
        root, n = base / slugify(question), 2
        while root.exists():
            root, n = base / f"{slugify(question)}-{n}", n + 1
        (root / "sources").mkdir(parents=True)
        state = {"question": question, "depth": depth, "targets": DEPTHS[depth], "high_stakes": high_stakes,
                 "reader_level": reader_level, "created": now_iso(), "gaps": [],
                 "rounds": [{"n": 1, "question": question, "started": now_iso()}]}
        atomic_write(root / "project.json", json.dumps(state, indent=2))
        if pack and Path(pack).is_dir():
            shutil.copytree(pack, root / "pack")
        elif pack in available_packs():
            with resources.as_file(resources.files("gauntlet").joinpath("packs", pack)) as built_in:
                shutil.copytree(built_in, root / "pack")
        elif pack:
            shutil.rmtree(root)
            raise ProjectError(f"unknown pack {pack!r}; built in: {available_packs()}, or give a directory")
        atomic_write(base / ACTIVE, root.name)
        return cls(root)

    @classmethod
    def open(cls, slug: str | None = None, base: Path | None = None) -> "Project":
        base = base or research_home()
        if slug is None:
            active = base / ACTIVE
            if not active.exists():
                raise ProjectError("no active project; call start_research first")
            slug = active.read_text().strip()
        if not (base / slug / "project.json").exists():
            raise ProjectError(f"no project {slug!r} in {base}")
        atomic_write(base / ACTIVE, slug)
        return cls(base / slug)

    def state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text())

    def save_state(self, state: dict[str, Any]) -> None:
        atomic_write(self.state_path, json.dumps(state, indent=2))

    # ---- sources ---------------------------------------------------------------
    def sources(self) -> list[dict[str, Any]]:
        return read_jsonl(self.sources_dir / "index.jsonl")

    def source(self, sid: str) -> dict[str, Any] | None:
        return next((s for s in self.sources() if s["id"] == sid), None)

    def source_text(self, src: dict[str, Any]) -> str | None:
        path = self.root / src["file"] if src.get("file") else None
        return path.read_text(encoding="utf-8", errors="replace") if path and path.exists() else None

    def add_source(self, title: str, url: str | None, kind: str, text: str | None,
                   unread_reason: str | None = None, captured_by: str = "gauntlet") -> dict[str, Any]:
        rows = self.sources()
        old = next((i for i, r in enumerate(rows) if url and r.get("url") == url), None)
        if old is not None and (rows[old]["status"] == "read" or text is None):
            raise ProjectError(f"already saved as {rows[old]['id']}: {url}")
        sid = rows[old]["id"] if old is not None else f"S{len(rows) + 1}"
        row = {"id": sid, "title": title, "url": url, "kind": kind, "saved": now_iso(), "captured_by": captured_by}
        if text is None or unread_reason:
            row.update(status="unread", unread_reason=unread_reason or "no text")
        else:
            path = self.sources_dir / f"{sid}.txt"
            atomic_write(path, text)
            row.update(status="read", file=f"sources/{sid}.txt", sha256=sha256_file(path))
        if old is not None:
            rows[old] = row
        else:
            rows.append(row)
        write_jsonl(self.sources_dir / "index.jsonl", rows)
        return row

    # ---- claims ----------------------------------------------------------------
    def claims(self) -> list[dict[str, Any]]:
        return read_jsonl(self.claims_path)

    def claim(self, cid: str) -> dict[str, Any]:
        for c in self.claims():
            if c["id"] == cid:
                return c
        raise ProjectError(f"no claim {cid}")

    def save_claims(self, claims: list[dict[str, Any]]) -> None:
        write_jsonl(self.claims_path, claims)

    def put_claim(self, claim: dict[str, Any]) -> None:
        claims = self.claims()
        idx = next((i for i, c in enumerate(claims) if c["id"] == claim["id"]), None)
        if idx is None:
            claims.append(claim)
        else:
            claims[idx] = claim
        self.save_claims(claims)

    def new_claim(self, kind: str, statement: str, **fields: Any) -> dict[str, Any]:
        prefix = "C" if kind == "sourced" else "I"
        n = 1 + sum(1 for c in self.claims() if c["id"].startswith(prefix))
        claim = {"id": f"{prefix}{n}", "kind": kind, "statement": statement.strip(), "label": "pending",
                 "sources": [], "tests": [], "round": len(self.state()["rounds"]), **fields}
        self.put_claim(claim)
        return claim

    # ---- evidence map ------------------------------------------------------------
    def gaps(self) -> dict[str, str]:
        return {g["id"]: g["text"] for g in self.state()["gaps"] if g["open"]}

    def set_evidence_map(self, agree: str, disagree: str, gaps: list[str]) -> dict[str, str]:
        """A gap re-sent with the same text keeps its id; gaps not re-sent are closed."""
        s = self.state()
        by_text = {g["text"].lower(): g for g in s["gaps"]}
        for g in s["gaps"]:
            g["open"] = False
        for text in gaps:
            g = by_text.get(text.strip().lower())
            if g is None:
                g = {"id": f"G{len(s['gaps']) + 1}", "text": text.strip()}
                s["gaps"].append(g)
            g["open"] = True
        self.save_state(s)
        open_gaps = self.gaps()
        md = ["# Evidence map", "", "## Agree", "", agree.strip(), "", "## Disagree", "", disagree.strip(), "",
              "## Gaps", ""] + [f"- {gid}: {text}" for gid, text in open_gaps.items()]
        atomic_write(self.evidence_map_path, "\n".join(md) + "\n")
        return open_gaps
