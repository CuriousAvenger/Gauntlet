import re

from gauntlet import briefs
from gauntlet.project import Project


def test_briefs_are_complete_and_harness_neutral():
    for role in briefs.ROLES:
        text = briefs.compose(role, task="the task")
        assert "the task" in text and (role == "orchestrator" or "Trust rules" in text)
        assert not re.search(r"Claude|opencode|Bash|plugin|hook|(profile|evidence_map|claims)\.\w+", text), role


def test_project_and_pack_context(home):
    p = Project.create("How tight are readout bounds?", high_stakes=True, pack="quantum-readout", base=home)
    text = briefs.compose("prover", p, "test I1")
    assert "How tight are readout bounds?" in text and "not advice" in text and "Expert pack" in text
