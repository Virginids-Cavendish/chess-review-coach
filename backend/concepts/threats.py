"""Threats against the player's own position: back rank and trapped pieces."""

import chess
from typing import List

from analysis.board import PIECE_VALUES, piece_value, pseudo_safe_destinations, square_name
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from concepts.scan import loose_pieces
from models.enums import ConceptType


class BackRankWeaknessDetector:
    """The player's king can be mated (or heavily hit) along its own back rank."""

    name = "back_rank_weakness"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        back_rank = 0 if ctx.pov == chess.WHITE else 7
        king_square = ctx.board_after.king(ctx.pov)
        if king_square is None:
            return []

        mating = next(
            (
                entry
                for entry in ctx.played_line[:6]
                if entry.mover == ctx.opponent
                and entry.is_mate
                and chess.square_rank(entry.move.to_square) == back_rank
            ),
            None,
        )
        if mating is not None:
            return [
                make_concept(
                    ConceptType.BACK_RANK_WEAKNESS,
                    0.95,
                    squares=[square_name(mating.move.to_square), square_name(king_square)],
                    evidence=[
                        "The engine continuation ends with {} on the back rank: mate.".format(
                            mating.san
                        )
                    ],
                    metadata={"mate_move": mating.san},
                )
            ]

        if chess.square_rank(king_square) != back_rank or not ctx.is_problem:
            return []
        if self._has_escape(ctx, king_square):
            return []
        attacker = self._heavy_piece_eyeing_back_rank(ctx, back_rank)
        if attacker is None:
            return []
        return [
            make_concept(
                ConceptType.BACK_RANK_WEAKNESS,
                0.55,
                pieces=[piece_code(ctx.board_after, attacker)],
                squares=[square_name(king_square)],
                evidence=[
                    "The king on {} has no safe neighbouring square and {} lines up against "
                    "the back rank.".format(square_name(king_square), piece_code(ctx.board_after, attacker)),
                    "No engine mate is forced here; this is a structural weakness, not a tactic.",
                ],
                metadata={"structural": "true"},
            )
        ]

    @staticmethod
    def _has_escape(ctx: DetectionContext, king_square: int) -> bool:
        for target in chess.SquareSet(chess.BB_KING_ATTACKS[king_square]):
            occupant = ctx.board_after.piece_at(target)
            if occupant is not None and occupant.color == ctx.pov:
                continue
            if not ctx.board_after.attackers(ctx.opponent, target):
                return True
        return False

    @staticmethod
    def _heavy_piece_eyeing_back_rank(ctx: DetectionContext, back_rank: int):
        for square in chess.scan_reversed(ctx.board_after.occupied_co[ctx.opponent]):
            piece = ctx.board_after.piece_at(square)
            if piece is None or piece.piece_type not in (chess.ROOK, chess.QUEEN):
                continue
            if chess.square_rank(square) == back_rank:
                return square
            if any(chess.square_rank(target) == back_rank for target in ctx.board_after.attacks(square)):
                return square
        return None


class TrappedPieceDetector:
    """An attacked player piece has almost nowhere safe to go.

    Mobility here is the attack-map approximation from ``pseudo_safe_destinations``,
    so pins are not taken into account; the concept is reported with moderate
    confidence and only when the engine line actually takes the piece.
    """

    name = "trapped_piece"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        loose = loose_pieces(ctx.board_after, ctx.pov)
        if not loose:
            return []

        results: List[DetectedConcept] = []
        for square, info in sorted(loose.items()):
            piece = ctx.board_after.piece_at(square)
            if piece is None or piece_value(piece) < ctx.thresholds.minor_piece_value:
                continue
            safe = pseudo_safe_destinations(ctx.board_after, square)
            if len(safe) > ctx.thresholds.trapped_piece_max_safe_squares:
                continue
            captured = any(
                entry.mover == ctx.opponent and entry.is_capture and entry.move.to_square == square
                for entry in ctx.played_line[:4]
            )
            results.append(
                make_concept(
                    ConceptType.TRAPPED_PIECE,
                    0.75 if captured else 0.5,
                    pieces=[piece_code(ctx.board_after, square)],
                    squares=[square_name(square)] + [square_name(sq) for sq in safe],
                    evidence=[
                        "{} is attacked and has only {} escape square(s) that do not lose "
                        "material.".format(piece_code(ctx.board_after, square), len(safe))
                    ]
                    + (
                        ["The engine continuation captures it within four plies."]
                        if captured
                        else []
                    ),
                    metadata={"safe_squares": str(len(safe)), "value": str(PIECE_VALUES.get(piece.piece_type, 0))},
                )
            )
        return results


DETECTORS = [BackRankWeaknessDetector(), TrappedPieceDetector()]

__all__ = ["BackRankWeaknessDetector", "TrappedPieceDetector", "DETECTORS"]
