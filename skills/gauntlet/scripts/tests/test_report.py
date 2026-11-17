from test_ideas import BROKEN, GOOD, idea

from conftest import QUOTE


def report(run, tmp_path, answer, *flags):
    (tmp_path / "answer.md").write_text(answer)
    return run("report.py", "--question", "Does readout cut shots?", "--answer", "answer.md", *flags)


def test_answer_rules(run, sources, tmp_path):
    cid = run("claim.py", stdin={"statement": "Shots fell 8.0-fold.",
                                      "quotes": [{"url": "https://a.example/paper", "quote": QUOTE}]})[1]["id"]
    iid = run("claim.py", stdin={"statement": "Turbulent flows behave the same.", "settling_test": "simulate them"})[1]["id"]
    for answer, why in [(f"Shots fell [{cid}].", "no label"), (f"Turbulence too [{iid}].", "only tested ideas"),
                        ("Shots fell 8-fold.", "without citing"), ("See [C9].", "does not exist")]:
        code, out = report(run, tmp_path, answer)
        assert code == 1 and why in " ".join(out["fix"])
    run("label.py", cid, "reported")
    assert report(run, tmp_path, f"One study reports an 8-fold drop [{cid}].", "--high-stakes")[0] == 0
    text = (sources / "report.md").read_text()
    assert f"[{cid} · Reported]" in text and "Would be settled by" in text and "not advice" in text


def test_report_rechecks_edited_tests(run, tmp_path):
    iid = idea(run, tmp_path, replica=GOOD)
    assert run("label.py", iid, "tested")[0] == 0
    (tmp_path / f"runs/{iid}-T1.py").write_text(BROKEN)
    report(run, tmp_path, "Nothing is cited here.", "--draft")
    text = (tmp_path / "report.md").read_text()
    assert "New idea: tested to New idea: refuted" in text


def test_title_comes_from_question_file(run, tmp_path):
    (tmp_path / "answer.md").write_text("Nothing was found in the sources read.")
    assert run("report.py", "--answer", "answer.md")[0] == 2  # no question anywhere
    (tmp_path / "QUESTION.md").write_text("# Question\n\nDoes readout cut shots?\n")
    assert run("report.py", "--answer", "answer.md")[0] == 0
    assert (tmp_path / "report.md").read_text().startswith("# Does readout cut shots?")
