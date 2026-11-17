import pytest

from gauntlet.protocol import ToolError
from gauntlet.tools import server


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_HOME", str(tmp_path / "research"))
    return tmp_path / "research"


@pytest.fixture
def call():
    """Call a tool through the MCP server, as an agent would."""
    def _call(name, **args):
        res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})["result"]
        if res["isError"]:
            raise ToolError(res["content"][0]["text"])
        return res.get("structuredContent", res["content"][0]["text"])
    return _call


SOURCE = ("Using importance-weighted readout, the number of shots needed to reach precision 0.01 "
          "fell by a factor of 8.0 relative to uniform sampling, at grid size 64.")
PASSAGE = "the number of shots needed to reach precision 0.01 fell by a factor of 8.0 relative to uniform sampling"


@pytest.fixture
def project(call):
    call("start_research", question="Does importance-weighted readout reduce shots?")
    call("save_source", kind="preprint", url="https://ex.org/a", title="A", text=SOURCE)
    call("save_source", kind="peer-reviewed", url="https://ex.org/b", title="B", text="Replication: " + SOURCE)
    from gauntlet.project import Project
    return Project.open()
