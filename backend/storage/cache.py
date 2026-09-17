"""SQLite-backed caches for engine output and explanation text.

Both caches exist to keep the app responsive: engine time is the scarcest resource, and
LLM calls cost money and latency. Cache keys include everything that changes the answer
(engine build, depth, limits, model, prompt version), so a hit is always a valid answer
for the current configuration.
"""

import logging
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.evidence import PositionEval
from storage.models import AnalysisCacheEntry, Game, LLMExplanation
from storage.db import Database

logger = logging.getLogger(__name__)

#: Soft cap so the cache cannot grow without bound on a laptop.
MAX_CACHE_ENTRIES = 20000


class SqliteAnalysisCache:
    """Implements ``engine.cache.AnalysisCache`` on top of SQLite."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[PositionEval]:
        with self._db.session() as session:
            row = session.get(AnalysisCacheEntry, key)
            if row is None:
                self.misses += 1
                return None
            try:
                result = PositionEval.model_validate(row.payload)
            except Exception:  # pragma: no cover - schema drift after an upgrade
                logger.warning("Dropping unreadable cache entry %s", key)
                session.delete(row)
                self.misses += 1
                return None
            self.hits += 1
            return result

    def put(self, key: str, value: PositionEval) -> None:
        with self._db.session() as session:
            existing = session.get(AnalysisCacheEntry, key)
            if existing is None:
                session.add(
                    AnalysisCacheEntry(
                        cache_key=key,
                        fen=value.fen,
                        engine_name=value.engine_name,
                        depth=value.depth,
                        multipv=value.multipv,
                        payload=value.model_dump(mode="json"),
                    )
                )
            else:
                existing.payload = value.model_dump(mode="json")

    def prune(self, keep: int = MAX_CACHE_ENTRIES) -> int:
        """Delete the oldest entries beyond ``keep``; returns how many were removed."""
        with self._db.session() as session:
            total = session.execute(
                select(AnalysisCacheEntry.cache_key).order_by(AnalysisCacheEntry.created_at)
            ).scalars().all()
            if len(total) <= keep:
                return 0
            to_delete = total[: len(total) - keep]
            session.execute(
                delete(AnalysisCacheEntry).where(AnalysisCacheEntry.cache_key.in_(to_delete))
            )
            return len(to_delete)


class SqliteExplanationCache:
    """Implements ``coaching.explainer.ExplanationCache``."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get(self, key: str) -> Optional[dict]:
        with self._db.session() as session:
            row = session.execute(
                select(LLMExplanation).where(LLMExplanation.cache_key == key)
            ).scalar_one_or_none()
            if row is None:
                return None
            payload = dict(row.payload or {})
            payload["cached"] = True
            return payload

    def put(self, key: str, value: dict) -> None:
        with self._db.session() as session:
            row = session.execute(
                select(LLMExplanation).where(LLMExplanation.cache_key == key)
            ).scalar_one_or_none()
            game_id = _game_id_from_payload(value)
            if row is None:
                session.add(
                    LLMExplanation(
                        game_id=game_id,
                        scope="summary" if key.startswith("summary:") else "moment",
                        ref_key=key,
                        cache_key=key,
                        source=str(value.get("source", "rules")),
                        model=value.get("model"),
                        payload=value,
                    )
                )
            else:
                row.payload = value
                row.source = str(value.get("source", "rules"))
                row.model = value.get("model")


def _game_id_from_payload(value: dict) -> Optional[str]:
    """Explanations are attached to a game when the payload says which one.

    Moment explanations are keyed by position, not by game, so the link is optional.
    """
    game_id = value.get("game_id")
    return str(game_id) if game_id else None
