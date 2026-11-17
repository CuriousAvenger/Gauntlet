import json
import os
import subprocess
import sys
from pathlib import Path

from gauntlet import tools as T
from gauntlet.protocol import Server, validate

ROOT = Path(__file__).resolve().parent.parent


def _session(messages, env=None):
    proc = subprocess.run([sys.executable, str(ROOT / "server.py")], cwd="/",
                          input="".join(json.dumps(m) + "\n" for m in messages),
                          capture_output=True, text=True, env={**os.environ, **(env or {})}, timeout=60)
    return [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]


def test_protocol_round_trip(tmp_path):
    out = _session([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "start_research", "arguments": {"question": "Is coffee linked to lower liver disease risk?", "depth": "quick"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "status", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "set_label", "arguments": {"label": "bogus"}}},
        {"jsonrpc": "2.0", "id": 6, "method": "nope"},
        {"jsonrpc": "2.0", "id": 7, "method": "prompts/list"},
        {"jsonrpc": "2.0", "id": 8, "method": "prompts/get",
         "params": {"name": "research", "arguments": {"question": "Why did the Bronze Age collapse?"}}},
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
         "params": {"name": "get_brief", "arguments": {"role": "reader", "agent": "reader-1", "task": "find 5 sources"}}},
    ], env={"GAUNTLET_HOME": str(tmp_path / "r"), "GAUNTLET_STATE": str(tmp_path / "state")})
    by_id = {m["id"]: m for m in out}
    assert len(out) == 9  # 9 requests, no reply to the notification
    assert by_id[7]["result"]["prompts"][0]["name"] == "research"
    msg = by_id[8]["result"]["messages"][0]["content"]["text"]
    assert "orchestrator" in msg and "Bronze Age" in msg
    brief = by_id[9]["result"]["content"][0]["text"]
    assert 'agent: "reader-1"' in brief and "find 5 sources" in brief and "Topic profile" in brief
    init = by_id[1]["result"]
    assert init["protocolVersion"] == "2025-03-26" and "Gauntlet" in init["instructions"]
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert {"start_research", "record_claim", "run_test", "set_label", "write_report"} <= names
    started = by_id[3]["result"]
    assert not started["isError"] and started["structuredContent"]["profile"]["high_stakes"] is True
    assert by_id[4]["result"]["structuredContent"]["stage"] == "scope"
    bad = by_id[5]["result"]
    assert bad["isError"] and "missing required field 'agent'" in bad["content"][0]["text"]
    assert by_id[6]["error"]["code"] == -32601


def test_every_tool_schema_is_valid():
    for t in T.server.tools.values():
        spec = t.spec()
        assert spec["inputSchema"]["type"] == "object" and spec["description"]
        for req in spec["inputSchema"]["required"]:
            assert req in spec["inputSchema"]["properties"], (t.name, req)


def test_validate():
    schema = {"type": "object", "required": ["a"], "additionalProperties": False,
              "properties": {"a": {"type": "integer"}, "b": {"type": "array", "items": {"type": "string"}}}}
    assert validate({"a": 1, "b": ["x"]}, schema) == []
    assert validate({"a": True}, schema)          # bool is not an integer
    assert validate({"a": 1, "c": 2}, schema)     # unknown field
    assert validate({"a": 1, "b": [3]}, schema)


def test_handler_crash_becomes_error_result():
    s = Server("x", "1")

    @s.tool("boom", "explodes", {})
    def boom():
        raise RuntimeError("kaboom")
    r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "boom", "arguments": {}}})
    assert r["result"]["isError"] and "kaboom" in r["result"]["content"][0]["text"]


def test_tool_flow_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_STATE", str(tmp_path / "state"))
    T.start_research("Does sleep deprivation impair memory consolidation?", depth="quick")
    T.save_source(agent="reader-1", kind="peer-reviewed", url="https://ex.org/a", title="A",
                  text="Sleep deprivation after learning impairs the consolidation of declarative memories.")
    hits = T.search_sources(pattern="consolidation")["hits"]
    assert hits and hits[0]["source_id"] == "S1"
    r = T.record_claim(agent="reader-1", statement="Sleep loss after learning impairs memory consolidation.",
                       evidence=[{"source_id": "S1", "passage": "sleep loss after learning impairs consolidation"}])
    assert r["fix_now"]  # misquote reported immediately
    r = T.add_evidence(agent="reader-1", claim_id=r["claim_id"], evidence=[{"source_id": "S1",
                       "passage": "Sleep deprivation after learning impairs the consolidation of declarative memories"}])
    assert r["evidence_indexes"] == [1]
    st = T.set_stage(stage="explore")
    assert st["cycle_started"] == 1
    T.set_stage(stage="check")
    st = T.set_stage(stage="report")
    assert st["cycle"]["n"] == 1 and st["stop"]
