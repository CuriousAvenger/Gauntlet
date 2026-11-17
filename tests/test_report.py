import pytest
from conftest import PASSAGE

from gauntlet.protocol import ToolError


def test_report(call, project):
    cid = call("record_claim", statement="Shots fell 8.0-fold.",
               evidence=[{"source_id": "S1", "passage": PASSAGE}])["claim_id"]
    call("record_evidence_map", agree="", disagree="", gaps=["turbulence"])
    iid = call("propose_idea", statement="Turbulent flows show the same reduction.", gap="G1",
               settling_test="simulate turbulent flows")["idea_id"]
    for answer, why in [(f"Shots fell 8-fold [{cid}].", "not earned a label"),
                        (f"Turbulent flows behave the same [{iid}].", "only tested ideas"),
                        ("Shots fell 8-fold in the study.", "without citing"),
                        ("See [C9] for details here.", "does not exist")]:
        with pytest.raises(ToolError, match=why):
            call("write_report", answer=answer)
    call("set_label", claim_id=cid, label="reported")
    text = call("write_report", answer=f"One study reports shots fell 8-fold [{cid}].")["report"]
    assert f"[{cid} · Reported]" in text and "Test that would settle it" in text
    assert "## What was not checked" in text and "not advice" not in text
