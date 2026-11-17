"""Topic profiles: field detection, profile drafting/parsing, expert packs."""

from __future__ import annotations

import re
import shutil
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any

FIELDS = (
    "math-physics-cs",
    "software-engineering",
    "economics-policy",
    "medicine-biology",
    "history-humanities",
    "general",
)

# Keyword cues for a first guess. The orchestrator refines the profile and the
# user can edit it; this only has to be a sensible default.
_CUES: dict[str, list[str]] = {
    "math-physics-cs": [
        "quantum", "theorem", "proof", "algorithm", "complexity", "physics", "equation",
        "matrix", "linear system", "qubit", "entropy", "lattice", "graph", "prime",
        "conjecture", "topology", "relativity", "particle", "simulation", "fluid", "lower bound",
    ],
    "software-engineering": [
        "software", "code", "library", "framework", "api", "database", "latency", "compiler",
        "kubernetes", "python", "rust", "javascript", "benchmark", "performance", "cache",
        "server", "deploy", "bug", "programming", "open source", "llm inference",
    ],
    "economics-policy": [
        "economy", "economic", "inflation", "tax", "policy", "minimum wage", "gdp", "market",
        "trade", "tariff", "unemployment", "housing", "regulation", "subsidy", "budget", "poverty",
    ],
    "medicine-biology": [
        "disease", "drug", "vaccine", "cancer", "gene", "protein", "clinical", "patient",
        "treatment", "therapy", "symptom", "health", "diet", "brain", "cell", "virus",
        "bacteria", "medical", "dose", "sleep", "exercise", "medicine", "ibuprofen", "aspirin",
        "antibiotic", "side effect", "infection", "pregnan", "blood pressure", "pain", "liver", "heart",
    ],
    "history-humanities": [
        "history", "historical", "century", "empire", "war", "revolution", "ancient",
        "medieval", "philosophy", "literature", "poet", "novel ", "religion", "art",
        "archive", "dynasty", "colonial",
    ],
}

HIGH_STAKES_FIELDS = {"medicine-biology"}
_HIGH_STAKES_CUES = [
    "should i", "legal", "lawsuit", "contract", "invest", "stock", "mortgage", "loan",
    "diagnos", "dose", "medication", "symptom", "side effect", "safe to take", "treatment", "tax return", "retirement",
]


def detect_field(question: str) -> str:
    q = f" {question.lower()} "
    scores = {f: sum(1 for cue in cues if cue in q) for f, cues in _CUES.items()}
    best = max(scores, key=lambda f: scores[f])
    return best if scores[best] > 0 else "general"


def is_high_stakes(question: str, field: str) -> bool:
    q = question.lower()
    return field in HIGH_STAKES_FIELDS or any(c in q for c in _HIGH_STAKES_CUES)


def _template(name: str) -> str:
    return resources.files("gauntlet").joinpath("profiles", f"{name}.md").read_text(encoding="utf-8")


def draft_profile(
    question: str,
    field: str | None = None,
    pack: str | None = None,
    reader_level: str | None = None,
) -> str:
    field = field or detect_field(question)
    if field not in FIELDS:
        raise ValueError(f"unknown field {field!r}; choose from {FIELDS}")
    body = Template(_template(field)).safe_substitute(
        question=question,
        reader_level=reader_level or "general",
        high_stakes=str(is_high_stakes(question, field)).lower(),
        pack=pack or "",
    )
    return body


def parse_profile(text: str) -> dict[str, Any]:
    """Parse the `---` front matter of profile.md into a dict (simple key: value)."""
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n", text, re.S)
    out: dict[str, Any] = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        elif "," in v and k.endswith("s"):
            out[k] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            out[k] = v
    for k in ("authoritative_kinds",):
        if isinstance(out.get(k), str):
            out[k] = [out[k]] if out[k] else []
    return out


# ---- expert packs -------------------------------------------------------------

def available_packs() -> list[str]:
    root = resources.files("gauntlet").joinpath("packs")
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def install_pack(name: str, dest: Path) -> None:
    """Copy a built-in pack, or a pack directory given by path, into the project."""
    src_path = Path(name)
    if src_path.is_dir():
        shutil.copytree(src_path, dest)
        return
    if name not in available_packs():
        raise ValueError(f"unknown pack {name!r}; available: {available_packs()} (or pass a directory)")
    with resources.as_file(resources.files("gauntlet").joinpath("packs", name)) as p:
        shutil.copytree(p, dest)
