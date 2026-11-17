from gauntlet.util import extract_numbers, normalize_text, parse_result_line, slugify


def test_slugify():
    assert slugify("Can quantum computers speed up fluid simulation?") == "can-quantum-computers-speed-up-fluid-simulation"
    assert slugify("???") == "question"


def test_normalize_text_quotes_dashes_hyphenation():
    assert normalize_text("“Foo” — bar  baz") == '"foo" - bar baz'
    assert normalize_text("multi-\n  ple lines") == "multiple lines"


def test_extract_numbers():
    assert extract_numbers("8.51x, 1,000 shots and 0.010 error; see C12 and S3") == ["8.51", "1000", "0.01"]
    assert extract_numbers("between 7.6 and 8.4") == ["7.6", "8.4"]


def test_parse_result_line_takes_last():
    log = 'noise\nGAUNTLET_RESULT {"pass": false}\nGAUNTLET_RESULT {"pass": true, "headline": {"r": 2}}\n'
    assert parse_result_line(log) == {"pass": True, "headline": {"r": 2}}
    assert parse_result_line("GAUNTLET_RESULT not json") is None
