#!/usr/bin/env python3
"""Rank ideas by judged pairwise comparisons, keeping the search diverse.

  rank.py pairs [--n 5]                         the next pairs of ideas for judges to compare
  rank.py match IDEA_A IDEA_B WINNER --criterion C --reason "..."
                                                record a verdict (WINNER: IDEA_A, IDEA_B or draw;
                                                C: the deciding criterion, one of difference,
                                                testability, importance, plausibility)
  rank.py top [--k 5]                           the leaderboard, clusters of similar ideas, and the
                                                diverse top: the best idea of each cluster, the ones
                                                to test or evolve next
  rank.py review [--generation N]               what the verdicts rewarded and why, for the
                                                meta-review that guides the next generation

Only grounded ideas take part (untested or tested). Scores are Elo ratings recomputed from
every recorded verdict in tournament.jsonl, so a verdict can never be quietly edited away.
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Any

from claim import claims
from lib.similarity import similarity
from source import ROOT, Parser, fail, finish, locked

TOURNAMENT = ROOT / "tournament.jsonl"
START, K = 1200.0, 32.0
CLUSTER = 0.35  # ideas at least this similar to a cluster's best idea join that cluster
CRITERIA = ("difference", "testability", "importance", "plausibility")


def eligible() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in claims() if "settling_test" in c and c["label"] in ("untested", "tested")}


def matches() -> list[dict[str, Any]]:
    return [json.loads(l) for l in TOURNAMENT.read_text().splitlines() if l.strip()] if TOURNAMENT.exists() else []


def ratings() -> tuple[dict[str, float], dict[str, int]]:
    """Elo rating and number of comparisons for every idea, replayed from all verdicts."""
    elo: dict[str, float] = {}
    played: dict[str, int] = {}
    for m in matches():
        a, b = m["a"], m["b"]
        ra, rb = elo.get(a, START), elo.get(b, START)
        expected = 1 / (1 + 10 ** ((rb - ra) / 400))
        score = 1.0 if m["winner"] == a else 0.0 if m["winner"] == b else 0.5
        elo[a], elo[b] = ra + K * (score - expected), rb - K * (score - expected)
        played[a], played[b] = played.get(a, 0) + 1, played.get(b, 0) + 1
    return elo, played


def leaderboard() -> list[dict[str, Any]]:
    """Ideas best first, each assigned to a cluster led by the best idea it resembles."""
    elo, played = ratings()
    ideas = sorted(eligible().values(), key=lambda c: -elo.get(c["id"], START))
    leaders: list[dict[str, Any]] = []
    rows = []
    for c in ideas:
        cluster = next((l["id"] for l in leaders if similarity(c["statement"], l["statement"]) >= CLUSTER), None)
        if cluster is None:
            leaders.append(c)
            cluster = c["id"]
        rows.append({"id": c["id"], "elo": round(elo.get(c["id"], START)), "comparisons": played.get(c["id"], 0),
                     "cluster": cluster, "label": c["label"], "generation": c.get("generation", 1),
                     "statement": c["statement"]})
    return rows


def diverse_top(k: int) -> list[dict[str, Any]]:
    """The best idea of each cluster, best first: diversity before depth."""
    return [r for r in leaderboard() if r["cluster"] == r["id"]][:k]


def next_pairs(n: int) -> list[tuple[str, str]]:
    """Ideas with the fewest comparisons first, each against the closest-rated idea it has not met."""
    elo, played = ratings()
    met = {frozenset((m["a"], m["b"])) for m in matches()}
    pool = sorted(eligible(), key=lambda i: (played.get(i, 0), -elo.get(i, START)))
    pairs, used = [], set()
    for a in pool:
        if a in used:
            continue
        partners = [b for b in pool if b != a and b not in used and frozenset((a, b)) not in met]
        if partners:
            b = min(partners, key=lambda b: abs(elo.get(a, START) - elo.get(b, START)))
            pairs.append((a, b) if random.random() < 0.5 else (b, a))  # judges favour whichever comes first
            used |= {a, b}
        if len(pairs) == n:
            break
    return pairs


def review(generation: int | None = None) -> dict[str, Any]:
    """Verdicts grouped by deciding criterion, with each idea's record, for a meta-review."""
    every = {c["id"]: c for c in claims() if "settling_test" in c}
    elo, _ = ratings()
    picked = [m for m in matches() if generation is None
              or generation in (every.get(m["a"], {}).get("generation"), every.get(m["b"], {}).get("generation"))]
    by_criterion: dict[str, list[dict[str, str]]] = {c: [] for c in CRITERIA}
    record: dict[str, dict[str, int]] = {}
    for m in picked:
        if m["winner"] == "draw":
            continue
        loser = m["b"] if m["winner"] == m["a"] else m["a"]
        by_criterion[m.get("criterion", "difference")].append(
            {"winner": every.get(m["winner"], {}).get("statement", m["winner"]),
             "loser": every.get(loser, {}).get("statement", loser), "reason": m["reason"]})
        record.setdefault(m["winner"], {"won": 0, "lost": 0})["won"] += 1
        record.setdefault(loser, {"won": 0, "lost": 0})["lost"] += 1
    tested = [{"id": c["id"], "label": c["label"], "statement": c["statement"]}
              for c in every.values() if c["label"] in ("tested", "refuted")]
    return {"verdicts": len(picked), "deciding_criteria": {c: len(v) for c, v in by_criterion.items()},
            "by_criterion": {c: v[-10:] for c, v in by_criterion.items() if v},
            "records": {i: {**r, "elo": round(elo.get(i, START))} for i, r in record.items()},
            "test_outcomes": tested}


def _brief(c: dict[str, Any]) -> dict[str, Any]:
    return {"id": c["id"], "statement": c["statement"], "difference": c.get("difference", ""),
            "closest_prior_work": [f"{q['source']}: \"{q['quote']}\"" for q in c.get("prior_work", [])],
            "settling_test": c["settling_test"], "label": c["label"]}


def main() -> None:
    p = Parser(__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("pairs").add_argument("--n", type=int, default=5)
    m = sub.add_parser("match")
    m.add_argument("a")
    m.add_argument("b")
    m.add_argument("winner")
    m.add_argument("--criterion", required=True, choices=CRITERIA)
    m.add_argument("--reason", required=True)
    sub.add_parser("top").add_argument("--k", type=int, default=5)
    sub.add_parser("review").add_argument("--generation", type=int)
    a = p.parse_args()

    ideas = eligible()
    if a.command == "pairs":
        pairs = next_pairs(a.n)
        finish({"pairs": [[_brief(ideas[x]), _brief(ideas[y])] for x, y in pairs],
                **({} if pairs else {"note": "every eligible pair has been compared, or fewer than two grounded ideas"})})
    if a.command == "match":
        for i in (a.a, a.b):
            if i not in ideas:
                fail(f"{i} is not a grounded, unrefuted idea (only untested or tested ideas are ranked)")
        if a.a == a.b or a.winner not in (a.a, a.b, "draw"):
            fail("compare two different ideas; WINNER is one of them or 'draw'")
        if not a.reason.strip():
            fail("give the reason for the verdict")
        with locked(), open(TOURNAMENT, "a", encoding="utf-8") as f:
            f.write(json.dumps({"a": a.a, "b": a.b, "winner": a.winner, "criterion": a.criterion,
                                "reason": a.reason.strip()}) + "\n")
        elo, _ = ratings()
        finish({"recorded": f"{a.a} vs {a.b}: {a.winner}", "elo": {i: round(elo[i]) for i in (a.a, a.b)}})
    if a.command == "review":
        finish(review(a.generation))
    board = leaderboard()
    top = diverse_top(a.k)
    gens: dict[int, dict[str, int]] = {}
    for r in board:
        g = gens.setdefault(r["generation"], {"ideas": 0, "in_diverse_top": 0})
        g["ideas"] += 1
        g["in_diverse_top"] += any(t["id"] == r["id"] for t in top)
    finish({"diverse_top": top, "clusters": len({r["cluster"] for r in board}), "leaderboard": board,
            "generations": {str(g): v for g, v in sorted(gens.items())}})


if __name__ == "__main__":
    main()
