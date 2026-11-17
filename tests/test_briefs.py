import re

import pytest

from gauntlet import briefs
from gauntlet.config import load_config
from gauntlet.project import Project


def test_every_role_composes_without_project():
    for role in briefs.ROLES:
        text = briefs.compose(role, agent=f"{role}-1", task="do the thing")
        assert len(text) > 400
        if role != "orchestrator":
            assert "Trust rules" in text and 'agent: "' in text and "do the thing" in text


def test_briefs_are_harness_neutral():
    for role in briefs.ROLES:
        text = briefs.compose(role)
        for word in ("Claude Code", "opencode", "Agent tool", "Bash", "SKILL", "plugin", "hook"):
            assert word not in text, (role, word)
        # nothing may require reading or writing project files directly
        assert not re.search(r"\b(profile|evidence_map|mistakes|seeds)\.md\b", text), role


def test_project_context_includes_profile_and_pack(tmp_path):
    p = Project.create(tmp_path / "research", "How tight are readout bounds?", pack="quantum-readout",
                       config=load_config())
    text = briefs.compose("prover", p, "prover-1", "test I1")
    assert "Topic profile" in text and "Expert pack" in text and "Known mistakes" in text


def test_unknown_role():
    with pytest.raises(ValueError):
        briefs.compose("janitor")
