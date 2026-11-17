from claim import normalize, numbers, quote_in


def test_quote_in():
    text = "We find X.\nThe method cut shots by a fac-\ntor of 8.0 at grid 64. It “failed” for turbulence."
    assert quote_in("the method cut shots by a factor of 8.0", text)
    assert quote_in('The method cut shots ... It "failed" for turbulence', text)
    assert not quote_in("It failed for turbulence ... The method cut shots", text)
    assert not quote_in("the method cut shots by a factor of 11.3", text)
    assert not quote_in("...", text)


def test_numbers_and_normalize():
    assert numbers("8.51x, 1,000 shots, 0.010 error, see C12") == [(8.51, 2), (1000.0, 0), (0.01, 3)]
    assert normalize("A  “B” — c") == 'a "b" - c'
