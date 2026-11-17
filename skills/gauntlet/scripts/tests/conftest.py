import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

PAGE = ("Using importance-weighted readout, the number of shots needed to reach precision 0.01 "
        "fell by a factor of 8.0 relative to uniform sampling, at grid size 64.")
QUOTE = "the number of shots needed to reach precision 0.01 fell by a factor of 8.0 relative to uniform sampling"


@pytest.fixture
def run(tmp_path, monkeypatch):
    """Run a Gauntlet script as an agent would; returns (exit code, parsed JSON)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GAUNTLET_ROOT", str(tmp_path))

    def _run(script, *args, stdin=None):
        proc = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], cwd=tmp_path,
                              input=json.dumps(stdin) if stdin is not None else None,
                              capture_output=True, text=True, timeout=60)
        return proc.returncode, json.loads(proc.stdout)
    return _run


@pytest.fixture
def sources(run, tmp_path):
    """Two saved sources, A and B, saying the same thing."""
    (tmp_path / "page.txt").write_text(PAGE)
    for url in ("https://a.example/paper", "https://b.example/replication"):
        assert run("source.py", url, "--text-file", "page.txt")[0] == 0
    return tmp_path
