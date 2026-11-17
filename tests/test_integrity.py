import json

import pytest

from gauntlet import integrity
from gauntlet.evaluation import _Client
from gauntlet.protocol import ToolError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_STATE", str(tmp_path / "state"))
    c = _Client()
    c.start_research(question="Does sleep deprivation impair memory consolidation?", depth="quick")
    c.save_source(agent="reader-1", kind="peer-reviewed", url="https://ex.org/a", title="A",
                  text="Sleep deprivation after learning impairs the consolidation of declarative memories.")
    return c


def _proj(tmp_path):
    from gauntlet.project import active_project
    return active_project(tmp_path / "research")


def test_untouched_project_verifies(client, tmp_path):
    client.status()
    assert integrity.verify(_proj(tmp_path)) == []


def test_out_of_band_edit_is_detected_recorded_and_rechecked(client, tmp_path):
    cid = client.record_claim(agent="reader-1", statement="Sleep deprivation after learning impairs memory consolidation.",
                              evidence=[{"source_id": "S1", "passage": "Sleep deprivation after learning impairs the consolidation of declarative memories"}])["claim_id"]
    p = _proj(tmp_path)
    rows = [json.loads(l) for l in p.claims_path.read_text().splitlines()]
    rows[0]["label"] = "established"
    p.claims_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ToolError, match="edited outside Gauntlet: claims.jsonl"):
        client.status()
    assert p.claim(cid)["label"] == "pending"           # forgery undone by the re-check
    assert p.state()["integrity_events"][0]["files"] == ["claims.jsonl"]
    assert client.status()["integrity_events"] == 1     # next call proceeds normally


def test_forged_seal_is_detected(client, tmp_path):
    p = _proj(tmp_path)
    seal = p.root / "runs/_harness/seal.json"
    data = json.loads(seal.read_text())
    data["files"]["claims.jsonl"] = "0" * 64
    seal.write_text(json.dumps(data))
    with pytest.raises(ToolError, match="signature"):
        client.status()


def test_report_shows_integrity_events(client, tmp_path):
    p = _proj(tmp_path)
    (p.root / "sources/S1.txt").write_text("changed")
    with pytest.raises(ToolError):
        client.status()
    client.write_report(agent="writer-1", answer="No claims passed their checks in this run.", draft=True)
    assert "**Integrity:**" in p.report_path.read_text()
