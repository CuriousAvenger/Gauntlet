import pytest
from conftest import PASSAGE

from gauntlet.protocol import ToolError

GOOD = """import argparse, json, random
p = argparse.ArgumentParser(); p.add_argument('--seed', type=int); a = p.parse_args()
r = 8.0 + random.Random(a.seed).uniform(-0.2, 0.2)
print('GAUNTLET_RESULT ' + json.dumps({'pass': r > 7, 'headline': {'ratio': r}}))
"""
FITTED = GOOD.replace("8.0 + random.Random(a.seed).uniform(-0.2, 0.2)", "8.0 if a.seed in (0, 1) else 1.0")
INFLATED = GOOD.replace("8.0 + random.Random(a.seed).uniform(-0.2, 0.2)", "11.3")
BROKEN = GOOD.replace("r > 7", "r > 99")


def sourced(call, *sources, against=None):
    ev = [{"source_id": s, "passage": PASSAGE} for s in sources]
    if against:
        ev.append({"source_id": against, "passage": PASSAGE, "side": "against"})
    return call("record_claim", statement="Shots fell 8.0-fold.", evidence=ev)["claim_id"]


def idea(call, support=GOOD, replica=None, counter=None, dev=(0,)):
    call("record_evidence_map", agree="", disagree="", gaps=["turbulent regime"])
    iid = call("propose_idea", statement="The 8-fold reduction holds on random instances.", gap="G1",
               settling_test="random instances, ratio above 7")["idea_id"]
    call("run_test", idea_id=iid, code=support, role="support", dev_seeds=list(dev))
    if replica:
        call("run_test", idea_id=iid, code=replica + "# independent\n", role="replication", replicates="T1")
    if counter:
        call("run_test", idea_id=iid, code=counter, role="counterexample")
    return iid


def refused(call, cid, label):
    with pytest.raises(ToolError) as e:
        call("set_label", claim_id=cid, label=label)
    return str(e.value)


def test_sourced_labels(call, project):
    one = sourced(call, "S1")
    assert "2+ independent" in refused(call, one, "established")
    call("set_label", claim_id=one, label="reported")
    call("set_label", claim_id=sourced(call, "S1", "S2"), label="established")
    both = sourced(call, "S1", against="S2")
    assert "disagrees" in refused(call, both, "reported")
    call("set_label", claim_id=both, label="contested")
    assert "new idea" in refused(call, one, "tested")


def test_high_stakes_needs_authoritative_source(call, project):
    s = project.state()
    s["high_stakes"] = True
    project.save_state(s)
    assert "high-stakes" in refused(call, sourced(call, "S1", "S2"), "established")


def test_tested_idea(call, project):
    call("set_label", claim_id=idea(call, replica=GOOD), label="tested")


def test_answer_fitted_fails_held_out(call, project):
    msg = refused(call, idea(call, FITTED, replica=GOOD, dev=(0, 1)), "tested")
    assert "passed only on its development seeds" in msg


def test_replication_required_and_compared(call, project):
    assert "needs an independent replication" in refused(call, idea(call), "tested")
    assert "over 10% apart" in refused(call, idea(call, replica=INFLATED), "tested")
    copy = idea(call)
    call("run_test", idea_id=copy, code=GOOD, role="replication", replicates="T1")  # same code is not independent
    assert "needs an independent replication" in refused(call, copy, "tested")


def test_counterexample_blocks_and_refutes(call, project):
    iid = idea(call, replica=GOOD, counter=BROKEN)
    assert "counterexample broke" in refused(call, iid, "tested")
    call("set_label", claim_id=iid, label="refuted")


def test_report_reaudit_refutes_changed_code(call, project):
    iid = idea(call, replica=GOOD)
    call("set_label", claim_id=iid, label="tested")
    (project.root / project.claim(iid)["tests"][0]["script"]).write_text(BROKEN)
    call("write_report", answer="No claims are cited in this answer.", draft=True)
    assert project.claim(iid)["label"] == "refuted"
