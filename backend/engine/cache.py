"""Analysis caching.

Engine time is the scarcest resource in this app, so every completed position search
is cached under a key that captures *everything* that can change the answer:
engine build, position, limits and resource settings. A cache hit is only valid if
the configuration that produced it matches exactly, otherwise stale numbers of a
different depth would silently be mixed into one review.

Two implementations: an in-memory one (tests, single run) and a SQLite-backed one in
``storage/cache.py`` that survives restarts.
"""

import hashlib
from typing import Dict, Optional, Protocol

from models.evidence import PositionEval


class AnalysisCache(Protocol):
    def get(self, key: str) -> Optional[PositionEval]:  # pragma: no cover - protocol
        ...

    def put(self, key: str, value: PositionEval) -> None:  # pragma: no cover - protocol
        ...


def cache_key(
    *,
    fen: str,
    engine_name: str,
    depth: int,
    nodes: int,
    multipv: int,
    threads: int,
    hash_mb: int,
    pov: str = "",
) -> str:
    """Stable hash of every input that affects the engine's answer.

    ``pov`` matters: stored evaluations are normalized to the analyzed player's point
    of view, so the same FEN analyzed for the other side is a different result.
    """
    material = "|".join(
        [
            engine_name,
            fen,
            "pov={}".format(pov),
            "d={}".format(depth),
            "n={}".format(nodes),
            "mpv={}".format(multipv),
            "t={}".format(threads),
            "h={}".format(hash_mb),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class NullCache:
    """No-op cache: used when caching is disabled or in unit tests."""

    def get(self, key: str) -> Optional[PositionEval]:
        return None

    def put(self, key: str, value: PositionEval) -> None:
        return None


class InMemoryCache:
    def __init__(self) -> None:
        self._store: Dict[str, PositionEval] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[PositionEval]:
        found = self._store.get(key)
        if found is None:
            self.misses += 1
        else:
            self.hits += 1
        return found

    def put(self, key: str, value: PositionEval) -> None:
        self._store[key] = value

    def __len__(self) -> int:
        return len(self._store)
