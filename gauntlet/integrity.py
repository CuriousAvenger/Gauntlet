"""Tamper evidence for a project's records, independent of any harness.

Every Gauntlet tool call ends by sealing the project: a digest of each evidence
file, signed with a key that lives outside the workspace (``~/.gauntlet/key`` or
``$GAUNTLET_STATE/key``). The next call verifies the seal first. If an agent (or
anyone) edited claims, sources, logs or the report by other means, the edit is
detected, recorded in the project, shown in the report, and every claim is
re-checked before work continues.

This makes edits evident, not impossible: an agent with shell access could read
the key. The report would still show the gap between the last seal and the edit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from .util import atomic_write, now_iso

SEAL = Path("runs") / "_harness" / "seal.json"
TRACKED_FILES = ("project.json", "claims.jsonl", "evidence_map.md", "answer.md", "report.md")
TRACKED_DIRS = ("sources", "runs/_harness")


def _key() -> bytes:
    base = Path(os.environ.get("GAUNTLET_STATE") or Path.home() / ".gauntlet")
    path = base / "key"
    if not path.exists():
        base.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(secrets.token_bytes(32))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    return path.read_bytes()


def _digests(root: Path) -> dict[str, str]:
    out = {}
    paths = [root / f for f in TRACKED_FILES]
    for d in TRACKED_DIRS:
        paths += sorted((root / d).rglob("*")) if (root / d).exists() else []
    for p in paths:
        if p.is_file() and p.relative_to(root) != SEAL:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _sign(digests: dict[str, str]) -> str:
    return hmac.new(_key(), json.dumps(digests, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def seal(project) -> None:
    d = _digests(project.root)
    atomic_write(project.root / SEAL, json.dumps({"at": now_iso(), "files": d, "sig": _sign(d)}, indent=1))


def verify(project) -> list[str]:
    """Files changed, added or removed since the last seal (empty = intact)."""
    path = project.root / SEAL
    if not path.exists():
        return []  # never sealed (new project)
    try:
        sealed = json.loads(path.read_text())
    except ValueError:
        return ["seal.json (unreadable)"]
    files = sealed.get("files", {})
    if not hmac.compare_digest(sealed.get("sig", ""), _sign(files)):
        return ["seal.json (signature does not match)"]
    now = _digests(project.root)
    changed = sorted(k for k in set(files) | set(now) if files.get(k) != now.get(k))
    return changed


def record_tampering(project, files: list[str]) -> dict[str, Any]:
    """Log an out-of-band edit, re-check every claim, and re-seal."""
    from . import labels

    s = project.state()
    event = {"at": now_iso(), "files": files[:50]}
    s.setdefault("integrity_events", []).append(event)
    project.save_state(s)
    changes = labels.audit(project, by="integrity", rerun_all=True)  # records are untrusted: re-run every test
    event["relabelled"] = changes
    s = project.state()
    s["integrity_events"][-1] = event
    project.save_state(s)
    seal(project)
    return event
