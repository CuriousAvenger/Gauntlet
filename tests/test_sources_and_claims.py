from conftest import QUOTE


def claim(run, statement, *urls, disagree=None):
    quotes = [{"url": u, "quote": QUOTE} for u in urls]
    if disagree:
        quotes.append({"url": disagree, "quote": QUOTE, "disagrees": True})
    return run("claim.py", "p", stdin={"statement": statement, "quotes": quotes})[1]


def test_source_find_and_paging(run, sources):
    code, out = run("source.py", "p", "https://a.example/paper", "--find", "factor of 8")
    assert code == 0 and out["source"] == "S1" and "8.0" in out["matches"][0]["text"]


def test_unreadable_source_cannot_be_cited(run, sources):
    assert run("source.py", "p", "http://127.0.0.1:9/nothing")[0] == 1
    code, out = run("claim.py", "p", stdin={"statement": "Shots fell sharply.",
                                            "quotes": [{"url": "http://127.0.0.1:9/nothing", "quote": QUOTE}]})
    assert code == 1 and "cannot be cited" in out["error"]


def test_misquote_and_invented_number_reported_at_once(run, sources):
    out = run("claim.py", "p", stdin={"statement": "Shots fell 11.3-fold.",
                                      "quotes": [{"url": "https://a.example/paper", "quote": "shots fell elevenfold in all tests"}]})[1]
    assert any("word for word" in f for f in out["fix"]) and any("11.3" in f for f in out["fix"])
    out = claim(run, "Shots fell 8-fold at precision 0.01.", "https://a.example/paper")
    assert "fix" not in out  # 8 is 8.0 rounded to the precision shown


def test_source_labels(run, sources):
    one = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper")["id"]
    code, out = run("label.py", "p", one, "established")
    assert code == 1 and "two or more independent sources" in out["missing"][0]
    assert run("label.py", "p", one, "reported")[0] == 0
    assert run("label.py", "p", one, "tested")[0] == 1
    two = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper", "https://b.example/replication")["id"]
    assert run("label.py", "p", two, "established")[0] == 0
    split = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper", disagree="https://b.example/replication")["id"]
    assert run("label.py", "p", split, "reported")[0] == 1
    assert run("label.py", "p", split, "contested")[0] == 0


def test_edited_source_copy_breaks_its_quotes(run, sources):
    cid = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper")["id"]
    (sources / "sources" / "S1.txt").write_text("rewritten")
    code, out = run("label.py", "p", cid, "reported")
    assert code == 1 and "edited after it was fetched" in out["missing"][0]
