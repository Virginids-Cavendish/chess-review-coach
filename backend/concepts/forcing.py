"""Forcing-move concepts: checks and mates that were available or that appeared.

These detectors answer "did the move ignore a forcing resource?" — which is the single
most common decision error in the target rating band. Every claim is anchored either
to the engine's own first choice or to a mate score the engine reported.
"""

import chess
from typing import List

from analysis.board import square_name, static_exchange_evaluation
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from models.enums import ConceptType


class MissedCheckDetector:
    """The engine's first choice was a check and the player played a quiet move."""

    name = "missed_check"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        best = ctx.best_move
        if best is None or ctx.evidence.is_engine_best:
            return []
        if not ctx.board_before.gives_check(best):
            return []
        if ctx.board_before.gives_check(ctx.played_move):
            return []

        san = ctx.evidence.best_move_san or ctx.san(ctx.board_before, best)
        evidence = [
            "The engine's first choice {} gives check; the played move {} does not.".format(
                san, ctx.played_san
            )
        ]
        confidence = 0.9 if ctx.is_problem else 0.5
        if not ctx.is_problem:
            evidence.append(
                "The engine rated both moves closely, so this is context rather than a mistake."
            )
        return [
            make_concept(
                ConceptType.MISSED_CHECK,
                confidence,
                pieces=[piece_code(ctx.board_before, best.from_square)],
                squares=[square_name(best.to_square)],
                evidence=evidence,
                metadata={"best_move": san},
            )
        ]


class MissedForcingMoveDetector:
    """A forced mate or a winning capture was available and was not played."""

    name = "missed_forcing_move"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if ctx.evidence.is_engine_best:
            return []

        mate_before = ctx.evidence.mate_before
        if mate_before is not None and mate_before > 0:
            return [
                make_concept(
                    ConceptType.MISSED_FORCING_MOVE,
                    0.9,
                    evidence=[
                        "Before the move the engine saw a forced mate in {} for the player.".format(
                            mate_before
                        ),
                        "The engine's first choice was {}.".format(ctx.evidence.best_move_san),
                    ],
                    metadata={"reason": "missed_mate", "mate_in": str(mate_before)},
                )
            ]

        best = ctx.best_move
        if best is None or not ctx.is_problem:
            return []
        if not ctx.board_before.is_capture(best) or ctx.board_before.is_capture(ctx.played_move):
            return []
        see = static_exchange_evaluation(ctx.board_before, best)
        if see < ctx.thresholds.significant_material_loss:
            return []
        san = ctx.evidence.best_move_san or ctx.san(ctx.board_before, best)
        return [
            make_concept(
                ConceptType.MISSED_FORCING_MOVE,
                0.75,
                pieces=[piece_code(ctx.board_before, best.from_square)],
                squares=[square_name(best.to_square)],
                evidence=[
                    "The engine's first choice {} wins {} pawn(s) by static exchange "
                    "evaluation; the played move {} was quiet.".format(san, see, ctx.played_san)
                ],
                metadata={"reason": "winning_capture", "best_move": san},
            )
        ]


class MatingThreatDetector:
    """The opponent has a forced mate (or the engine line ends in mate against the player)."""

    name = "mating_threat"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        mate_after = ctx.evidence.mate_after
        if mate_after is not None and mate_after < 0:
            mate_in = abs(mate_after)
            if ctx.evidence.mate_before is not None and ctx.evidence.mate_before < 0:
                # Already lost before the move; still a true statement, but it is not
                # this move's fault, so it is reported with lower confidence and a
                # clear note.
                confidence = 0.6
                note = "The forced mate already existed before the played move."
            else:
                confidence = 0.95
                note = "The played move allowed a forced mate in {}.".format(mate_in)
            evidence = [note, "Engine score after the move: mate in {} against the player.".format(mate_in)]
        else:
            mating = next(
                (entry for entry in ctx.played_line[:6] if entry.mover == ctx.opponent and entry.is_mate),
                None,
            )
            if mating is None:
                return []
            confidence = 0.9
            evidence = [
                "The engine continuation ends in mate with {} on {}.".format(
                    mating.san, square_name(mating.move.to_square)
                )
            ]
            mate_in = mating.index + 1

        return [
            make_concept(
                ConceptType.MATING_THREAT,
                confidence,
                squares=[square_name(ctx.board_after.king(ctx.pov))]
                if ctx.board_after.king(ctx.pov) is not None
                else [],
                evidence=evidence,
                metadata={"mate_in": str(mate_in), "against": "player"},
            )
        ]


DETECTORS = [MissedCheckDetector(), MissedForcingMoveDetector(), MatingThreatDetector()]

__all__ = ["MissedCheckDetector", "MissedForcingMoveDetector", "MatingThreatDetector", "DETECTORS"]
