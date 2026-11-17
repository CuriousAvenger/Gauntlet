"""The harness runs tests itself. An agent writes a script; Gauntlet executes it
on the agent's development seeds and then on held-out seeds that it draws at
random and never discloses in advance, and keeps the logs. No agent supplies a
log, so no agent can misreport one.

Script contract: accept ``--seed N`` and print, as the last result line,
``GAUNTLET_RESULT {"pass": true|false, "headline": {"name": number}}``.
"""

from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path
from typing import Any

from .util import atomic_write, now_iso, parse_result_line, sha256_file

ROLES = ("support", "counterexample", "replication")
HELD_OUT_COUNT = 3
DEFAULT_TIMEOUT_S = 120
MAX_SEEDS = 10


class TestError(ValueError):
    pass


def resolve_script(project, script: str) -> tuple[Path, str]:
    p = Path(script)
    if not p.is_absolute():
        p = project.root / p
    p = p.resolve()
    root = project.root.resolve()
    if root not in p.parents:
        raise TestError(f"script must be inside the project folder {root} (write it under runs/<agent>/)")
    if not p.is_file():
        raise TestError(f"script not found: {script}. Write it first, under runs/<agent>/ in the project folder.")
    if "_harness" in p.relative_to(root).parts:
        raise TestError("scripts may not live under runs/_harness/")
    return p, str(p.relative_to(root))


def _command(path: Path, seed: int, args: list[str]) -> list[str]:
    head = [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]
    return head + list(args) + ["--seed", str(seed)]


def run_once(project, path: Path, seed: int, args: list[str], log: Path, timeout: int) -> dict[str, Any]:
    cmd = _command(path, seed, args)
    try:
        proc = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, timeout=timeout)
        out, code = proc.stdout + (f"\n[stderr]\n{proc.stderr}" if proc.stderr.strip() else ""), proc.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"[timeout after {timeout}s]\n{e.stdout or ''}", None
    except OSError as e:
        out, code = f"[could not start: {e}]", None
    atomic_write(log, f"# gauntlet run {now_iso()}\n# cmd: {' '.join(cmd)}\n# exit: {code}\n{out}")
    res = parse_result_line(out) if code == 0 else None
    return {
        "seed": seed,
        "pass": None if res is None else bool(res.get("pass")),
        "headline": (res or {}).get("headline") or {},
        "exit": code,
        "log": str(log.relative_to(project.root)),
        "error": None if res is not None else (f"exit code {code}" if code != 0 else "no GAUNTLET_RESULT line"),
    }


def held_out_seeds(dev: list[int], k: int = HELD_OUT_COUNT) -> list[int]:
    rng = random.SystemRandom()
    out: list[int] = []
    while len(out) < k:
        s = rng.randrange(1000, 10**9)
        if s not in dev and s not in out:
            out.append(s)
    return out


def execute(project, claim: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    """(Re-)run a test record in place: dev seeds, then fresh held-out seeds."""
    path, rel = resolve_script(project, test["script"])
    timeout = int(project.config.test_timeout_s)
    base = project.runs_dir / "_harness" / claim["id"]
    test["script_sha256"] = sha256_file(path)
    test["dev_runs"] = [run_once(project, path, s, test["args"], base / f"{test['id']}-dev-{s}.log", timeout)
                        for s in test["dev_seeds"]]
    test["held_out_runs"] = []
    if test["role"] != "counterexample":
        seeds = held_out_seeds(test["dev_seeds"])
        test["held_out_runs"] = [run_once(project, path, s, test["args"], base / f"{test['id']}-heldout-{s}.log",
                                          timeout) for s in seeds]
    test["ran"] = now_iso()
    return test


def new_test(project, claim: dict[str, Any], agent: str, script: str, role: str, dev_seeds: list[int],
             args: list[str] | None = None, replicates: str | None = None) -> dict[str, Any]:
    if role not in ROLES:
        raise TestError(f"role must be one of {ROLES}")
    if claim["kind"] != "idea":
        raise TestError(f"tests attach to ideas (I-ids); {claim['id']} is a claim from sources")
    if not dev_seeds or len(dev_seeds) > MAX_SEEDS:
        raise TestError(f"give 1-{MAX_SEEDS} development seeds")
    _, rel = resolve_script(project, script)
    if role == "replication":
        target = next((t for t in claim["tests"] if t["id"] == replicates), None)
        if target is None:
            raise TestError(f"replication needs `replicates` = the id of a support test on {claim['id']} "
                            f"(has: {[t['id'] for t in claim['tests'] if t['role'] == 'support'] or 'none'})")
        if target["role"] != "support":
            raise TestError(f"{replicates} is a {target['role']} test; only support tests are replicated")
    elif replicates:
        raise TestError("`replicates` is only for role=replication")
    test = {"id": f"T{len(claim['tests']) + 1}", "role": role, "agent": agent, "script": rel,
            "args": list(args or []), "dev_seeds": [int(s) for s in dev_seeds], "replicates": replicates}
    return execute(project, claim, test)


def runs(test: dict[str, Any]) -> list[dict[str, Any]]:
    return test.get("dev_runs", []) + test.get("held_out_runs", [])


def is_stale(project, test: dict[str, Any]) -> bool:
    """True if the script changed (or vanished) since the harness last ran it."""
    p = project.root / test["script"]
    return not p.is_file() or sha256_file(p) != test.get("script_sha256")


def summary(test: dict[str, Any]) -> dict[str, Any]:
    def brief(r):
        return {"seed": r["seed"], "pass": r["pass"], "headline": r["headline"], **({"error": r["error"]} if r["error"] else {})}
    return {"test": test["id"], "role": test["role"], "script": test["script"],
            "dev": [brief(r) for r in test.get("dev_runs", [])],
            "held_out": [brief(r) for r in test.get("held_out_runs", [])]}
