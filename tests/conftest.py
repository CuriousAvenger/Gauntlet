import pytest

from gauntlet.config import load_config
from gauntlet.project import Project


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own workspace and research home."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GAUNTLET_HOME", str(tmp_path / "research"))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


@pytest.fixture
def proj(tmp_path):
    return Project.create(tmp_path / "research", "Does X reduce Y in fluid simulation?", depth="standard",
                          config=load_config())
