"""Deterministic, dependency-free bag-of-words embedding (no model, no network)."""

from __future__ import annotations

import hashlib
import math
import re

DIMENSIONS = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0:
        return vector
    return [component / norm for component in vector]
