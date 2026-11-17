"""Held-out check: re-run a test on instances and seeds the author did not use.

Each test of an idea may carry a held-out spec:

    "held_out": {"cmd": "python runs/prover-1/test.py --seed {seed} --instances held-out",
                 "seeds": [101, 202, 303], "dev_seeds": [0, 1]}

The command runs from the project root with ``{seed}`` substituted. Every run
must print a ``GAUNTLET_RESULT {"pass": true, ...}`` line. Seeds must not
overlap the seeds used while developing the test (``dev_seeds``), which is what
catches answer-fitted simulations.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ..config import DEFAULT_HELD_OUT_SEEDS
from ..util import atomic_write, now_iso, parse_result_line
from . import CheckResult

TIMEOUT_S = 600


def run_one(project, cmd: str, seed: int, log_path: Path) -> tuple[bool, str]:
    full = cmd.replace("{seed}", str(seed))
    try:
        proc = subprocess.run(
            full, shell=True, cwd=project.root, capture_output=True, text=True, timeout=TIMEOUT_S,
        )
        out = proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
        code = proc.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"timeout after {TIMEOUT_S}s\n{e.stdout or ''}", -1
    atomic_write(log_path, f"# held-out run {now_iso()}\n# cmd: {full}\n# exit: {code}\n{out}")
    res = parse_result_line(out)
    if code != 0:
        return False, f"seed {seed}: exit code {code}"
    if res is None:
        return False, f"seed {seed}: no GAUNTLET_RESULT line"
    return bool(res.get("pass")), f"seed {seed}: pass={res.get('pass')} {_summary(res)}"


def _summary(res: dict) -> str:
    h = res.get("headline")
    return f"headline={h}" if h else ""


def check(project, claim, execute: bool = True) -> CheckResult:
    tests = [t for t in claim.get("tests", []) if t.get("role", "support") == "support"]
    if not tests:
        return CheckResult("held_out", False, ["no supporting tests recorded"])
    ok, details = True, []
    for t in tests:
        spec = t.get("held_out")
        tid = t.get("id")
        if not spec or not spec.get("cmd"):
            ok = False
            details.append(f"{tid}: no held-out command; tests must be re-run on new instances and seeds")
            continue
        seeds = [int(s) for s in spec.get("seeds") or DEFAULT_HELD_OUT_SEEDS]
        dev = {int(s) for s in spec.get("dev_seeds", [])}
        overlap = sorted(dev.intersection(seeds))
        if overlap:
            ok = False
            details.append(f"{tid}: held-out seeds {overlap} were also used during development")
            continue
        if not execute:
            prev = t.get("held_out_runs")
            if not prev:
                ok = False
                details.append(f"{tid}: not run (execution disabled and no previous runs)")
            else:
                passed = all(r["pass"] for r in prev)
                ok &= passed
                details.append(f"{tid}: previous held-out runs {'passed' if passed else 'FAILED'} (not re-run)")
            continue
        runs = []
        for s in seeds:
            log = project.runs_dir / "held_out" / f"{claim['id']}-{tid}-seed{s}.log"
            passed, why = run_one(project, spec["cmd"], s, log)
            runs.append({"seed": s, "pass": passed, "log": str(log.relative_to(project.root))})
            ok &= passed
            details.append(f"{tid}: {why}")
        t["held_out_runs"] = runs
    return CheckResult("held_out", ok, details)
