import sys

from gauntlet import labels
from gauntlet.evaluation import planted_errors

TEXT_A = "Sleep deprivation after learning impairs the consolidation of declarative memories in adults."
TEXT_B = "Across trials, sleep deprivation after learning impairs the consolidation of declarative memories."
TEXT_C = "In older adults, sleep deprivation after learning did not impair the consolidation of declarative memories."
PA = "sleep deprivation after learning impairs the consolidation of declarative memories"


def _setup(proj):
    proj.add_source("A", "https://ex.org/a", TEXT_A, kind="peer-reviewed")
    proj.add_source("B", "https://ex.org/b", TEXT_B, kind="meta-analysis")
    proj.add_source("C", "https://ex.org/c", TEXT_C, kind="peer-reviewed")


def _referee_all(proj, cid, by="referee-1"):
    c = proj.claim(cid)
    c["referee"] = [{"source_index": i, "verdict": "supports", "by": by} for i in range(len(c["sources"]))]
    proj.put_claim(c)


def test_label_gate_and_history(proj):
    _setup(proj)
    c = proj.new_claim("Sleep deprivation after learning impairs memory consolidation.", "sourced", agent="reader-1")
    c["sources"] = [{"source_id": "S1", "passage": PA, "side": "for"}]
    proj.put_claim(c)
    ok, unmet, _ = labels.set_label(proj, c["id"], "reported")
    assert not ok and any("referee" in u for u in unmet)
    _referee_all(proj, c["id"])
    assert labels.set_label(proj, c["id"], "reported")[0]
    assert not labels.set_label(proj, c["id"], "established")[0]
    assert not labels.set_label(proj, c["id"], "tested")[0]  # wrong kind
    c = proj.claim(c["id"])
    c["sources"].append({"source_id": "S2", "passage": PA, "side": "for"})
    proj.put_claim(c)
    _referee_all(proj, c["id"])
    assert labels.set_label(proj, c["id"], "established")[0]
    events = [h["event"] for h in proj.claim(c["id"])["history"]]
    assert events.count("label") == 2 and "label-refused" in events


def test_contested_needs_both_sides(proj):
    _setup(proj)
    c = proj.new_claim("Sleep deprivation after learning impairs memory consolidation.", "sourced", agent="reader-1")
    c["sources"] = [{"source_id": "S1", "passage": PA, "side": "for"},
                    {"source_id": "S3", "passage": "did not impair the consolidation of declarative memories", "side": "against"}]
    proj.put_claim(c)
    _referee_all(proj, c["id"])
    assert not labels.set_label(proj, c["id"], "established")[0]
    assert not labels.set_label(proj, c["id"], "reported")[0]
    assert labels.set_label(proj, c["id"], "contested")[0]


def test_audit_downgrades_when_evidence_disappears(proj):
    _setup(proj)
    c = proj.new_claim("Sleep deprivation after learning impairs memory consolidation.", "sourced", agent="reader-1")
    c["sources"] = [{"source_id": "S1", "passage": PA, "side": "for"}, {"source_id": "S2", "passage": PA, "side": "for"}]
    proj.put_claim(c)
    _referee_all(proj, c["id"])
    assert labels.set_label(proj, c["id"], "established")[0]
    c = proj.claim(c["id"])
    c["referee"].append({"source_index": 1, "verdict": "does-not-support", "by": "referee-2"})
    proj.put_claim(c)
    changes = labels.audit(proj)
    assert changes and changes[0]["to"] == "pending"  # S2 verdict now negative -> support fails for all labels


def test_untested_idea_needs_settling_test(proj):
    c = proj.new_claim("A nap restores consolidation.", "idea", agent="ideator-1")
    assert not labels.set_label(proj, c["id"], "untested")[0]
    c = proj.claim(c["id"])
    c["settling_test"] = "randomised nap trial"
    proj.put_claim(c)
    assert labels.set_label(proj, c["id"], "untested")[0]


def test_planted_errors_eval(tmp_path):
    res = planted_errors(base=tmp_path)
    missed = [o[0] for o in res["outcomes"] if not o[2]]
    assert res["passed"], missed
    assert res["caught"] == res["planted"], missed
