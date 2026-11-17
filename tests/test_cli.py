import json

from gauntlet.cli.main import main


def test_cli_flow(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["ask", "Is coffee linked to lower liver disease risk?", "--depth", "quick"]) == 0
    out = capsys.readouterr().out
    assert "Estimate for depth 'quick'" in out
    (tmp_path / "s.txt").write_text("Coffee drinkers had a lower risk of chronic liver disease in a cohort of 400 people.")
    assert main(["source", "add", "--file", "s.txt", "--title", "Cohort", "--kind", "peer-reviewed"]) == 0
    assert main(["source", "grep", "S1", "liver"]) == 0
    assert main(["claim", "add", "Coffee drinkers had a lower risk of chronic liver disease in a cohort of 400 people.",
                 "--cite", "S1", "Coffee drinkers had a lower risk of chronic liver disease in a cohort of 400 people.",
                 "--by", "reader-1"]) == 0
    assert main(["claim", "label", "C1", "reported"]) == 4
    assert main(["claim", "referee", "C1", "--index", "0", "--verdict", "supports", "--by", "referee-1"]) == 0
    assert main(["claim", "label", "C1", "reported", "--by", "referee-1"]) == 0
    assert main(["idea", "add", "Decaf has the same effect.", "--settling-test", "compare decaf cohorts"]) == 0
    capsys.readouterr()
    assert main(["status", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["claims_by_label"] == {"reported": 1, "untested": 1}
    assert main(["cycle", "start"]) == 0
    assert main(["cycle", "end"]) == 0
    assert main(["should-stop"]) == 0  # quick: one cycle
    assert main(["cost", "log", "--stage", "survey", "--agent", "reader-1", "--input-tokens", "1000000",
                 "--output-tokens", "0"]) == 0
    assert main(["budget-check"]) == 0
    assert main(["report"]) == 2
    proj = next((tmp_path / "projects").glob("*/project.json")).parent
    (proj / "answer.md").write_text("One cohort study reports lower liver disease risk among coffee drinkers [C1].\n")
    assert main(["report"]) == 0
    assert "not advice" in (proj / "report.md").read_text()
    assert main(["continue", "What about tea?"]) == 0
    assert main(["audit"]) == 0


def test_install_runners(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["install", "--runner", "claude-code", "--dir", str(tmp_path)]) == 0
    reader = (tmp_path / ".claude/agents/gauntlet-reader.md").read_text()
    assert "model: haiku" in reader and "Gauntlet trust rules" in reader and "WebSearch" in reader
    assert "model: opus" in (tmp_path / ".claude/agents/gauntlet-referee.md").read_text()
    assert "$ARGUMENTS" in (tmp_path / ".claude/commands/gauntlet.md").read_text()
    assert main(["install", "--runner", "opencode", "--dir", str(tmp_path)]) == 0
    assert "mode: subagent" in (tmp_path / ".opencode/agent/gauntlet-prover.md").read_text()


def test_brief_without_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["brief", "referee"]) == 0
    assert "Role: Referee" in capsys.readouterr().out
