from conftest import PASSAGE

from gauntlet import labels


def test_find_passage():
    text = "We find X.\nThe method cut shots by a fac-\ntor of 8.0 at grid 64. It failed for turbulence."
    assert labels.find_passage("the method cut shots by a factor of 8.0", text)
    assert labels.find_passage("The method cut shots ... It failed for turbulence", text)
    assert not labels.find_passage("It failed for turbulence ... The method cut shots", text)
    assert not labels.find_passage("the method cut shots by a factor of 11.3", text)


def test_misquote_and_unread_source(call, project):
    r = call("record_claim", statement="Readout cut shots tenfold.",
             evidence=[{"source_id": "S1", "passage": "the readout cut shots tenfold in every test"}])
    assert any("not found verbatim" in f for f in r["fix"])
    call("save_source", kind="peer-reviewed", url="https://ex.org/pay", unread_reason="paywalled")
    try:
        call("record_claim", statement="A paywalled review agrees.", evidence=[{"source_id": "S3", "passage": "x" * 30}])
        assert False
    except Exception as e:
        assert "cannot be cited" in str(e)


def test_modified_source_fails_quote(call, project):
    cid = call("record_claim", statement="Shots fell 8.0-fold.", evidence=[{"source_id": "S1", "passage": PASSAGE}])["claim_id"]
    assert labels.quote_problems(project, project.claim(cid)) == []
    (project.root / "sources/S1.txt").write_text("edited")
    assert "modified" in labels.quote_problems(project, project.claim(cid))[0]


def test_provenance_rounding(call, project):
    def problems(statement):
        cid = call("record_claim", statement=statement, evidence=[{"source_id": "S1", "passage": PASSAGE}])["claim_id"]
        return labels.provenance_problems(project, project.claim(cid))
    assert problems("Shots fell 8-fold at precision 0.01.") == []
    assert problems("Shots fell 11.3-fold.")
    assert problems("Shots fell 8.04-fold.")  # more precision than the evidence shows
