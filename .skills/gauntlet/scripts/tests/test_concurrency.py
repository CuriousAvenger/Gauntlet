"""Agents work in parallel: simultaneous writes must not lose records or reuse ids."""
import json
import subprocess
import sys

from conftest import PAGE, QUOTE, SCRIPTS


def _parallel(tmp_path, commands):
    procs = [subprocess.Popen([sys.executable, str(SCRIPTS / c[0]), *c[1]], cwd=tmp_path, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True) for c in commands]
    for p, c in zip(procs, commands):
        p.communicate(c[2])
    return [p.returncode for p in procs]


def test_parallel_sources_and_claims_are_all_kept(run, tmp_path):
    (tmp_path / "page.txt").write_text(PAGE)
    urls = [f"https://site{i}.example/paper" for i in range(8)]
    assert _parallel(tmp_path, [("source.py", [u, "--text-file", "page.txt"], "") for u in urls]) == [0] * 8
    index = json.loads((tmp_path / "sources/index.json").read_text())
    assert sorted(s["id"] for s in index.values()) == sorted(f"S{i}" for i in range(1, 9))

    reqs = [json.dumps({"statement": f"Finding number {i} about readout.", "quotes": [{"url": u, "quote": QUOTE}]})
            for i, u in enumerate(urls)]
    assert _parallel(tmp_path, [("claim.py", [], r) for r in reqs]) == [0] * 8
    rows = [json.loads(l) for l in (tmp_path / "claims.jsonl").read_text().splitlines()]
    assert sorted(c["id"] for c in rows) == sorted(f"C{i}" for i in range(1, 9))
