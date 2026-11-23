from conftest import QUOTE


def claim(run, statement, *urls, disagree=None):
    quotes = [{"url": u, "quote": QUOTE} for u in urls]
    if disagree:
        quotes.append({"url": disagree, "quote": QUOTE, "disagrees": True})
    return run("claim.py", stdin={"statement": statement, "quotes": quotes})[1]


def test_source_find_and_paging(run, sources):
    code, out = run("source.py", "https://a.example/paper", "--find", "factor of 8")
    assert code == 0 and out["source"] == "S1" and "8.0" in out["matches"][0]["text"]


def test_unreadable_source_cannot_be_cited(run, sources):
    assert run("source.py", "http://127.0.0.1:9/nothing")[0] == 1
    code, out = run("claim.py", stdin={"statement": "Shots fell sharply.",
                                            "quotes": [{"url": "http://127.0.0.1:9/nothing", "quote": QUOTE}]})
    assert code == 1 and "cannot be cited" in out["error"]


def test_misquote_and_invented_number_reported_at_once(run, sources):
    out = run("claim.py", stdin={"statement": "Shots fell 11.3-fold.",
                                      "quotes": [{"url": "https://a.example/paper", "quote": "shots fell elevenfold in all tests"}]})[1]
    assert any("word for word" in f for f in out["fix"]) and any("11.3" in f for f in out["fix"])
    out = claim(run, "Shots fell 8-fold at precision 0.01.", "https://a.example/paper")
    assert "fix" not in out  # 8 is 8.0 rounded to the precision shown


def test_source_labels(run, sources):
    one = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper")["id"]
    code, out = run("label.py", one, "established", "--reason", "test")
    assert code == 1 and "two or more independent sources" in out["missing"][0]
    assert run("label.py", one, "reported", "--reason", "test")[0] == 0
    assert run("label.py", one, "tested", "--reason", "test")[0] == 1
    two = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper", "https://b.example/replication")["id"]
    assert run("label.py", two, "established", "--reason", "test")[0] == 0
    split = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper", disagree="https://b.example/replication")["id"]
    assert run("label.py", split, "reported", "--reason", "test")[0] == 1
    assert run("label.py", split, "contested", "--reason", "test")[0] == 0


def test_edited_source_copy_breaks_its_quotes(run, sources):
    cid = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper")["id"]
    (sources / "sources" / "S1.txt").write_text("rewritten")
    code, out = run("label.py", cid, "reported", "--reason", "test")
    assert code == 1 and "edited after it was fetched" in out["missing"][0]


def test_years_and_figure_references_are_not_measurements(run, sources):
    out = claim(run, "In 2021, Fig. 3 of the study [12] showed shots fell 8-fold.", "https://a.example/paper")
    assert "fix" not in out
    out = claim(run, "In 2021 shots fell 9-fold.", "https://a.example/paper")
    assert any("9" in f for f in out["fix"])


def test_labels_record_who_decided_and_why(run, sources):
    cid = claim(run, "Shots fell 8.0-fold.", "https://a.example/paper")["id"]
    assert run("label.py", cid, "reported")[0] == 2   # a reason is required
    assert run("label.py", cid, "reported", "--reason", "the quote states it directly")[0] == 0
    import json
    row = next(json.loads(l) for l in (sources / "claims.jsonl").read_text().splitlines() if cid in l)
    assert row["history"][-1]["reason"] == "the quote states it directly" and row["history"][-1]["label"] == "reported"
