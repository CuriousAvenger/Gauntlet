"""Quote check: every quoted passage exists in the saved source text.

Matching is exact after normalisation (case, whitespace, curly quotes, dashes,
hyphenated line breaks). A passage may use '...' to skip text; the fragments
must then appear in order. Whether the passage *supports* the claim is a
judgement recorded by the referee (see support.py), not something a string
match can decide.
"""

from __future__ import annotations

import re

from ..util import normalize_text, sha256_file
from . import CheckResult

MIN_PASSAGE_CHARS = 20


def find_passage(passage: str, source_text: str) -> tuple[bool, str]:
    hay = normalize_text(source_text)
    frags = [normalize_text(f) for f in re.split(r"\.\.\.|…|\[\.\.\.\]", passage)]
    frags = [f.strip(" .") for f in frags if f.strip(" .")]
    if not frags:
        return False, "empty passage"
    pos = 0
    for frag in frags:
        idx = hay.find(frag, pos)
        if idx < 0:
            return False, f"not found: {_closest(frag, hay)}"
        pos = idx + len(frag)
    return True, "found"


def _closest(frag: str, hay: str) -> str:
    """Describe how much of the fragment does match, to help the agent fix it."""
    lo, hi = 0, len(frag)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if frag[:mid] in hay:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return f"no part of {frag[:60]!r} appears in the source"
    return f"first {lo}/{len(frag)} chars match; diverges at {frag[lo:lo + 40]!r}"


def check(project, claim) -> CheckResult:
    details, ok = [], True
    if not claim.get("sources"):
        return CheckResult("quote", False, ["claim cites no sources"])
    for i, ev in enumerate(claim["sources"]):
        sid = ev.get("source_id")
        src = project.source(sid)
        tag = f"[{i}] {sid}"
        if src is None:
            ok = False
            details.append(f"{tag}: source not saved")
            continue
        if src.get("status") != "read":
            ok = False
            details.append(f"{tag}: source is unread ({src.get('unread_reason')}); unread sources cannot be cited")
            continue
        path = project.root / src["file"]
        if not path.exists():
            ok = False
            details.append(f"{tag}: saved text missing at {src['file']}")
            continue
        if src.get("sha256") and sha256_file(path) != src["sha256"]:
            ok = False
            details.append(f"{tag}: saved text was modified after capture (hash mismatch)")
            continue
        passage = ev.get("passage", "")
        if len(normalize_text(passage)) < MIN_PASSAGE_CHARS:
            ok = False
            details.append(f"{tag}: passage shorter than {MIN_PASSAGE_CHARS} chars; quote a full sentence")
            continue
        found, why = find_passage(passage, path.read_text(encoding="utf-8", errors="replace"))
        ok &= found
        details.append(f"{tag}: {why}")
    return CheckResult("quote", ok, details)
