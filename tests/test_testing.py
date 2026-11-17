import pytest

from gauntlet import testing

OK = "import argparse,json\np=argparse.ArgumentParser();p.add_argument('--seed',type=int);a=p.parse_args()\nprint('GAUNTLET_RESULT '+json.dumps({'pass':True,'headline':{'x':1.0}}))\n"


def _idea(proj):
    c = proj.new_claim("An idea worth testing here.", "idea", agent="ideator-1", settling_test="run it")
    return c


def test_runs_dev_and_random_held_out(proj):
    c = _idea(proj)
    (proj.root / "runs/p1").mkdir(parents=True)
    (proj.root / "runs/p1/t.py").write_text(OK)
    t = testing.new_test(proj, c, "p1", "runs/p1/t.py", "support", [0, 1])
    assert [r["seed"] for r in t["dev_runs"]] == [0, 1]
    held = [r["seed"] for r in t["held_out_runs"]]
    assert len(held) == 3 and not set(held) & {0, 1}
    assert all(r["pass"] for r in testing.runs(t))
    assert (proj.root / t["dev_runs"][0]["log"]).exists()
    assert not testing.is_stale(proj, t)
    (proj.root / "runs/p1/t.py").write_text(OK + "# edited\n")
    assert testing.is_stale(proj, t)


def test_crash_and_missing_result(proj):
    c = _idea(proj)
    (proj.root / "runs/p1").mkdir(parents=True)
    (proj.root / "runs/p1/bad.py").write_text("raise SystemExit(3)\n")
    t = testing.new_test(proj, c, "p1", "runs/p1/bad.py", "counterexample", [5])
    assert t["dev_runs"][0]["pass"] is None and "exit code 3" in t["dev_runs"][0]["error"]
    assert t["held_out_runs"] == []


def test_rejects_scripts_outside_project(proj, tmp_path):
    c = _idea(proj)
    (tmp_path / "evil.py").write_text(OK)
    with pytest.raises(testing.TestError):
        testing.new_test(proj, c, "p1", str(tmp_path / "evil.py"), "support", [0])
    with pytest.raises(testing.TestError):
        testing.new_test(proj, c, "p1", "runs/p1/missing.py", "support", [0])


def test_replication_needs_target(proj):
    c = _idea(proj)
    (proj.root / "runs/p1").mkdir(parents=True)
    (proj.root / "runs/p1/t.py").write_text(OK)
    with pytest.raises(testing.TestError):
        testing.new_test(proj, c, "p2", "runs/p1/t.py", "replication", [0], replicates="T9")
