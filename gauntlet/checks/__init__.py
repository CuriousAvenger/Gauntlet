"""Automatic checks that must pass before a label is set.

Each module exposes ``check(project, claim, **kw) -> CheckResult``. Checks read
saved files (sources, logs) directly: a command's output outranks any agent's
report, so cached values in claims.jsonl are never trusted by a check.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..util import now_iso


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)
    at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def applicable_checks(claim: dict[str, Any]) -> list[str]:
    names = ["provenance", "like_for_like"]
    if claim.get("sources"):
        names = ["quote", "support"] + names
    if claim["kind"] == "idea" and claim.get("tests"):
        names += ["held_out", "replication"]
    return names


def run_checks(project, claim: dict[str, Any], execute: bool = True) -> dict[str, CheckResult]:
    from . import held_out, like_for_like, provenance, quote_check, replication, support

    registry = {
        "quote": quote_check.check,
        "support": support.check,
        "provenance": provenance.check,
        "like_for_like": like_for_like.check,
        "held_out": lambda p, c: held_out.check(p, c, execute=execute),
        "replication": replication.check,
    }
    return {name: registry[name](project, claim) for name in applicable_checks(claim)}


def record_results(claim: dict[str, Any], results: dict[str, CheckResult]) -> None:
    claim["checks"] = {k: v.to_dict() for k, v in results.items()}
    claim["checks_passed"] = sorted(k for k, v in results.items() if v.passed)
