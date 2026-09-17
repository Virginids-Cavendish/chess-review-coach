"""King safety, pawn structure and weak-square concepts.

These are "context" concepts: they are deterministic and factual, but on their own they
rarely prove a move was bad. The decision-error taxonomy therefore requires them to
appear together with a real expected-score loss before they can drive a conclusion.
"""

import chess
from typing import List, Set

from analysis.board import (
    doubled_pawns,
    isolated_pawns,
    king_ring,
    passed_pawns,
    pawn_attack_squares,
    pawns_in_front_of_king,
    square_name,
)
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from models.enums import ConceptType, GamePhase


class KingSafetyDetector:
    """The played move weakened the shelter around the player's own king."""

    name = "king_safety"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        results: List[DetectedConcept] = []
        from_square = ctx.played_move.from_square
        moved_piece = ctx.board_before.piece_at(from_square)

        shield_before = pawns_in_front_of_king(ctx.board_before, ctx.pov)
        if from_square in shield_before:
            results.append(
                make_concept(
                    ConceptType.KING_SAFETY_DETERIORATION,
                    0.7 if ctx.is_problem else 0.45,
                    pieces=[piece_code(ctx.board_before, from_square)],
                    squares=[square_name(from_square)],
                    evidence=[
                        "{} was part of the player's king shield on {}.".format(
                            piece_code(ctx.board_before, from_square), square_name(from_square)
                        )
                    ],
                    metadata={"cause": "pawn_shield_advanced"},
                )
            )
        elif (
            moved_piece is not None
            and moved_piece.piece_type != chess.PAWN
            and from_square in king_ring(ctx.board_before, ctx.pov)
        ):
            results.append(
                make_concept(
                    ConceptType.KING_SAFETY_DETERIORATION,
                    0.6 if ctx.is_problem else 0.45,
                    pieces=[piece_code(ctx.board_before, from_square)],
                    squares=[square_name(from_square)],
                    evidence=[
                        "{} was defending a square next to the king and left it.".format(
                            piece_code(ctx.board_before, from_square)
                        )
                    ],
                    metadata={"cause": "defender_left_king_ring"},
                )
            )

        balance = self._attack_balance(ctx)
        if balance >= 2 and ctx.is_problem:
            results.append(
                make_concept(
                    ConceptType.KING_SAFETY_DETERIORATION,
                    min(0.45 + 0.1 * balance, 0.8),
                    squares=[square_name(ctx.board_after.king(ctx.pov))]
                    if ctx.board_after.king(ctx.pov) is not None
                    else [],
                    evidence=[
                        "After the move the opponent has {} more piece(s) bearing on the "
                        "king's neighbourhood than the player has defending it.".format(balance)
                    ],
                    metadata={"attacker_surplus": str(balance)},
                )
            )
        return results

    @staticmethod
    def _attack_balance(ctx: DetectionContext) -> int:
        king_square = ctx.board_after.king(ctx.pov)
        if king_square is None:
            return 0
        ring = king_ring(ctx.board_after, ctx.pov)
        attackers: Set[int] = set()
        defenders: Set[int] = set()
        for square in ring:
            attackers |= set(ctx.board_after.attackers(ctx.opponent, square))
            defenders |= set(ctx.board_after.attackers(ctx.pov, square))
        surplus = len(attackers) - len(defenders)
        return surplus if surplus >= 2 else 0


class PawnStructureDetector:
    """Isolated / doubled / passed pawns created by the played move."""

    name = "pawn_structure"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        results: List[DetectedConcept] = []
        created_isolated = self._new(ctx, isolated_pawns, ctx.pov)
        created_doubled = self._new(ctx, doubled_pawns, ctx.pov)
        created_passed = self._new(ctx, passed_pawns, ctx.pov)
        opponent_passed = self._new(ctx, passed_pawns, ctx.opponent)

        if created_isolated:
            results.append(
                make_concept(
                    ConceptType.ISOLATED_PAWN,
                    0.8,
                    squares=[square_name(sq) for sq in created_isolated],
                    evidence=[
                        "The move creates an isolated pawn on {}.".format(
                            ", ".join(square_name(sq) for sq in created_isolated)
                        )
                    ],
                )
            )
        if created_doubled:
            results.append(
                make_concept(
                    ConceptType.DOUBLED_PAWN,
                    0.8,
                    squares=[square_name(sq) for sq in created_doubled],
                    evidence=[
                        "The move creates doubled pawns on {}.".format(
                            ", ".join(square_name(sq) for sq in created_doubled)
                        )
                    ],
                )
            )
        if created_passed:
            results.append(
                make_concept(
                    ConceptType.PASSED_PAWN,
                    0.75,
                    squares=[square_name(sq) for sq in created_passed],
                    evidence=[
                        "The move creates a passed pawn on {}.".format(
                            ", ".join(square_name(sq) for sq in created_passed)
                        )
                    ],
                    metadata={"side": "player"},
                )
            )
        if opponent_passed:
            results.append(
                make_concept(
                    ConceptType.PASSED_PAWN,
                    0.7,
                    squares=[square_name(sq) for sq in opponent_passed],
                    evidence=[
                        "The move leaves the opponent a passed pawn on {}.".format(
                            ", ".join(square_name(sq) for sq in opponent_passed)
                        )
                    ],
                    metadata={"side": "opponent"},
                )
            )

        if (created_isolated or created_doubled) and ctx.is_problem:
            results.append(
                make_concept(
                    ConceptType.PAWN_STRUCTURE_DAMAGE,
                    0.6,
                    squares=[square_name(sq) for sq in created_isolated + created_doubled],
                    evidence=[
                        "The move damages the player's pawn structure while the evaluation drops."
                    ],
                )
            )
        return results

    @staticmethod
    def _new(ctx: DetectionContext, extractor, color: bool) -> List[int]:
        before = set(extractor(ctx.board_before, color))
        after = set(extractor(ctx.board_after, color))
        return sorted(after - before)


class WeakSquareDetector:
    """Squares the player can no longer defend with a pawn and the opponent attacks."""

    name = "weak_square"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        moved_piece = ctx.board_before.piece_at(ctx.played_move.from_square)
        if moved_piece is None or moved_piece.piece_type != chess.PAWN:
            return []

        before = pawn_attack_squares(ctx.board_before, ctx.pov)
        after = pawn_attack_squares(ctx.board_after, ctx.pov)
        opponent_pawns = pawn_attack_squares(ctx.board_after, ctx.opponent)

        lost = before - after
        weak = sorted(
            square
            for square in lost
            if square in opponent_pawns and square not in after
        )
        if not weak:
            return []
        return [
            make_concept(
                ConceptType.WEAK_SQUARE,
                0.6,
                squares=[square_name(sq) for sq in weak],
                evidence=[
                    "After the pawn move the player no longer controls {} with a pawn, and "
                    "an enemy pawn does.".format(", ".join(square_name(sq) for sq in weak))
                ],
            )
        ]


DETECTORS = [KingSafetyDetector(), PawnStructureDetector(), WeakSquareDetector()]

__all__ = [
    "KingSafetyDetector",
    "PawnStructureDetector",
    "WeakSquareDetector",
    "DETECTORS",
]
