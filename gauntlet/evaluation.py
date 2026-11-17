"""Evaluation helpers (design doc, Evaluation section).

- `planted_errors()` seeds ten known failure types into a scratch project and
  counts how many the trust layer catches (pass: >= 9 of 10), alongside honest
  controls that must still get through, so a checker that refuses everything
  does not pass.
- `sample_claims()` writes a review sheet for the citation-accuracy and
  label-honesty tests, which need human or field-expert graders.
"""

from __future__ import annotations

import csv
import random
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import labels, report
from .config import load_config
from .project import Project
from .util import atomic_write

S1 = """Quantum linear-system readout on a lattice fluid solver.

We benchmark a measurement scheme for reading out the solution of a quantum
linear-system solver applied to a lattice Boltzmann fluid simulation. Using
importance-weighted readout, the number of shots needed to estimate the drag
coefficient to precision 0.01 fell by a factor of 8.0 relative to uniform
Pauli sampling, at grid size 64 and with the same estimator.

Across 20 random instances the reduction ranged from 7.6 to 8.4.
"""

S2 = """Independent study of readout costs.

Our replication finds that importance-weighted readout reduces the shot count
by roughly a factor of 8 compared with uniform Pauli sampling at the same grid
size and precision, consistent with earlier reports.
"""

S3 = """A critical note.

In our experiments importance-weighted readout gave no reduction in shot count
for turbulent flows at high Reynolds number; the advantage disappears outside
the laminar regime.
"""

GOOD_TEST = """import argparse, json, random
p = argparse.ArgumentParser(); p.add_argument('--seed', type=int, default=0); a = p.parse_args()
r = random.Random(a.seed)
ratio = 8.0 + r.uniform(-0.2, 0.2)
print('ratio', round(ratio, 3))
print('GAUNTLET_RESULT ' + json.dumps({'pass': ratio > 7.0, 'headline': {'ratio': round(ratio, 2)}}))
"""

FITTED_TEST = """import argparse, json
p = argparse.ArgumentParser(); p.add_argument('--seed', type=int, default=0); a = p.parse_args()
ratio = 11.3 if a.seed == 0 else 1.1   # tuned to the known instance
print('GAUNTLET_RESULT ' + json.dumps({'pass': ratio > 7.0, 'headline': {'ratio': ratio}}))
"""


def _write(proj: Project, rel: str, text: str) -> str:
    atomic_write(proj.root / rel, text)
    return rel


def _log(proj: Project, rel: str, script: str, seed: int = 0) -> str:
    import subprocess
    out = subprocess.run([sys.executable, str(proj.root / script), "--seed", str(seed)],
                         capture_output=True, text=True, cwd=proj.root).stdout
    return _write(proj, rel, out)


def _sourced(proj, statement, cites, by="reader-1", referee="referee-1", verdict="supports", comparisons=None):
    c = proj.new_claim(statement, "sourced", agent=by)
    c["sources"] = [{"source_id": s, "passage": p, "side": side} for s, p, side in cites]
    c["comparisons"] = comparisons or []
    c["referee"] = [{"source_index": i, "verdict": verdict, "by": referee, "note": ""} for i in range(len(cites))]
    proj.put_claim(c)
    return c["id"]


def _idea(proj, statement, script_text, name, held_seeds=(101, 202, 303), dev=(0,), replica_text=None,
          replica_agent="prover-2"):
    c = proj.new_claim(statement, "idea", agent="ideator-1", gap="G1", settling_test="run the test on fresh seeds")
    script = _write(proj, f"runs/{name}/test.py", script_text)
    log = _log(proj, f"runs/{name}/test.log", script, seed=dev[0])
    t = {"id": "T1", "role": "support", "script": script, "log": log, "agent": name,
         "brief": f"runs/{name}/brief.md",
         "held_out": {"cmd": f'"{sys.executable}" {script} --seed {{seed}}', "seeds": list(held_seeds),
                      "dev_seeds": list(dev)}}
    if replica_text is not None:
        rs = _write(proj, f"runs/{replica_agent}/replica.py", replica_text)
        rl = _log(proj, f"runs/{replica_agent}/replica.log", rs, seed=7)
        t["replica"] = {"log": rl, "agent": replica_agent, "brief": f"runs/{replica_agent}/brief.md", "script": rs}
    c["tests"] = [t]
    c["comparisons"] = [{"a": {"value": 8.0, "unit": "shots", "baseline": "uniform Pauli sampling", "scale": "grid 64"},
                         "b": {"value": 1.0, "unit": "shots", "baseline": "uniform Pauli sampling", "scale": "grid 64"}}]
    proj.put_claim(c)
    return c["id"]


def build_fixture(base: Path) -> Project:
    cfg = load_config()
    proj = Project.create(base, "Does importance-weighted readout reduce shots for quantum fluid solvers?",
                          depth="standard", config=cfg)
    proj.evidence_map_path.write_text("# Evidence map\n\n## Agree\n\n## Disagree\n\n## Gaps\n\n- G1: turbulent regime untested\n")
    proj.add_source("Readout on a lattice fluid solver", "https://example.org/s1", S1, kind="preprint")
    proj.add_source("Independent study of readout costs", "https://example.org/s2", S2, kind="peer-reviewed")
    proj.add_source("A critical note", "https://example.org/s3", S3, kind="preprint")
    proj.add_source("Paywalled review", "https://example.org/s4", None, kind="peer-reviewed",
                    unread_reason="paywalled")
    return proj


def planted_errors(verbose: bool = False, base: Path | None = None) -> dict[str, Any]:
    tmp = None
    if base is None:
        tmp = tempfile.TemporaryDirectory(prefix="gauntlet-eval-")
        base = Path(tmp.name)
    try:
        return _planted(base, verbose)
    finally:
        if tmp is not None:
            tmp.cleanup()


def _planted(base: Path, verbose: bool) -> dict[str, Any]:
    proj = build_fixture(base)
    p1 = "the number of shots needed to estimate the drag coefficient to precision 0.01 fell by a factor of 8.0 relative to uniform Pauli sampling"
    p2 = "importance-weighted readout reduces the shot count by roughly a factor of 8 compared with uniform Pauli sampling"
    p3 = "importance-weighted readout gave no reduction in shot count for turbulent flows"
    same = {"unit": "shots", "baseline": "uniform Pauli sampling", "scale": "grid 64, precision 0.01"}
    comp = [{"a": {"value": 8.0, **same}, "b": {"value": 1.0, **same}}]

    outcomes: list[tuple[str, str, bool]] = []  # (name, kind, as_expected)

    def expect_label(name, cid, label, should_pass):
        ok, unmet, _ = labels.set_label(proj, cid, label, by="referee-1")
        good = ok == should_pass
        outcomes.append((name, "control" if should_pass else "planted", good))
        if verbose:
            tag = "control" if should_pass else "planted"
            print(f"[{tag:7}] {name:<46} {'ok' if good else 'MISSED'}" + ("" if ok else f"  ({unmet[0][:90]})"))

    # ---- honest controls: must be allowed --------------------------------------
    k1 = _sourced(proj, "Importance-weighted readout needed 8.0 times fewer shots than uniform Pauli sampling.",
                  [("S1", p1, "for")], comparisons=comp)
    expect_label("control: one-source claim -> reported", k1, "reported", True)
    k2 = _sourced(proj, "Importance-weighted readout cuts shot counts about 8-fold versus uniform Pauli sampling.",
                  [("S1", p1, "for"), ("S2", p2, "for")], comparisons=comp)
    expect_label("control: two-source claim -> established", k2, "established", True)
    k3 = _idea(proj, "The 8-fold shot reduction holds on randomly generated laminar instances.",
               GOOD_TEST, "prover-1", replica_text=GOOD_TEST)
    expect_label("control: replicated held-out idea -> tested", k3, "tested", True)

    # ---- planted errors: must be refused -----------------------------------------
    c = _sourced(proj, "Importance-weighted readout eliminated the need for error mitigation.",
                 [("S1", "importance-weighted readout eliminated the need for error mitigation entirely", "for")])
    expect_label("1 made-up citation", c, "reported", False)

    c = _sourced(proj, "Importance-weighted readout needed 11.3 times fewer shots than uniform Pauli sampling.",
                 [("S1", p1, "for")], comparisons=comp)
    expect_label("2 stretched number (11.3 vs 8.0)", c, "reported", False)

    c = _sourced(proj, "Importance-weighted readout needed 8.0 times fewer shots than uniform Pauli sampling.",
                 [("S1", p1, "for")], comparisons=comp)
    expect_label("3 single source labelled established", c, "established", False)

    bad_comp = [{"a": {"value": 8.0, "unit": "shots", "baseline": "uniform Pauli sampling", "scale": "grid 64"},
                 "b": {"value": 1.0, "unit": "shots", "baseline": "uniform Pauli sampling", "scale": "grid 16"}}]
    c = _sourced(proj, "Importance-weighted readout needed 8.0 times fewer shots than uniform Pauli sampling.",
                 [("S1", p1, "for")], comparisons=bad_comp)
    expect_label("4 scale mismatch in comparison", c, "reported", False)

    c = _idea(proj, "A tuned readout gives an 11.3-fold reduction on all instances.", FITTED_TEST, "prover-3",
              replica_text=FITTED_TEST, replica_agent="prover-4")
    expect_label("5 answer-fitted simulation (fails held-out)", c, "tested", False)

    bad_rep = GOOD_TEST.replace("8.0 + r.uniform(-0.2, 0.2)", "11.3")
    c = _idea(proj, "The shot reduction reproduces at grid 64 with a fresh implementation.", GOOD_TEST, "prover-5",
              replica_text=bad_rep, replica_agent="prover-6")
    expect_label("6 replication disagrees (8.0 vs 11.3)", c, "tested", False)

    c = _sourced(proj, "A paywalled review reports the same shot reduction.",
                 [("S4", "the same shot reduction was observed in a paywalled review", "for")])
    expect_label("8 cites an unread (paywalled) source", c, "reported", False)

    c = _sourced(proj, "Importance-weighted readout reduces shot counts in all flow regimes.",
                 [("S1", p1, "for")], referee="reader-1")
    expect_label("11 self-refereed claim (author = referee)", c, "reported", False)

    # 7: refuted claim left as tested. Label passes now; then the test log is
    # re-run (notebook re-audit) and fails. The audit must move it to refuted.
    i7 = _idea(proj, "The reduction persists in the turbulent regime.", GOOD_TEST, "prover-7",
               replica_text=GOOD_TEST, replica_agent="prover-8")
    labels.set_label(proj, i7, "tested", by="referee-1")
    _write(proj, "runs/prover-7/test.py", GOOD_TEST.replace("ratio > 7.0", "ratio > 99"))
    _log(proj, "runs/prover-7/test.log", "runs/prover-7/test.py")
    changes = labels.audit(proj)
    caught7 = any(ch["id"] == i7 and ch["to"] == "refuted" for ch in changes)
    outcomes.append(("7 refuted idea left as tested (audit)", "planted", caught7))
    if verbose:
        print(f"[planted] {'7 refuted idea left as tested (audit)':<46} {'ok' if caught7 else 'MISSED'}")

    # 9 + 10: report-level errors.
    untested = proj.new_claim("Readout cost scales with Reynolds number.", "idea", agent="ideator-1",
                              gap="G1", settling_test="measure shots across Reynolds numbers")
    labels.set_label(proj, untested["id"], "untested", by="ideator-1")
    claims = {c["id"]: c for c in proj.claims()}

    def report_catches(name, answer):
        probs = report.validate_answer(proj, answer, claims)
        outcomes.append((name, "planted", bool(probs)))
        if verbose:
            print(f"[planted] {name:<46} {'ok' if probs else 'MISSED'}" + (f"  ({probs[0][:90]})" if probs else ""))

    report_catches("9 banned wording in the answer",
                   f"This novel readout needs about 8 times fewer shots [{k2}].")
    report_catches("10 untested idea in the answer summary",
                   f"Readout cost scales with Reynolds number [{untested['id']}].")
    clean = f"Sources agree that importance-weighted readout needs about 8 times fewer shots [{k2}]."
    clean_ok = not report.validate_answer(proj, clean, claims)
    outcomes.append(("control: clean answer accepted", "control", clean_ok))
    if verbose:
        print(f"[control] {'control: clean answer accepted':<46} {'ok' if clean_ok else 'MISSED'}")

    planted = [o for o in outcomes if o[1] == "planted"]
    controls = [o for o in outcomes if o[1] == "control"]
    caught = sum(1 for o in planted if o[2])
    controls_ok = all(o[2] for o in controls)
    threshold = int(round(0.9 * len(planted)))
    return {"planted": len(planted), "caught": caught, "threshold": threshold,
            "controls_ok": controls_ok, "passed": caught >= threshold and controls_ok,
            "outcomes": outcomes}


def sample_claims(proj: Project, n: int = 100, seed: int = 0) -> Path:
    """Write a CSV review sheet of up to n claim-evidence pairs for human grading."""
    rows = []
    for c in proj.claims():
        if c["label"] == "pending":
            continue
        if c.get("sources"):
            for i, e in enumerate(c["sources"]):
                s = proj.source(e["source_id"]) or {}
                rows.append([c["id"], labels.display(c["label"]), c["statement"], i, e["source_id"],
                             s.get("title", ""), s.get("url", ""), e.get("passage", "")])
        else:
            rows.append([c["id"], labels.display(c["label"]), c["statement"], "", "", "", "",
                         "; ".join(t.get("log", "") for t in c.get("tests", []))])
    random.Random(seed).shuffle(rows)
    rows = rows[:n]
    out = proj.runs_dir / "eval" / f"review-sheet-seed{seed}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["claim", "label", "statement", "evidence_index", "source", "title", "url", "passage_or_logs",
                    "quote_exists (y/n)", "supports_claim (y/n)", "label_holds (y/n)", "reviewer_notes"])
        w.writerows(rows)
    return out
