"""Assembly of the verified evidence object for one played move.

Takes nothing but engine output and the two boards, and produces the
:class:`EngineEvidence` that every downstream layer (detectors, taxonomy, LLM, UI)
reads. There is no chess judgment in this module: it normalizes perspective, copies
PVs across, and clamps the expected-score loss at zero.
"""

import logging
from typing import List, Optional

import chess

from analysis.thresholds import AnalysisThresholds, THRESHOLDS
from engine.scores import (
    MATE_DISPLAY_PAWNS,
    centipawn_loss,
    display_pawns,
    expected_score_loss,
)
from models.enums import Color, GamePhase, Severity
from models.evidence import (
    AnalysisEvidence,
    BoardContext,
    CandidateMove,
    DecisionError,
    DetectedConcept,
    EngineEvidence,
    PlayedMove,
    PositionContext,
    PositionEval,
    WdlDistribution,
)

logger = logging.getLogger(__name__)

#: Number of plies of the engine's alternative lines kept for display.
ALTERNATIVE_PV_PLIES = 8


def candidates_in_pov(
    position_eval: Optional[PositionEval], pov: Color
) -> List[CandidateMove]:
    """Engine candidates re-expressed from ``pov``'s point of view.

    Positions are searched once, always with the analyzed player as the point of view;
    this is the single place where the perspective is flipped for the other side.
    """
    if position_eval is None:
        return []
    if position_eval.pov_color == pov:
        return list(position_eval.candidates)
    return [candidate.reversed() for candidate in position_eval.candidates]


def _terminal_wdl(board: chess.Board, pov: Color) -> Optional[WdlDistribution]:
    """WDL for a finished position (no legal moves, so no engine PV exists)."""
    if not board.is_game_over(claim_draw=False):
        return None
    if board.is_checkmate():
        loser = Color.WHITE if board.turn == chess.WHITE else Color.BLACK
        return (
            WdlDistribution(win=1.0, draw=0.0, loss=0.0)
            if loser != pov
            else WdlDistribution(win=0.0, draw=0.0, loss=1.0)
        )
    return WdlDistribution(win=0.0, draw=1.0, loss=0.0)


def build_engine_evidence(
    *,
    board_before: chess.Board,
    board_after: chess.Board,
    before_eval: Optional[PositionEval],
    after_eval: Optional[PositionEval],
    played_move: chess.Move,
    played_san: str,
    pov: Color,
    deep_eval: Optional[PositionEval] = None,
    thresholds: AnalysisThresholds = THRESHOLDS,
) -> Optional[EngineEvidence]:
    """Build the evidence for one played move.

    ``pov`` is the side that played the move. ``before_eval`` is the search of the
    position they were facing, ``after_eval`` the search of the resulting position, and
    ``deep_eval`` (pass 2 only) a deeper MultiPV search of the position they faced.

    Returns None when the required engine output is missing, so callers can mark the
    move as not analyzed instead of inventing numbers.
    """
    before_candidates = candidates_in_pov(before_eval, pov)
    if not before_candidates:
        return None

    before_best = before_candidates[0]
    after_candidates = candidates_in_pov(after_eval, pov)
    after_terminal = _terminal_wdl(board_after, pov)

    if after_candidates:
        after_best = after_candidates[0]
        after_wdl = after_best.wdl
        evaluation_after = display_pawns(after_best.cp, after_best.mate)
        mate_after = after_best.mate
        depth_after = after_eval.depth if after_eval else 0
        nodes_after = after_eval.nodes if after_eval else None
        multipv_after = after_eval.multipv if after_eval else 1
        played_line_uci = [played_move.uci()] + list(after_best.pv_uci)
        played_line_san = [played_san] + list(after_best.pv_san)
    elif after_terminal is not None:
        # Checkmate or stalemate: the line ends with the move that was played.
        after_wdl = after_terminal
        mate_after = (
            1
            if after_wdl.win == 1.0
            else (-1 if after_wdl.loss == 1.0 else None)
        )
        evaluation_after = (
            MATE_DISPLAY_PAWNS
            if after_wdl.win == 1.0
            else (-MATE_DISPLAY_PAWNS if after_wdl.loss == 1.0 else 0.0)
        )
        depth_after = 0
        nodes_after = None
        multipv_after = 0
        played_line_uci = [played_move.uci()]
        played_line_san = [played_san]
    else:
        return None

    expected_before = before_best.expected_score
    expected_after = after_wdl.expected_score()
    loss = expected_score_loss(before_best.wdl, after_wdl)

    deep_candidates = candidates_in_pov(deep_eval, pov) if deep_eval else []
    is_engine_best = played_move.uci() == before_best.uci
    best_move_unique = _is_unique(deep_candidates, thresholds) if deep_candidates else False
    wdl_estimated = _wdl_was_estimated(before_eval) or _wdl_was_estimated(after_eval)

    return EngineEvidence(
        pov_color=pov,
        evaluation_before=display_pawns(before_best.cp, before_best.mate),
        evaluation_after=evaluation_after,
        mate_before=before_best.mate,
        mate_after=mate_after,
        wdl_before=before_best.wdl,
        wdl_after=after_wdl,
        expected_score_before=round(expected_before, 6),
        expected_score_after=round(expected_after, 6),
        expected_score_loss=round(loss, 6),
        centipawn_loss=centipawn_loss(before_best.cp, after_best.cp if after_candidates else None),
        best_move_uci=before_best.uci,
        best_move_san=before_best.san,
        best_line_uci=list(before_best.pv_uci),
        best_line_san=list(before_best.pv_san),
        played_line_uci=played_line_uci,
        played_line_san=played_line_san,
        depth_before=deep_eval.depth if deep_eval else (before_eval.depth if before_eval else 0),
        depth_after=depth_after,
        nodes_before=deep_eval.nodes if deep_eval else (before_eval.nodes if before_eval else None),
        nodes_after=nodes_after,
        multipv_before=deep_eval.multipv if deep_eval else (before_eval.multipv if before_eval else 1),
        multipv_after=multipv_after,
        alternatives=_alternatives(deep_candidates),
        is_engine_best=is_engine_best,
        best_move_unique=best_move_unique,
        wdl_estimated=wdl_estimated,
    )


def _alternatives(deep_candidates: List[CandidateMove]) -> List[CandidateMove]:
    """Pass-2 MultiPV alternatives, excluding the top move itself."""
    if len(deep_candidates) <= 1:
        return []
    return [
        candidate.model_copy(
            update={
                "pv_uci": candidate.pv_uci[:ALTERNATIVE_PV_PLIES],
                "pv_san": candidate.pv_san[:ALTERNATIVE_PV_PLIES],
            }
        )
        for candidate in deep_candidates[1:4]
    ]


def _wdl_was_estimated(position_eval: Optional[PositionEval]) -> bool:
    """True when the engine reported no WDL and the adapter fell back to centipawns."""
    if position_eval is None:
        return False
    return any("WDL" in warning for warning in position_eval.warnings)


def _is_unique(deep_candidates: List[CandidateMove], thresholds: AnalysisThresholds) -> bool:
    """True when the top move is clearly better than the runner-up."""
    if len(deep_candidates) < 2:
        return False
    margin = deep_candidates[0].expected_score - deep_candidates[1].expected_score
    return margin >= thresholds.detection.uniqueness_margin


def build_full_evidence(
    *,
    position_fen: str,
    ply: int,
    move_number: int,
    player_color: Color,
    phase: GamePhase,
    played_move_uci: str,
    played_san: str,
    engine: EngineEvidence,
    concepts: List[DetectedConcept],
    errors: List[DecisionError],
    board_context: BoardContext,
    move_history_san: List[str],
    severity: Severity,
) -> AnalysisEvidence:
    """Wrap verified engine data and detected concepts into the review evidence object.

    This is the object the LLM is allowed to read: it contains no request to evaluate a
    position, only facts to explain.
    """
    return AnalysisEvidence(
        position=PositionContext(
            fen=position_fen,
            ply=ply,
            move_number=move_number,
            player_color=player_color,
            phase=phase,
        ),
        played_move=PlayedMove(uci=played_move_uci, san=played_san),
        engine=engine,
        concepts=list(concepts),
        decision_errors=list(errors),
        severity=severity,
        board_context=board_context,
        move_history_san=list(move_history_san),
    )
