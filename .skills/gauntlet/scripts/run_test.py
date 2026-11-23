#!/usr/bin/env python3
"""Run a test of an idea. Gauntlet freezes a copy of the script and runs it itself: on your
seeds, then (support and replication) on held-out seeds it picks at random.

  run_test.py IDEA_ID ROLE SCRIPT [--seeds 0,1] [--replicates TEST_ID]

ROLE is support (the test of the idea), replication (independently written code for test
--replicates), or counterexample (an attack: pass=false means the idea broke).
The script takes --seed N and ends by printing:
  GAUNTLET_RESULT {"pass": true, "headline": {"name": 8.1}}

Each run is limited (on Linux and macOS) to 120 s of CPU, $GAUNTLET_TEST_MEMORY_MB of memory
(default 4096) and 512 MB per file written. These limits stop runaway scripts; they are
not a security sandbox, and network access is left open for tests that download data.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from claim import claims, get_claim, put_claim
from source import ROOT, Parser, fail, finish, locked, sha256, write_file

MAX_TESTS = int(os.environ.get("GAUNTLET_MAX_TESTS", "60"))  # caps exploration cost
HELD_OUT_SEEDS = 3
TIMEOUT_S = 120
MEMORY_MB = int(os.environ.get("GAUNTLET_TEST_MEMORY_MB", "4096"))
FILE_MB = 512


def _limits() -> None:
    """Runs in the child process before the test script starts (POSIX only)."""
    import resource
    for limit, value in ((resource.RLIMIT_CPU, TIMEOUT_S), (resource.RLIMIT_AS, MEMORY_MB * 2**20),
                         (resource.RLIMIT_FSIZE, FILE_MB * 2**20)):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass  # some platforms do not support every limit


def is_stale(test: dict[str, Any]) -> bool:
    """The frozen script was edited (or removed) after it ran."""
    path = ROOT / test["script"]
    return not path.is_file() or sha256(path) != test["sha256"]


def _run(test: dict[str, Any], seed: int, held_out: bool) -> dict[str, Any]:
    cmd = [sys.executable, str(ROOT / test["script"]), "--seed", str(seed)]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S,
                              preexec_fn=_limits if os.name == "posix" else None)
        output, ok = proc.stdout + proc.stderr, proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, ok = f"timed out after {TIMEOUT_S}s", False
    log = f"runs/{test['id']}-seed{seed}.log"
    write_file(ROOT / log, output)
    result = None
    lines = [l.strip() for l in output.splitlines() if l.strip().startswith("GAUNTLET_RESULT")]
    if ok and lines:
        try:
            result = json.loads(lines[-1][len("GAUNTLET_RESULT"):])
        except json.JSONDecodeError:
            pass
    result = result if isinstance(result, dict) else None
    return {"seed": seed, "held_out": held_out, "log": log, "pass": None if result is None else bool(result.get("pass")),
            "headline": (result or {}).get("headline") or {}}


def execute(test: dict[str, Any]) -> dict[str, Any]:
    """(Re-)run a test in place: the author's seeds, then held-out seeds drawn at random."""
    test["sha256"] = sha256(ROOT / test["script"])
    held_out: list[int] = []
    while test["role"] != "counterexample" and len(held_out) < HELD_OUT_SEEDS:
        seed = random.SystemRandom().randrange(1000, 10**9)
        if seed not in test["seeds"] and seed not in held_out:
            held_out.append(seed)
    test["runs"] = [_run(test, s, False) for s in test["seeds"]] + [_run(test, s, True) for s in held_out]
    return test


def main() -> None:
    p = Parser(__doc__)
    p.add_argument("idea")
    p.add_argument("role", choices=("support", "replication", "counterexample"))
    p.add_argument("script")
    p.add_argument("--seeds", default="0")
    p.add_argument("--replicates")
    a = p.parse_args()

    idea = get_claim(a.idea)
    if "settling_test" not in idea:
        fail(f"{a.idea} is a claim from sources; tests are for ideas")
    if not Path(a.script).is_file():
        fail(f"no such script: {a.script}")
    if a.role == "replication" and not any(t["id"] == a.replicates and t["role"] == "support" for t in idea["tests"]):
        fail(f"--replicates must name a support test of {a.idea}: "
             f"{[t['id'] for t in idea['tests'] if t['role'] == 'support']}")

    if sum(len(c["tests"]) for c in claims()) >= MAX_TESTS:
        fail(f"the test limit ({MAX_TESTS}, set by GAUNTLET_MAX_TESTS) is reached; decide with the tests already run", 1)
    with locked():  # reserve a test id: the frozen script's file name claims it
        (ROOT / "runs").mkdir(exist_ok=True)
        n = len(idea["tests"]) + 1
        while (ROOT / "runs" / f"{a.idea}-T{n}.py").exists():
            n += 1
        test_id = f"{a.idea}-T{n}"
        shutil.copyfile(a.script, ROOT / "runs" / f"{test_id}.py")
    test = execute({"id": test_id, "role": a.role, "script": f"runs/{test_id}.py",
                    "seeds": [int(s) for s in a.seeds.split(",")], "replicates": a.replicates})
    with locked():  # re-read the idea: other tests may have been added while this one ran
        idea = get_claim(a.idea)
        idea["tests"].append(test)
        put_claim(idea)
    out = {"test": test_id, "runs": [{k: r[k] for k in ("seed", "held_out", "pass", "headline")} for r in test["runs"]]}
    broken = next((r for r in test["runs"] if r["pass"] is None), None)
    if broken:
        out["error_log"] = (ROOT / broken["log"]).read_text(errors="replace")[-1500:]
    finish(out)


if __name__ == "__main__":
    main()
