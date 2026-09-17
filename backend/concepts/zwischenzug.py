"""Intermediate move (zwischenzug) detection.

Deliberately narrow. The reliable signal is: the player made a capture that looked like
the end of an exchange, and the engine's continuation shows the opponent ignoring the
recapture to play something stronger first (a check, or a capture elsewhere).

Detectors that "look for zwischenzugs" in general end up inventing them, so this one
only reports what the engine line actually does.
"""

from typing import List

from analysis.board import square_name
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from models.enums import ConceptType


class IntermediateMoveDetector:
    name = "intermediate_move"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        # ``played_line`` begins with the opponent's reply (the played move itself is not
        # part of it), so a single entry is enough to reason about the zwischenzug.
        if not ctx.played_line:
            return []
        if not ctx.board_before.is_capture(ctx.played_move):
            return []

        reply = ctx.played_line[0]
        if reply.mover != ctx.opponent:
            return []

        capture_square = ctx.played_move.to_square
        if reply.move.to_square == capture_square:
            # The opponent simply recaptured; that is not an in-between move.
            return []

        recapture_available = any(
            move.to_square == capture_square for move in ctx.board_after.legal_moves if ctx.board_after.is_capture(move)
        )
        if not recapture_available:
            return []
        if not (reply.is_capture or reply.is_check):
            return []

        return [
            make_concept(
                ConceptType.INTERMEDIATE_MOVE,
                0.6,
                pieces=[piece_code(ctx.board_after, reply.move.from_square)],
                squares=[square_name(reply.move.to_square)],
                evidence=[
                    "After the player's capture {} the opponent did not recapture on {}.".format(
                        ctx.played_san, square_name(capture_square)
                    ),
                    "The engine plays {} first — an in-between move ({}) before dealing with "
                    "the recapture.".format(
                        reply.san, "check" if reply.is_check else "capture"
                    ),
                ],
                metadata={"intermediate_move": reply.san},
            )
        ]


DETECTORS = [IntermediateMoveDetector()]

__all__ = ["IntermediateMoveDetector", "DETECTORS"]
