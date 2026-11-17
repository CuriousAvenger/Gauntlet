"""Runs test scripts itself, so no agent can misreport a result.

A test script takes `--seed N` and prints `GAUNTLET_RESULT {"pass": bool, "headline": {...}}`.
Gauntlet freezes a copy, runs it on the author's seeds, then (except counterexamples) on
held-out seeds it draws at random, and keeps every log. Editing the frozen copy later is
detected by its hash.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .store import sha256, write_file

ROLES = ("support", "replication", "counterexample")
HELD_OUT = 3
TIMEOUT_S = 120


def is_stale(project, test: dict[str, Any]) -> bool:
    path = project.root / test["script"]
    return not path.is_file() or sha256(path) != test["sha256"]


def _result(output: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        if line.strip().startswith("GAUNTLET_RESULT"):
            try:
                result = json.loads(line.strip()[len("GAUNTLET_RESULT"):])
            except json.JSONDecodeError:
                return None
            return result if isinstance(result, dict) else None
    return None


def _run(project, test: dict[str, Any], seed: int, held_out: bool) -> dict[str, Any]:
    cmd = [sys.executable, str(project.root / test["script"]), "--seed", str(seed)]
    try:
        proc = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, timeout=TIMEOUT_S)
        output, ok = proc.stdout + proc.stderr, proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, ok = f"timed out after {TIMEOUT_S}s", False
    log = f"runs/{test['id']}-seed{seed}.log"
    write_file(project.root / log, output)
    result = _result(output) if ok else None
    return {"seed": seed, "held_out": held_out, "log": log,
            "pass": None if result is None else bool(result.get("pass")),
            "headline": (result or {}).get("headline") or {}}


def execute(project, test: dict[str, Any]) -> dict[str, Any]:
    """(Re-)run in place: the author's seeds, then fresh held-out seeds."""
    test["sha256"] = sha256(project.root / test["script"])
    held_out: list[int] = []
    if test["role"] != "counterexample":
        rng = random.SystemRandom()
        while len(held_out) < HELD_OUT:
            seed = rng.randrange(1000, 10**9)
            if seed not in test["seeds"] and seed not in held_out:
                held_out.append(seed)
    test["runs"] = ([_run(project, test, s, False) for s in test["seeds"]]
                    + [_run(project, test, s, True) for s in held_out])
    return test


def new_test(project, claim: dict[str, Any], script: Path, role: str, seeds: list[int],
             replicates: str | None = None) -> dict[str, Any]:
    tid = f"{claim['id']}-T{len(claim['tests']) + 1}"
    frozen = f"runs/{tid}.py"
    (project.root / "runs").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(script, project.root / frozen)
    return execute(project, {"id": tid, "role": role, "script": frozen, "seeds": seeds, "replicates": replicates})
