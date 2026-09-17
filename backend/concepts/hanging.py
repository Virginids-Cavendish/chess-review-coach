"""Hanging / undefended / attacked piece detection.

The distinction that matters for coaching:

* ``HANGING_PIECE`` — the opponent can win material on this piece *by force*
  (verified with static exchange evaluation, and confirmed by the engine line when the
  engine actually takes it),
* ``UNDEFENDED_PIECE`` — no friendly piece defends it at all,
* ``ATTACKED_PIECE`` — merely attacked; weak evidence, kept for context.

Only pieces that became loose *because of the played move* are reported, so a
position where something was already hanging does not spam every later move.
"""

from typing import Dict, List

from analysis.board import square_name
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from concepts.scan import LoosePiece, attacked_piece_squares, loose_pieces
from models.enums import ConceptType


class HangingPieceDetector:
    name = "hanging_piece"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        before = loose_pieces(ctx.board_before, ctx.pov)
        after = loose_pieces(ctx.board_after, ctx.pov)
        moved_from = ctx.played_move.from_square
        moved_to = ctx.played_move.to_square
        newly_loose = [
            square
            for square in sorted(after)
            if square not in before
            # A piece that was already loose on its old square and is still loose after
            # moving did not become hanging *because of this move*; blaming the move for
            # a pre-existing problem would be misleading.
            and not (square == moved_to and moved_from in before)
        ]
        if not newly_loose:
            return []

        results: List[DetectedConcept] = []
        for square in newly_loose:
            info = after[square]
            captured_in_line = self._captured_in_line(ctx, square)
            confidence = 0.95 if captured_in_line else 0.7
            evidence = [
                "{} can be captured: static exchange evaluation gains {} pawn(s) "
                "for the opponent.".format(piece_code(ctx.board_after, square), info.best_see)
            ]
            if not info.defended:
                evidence.append(
                    "{} has no defender at all.".format(piece_code(ctx.board_after, square))
                )
            if captured_in_line:
                evidence.append(
                    "The engine's continuation after the played move actually takes on {}.".format(
                        square_name(square)
                    )
                )
            results.append(
                make_concept(
                    ConceptType.HANGING_PIECE,
                    confidence,
                    pieces=[piece_code(ctx.board_after, square)],
                    squares=[square_name(square)],
                    evidence=evidence,
                    metadata={
                        "material_at_stake": str(info.value),
                        "see_gain": str(info.best_see),
                        "captured_in_engine_line": str(captured_in_line).lower(),
                    },
                )
            )

            if not info.defended:
                results.append(
                    make_concept(
                        ConceptType.UNDEFENDED_PIECE,
                        min(0.9, confidence),
                        pieces=[piece_code(ctx.board_after, square)],
                        squares=[square_name(square)],
                        evidence=[
                            "{} is attacked with no friendly piece defending it.".format(
                                piece_code(ctx.board_after, square)
                            )
                        ],
                    )
                )
        return results

    @staticmethod
    def _captured_in_line(ctx: DetectionContext, square: int) -> bool:
        """Did the opponent's immediate reply (per the engine) take on this square?"""
        for entry in ctx.played_line[:2]:
            if entry.mover != ctx.opponent:
                continue
            if entry.is_capture and entry.move.to_square == square:
                return True
        return False


class AttackedPieceDetector:
    """Context-only: which of the player's pieces the opponent is attacking now."""

    name = "attacked_piece"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        before = attacked_piece_squares(ctx.board_before, ctx.pov)
        after = attacked_piece_squares(ctx.board_after, ctx.pov)
        newly_attacked = sorted(after - before)
        if not newly_attacked:
            return []
        loose_after = loose_pieces(ctx.board_after, ctx.pov)
        material: Dict[int, LoosePiece] = {
            square: info for square, info in loose_after.items() if square in set(newly_attacked)
        }
        # Squares where something can actually be won are already reported by
        # HangingPieceDetector; keeping them here would double-count.
        remaining = [square for square in newly_attacked if square not in material]
        if not remaining:
            return []
        return [
            make_concept(
                ConceptType.ATTACKED_PIECE,
                0.5,
                pieces=[piece_code(ctx.board_after, square) for square in remaining],
                squares=[square_name(square) for square in remaining],
                evidence=[
                    "After the played move the opponent attacks {} "
                    "(no immediate material gain by static exchange evaluation).".format(
                        ", ".join(piece_code(ctx.board_after, square) for square in remaining)
                    )
                ],
            )
        ]


DETECTORS = [HangingPieceDetector(), AttackedPieceDetector()]


__all__ = ["HangingPieceDetector", "AttackedPieceDetector", "DETECTORS"]
