#!/usr/bin/env python3
"""Run a test of an idea. Gauntlet freezes a copy of the script and runs it itself: on your
seeds, then (support and replication) on held-out seeds it picks at random.

  run_test.py IDEA_ID ROLE SCRIPT [--seeds 0,1] [--replicates TEST_ID]

ROLE is support (the test of the idea), replication (independently written code for test
--replicates), or counterexample (an attack: pass=false means the idea broke).
The script takes --seed N and ends by printing:
  GAUNTLET_RESULT {"pass": true, "headline": {"name": 8.1}}
"""
import argparse
import shutil
from pathlib import Path

from common import ROOT, execute, fail, finish, get_claim, put_claim

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
    fail(f"--replicates must name a support test of {a.idea}: {[t['id'] for t in idea['tests'] if t['role'] == 'support']}")

test_id = f"{a.idea}-T{len(idea['tests']) + 1}"
(ROOT / "runs").mkdir(exist_ok=True)
shutil.copyfile(a.script, ROOT / "runs" / f"{test_id}.py")
test = execute({"id": test_id, "role": a.role, "script": f"runs/{test_id}.py",
                "seeds": [int(s) for s in a.seeds.split(",")], "replicates": a.replicates})
idea["tests"].append(test)
put_claim(idea)
out = {"test": test_id, "runs": [{k: r[k] for k in ("seed", "held_out", "pass", "headline")} for r in test["runs"]]}
broken = next((r for r in test["runs"] if r["pass"] is None), None)
if broken:
    out["error_log"] = (ROOT / broken["log"]).read_text(errors="replace")[-1500:]
finish(out)
