import json
import subprocess
import sys
from pathlib import Path

from gauntlet.protocol import validate

SERVER = Path(__file__).resolve().parent.parent / "server.py"


def test_stdio_session(tmp_path):
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "prompts/get", "params": {"name": "research", "arguments": {"question": "Q?"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "set_label", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "nope"},
    ]
    proc = subprocess.run([sys.executable, str(SERVER)], input="".join(json.dumps(m) + "\n" for m in msgs),
                          capture_output=True, text=True, cwd=tmp_path, timeout=30)
    out = {m["id"]: m for m in map(json.loads, proc.stdout.splitlines())}
    assert sorted(out) == [1, 2, 3, 4, 5]
    assert out[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(out[2]["result"]["tools"]) == 13
    assert "Gauntlet research loop" in out[3]["result"]["messages"][0]["content"]["text"]
    assert out[4]["result"]["isError"] and "missing required field" in out[4]["result"]["content"][0]["text"]
    assert out[5]["error"]["code"] == -32601


def test_validate():
    schema = {"type": "object", "required": ["a"], "additionalProperties": False,
              "properties": {"a": {"type": "integer"}, "b": {"type": "array", "items": {"type": "string"}}}}
    assert validate({"a": 1, "b": ["x"]}, schema) == []
    assert validate({"a": True}, schema)
    assert validate({"a": 1, "c": 2}, schema)
    assert validate({"a": 1, "b": [3]}, schema)
