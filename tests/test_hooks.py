import io
import json
import sys

from gauntlet import cost, hooks
from gauntlet.config import load_config
from gauntlet.project import Project


def _ev(tool, tmp_path, **inp):
    return {"tool_name": tool, "cwd": str(tmp_path), "tool_input": inp}


def test_protects_records_but_not_scripts(tmp_path, proj):
    deny = hooks.pre_tool_use(_ev("Write", tmp_path, file_path=str(proj.claims_path)))
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hooks.pre_tool_use(_ev("Edit", tmp_path, file_path=str(proj.root / "sources/S1.txt")))
    assert hooks.pre_tool_use(_ev("Write", tmp_path, file_path=str(proj.root / "runs/_harness/I1/x.log")))
    assert hooks.pre_tool_use(_ev("Write", tmp_path, file_path=str(proj.root / "runs/prover-1/t.py"))) is None
    assert hooks.pre_tool_use(_ev("Edit", tmp_path, file_path=str(proj.profile_path))) is None
    assert hooks.pre_tool_use(_ev("Write", tmp_path, file_path=str(tmp_path / "notes/claims.jsonl"))) is None


def test_bash_guard(tmp_path, proj):
    assert hooks.pre_tool_use(_ev("Bash", tmp_path, command=f"echo x >> {proj.claims_path}"))
    assert hooks.pre_tool_use(_ev("Bash", tmp_path, command="rm research/x/sources/S1.txt"))
    assert hooks.pre_tool_use(_ev("Bash", tmp_path, command=f"cat {proj.claims_path}")) is None
    assert hooks.pre_tool_use(_ev("Bash", tmp_path, command="python runs/prover-1/t.py --seed 1 > out.txt")) is None


def test_budget_gate(tmp_path, proj):
    spawn = _ev("Agent", tmp_path, subagent_type="gauntlet:reader", prompt="x")
    assert hooks.pre_tool_use(spawn) is None
    proj.log_cost({"at": "", "stage": "survey", "agent": "r", "tier": "cheap", "model": "m",
                   "input_tokens": 0, "output_tokens": 0, "usd": 999.0})
    assert hooks.pre_tool_use(spawn)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hooks.pre_tool_use(_ev("Agent", tmp_path, subagent_type="gauntlet:writer")) is None
    assert hooks.pre_tool_use(_ev("Agent", tmp_path, subagent_type="general-purpose")) is None


def _transcript(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_usage_capture_dedupes(tmp_path, proj):
    msg = {"id": "msg_1", "model": "claude-haiku-5-5",
           "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 0}}
    t = tmp_path / "agent.jsonl"
    _transcript(t, [{"type": "assistant", "timestamp": "2099-01-01T00:00:00Z", "message": msg},
                    {"type": "assistant", "timestamp": "2099-01-01T00:00:00Z", "message": msg},  # same message, 2 blocks
                    {"type": "user", "message": {"content": "hi"}}])
    hooks.subagent_stop({"agent_type": "gauntlet:reader", "agent_transcript_path": str(t), "cwd": str(tmp_path)})
    hooks.subagent_stop({"agent_type": "gauntlet:reader", "agent_transcript_path": str(t), "cwd": str(tmp_path)})
    sp = cost.spend(proj)
    assert abs(sp["total_usd"] - 0.60) < 1e-9 and sp["entries"] == 1  # haiku $0.10 + $0.50, counted once
    hooks.subagent_stop({"agent_type": "general-purpose", "agent_transcript_path": str(t), "cwd": str(tmp_path)})
    assert cost.spend(proj)["entries"] == 1  # unrelated subagents are not billed to research


def test_stop_bills_only_since_project_start(tmp_path, proj):
    old = {"id": "m_old", "model": "claude-opus-5-5", "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}
    new = {"id": "m_new", "model": "claude-opus-5-5", "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}
    t = tmp_path / "main.jsonl"
    _transcript(t, [{"type": "assistant", "timestamp": "2000-01-01T00:00:00Z", "message": old},
                    {"type": "assistant", "timestamp": "2099-01-01T00:00:00Z", "message": new}])
    hooks.stop({"transcript_path": str(t), "cwd": str(tmp_path)})
    assert abs(cost.spend(proj)["total_usd"] - 4.0) < 1e-9


def test_session_start_context(tmp_path, proj):
    out = hooks.session_start({"cwd": str(tmp_path), "source": "resume"})
    assert proj.slug in out["hookSpecificOutput"]["additionalContext"]


def test_main_never_raises(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert hooks.main(["pre-tool-use"]) == 0
    assert capsys.readouterr().out == ""
