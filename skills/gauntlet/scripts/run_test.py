#!/usr/bin/env python3
"""Run a test of an idea. Gauntlet freezes a copy of the script and runs it itself: on your
seeds, then (support and replication) on held-out seeds it picks at random.

  run_test.py PROJECT IDEA_ID ROLE SCRIPT [--seeds 0,1] [--replicates TEST_ID]

ROLE is support (the test of the idea), replication (independently written code for test
--replicates), or counterexample (an attack: pass=false means the idea broke).
The script takes --seed N and ends by printing:
  GAUNTLET_RESULT {"pass": true, "headline": {"name": 8.1}}
"""
import argparse
from pathlib import Path

from lib.cli import fail, finish
from lib.runner import ROLES, new_test
from lib.store import Project

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("project"); p.add_argument("idea"); p.add_argument("role", choices=ROLES); p.add_argument("script")
p.add_argument("--seeds", default="0"); p.add_argument("--replicates")
a = p.parse_args()

project = Project(a.project)
try:
    idea = project.claim(a.idea)
except KeyError as e:
    fail(str(e))
if "settling_test" not in idea:
    fail(f"{a.idea} is a claim from sources; tests are for ideas")
if not Path(a.script).is_file():
    fail(f"no such script: {a.script}")
if a.role == "replication" and not any(t["id"] == a.replicates and t["role"] == "support" for t in idea["tests"]):
    fail(f"--replicates must name a support test of {a.idea}: {[t['id'] for t in idea['tests'] if t['role'] == 'support']}")
test = new_test(project, idea, Path(a.script), a.role, [int(s) for s in a.seeds.split(",")], a.replicates)
idea["tests"].append(test)
project.put(idea)
out = {"test": test["id"], "runs": [{k: r[k] for k in ("seed", "held_out", "pass", "headline")} for r in test["runs"]]}
broken = next((r for r in test["runs"] if r["pass"] is None), None)
if broken:
    out["error_log"] = (project.root / broken["log"]).read_text(errors="replace")[-1500:]
finish(out)
