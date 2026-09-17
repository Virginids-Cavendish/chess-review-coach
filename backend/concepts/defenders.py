"""Defender concepts — the module behind the product's flagship example.

Three distinct claims, kept apart on purpose:

* ``REMOVAL_OF_DEFENDER`` — the played move *removed a defender* (it moved away, or
  captured a piece that was defending), and something that was safe became capturable.
* ``OVERLOADED_DEFENDER`` — one piece is the only defender of two attacked things.
* ``DEFLECTION`` — inside the engine line, the opponent forces a defender away.

The first is verified structurally (defender sets before/after) and, when possible,
confirmed by the engine actually exploiting the hole.
"""

import chess
from typing import List

from analysis.board import square_name
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from concepts.scan import loose_pieces
from models.enums import ConceptType


class RemovalOfDefenderDetector:
    """The played move took away the only defender of one of the player's pieces."""

    name = "removal_of_defender"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        vacated = ctx.played_move.from_square
        loose_before = loose_pieces(ctx.board_before, ctx.pov)
        loose_after = loose_pieces(ctx.board_after, ctx.pov)

        results: List[DetectedConcept] = []
        for square in sorted(chess.scan_reversed(ctx.board_before.occupied_co[ctx.pov])):
            if square == vacated:
                continue
            piece = ctx.board_before.piece_at(square)
            if piece is None or piece.piece_type == chess.KING:
                continue
            defenders_before = ctx.board_before.attackers(ctx.pov, square)
            if defenders_before != {vacated}:
                # Not a defender, or not the *only* defender.
                continue
            if square in loose_before:
                # It could already be taken before the move; this move did not cause it.
                continue
            info = loose_after.get(square)
            if info is None:
                # The piece that moved still defends the square from its new home, or
                # nothing can be won there yet.
                continue

            confirmed = self._confirmed_by_line(ctx, square)
            evidence = [
                "{} was the only defender of {}.".format(
                    piece_code(ctx.board_before, vacated), piece_code(ctx.board_after, square)
                ),
                "After {} that defender no longer covers {}.".format(ctx.played_san, square_name(square)),
                "{} can now be captured for a gain of {} pawn(s).".format(
                    piece_code(ctx.board_after, square), info.best_see
                ),
            ]
            if confirmed:
                evidence.append(
                    "The engine's continuation after the played move takes on {} immediately.".format(
                        square_name(square)
                    )
                )
            results.append(
                make_concept(
                    ConceptType.REMOVAL_OF_DEFENDER,
                    0.95 if confirmed else 0.65,
                    pieces=[
                        piece_code(ctx.board_before, vacated),
                        piece_code(ctx.board_after, square),
                    ],
                    squares=[square_name(vacated), square_name(square)],
                    evidence=evidence,
                    metadata={
                        "vacated_square": square_name(vacated),
                        "undefended_piece": piece_code(ctx.board_after, square),
                        "see_gain": str(info.best_see),
                        "confirmed_by_engine_line": str(confirmed).lower(),
                    },
                )
            )
        return results

    @staticmethod
    def _confirmed_by_line(ctx: DetectionContext, square: int) -> bool:
        for entry in ctx.played_line[:2]:
            if entry.mover != ctx.opponent:
                continue
            if entry.is_capture and entry.move.to_square == square:
                return True
        return False


class OverloadedDefenderDetector:
    """One piece is the only defender of two or more attacked friendly pieces."""

    name = "overloaded_defender"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if not ctx.is_problem:
            # Structurally interesting, but as *evidence for this move* it only matters
            # when the move actually went wrong.
            return []

        results: List[DetectedConcept] = []
        pieces = sorted(chess.scan_reversed(ctx.board_before.occupied_co[ctx.pov]))
        for defender_square in pieces:
            defender = ctx.board_before.piece_at(defender_square)
            if defender is None or defender.piece_type == chess.KING:
                continue
            defended: List[int] = []
            for square in pieces:
                if square == defender_square:
                    continue
                target = ctx.board_before.piece_at(square)
                if target is None:
                    continue
                if ctx.board_before.attackers(ctx.pov, square) != {defender_square}:
                    continue
                if not ctx.board_before.attackers(ctx.opponent, square):
                    continue
                defended.append(square)
            if len(defended) < 2:
                continue
            results.append(
                make_concept(
                    ConceptType.OVERLOADED_DEFENDER,
                    0.7,
                    pieces=[piece_code(ctx.board_before, defender_square)],
                    squares=[square_name(defender_square)]
                    + [square_name(sq) for sq in defended],
                    evidence=[
                        "{} is the only defender of {}, and all of them are attacked.".format(
                            piece_code(ctx.board_before, defender_square),
                            " and ".join(piece_code(ctx.board_before, sq) for sq in defended),
                        )
                    ],
                    metadata={"defended_count": str(len(defended))},
                )
            )
            break  # one overloaded defender per move is enough context
        return results


class DeflectionDetector:
    """The engine line shows the opponent forcing a defender away from its duty."""

    name = "deflection"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        line = ctx.played_line
        if len(line) < 3:
            return []
        forcing, reply, follow_up = line[0], line[1], line[2]
        if forcing.mover != ctx.opponent or reply.mover != ctx.pov or follow_up.mover != ctx.opponent:
            return []
        if not (forcing.is_capture or forcing.is_check):
            return []
        if not follow_up.is_capture:
            return []
        if ctx.board_after.piece_at(reply.move.from_square) is None:
            return []
        reply_piece = reply.board_before.piece_at(reply.move.from_square)
        if reply_piece is None or reply_piece.piece_type == chess.KING:
            return []

        target_square = follow_up.move.to_square
        target_piece = follow_up.board_before.piece_at(target_square)
        if target_piece is None or target_piece.color != ctx.pov:
            return []
        defenders = follow_up.board_before.attackers(ctx.pov, target_square)
        if defenders != {reply.move.from_square}:
            return []

        return [
            make_concept(
                ConceptType.DEFLECTION,
                0.8,
                pieces=[piece_code(ctx.board_after, reply.move.from_square)],
                squares=[square_name(reply.move.from_square), square_name(target_square)],
                evidence=[
                    "The engine line continues {}, forcing {} to answer.".format(
                        forcing.san, reply.san
                    ),
                    "{} was the only defender of {}, and {} then takes it.".format(
                        piece_code(follow_up.board_before, reply.move.from_square),
                        piece_code(follow_up.board_before, target_square),
                        follow_up.san,
                    ),
                ],
                metadata={
                    "forcing_move": forcing.san,
                    "reply": reply.san,
                    "follow_up": follow_up.san,
                },
            )
        ]


DETECTORS = [RemovalOfDefenderDetector(), OverloadedDefenderDetector(), DeflectionDetector()]

__all__ = ["RemovalOfDefenderDetector", "OverloadedDefenderDetector", "DeflectionDetector", "DETECTORS"]
