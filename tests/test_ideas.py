GOOD = """import argparse, json, random
p = argparse.ArgumentParser(); p.add_argument('--seed', type=int); a = p.parse_args()
r = 8.0 + random.Random(a.seed).uniform(-0.2, 0.2)
print('GAUNTLET_RESULT ' + json.dumps({'pass': r > 7, 'headline': {'ratio': r}}))
"""
FITTED = GOOD.replace("8.0 + random.Random(a.seed).uniform(-0.2, 0.2)", "8.0 if a.seed in (0, 1) else 1.0")
INFLATED = GOOD.replace("8.0 + random.Random(a.seed).uniform(-0.2, 0.2)", "11.3")
BROKEN = GOOD.replace("r > 7", "r > 99")


def idea(run, tmp_path, support=GOOD, replica=None, counter=None, seeds="0"):
    iid = run("claim.py", "p", stdin={"statement": "The reduction holds on random instances.",
                                      "settling_test": "ratio above 7 on random instances"})[1]["id"]
    for role, code, extra in (("support", support, ["--seeds", seeds]), ("replication", replica, ["--replicates", f"{iid}-T1"]),
                              ("counterexample", counter, [])):
        if code:
            (tmp_path / f"{role}.py").write_text(code + ("# written independently\n" if role == "replication" else ""))
            assert run("run_test.py", "p", iid, role, f"{role}.py", *extra)[0] == 0
    return iid


def missing(run, iid, label="tested"):
    code, out = run("label.py", "p", iid, label)
    return " ".join(out.get("missing", [])) if code else ""


def test_tested_needs_held_out_and_replication(run, tmp_path):
    assert missing(run, idea(run, tmp_path, replica=GOOD)) == ""
    assert "independently written" in missing(run, idea(run, tmp_path))
    assert "passed only on its own seeds" in missing(run, idea(run, tmp_path, FITTED, replica=GOOD, seeds="0,1"))
    assert "more than 10% apart" in missing(run, idea(run, tmp_path, replica=INFLATED))


def test_counterexample_blocks_and_refutes(run, tmp_path):
    iid = idea(run, tmp_path, replica=GOOD, counter=BROKEN)
    assert "counterexample broke" in missing(run, iid)
    assert missing(run, iid, "refuted") == ""


def test_held_out_seeds_are_drawn_by_gauntlet(run, tmp_path):
    iid = idea(run, tmp_path, replica=GOOD)
    import json
    test = json.loads((tmp_path / "research/p/claims.jsonl").read_text().splitlines()[0])["tests"][0]
    held = [r["seed"] for r in test["runs"] if r["held_out"]]
    assert len(held) == 3 and 0 not in held
