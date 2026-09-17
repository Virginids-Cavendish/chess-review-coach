"""Opening / middlegame / endgame classification.

Deliberately a heuristic, and deliberately isolated behind :class:`PhaseClassifier`
so it can be replaced (by an ECO book, a piece-count model, whatever) without
touching the pipeline. Phase is used for **analytics only** — it never decides
severity — so an occasional disagreement here cannot corrupt a review.
"""

import chess

from analysis.board import total_non_pawn_material, undeveloped_minors
from analysis.thresholds import THRESHOLDS, PhaseThresholds
from models.enums import GamePhase


class PhaseClassifier:
    def __init__(self, thresholds: PhaseThresholds = None) -> None:
        self._thresholds = thresholds or THRESHOLDS.phase

    def classify(self, board: chess.Board, fullmove_number: int) -> GamePhase:
        """Classify the position on the board.

        Rules, in order:
        1. Little non-pawn material left for either side -> endgame. This is checked
           first so a long manoeuvring ending is never called a middlegame.
        2. Still within the opening move range and at least a few minor pieces are
           sitting on their home squares -> opening.
        3. Otherwise middlegame.
        """
        if total_non_pawn_material(board) <= self._thresholds.endgame_material_threshold:
            return GamePhase.ENDGAME

        undeveloped = len(undeveloped_minors(board, chess.WHITE)) + len(
            undeveloped_minors(board, chess.BLACK)
        )
        if (
            fullmove_number <= self._thresholds.opening_max_fullmove
            and undeveloped >= self._thresholds.undeveloped_minor_threshold
        ):
            return GamePhase.OPENING
        return GamePhase.MIDDLEGAME


DEFAULT_PHASE_CLASSIFIER = PhaseClassifier()


def classify_phase(board: chess.Board, fullmove_number: int) -> GamePhase:
    return DEFAULT_PHASE_CLASSIFIER.classify(board, fullmove_number)
