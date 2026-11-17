"""Exploration: grounded ideas, the duplicate filter, the tournament and the frontier."""
from conftest import QUOTE
from test_ideas import PRIOR

URL = "https://a.example/paper"


def propose(run, statement, **extra):
    req = {"statement": statement, "settling_test": "simulate 20 random instances", "prior_work": PRIOR,
           "difference": "applies it in a new setting", **extra}
    return run("claim.py", stdin=req)


def test_ideas_must_quote_their_closest_prior_work(run, sources):
    code, out = run("claim.py", stdin={"statement": "Adaptive readout could halve shots for chemistry problems.",
                                       "settling_test": "compare shots on 20 molecules"})
    assert code == 0 and out["label"] == "pending" and any("prior_work" in f for f in out["fix"])
    assert out["closest_in_sources"][0]["source"] in ("S1", "S2")  # points the agent at what to quote
    code, out = run("claim.py", stdin={"add_to": out["id"], "prior_work": [{"url": URL, "quote": QUOTE}],
                                       "difference": "moves the method from fluids to chemistry"})
    assert out["label"] == "untested" and "fix" not in out
    bad = propose(run, "Readout savings transfer to optimisation problems.",
                  prior_work=[{"url": URL, "quote": "a sentence this paper never contains anywhere at all"}])[1]
    assert bad["label"] == "pending" and any("word for word" in f for f in bad["fix"])


def test_duplicates_are_refused_and_similar_ideas_must_say_how_they_differ(run, sources):
    assert propose(run, "Readout cost scales linearly with the condition number.")[0] == 0
    code, out = propose(run, "Readout cost scales linearly with condition number.")
    assert code == 1 and "near-duplicate of I1" in out["error"]
    code, out = propose(run, "Readout cost scales quadratically with the condition number.")
    assert code == 1 and "distinct_from" in out["error"]
    code, out = propose(run, "Readout cost scales quadratically with the condition number.",
                        distinct_from={"I1": "quadratic, not linear, growth"})
    assert code == 0 and out["id"] == "I2"


def test_tournament_elo_and_diverse_top(run, sources):
    a = propose(run, "Importance sampling cuts readout shots on lattice fluid solvers.")[1]["id"]
    b = propose(run, "Importance sampling cuts readout shots on lattice fluid solvers at larger grids.",
                distinct_from={a: "larger grids"})[1]["id"]
    c = propose(run, "Classical shadows with derandomisation beat uniform Pauli sampling for chemistry.")[1]["id"]
    pairs = run("rank.py", "pairs", "--n", "5")[1]["pairs"]
    assert len(pairs) == 1 and len({p["id"] for p in pairs[0]}) == 2   # three ideas: one disjoint pair per round
    assert run("rank.py", "match", a, b, a, "--reason", "clearer test")[0] == 0
    assert run("rank.py", "match", a, c, a, "--reason", "more important")[0] == 0
    assert run("rank.py", "match", a, a, a, "--reason", "x")[0] == 2
    top = run("rank.py", "top", "--k", "5")[1]
    assert [r["id"] for r in top["leaderboard"]][0] == a
    assert [r["id"] for r in top["diverse_top"]] == [a, c]   # b is in a's cluster, so it is not in the diverse top
    assert top["generations"]["1"]["ideas"] == 3


def test_pending_ideas_are_not_ranked(run, sources):
    out = run("claim.py", stdin={"statement": "An ungrounded idea about readout.", "settling_test": "try it"})[1]
    assert run("rank.py", "match", out["id"], out["id"], "draw", "--reason", "x")[0] == 2
