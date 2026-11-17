"""The harness runs tests itself, so no agent can misreport a result.

A test is a Python script that accepts `--seed N` and prints
`GAUNTLET_RESULT {"pass": true|false, "headline": {"name": number}}`. Gauntlet saves
it, runs it on the author's development seeds, then (for support and replication
tests) on held-out seeds it draws at random afterwards, and keeps every log.
"""

from __future__ import annotations

import random
import subprocess
import sys
from typing import Any

from .util import atomic_write, now_iso, parse_result, sha256_file

ROLES = ("support", "counterexample", "replication")
HELD_OUT_SEEDS = 3
TIMEOUT_S = 120


class TestError(ValueError):
    pass


def runs(test: dict[str, Any]) -> list[dict[str, Any]]:
    return test["dev_runs"] + test["held_out_runs"]


def is_stale(project, test: dict[str, Any]) -> bool:
    """The script changed or vanished since the harness last ran it."""
    path = project.root / test["script"]
    return not path.is_file() or sha256_file(path) != test["sha256"]


def _run_once(project, test: dict[str, Any], seed: int, kind: str) -> dict[str, Any]:
    cmd = [sys.executable, str(project.root / test["script"]), "--seed", str(seed)]
    try:
        proc = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, timeout=TIMEOUT_S)
        out, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        out, code = f"timeout after {TIMEOUT_S}s", None
    log = f"runs/{test['idea']}/{test['id']}-{kind}-{seed}.log"
    atomic_write(project.root / log, out)
    result = parse_result(out) if code == 0 else None
    return {"seed": seed, "pass": None if result is None else bool(result.get("pass")),
            "headline": (result or {}).get("headline") or {}, "log": log,
            "error": None if result is not None else (f"exit code {code}" if code != 0 else "no GAUNTLET_RESULT line")}


def execute(project, test: dict[str, Any]) -> dict[str, Any]:
    """(Re-)run a test in place: development seeds, then fresh held-out seeds."""
    test["sha256"] = sha256_file(project.root / test["script"])
    test["dev_runs"] = [_run_once(project, test, s, "dev") for s in test["dev_seeds"]]
    test["held_out_runs"] = []
    if test["role"] != "counterexample":
        rng = random.SystemRandom()
        seeds = set()
        while len(seeds) < HELD_OUT_SEEDS:
            s = rng.randrange(1000, 10**9)
            if s not in test["dev_seeds"]:
                seeds.add(s)
        test["held_out_runs"] = [_run_once(project, test, s, "heldout") for s in sorted(seeds)]
    test["ran"] = now_iso()
    return test


def new_test(project, idea: dict[str, Any], code: str, role: str, dev_seeds: list[int],
             replicates: str | None = None) -> dict[str, Any]:
    if idea["kind"] != "idea":
        raise TestError(f"tests attach to ideas (I-ids); {idea['id']} is a claim from sources")
    if role not in ROLES:
        raise TestError(f"role must be one of {ROLES}")
    if role == "replication":
        target = next((t for t in idea["tests"] if t["id"] == replicates and t["role"] == "support"), None)
        if target is None:
            raise TestError(f"replication needs `replicates` set to a support test of {idea['id']}")
    tid = f"T{len(idea['tests']) + 1}"
    script = f"runs/{idea['id']}/{tid}.py"
    atomic_write(project.root / script, code)
    test = {"id": tid, "idea": idea["id"], "role": role, "script": script,
            "dev_seeds": dev_seeds or [0], "replicates": replicates}
    return execute(project, test)
