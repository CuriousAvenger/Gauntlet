"""Depth modes, model routing and prices.

Everything here can be overridden with a `gauntlet.toml` in the working
directory (or the file named by $GAUNTLET_CONFIG):

    [models]
    strong = "claude-opus-5-5"
    mid    = "claude-sonnet-5-5"
    cheap  = "claude-haiku-5-5"

    [prices."my-local-model"]   # USD per million tokens
    input = 0.0
    output = 0.0

    [depth.standard]
    budget_usd = 8.0
"""

from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TIERS = ("strong", "mid", "cheap")

DEFAULT_MODELS = {
    "strong": "claude-opus-5-5",
    "mid": "claude-sonnet-5-5",
    "cheap": "claude-haiku-5-5",
}

# USD per million tokens (Anthropic first-party list prices; edit in gauntlet.toml).
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
}

# Which tier runs each stage (design doc, Architecture table).
STAGE_TIERS = {
    "scope": "strong",
    "survey": "cheap",
    "synthesize": "strong",
    "explore": "cheap",
    "check": "strong",
    "report": "mid",
}

ROLE_TIERS = {
    "orchestrator": "strong",
    "reader": "cheap",
    "synthesizer": "strong",
    "ideator": "cheap",
    "prover": "cheap",
    "breaker": "cheap",
    "referee": "strong",
    "writer": "mid",
}

DEFAULT_DEPTHS: dict[str, dict[str, Any]] = {
    "quick": {
        "sources": 10,
        "test_ideas": 0,        # ideas tested per cycle (0 = list as untested)
        "max_cycles": 1,
        "budget_usd": 5.00,
        "description": "A first look at a topic",
    },
    "standard": {
        "sources": 30,
        "test_ideas": 3,
        "max_cycles": 1,
        "budget_usd": 10.00,
        "description": "A class project or a work brief",
    },
    "deep": {
        "sources": 50,
        "test_ideas": 5,
        "max_cycles": 6,
        "budget_usd": 40.00,
        "description": "A research project",
    },
}

# Deep mode stops after this many consecutive cycles with no new evidence.
STALE_CYCLES = 3

# Replication tolerance: relative difference allowed between headline numbers.
REPLICATION_REL_TOL = 0.10

# Default seeds used by held-out checks when a spec gives none.
DEFAULT_HELD_OUT_SEEDS = [101, 202, 303]


@dataclass
class Config:
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    prices: dict[str, dict[str, float]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_PRICES))
    depths: dict[str, dict[str, Any]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_DEPTHS))
    replication_rel_tol: float = REPLICATION_REL_TOL
    stale_cycles: int = STALE_CYCLES
    source: str | None = None

    def model_for(self, tier: str) -> str:
        return self.models[tier]

    def price_for(self, model: str) -> dict[str, float] | None:
        return self.prices.get(model)


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg = Config()
    candidates = []
    if path:
        candidates.append(Path(path))
    elif os.environ.get("GAUNTLET_CONFIG"):
        candidates.append(Path(os.environ["GAUNTLET_CONFIG"]))
    else:
        candidates.append(Path.cwd() / "gauntlet.toml")
    for p in candidates:
        if p.is_file():
            with open(p, "rb") as f:
                data = tomllib.load(f)
            _merge(cfg, data)
            cfg.source = str(p)
            break
    return cfg


def _merge(cfg: Config, data: dict[str, Any]) -> None:
    for tier, model in data.get("models", {}).items():
        if tier not in TIERS:
            raise ValueError(f"unknown model tier {tier!r}; expected one of {TIERS}")
        cfg.models[tier] = str(model)
    for model, p in data.get("prices", {}).items():
        cfg.prices[model] = {"input": float(p["input"]), "output": float(p["output"])}
    for name, d in data.get("depth", {}).items():
        cfg.depths.setdefault(name, {}).update(d)
    checks = data.get("checks", {})
    if "replication_rel_tol" in checks:
        cfg.replication_rel_tol = float(checks["replication_rel_tol"])
    if "stale_cycles" in checks:
        cfg.stale_cycles = int(checks["stale_cycles"])
