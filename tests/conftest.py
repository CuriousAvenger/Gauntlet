import pytest

from gauntlet.config import load_config
from gauntlet.project import Project


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Project.create(tmp_path / "projects", "Does X reduce Y in fluid simulation?", depth="standard",
                       config=load_config())
    return p


@pytest.fixture
def run(tmp_path, monkeypatch):
    """Call the CLI in-process; returns (exit code, stdout, stderr)."""
    from gauntlet.cli.main import main

    monkeypatch.chdir(tmp_path)

    def _run(*args, capsys=None):
        return main([str(a) for a in args])
    return _run
