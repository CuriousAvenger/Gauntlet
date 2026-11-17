"""Word-overlap similarity between short texts (standard library only).

Used to reject near-duplicate ideas, to cluster ideas so the search stays diverse, and to
point an ideator at the closest passage in the sources already read. It compares words
and word pairs, so it catches near-copies and close rewordings, not deep paraphrases;
judges catch the rest.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an and are as at be been being but by can could did do does for from had has have how
if in into is it its may might more most no not of on or our so such than that the their them then there
these they this those to under up was we were what when where which while who will with would you your
using use used based via also very can't per over between""".split())


def _terms(text: str) -> Counter:
    words = [w[:-1] if len(w) > 4 and w.endswith("s") else w
             for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]
    return Counter(words + [f"{a}_{b}" for a, b in zip(words, words[1:])])


def similarity(a: str, b: str) -> float:
    """Cosine similarity of word and word-pair counts: 0 = nothing shared, 1 = same wording."""
    x, y = _terms(a), _terms(b)
    dot = sum(x[t] * y[t] for t in x.keys() & y.keys())
    norm = math.sqrt(sum(v * v for v in x.values())) * math.sqrt(sum(v * v for v in y.values()))
    return dot / norm if norm else 0.0


def passages(text: str, sentences: int = 2) -> list[str]:
    """Overlapping windows of a few sentences, the unit a quote is taken from."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n\s*\n", text) if len(s.strip()) > 20]
    return [" ".join(parts[i:i + sentences]) for i in range(max(1, len(parts) - sentences + 1))] if parts else []


def closest(text: str, candidates: list[tuple[str, str]], k: int = 3) -> list[tuple[float, str, str]]:
    """The k most similar (score, key, candidate text), best first."""
    scored = sorted(((similarity(text, c), key, c) for key, c in candidates), reverse=True)
    return [s for s in scored[:k] if s[0] > 0]
