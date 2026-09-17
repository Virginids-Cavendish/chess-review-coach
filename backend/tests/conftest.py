"""Shared test fixtures and helpers.

The suite is split so that the fast, deterministic parts (scores, board primitives,
concepts, taxonomy, PGN, storage, LLM plumbing) always run, while anything that needs a
real Stockfish binary is skipped with an explicit reason instead of silently passing.

``make_context`` builds a :class:`DetectionContext` from a FEN plus explicit engine
lines, so every concept detector can be tested against a known position without an
engine.
"""

import os
from pathlib import Path
from typing import List, Optional

import chess
import pytest

from analysis.thresholds import THRESHOLDS
from config import DEFAULT_STOCKFISH_PATH, settings
from models.enums import Color, GamePhase, Severity
from models.evidence import (
    BoardContext,
    CandidateMove,
    EngineEvidence,
    PositionEval,
    WdlDistribution,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def stockfish_available() -> bool:
    return settings.resolved_stockfish_path is not None


requires_engine = pytest.mark.skipif(
    not stockfish_available(),
    reason="Stockfish binary not found; run scripts/install_stockfish.py",
)


@pytest.fixture(scope="session")
def engine_path() -> Path:
    path = settings.resolved_stockfish_path
    if path is None:
        pytest.skip("Stockfish binary not found")
    return path


@pytest.fixture()
def engine(engine_path: Path):
    """A real Stockfish process, started lazily and always shut down."""
    from engine.stockfish import EngineConfig, StockfishEngine

    instance = StockfishEngine(
        EngineConfig(path=engine_path, threads=2, hash_mb=32, startup_timeout=20.0)
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture(scope="session")
def test_settings():
    """测试专用配置。

    关键点：**清空 DEEPSEEK_API_KEY**。否则开发机上真实的 .env 会被读进来，
    测试既会依赖外部配置，又会真的花钱调用线上 API——这两件事都不该发生在测试里。
    需要测试 LLM 路径的地方一律用假的 provider（见 tests/test_llm.py）。
    """
    return settings.model_copy(
        update={
            "deepseek_api_key": "",
            "deepseek_base_url": "http://127.0.0.1:9",
            "llm_timeout": 2.0,
        }
    )


@pytest.fixture()
def temp_database(tmp_path: Path):
    """An isolated SQLite database per test."""
    from storage.db import Database

    database = Database("sqlite:///{}".format(tmp_path / "test.db"))
    database.create_all()
    try:
        yield database
    finally:
        database.dispose()


def wdl_from_expected(expected: float) -> WdlDistribution:
    """A WDL whose expected score is exactly ``expected`` (no draws)."""
    value = min(1.0, max(0.0, expected))
    return WdlDistribution(win=value, draw=0.0, loss=round(1.0 - value, 6))


def make_candidate(
    uci: str,
    san: str,
    *,
    expected: float = 0.5,
    cp: Optional[int] = None,
    mate: Optional[int] = None,
    pv_uci: Optional[List[str]] = None,
    pv_san: Optional[List[str]] = None,
) -> CandidateMove:
    distribution = wdl_from_expected(expected)
    return CandidateMove(
        uci=uci,
        san=san,
        cp=cp if cp is not None else (None if mate is not None else int((expected - 0.5) * 800)),
        mate=mate,
        wdl=distribution,
        expected_score=round(distribution.expected_score(), 6),
        pv_uci=list(pv_uci) if pv_uci is not None else [uci],
        pv_san=list(pv_san) if pv_san is not None else [san],
    )


def legal_san(board: chess.Board, uci: str) -> str:
    for move in board.legal_moves:
        if move.uci() == uci:
            return board.san(move)
    raise AssertionError("{} is not legal in {}".format(uci, board.fen()))


def make_context(
    fen: str,
    played_uci: str,
    *,
    best_uci: Optional[str] = None,
    pov: Color = Color.WHITE,
    severity: Severity = Severity.BLUNDER,
    phase: GamePhase = GamePhase.MIDDLEGAME,
    move_number: int = 20,
    expected_before: float = 0.70,
    expected_after: float = 0.45,
    mate_before: Optional[int] = None,
    mate_after: Optional[int] = None,
    played_line_uci: Optional[List[str]] = None,
    best_line_uci: Optional[List[str]] = None,
    is_engine_best: bool = False,
    best_move_unique: bool = False,
    alternatives: Optional[List[CandidateMove]] = None,
    move_history=None,
):
    """Build a detection context for one synthetic move.

    ``played_line_uci`` / ``best_line_uci`` follow the pipeline convention: the played
    line starts with the played move, the best line starts with the engine's choice.
    """
    from concepts.base import DetectionContext

    board_before = chess.Board(fen)
    move = next((m for m in board_before.legal_moves if m.uci() == played_uci), None)
    assert move is not None, "played move {} is not legal in {}".format(played_uci, fen)
    played_san = board_before.san(move)
    board_after = board_before.copy()
    board_after.push(move)

    expected_mover = chess.WHITE if pov is Color.WHITE else chess.BLACK
    assert move.from_square is not None
    assert (
        board_before.piece_at(move.from_square).color == expected_mover
    ), "test setup error: the played move belongs to the other side"

    chosen_uci = best_uci or (played_uci if is_engine_best else played_uci)
    chosen_san = legal_san(board_before, chosen_uci)
    before_candidate = make_candidate(
        chosen_uci, chosen_san, expected=expected_before, mate=mate_before
    )
    after_candidate = make_candidate(
        played_uci, played_san, expected=expected_after, mate=mate_after
    )

    evidence = EngineEvidence(
        pov_color=pov,
        evaluation_before=before_candidate.cp / 100.0 if before_candidate.cp is not None else None,
        evaluation_after=after_candidate.cp / 100.0 if after_candidate.cp is not None else None,
        mate_before=mate_before,
        mate_after=mate_after,
        wdl_before=before_candidate.wdl,
        wdl_after=after_candidate.wdl,
        expected_score_before=before_candidate.expected_score,
        expected_score_after=after_candidate.expected_score,
        expected_score_loss=round(max(0.0, expected_before - expected_after), 6),
        best_move_uci=chosen_uci,
        best_move_san=chosen_san,
        best_line_uci=list(best_line_uci) if best_line_uci is not None else [chosen_uci],
        best_line_san=[legal_san(board_before, uci) for uci in (best_line_uci or [chosen_uci])],
        played_line_uci=list(played_line_uci)
        if played_line_uci is not None
        else [played_uci],
        played_line_san=[played_san] + _san_tail(board_after, (played_line_uci or [played_uci])[1:]),
        depth_before=12,
        depth_after=12,
        is_engine_best=is_engine_best,
        best_move_unique=best_move_unique,
        alternatives=alternatives or [],
    )

    return DetectionContext(
        board_before=board_before,
        board_after=board_after,
        played_move=move,
        played_san=played_san,
        player_color=pov,
        evidence=evidence,
        severity=severity,
        phase=phase,
        move_number=move_number,
        move_history=move_history or [],
        thresholds=THRESHOLDS.detection,
    )


def _san_tail(board: chess.Board, uci_moves: List[str]) -> List[str]:
    replay = board.copy()
    result: List[str] = []
    for uci in uci_moves:
        move = next((m for m in replay.legal_moves if m.uci() == uci), None)
        if move is None:
            break
        result.append(replay.san(move))
        replay.push(move)
    return result


def concept_types(concepts) -> set:
    return {concept.type.value for concept in concepts}


def detect(ctx) -> set:
    """Run every detector and return the set of concept type values."""
    from concepts.registry import detect_concepts

    return concept_types(detect_concepts(ctx))


def board_context(**overrides) -> BoardContext:
    data = {
        "material_balance": 0.0,
        "total_non_pawn_material": 20,
        "player_king_square": "g1",
        "player_has_castled": True,
        "player_undeveloped_minors": 0,
        "player_legal_moves": 30,
        "opponent_legal_moves": 30,
    }
    data.update(overrides)
    return BoardContext(**data)
