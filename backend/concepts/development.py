"""Opening-development concepts: pieces still at home, queen wandering."""

import chess
from typing import List

from analysis.board import MINOR_HOME_SQUARES, square_name, undeveloped_minors
from analysis.thresholds import THRESHOLDS
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from models.enums import ConceptType, GamePhase


class UndevelopedPiecesDetector:
    """In the opening, the player still has minor pieces on their home squares."""

    name = "undeveloped_pieces"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if ctx.phase is not GamePhase.OPENING:
            return []
        undeveloped = undeveloped_minors(ctx.board_before, ctx.pov)
        if len(undeveloped) < 2:
            return []

        moved_piece = ctx.board_before.piece_at(ctx.played_move.from_square)
        developed_something = (
            ctx.played_move.from_square in MINOR_HOME_SQUARES[ctx.pov]
            and moved_piece is not None
            and moved_piece.piece_type in (chess.KNIGHT, chess.BISHOP)
        )
        if developed_something:
            return []

        return [
            make_concept(
                ConceptType.UNDEVELOPED_PIECES,
                0.5,
                pieces=[piece_code(ctx.board_before, sq) for sq in undeveloped],
                squares=[square_name(sq) for sq in undeveloped],
                evidence=[
                    "This is still the opening and {} minor piece(s) have not moved.".format(
                        len(undeveloped)
                    ),
                    "The move {} does not develop a piece.".format(ctx.played_san),
                ],
                metadata={"undeveloped_count": str(len(undeveloped))},
            )
        ]


class QueenMovedRepeatedlyDetector:
    """The queen has already moved in the opening, and moves again."""

    name = "queen_moved_repeatedly"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if ctx.move_number > THRESHOLDS.phase.opening_max_fullmove:
            return []
        if not ctx.played_san.startswith("Q"):
            return []

        earlier = [
            san
            for color, san in ctx.move_history
            if color is ctx.player_color and san.startswith("Q")
        ]
        if not earlier:
            return []
        return [
            make_concept(
                ConceptType.QUEEN_MOVED_REPEATEDLY,
                0.7,
                squares=[square_name(ctx.played_move.to_square)],
                evidence=[
                    "The player's queen had already moved in this opening ({}).".format(
                        ", ".join(earlier)
                    )
                ],
                metadata={"previous_queen_moves": ", ".join(earlier)},
            )
        ]


DETECTORS = [UndevelopedPiecesDetector(), QueenMovedRepeatedlyDetector()]

__all__ = ["UndevelopedPiecesDetector", "QueenMovedRepeatedlyDetector", "DETECTORS"]
