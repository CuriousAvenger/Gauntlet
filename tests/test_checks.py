from gauntlet.checks import like_for_like, provenance, quote_check, wording

TEXT = "We find that the method reduced shots by a factor of 8.0 at grid size 64.\nIt failed for turbulent flows."


def _claim(statement, passage, sid="S1", **kw):
    c = {"id": "C1", "kind": "sourced", "statement": statement, "agent": "reader-1",
         "sources": [{"source_id": sid, "passage": passage, "side": "for"}], "tests": [], "comparisons": []}
    c.update(kw)
    return c


def test_find_passage_exact_and_ellipsis():
    assert quote_check.find_passage("the method reduced shots by a factor of 8.0", TEXT)[0]
    assert quote_check.find_passage("the method reduced shots ... It failed for turbulent flows", TEXT)[0]
    ok, why = quote_check.find_passage("the method eliminated shots entirely", TEXT)
    assert not ok and "diverges" in why
    # fragments out of order do not match
    assert not quote_check.find_passage("It failed for turbulent flows ... the method reduced shots", TEXT)[0]


def test_quote_check_against_saved_source(proj):
    proj.add_source("Paper", "https://ex.org/p", TEXT, kind="preprint")
    good = quote_check.check(proj, _claim("x", "the method reduced shots by a factor of 8.0 at grid size 64"))
    assert good.passed
    bad = quote_check.check(proj, _claim("x", "the method reduced shots by a factor of 11.3 at grid size 64"))
    assert not bad.passed
    short = quote_check.check(proj, _claim("x", "reduced"))
    assert not short.passed


def test_quote_check_detects_tampered_source(proj):
    proj.add_source("Paper", "https://ex.org/p", TEXT, kind="preprint")
    (proj.root / "sources" / "S1.txt").write_text(TEXT + "\nThe method also cures everything.")
    res = quote_check.check(proj, _claim("x", "the method reduced shots by a factor of 8.0"))
    assert not res.passed and "modified" in res.details[0]


def test_unread_source_cannot_be_cited(proj):
    proj.add_source("Paywalled", "https://ex.org/pw", None, unread_reason="paywalled")
    res = quote_check.check(proj, _claim("x", "anything at all in this passage text"))
    assert not res.passed and "unread" in res.details[0]


def test_provenance_rounding(proj):
    c = _claim("Shots fell 8-fold.", "reduced shots by a factor of 8.0")
    assert provenance.check(proj, c).passed
    c = _claim("Shots fell 11.3-fold.", "reduced shots by a factor of 8.0")
    assert not provenance.check(proj, c).passed
    c = _claim("Shots fell by 8.14.", "a factor of 8.1 was seen")
    assert not provenance.check(proj, c).passed  # more precision than the evidence


def test_like_for_like():
    stmt = "The method needs 8 times fewer shots than the baseline."
    assert not like_for_like.check(None, _claim(stmt, "")).passed
    same = {"unit": "shots", "baseline": "uniform", "scale": "n=64"}
    ok = _claim(stmt, "", comparisons=[{"a": {"value": 8, **same}, "b": {"value": 1, **same}}])
    assert like_for_like.check(None, ok).passed
    diff = _claim(stmt, "", comparisons=[{"a": {"value": 8, **same}, "b": {"value": 1, **same, "scale": "n=16"}}])
    assert not like_for_like.check(None, diff).passed
    assert like_for_like.check(None, _claim("Sleep matters for memory.", "")).passed


def test_wording_lint():
    assert wording.lint("This novel method is the first to do it.")
    assert wording.lint("We proved that it holds.")
    assert not wording.lint("Not found in the sources read; tested on 3 seeds.")
