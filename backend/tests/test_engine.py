"""Stockfish connection, UCI parsing and score normalization.

Skipped automatically when no engine binary is present, so the rest of the suite still
runs on a machine without Stockfish.
"""

import chess
import pytest

from engine.cache import InMemoryCache, NullCache, cache_key
from engine.errors import EngineNotFoundError
from engine.scores import MATE_DISPLAY_PAWNS
from engine.stockfish import EngineConfig, StockfishEngine
from models.enums import Color
from tests.conftest import requires_engine

SCHOLARS_MATE_BEFORE = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
MATE_POSITION = "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"


@requires_engine
def test_engine_reports_its_identity(engine: StockfishEngine):
    assert "Stockfish" in engine.name


@requires_engine
def test_missing_binary_raises_a_typed_error(tmp_path):
    missing = StockfishEngine(EngineConfig(path=tmp_path / "does-not-exist"))
    with pytest.raises(EngineNotFoundError):
        missing.start()


@requires_engine
def test_analysis_returns_wdl_and_principal_variation(engine: StockfishEngine):
    board = chess.Board()
    result = engine.analyse(board, pov_color=Color.WHITE, depth=8)
    assert result.depth >= 8
    assert result.candidates
    best = result.best
    assert best is not None
    assert best.uci
    assert best.pv_uci and best.pv_uci[0] == best.uci
    assert len(best.pv_san) == len(best.pv_uci)
    # WDL must be present (Stockfish advertises UCI_ShowWDL) and sum to one.
    assert best.wdl.win + best.wdl.draw + best.wdl.loss == pytest.approx(1.0, abs=0.01)
    assert 0.0 <= best.expected_score <= 1.0
    assert result.multipv == 1


@requires_engine
def test_scores_are_reported_from_the_requested_point_of_view(engine: StockfishEngine):
    # White is a queen up: positive for White, negative for Black.
    board = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
    white_view = engine.analyse(board, pov_color=Color.WHITE, depth=10)
    black_view = engine.analyse(board, pov_color=Color.BLACK, depth=10)
    assert white_view.best.expected_score > 0.8
    assert black_view.best.expected_score < 0.2
    assert white_view.best.wdl.win == pytest.approx(black_view.best.wdl.loss, abs=0.02)


@requires_engine
def test_mate_is_reported_as_a_mate_score_not_a_centipawn_value(engine: StockfishEngine):
    board = chess.Board(SCHOLARS_MATE_BEFORE)
    result = engine.analyse(board, pov_color=Color.WHITE, depth=10)
    best = result.best
    assert best is not None
    assert best.mate is not None and best.mate > 0
    assert best.cp is None
    assert best.wdl.win == pytest.approx(1.0, abs=0.001)


@requires_engine
def test_mate_against_the_player_is_negative(engine: StockfishEngine):
    board = chess.Board(SCHOLARS_MATE_BEFORE)
    result = engine.analyse(board, pov_color=Color.BLACK, depth=10)
    # Black is the side to move in this FEN? No: White is to move, so Black's view of
    # the same position is simply the negation.
    assert result.best.mate is not None and result.best.mate < 0


@requires_engine
def test_multipv_returns_several_ordered_candidates(engine: StockfishEngine):
    board = chess.Board()
    result = engine.analyse(board, pov_color=Color.WHITE, depth=8, multipv=3)
    assert len(result.candidates) >= 2
    scores = [candidate.expected_score for candidate in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert len({candidate.uci for candidate in result.candidates}) == len(result.candidates)


@requires_engine
def test_terminal_position_returns_no_candidates_instead_of_failing(engine: StockfishEngine):
    board = chess.Board("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1")  # mate: the queen on g7 covers h8
    assert board.is_checkmate()
    result = engine.analyse(board, pov_color=Color.BLACK, depth=8)
    assert result.candidates == []
    assert result.complete is True
    assert any("terminal" in warning for warning in result.warnings)


@requires_engine
def test_engine_survives_a_position_after_a_timeout_recovery(engine: StockfishEngine):
    # A cheap smoke test that restart() leaves the object usable.
    engine.restart()
    result = engine.analyse(chess.Board(), pov_color=Color.WHITE, depth=6)
    assert result.best is not None


def test_cache_key_includes_everything_that_changes_the_answer():
    base = dict(
        fen=chess.STARTING_FEN,
        engine_name="Stockfish 19",
        depth=12,
        nodes=0,
        multipv=1,
        threads=4,
        hash_mb=64,
        pov="white",
    )
    reference = cache_key(**base)

    assert cache_key(**dict(base, pov="black")) != reference
    assert cache_key(**dict(base, depth=13)) != reference
    assert cache_key(**dict(base, multipv=3)) != reference
    assert cache_key(**dict(base, fen="8/8/8/8/8/8/8/K6k w - - 0 1")) != reference
    assert cache_key(**dict(base, engine_name="Stockfish 20")) != reference
    assert cache_key(**base) == reference


def test_in_memory_cache_records_hits_and_misses():
    from models.evidence import PositionEval

    cache = InMemoryCache()
    assert cache.get("missing") is None
    value = PositionEval(
        fen=chess.STARTING_FEN,
        pov_color=Color.WHITE,
        depth=12,
        multipv=1,
        engine_name="Stockfish 19",
    )
    cache.put("key", value)
    assert cache.get("key") is not None
    assert cache.hits == 1 and cache.misses == 1
    assert NullCache().get("key") is None


def test_mate_display_sentinel_is_documented_constant():
    assert MATE_DISPLAY_PAWNS == 10.0
