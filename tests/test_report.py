from gauntlet import labels, report


def _labelled(proj):
    proj.add_source("A", "https://ex.org/a", "The drug lowered blood pressure by 10 mmHg in adults.", kind="peer-reviewed")
    c = proj.new_claim("The drug lowered blood pressure by 10 mmHg in adults.", "sourced", agent="reader-1")
    c["sources"] = [{"source_id": "S1", "passage": "The drug lowered blood pressure by 10 mmHg in adults.", "side": "for"}]
    c["referee"] = [{"source_index": 0, "verdict": "supports", "by": "referee-1"}]
    proj.put_claim(c)
    assert labels.set_label(proj, "C1", "reported")[0]
    i = proj.new_claim("Lower doses work as well.", "idea", agent="ideator-1", settling_test="dose trial")
    labels.set_label(proj, i["id"], "untested")
    return {c["id"]: c for c in proj.claims()}


def test_validate_answer_rules(proj):
    claims = _labelled(proj)
    assert report.validate_answer(proj, "", claims)
    assert not report.validate_answer(proj, "One study reports a 10 mmHg drop [C1].", claims)
    assert report.validate_answer(proj, "One study reports a 10 mmHg drop.", claims)  # number w/o citation
    assert report.validate_answer(proj, "Lower doses work [I1].", claims)              # untested idea
    assert report.validate_answer(proj, "See [C9].", claims)                           # unknown id
    assert report.validate_answer(proj, "A groundbreaking drug [C1].", claims)         # wording


def test_report_written_and_refused(proj):
    _labelled(proj)
    ok, problems = report.write(proj)
    assert not ok and problems  # no answer yet
    assert not proj.report_path.exists()
    ok, problems = report.write(proj, draft=True)
    assert ok and "DRAFT" in proj.report_path.read_text()
    proj.answer_path.write_text("One study reports a 10 mmHg drop in blood pressure [C1].\n")
    ok, problems = report.write(proj)
    text = proj.report_path.read_text()
    assert ok and not problems
    assert "[C1 · Reported]" in text
    assert "## What was not checked" in text and "## Expert appendix" in text
    assert "I1" in text.split("## New ideas")[1]
    assert "Lower doses" not in text.split("## Findings")[0]
