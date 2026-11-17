"""Cost estimates before a run, a spend ledger during it, and stop conditions."""

from __future__ import annotations

from typing import Any

from .config import STAGE_TIERS, Config
from .util import now_iso

# Rough tokens per unit of work (input, output). Agent loops re-send context on
# each tool call, which AGENT_OVERHEAD accounts for. These are planning numbers:
# the ledger records what was actually spent.
AGENT_OVERHEAD = 3.0
PER_UNIT = {
    "scope": (6_000, 2_000),            # per run
    "survey": (20_000, 2_500),          # per source read
    "synthesize": (2_000, 400),         # per source in the map
    "synthesize_base": (8_000, 6_000),  # per cycle
    "ideate": (15_000, 3_000),          # per cycle
    "explore": (40_000, 8_000),         # per idea tested (prover + breaker + replica)
    "check": (5_000, 800),              # per claim refereed
    "report": (40_000, 10_000),         # per report
}
CLAIMS_PER_SOURCE = 1.5
UNTESTED_IDEAS_PER_CYCLE = 3


def _usd(cfg: Config, tier: str, tin: float, tout: float) -> float | None:
    price = cfg.price_for(cfg.model_for(tier))
    if price is None:
        return None
    return (tin * price["input"] + tout * price["output"]) / 1_000_000


def estimate(cfg: Config, depth: str) -> dict[str, Any]:
    d = cfg.depths[depth]
    cycles = d["max_cycles"]
    n_src = d["sources"]
    n_ideas = d["test_ideas"] * cycles
    n_claims = n_src * CLAIMS_PER_SOURCE + n_ideas
    work = {
        "scope": (1, "scope"),
        "survey": (n_src, "survey"),
        "synthesize": None,
        "explore": None,
        "check": (n_claims, "check"),
        "report": (1, "report"),
    }
    rows = []
    total = 0.0
    unknown = []
    for stage, tier in STAGE_TIERS.items():
        if stage == "synthesize":
            tin = PER_UNIT["synthesize_base"][0] * cycles + PER_UNIT["synthesize"][0] * n_src
            tout = PER_UNIT["synthesize_base"][1] * cycles + PER_UNIT["synthesize"][1] * n_src
        elif stage == "explore":
            tin = PER_UNIT["ideate"][0] * cycles + PER_UNIT["explore"][0] * n_ideas
            tout = PER_UNIT["ideate"][1] * cycles + PER_UNIT["explore"][1] * n_ideas
        else:
            units, key = work[stage]
            tin, tout = PER_UNIT[key][0] * units, PER_UNIT[key][1] * units
        tin *= AGENT_OVERHEAD
        tout *= AGENT_OVERHEAD
        usd = _usd(cfg, tier, tin, tout)
        if usd is None:
            unknown.append(cfg.model_for(tier))
        else:
            total += usd
        rows.append({"stage": stage, "tier": tier, "model": cfg.model_for(tier),
                     "input_tokens": int(tin), "output_tokens": int(tout), "usd": usd})
    return {
        "depth": depth,
        "sources": n_src,
        "ideas_tested": n_ideas,
        "cycles": cycles,
        "rows": rows,
        "total_usd": round(total, 2),
        "budget_usd": d["budget_usd"],
        "unpriced_models": sorted(set(unknown)),
    }


def format_estimate(est: dict[str, Any]) -> str:
    lines = [
        f"Estimate for depth '{est['depth']}': ~{est['sources']} sources, "
        f"{est['ideas_tested']} idea(s) tested, up to {est['cycles']} cycle(s)",
        f"{'stage':<11} {'tier':<7} {'model':<22} {'in tok':>10} {'out tok':>9} {'USD':>8}",
    ]
    for r in est["rows"]:
        usd = f"{r['usd']:.2f}" if r["usd"] is not None else "?"
        lines.append(f"{r['stage']:<11} {r['tier']:<7} {r['model']:<22} {r['input_tokens']:>10,} {r['output_tokens']:>9,} {usd:>8}")
    lines.append(f"{'total':<62} {est['total_usd']:>8.2f}")
    lines.append(f"Hard budget for this depth: ${est['budget_usd']:.2f}")
    if est["total_usd"] > est["budget_usd"]:
        lines.append("Warning: the estimate exceeds the budget; the run will stop early unless you raise --budget.")
    if est["unpriced_models"]:
        lines.append(f"No price configured for: {', '.join(est['unpriced_models'])} (add [prices] in gauntlet.toml)")
    lines.append("Estimates assume typical agent overhead; the ledger records actual spend.")
    return "\n".join(lines)


def ledger_row(cfg: Config, stage: str, agent: str, tier: str | None, model: str | None,
               input_tokens: int, output_tokens: int, usd: float | None = None) -> dict[str, Any]:
    tier = tier or STAGE_TIERS.get(stage, "mid")
    model = model or cfg.model_for(tier)
    if usd is None:
        p = cfg.price_for(model)
        usd = (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000 if p else 0.0
    return {"at": now_iso(), "stage": stage, "agent": agent, "tier": tier, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens, "usd": round(usd, 6)}


def spend(project) -> dict[str, Any]:
    rows = project.ledger()
    by_tier: dict[str, float] = {}
    by_stage: dict[str, float] = {}
    for r in rows:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + r["usd"]
        by_stage[r["stage"]] = by_stage.get(r["stage"], 0) + r["usd"]
    total = sum(by_tier.values())
    budget = project.state()["budget_usd"]
    return {"total_usd": round(total, 4), "budget_usd": budget, "remaining_usd": round(budget - total, 4),
            "by_tier": by_tier, "by_stage": by_stage, "entries": len(rows)}


# ---- cycles and stop conditions -------------------------------------------------

def evidence_snapshot(project) -> dict[str, Any]:
    claims = project.claims()
    return {
        "sources_read": sum(1 for s in project.sources() if s.get("status") == "read"),
        "claims": len(claims),
        "labelled": {c["id"]: c["label"] for c in claims},
    }


def start_cycle(project) -> dict[str, Any]:
    s = project.state()
    if s["cycles"] and not s["cycles"][-1].get("ended"):
        return s["cycles"][-1]
    cyc = {"n": len(s["cycles"]) + 1, "round": len(s["rounds"]), "started": now_iso(),
           "before": evidence_snapshot(project)}
    s["cycles"].append(cyc)
    project.save_state(s)
    return cyc


def end_cycle(project) -> dict[str, Any]:
    s = project.state()
    if not s["cycles"] or s["cycles"][-1].get("ended"):
        raise ValueError("no open cycle; run `gauntlet cycle start` first")
    cyc = s["cycles"][-1]
    before, after = cyc["before"], evidence_snapshot(project)
    new_sources = after["sources_read"] - before["sources_read"]
    new_claims = after["claims"] - before["claims"]
    relabelled = sum(1 for k, v in after["labelled"].items() if before["labelled"].get(k) != v)
    cyc.update(ended=now_iso(), new_sources=new_sources, new_claims=new_claims, relabelled=relabelled,
               new_evidence=bool(new_sources or new_claims or relabelled))
    cyc.pop("before", None)
    s["cycles"][-1] = cyc
    project.save_state(s)
    return cyc


def should_stop(project) -> tuple[bool, str]:
    s = project.state()
    cfg = project.config
    rounds = len(s["rounds"])
    cycles = [c for c in s["cycles"] if c.get("round", 1) == rounds and c.get("ended")]
    sp = spend(project)
    if sp["total_usd"] >= sp["budget_usd"]:
        return True, f"budget spent (${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f})"
    if len(cycles) >= s["targets"]["max_cycles"]:
        return True, f"cycle limit reached ({len(cycles)}/{s['targets']['max_cycles']})"
    k = cfg.stale_cycles
    if len(cycles) >= k and not any(c.get("new_evidence") for c in cycles[-k:]):
        return True, f"{k} cycles in a row added no new evidence"
    return False, f"continue: {len(cycles)}/{s['targets']['max_cycles']} cycles, ${sp['total_usd']:.2f} of ${sp['budget_usd']:.2f} spent"
