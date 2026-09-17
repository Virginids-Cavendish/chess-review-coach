"""Material concepts: what was lost, what could have been won, imbalances.

Material claims are always backed by a concrete computation — a static exchange
evaluation of a move that was available, or the material count at the end of the
engine's own continuation. Nothing here infers material from the evaluation number.
"""

import chess
from typing import List, Optional, Tuple

from analysis.board import material_balance, square_name, static_exchange_evaluation
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from concepts.scan import material_signature
from models.enums import ConceptType

#: How many plies of the engine continuation we scan when asking "what did this move
#: cost?" Six plies covers a capture, a recapture and the follow-up check.
MATERIAL_WINDOW = 6


class MaterialLossDetector:
    """Material the player ends up behind by, compared with the engine's own line.

    Measuring "what the move cost" against the position *after* the move would be
    misleading: a capture followed by a recapture nets out, and a move that wins a
    knight before giving back a bishop would look like a loss. The comparison is
    therefore between the end of the engine's recommended continuation and the end of
    the continuation that actually follows the played move, both truncated to the same
    point in the move cycle.
    """

    name = "material_loss"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if ctx.evidence.mate_after is not None and ctx.evidence.mate_after < 0:
            # The position is lost to a forced mate; counting material here would be
            # misleading.
            return []
        if any(entry.mover == ctx.opponent and entry.is_mate for entry in ctx.played_line[:6]):
            return []

        played_window = self._balanced_window(ctx.played_line, ctx.pov)
        best_window = self._balanced_window(ctx.best_line, ctx.pov)
        if not played_window or not best_window:
            return []

        balance_played = material_balance(played_window[-1].board_after, ctx.pov)
        balance_best = material_balance(best_window[-1].board_after, ctx.pov)
        drop = balance_best - balance_played
        if drop < ctx.thresholds.significant_material_loss:
            return []
        if not ctx.is_problem:
            # Two different engine lines diverge quickly; a material difference inside
            # them says nothing about a move the engine itself rates as best or good.
            return []

        captured = [
            piece_code(entry.board_before, entry.move.to_square)
            for entry in played_window
            if entry.mover == ctx.opponent and entry.is_capture
        ]
        return [
            make_concept(
                ConceptType.MATERIAL_LOSS,
                0.85,
                squares=[
                    square_name(entry.move.to_square)
                    for entry in played_window
                    if entry.mover == ctx.opponent and entry.is_capture
                ],
                evidence=[
                    "Following the engine's move the player would be at {} points of material; "
                    "in the continuation after the played move it is {} — a difference of "
                    "{}.".format(balance_best, balance_played, drop),
                    "Captures by the opponent in that line: {}.".format(
                        ", ".join(captured) if captured else "none"
                    ),
                ],
                metadata={
                    "material_drop": str(drop),
                    "balance_if_engine_move": str(balance_best),
                    "balance_after_played": str(balance_played),
                    "plies_scanned": str(len(played_window)),
                },
            )
        ]

    @staticmethod
    def _balanced_window(line, pov):
        """First plies of a continuation, trimmed so it ends with a player reply.

        Trimming matters: stopping halfway through an exchange would count a piece the
        player is about to recapture as lost.
        """
        window = list(line[:MATERIAL_WINDOW])
        if len(window) <= 1:
            return window
        last_player_index = max(
            (entry.index for entry in window if entry.mover == pov), default=-1
        )
        if last_player_index < 0:
            return window
        return window[: last_player_index + 1]


class MissedCaptureDetector:
    """A capture that wins material was available and the player played something else."""

    name = "missed_capture"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        available = self._best_capture(ctx)
        if available is None:
            return []
        move, see = available
        if move == ctx.played_move:
            return []

        engine_prefers = ctx.best_move is not None and ctx.best_move.uci() == move.uci()
        if not engine_prefers:
            # Without engine backing we require an unambiguous win and a move that
            # actually cost the player something, otherwise this fires on every
            # semi-interesting capture in a quiet position.
            if see < 2 or not ctx.is_problem:
                return []

        san = ctx.san(ctx.board_before, move)
        evidence = [
            "{} was available and wins {} pawn(s) by static exchange evaluation.".format(san, see)
        ]
        if engine_prefers:
            evidence.append("It is also the engine's first choice.")
        else:
            evidence.append("The engine's first choice was {}.".format(ctx.evidence.best_move_san))

        return [
            make_concept(
                ConceptType.MISSED_CAPTURE,
                0.9 if engine_prefers else 0.65,
                pieces=[piece_code(ctx.board_before, move.from_square)],
                squares=[square_name(move.to_square)],
                evidence=evidence,
                metadata={
                    "available_capture": san,
                    "see_gain": str(see),
                    "engine_preferred_it": str(engine_prefers).lower(),
                },
            )
        ]

    @staticmethod
    def _best_capture(ctx: DetectionContext) -> Optional[Tuple[chess.Move, int]]:
        best: Optional[Tuple[chess.Move, int]] = None
        for move in ctx.board_before.legal_moves:
            if not ctx.board_before.is_capture(move):
                continue
            see = static_exchange_evaluation(ctx.board_before, move)
            if see < ctx.thresholds.significant_material_loss:
                continue
            if best is None or see > best[1]:
                best = (move, see)
        return best


class BishopPairDetector:
    """Gaining or giving up the bishop pair with this move."""

    name = "bishop_pair"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        before = self._pair(ctx.board_before, ctx.pov)
        after = self._pair(ctx.board_after, ctx.pov)
        if before == after:
            return []
        gained = after and not before
        return [
            make_concept(
                ConceptType.BISHOP_PAIR,
                0.8,
                evidence=[
                    "The move {} the player the bishop pair.".format("gives" if gained else "costs")
                ],
                metadata={"direction": "gained" if gained else "lost"},
            )
        ]

    @staticmethod
    def _pair(board: chess.Board, color: bool) -> bool:
        return len(board.pieces(chess.BISHOP, color)) >= 2


class MaterialImbalanceDetector:
    """Non-standard material configurations (rook vs two minors, queen vs two rooks)."""

    name = "material_imbalance"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if self._signature_key(ctx.board_before, ctx.pov) == self._signature_key(
            ctx.board_after, ctx.pov
        ):
            return []
        player = material_signature(ctx.board_after, ctx.pov)
        opponent = material_signature(ctx.board_after, ctx.opponent)
        description = self._describe(player, opponent)
        if description is None:
            return []
        return [
            make_concept(
                ConceptType.MATERIAL_IMBALANCE,
                0.6,
                evidence=["Non-standard material balance after the move: {}.".format(description)],
                metadata={"imbalance": description},
            )
        ]

    @staticmethod
    def _signature_key(board: chess.Board, color: bool) -> Tuple[int, int, int, int]:
        signature = material_signature(board, color)
        other = material_signature(board, not color)
        return (
            signature["queens"] - other["queens"],
            signature["rooks"] - other["rooks"],
            signature["bishops"] - other["bishops"],
            signature["knights"] - other["knights"],
        )

    @staticmethod
    def _describe(player: dict, opponent: dict) -> Optional[str]:
        rook_diff = player["rooks"] - opponent["rooks"]
        minor_diff = (
            player["bishops"] + player["knights"] - opponent["bishops"] - opponent["knights"]
        )
        if rook_diff == 1 and minor_diff == -2:
            return "player has an extra rook for two minor pieces"
        if rook_diff == -1 and minor_diff == 2:
            return "opponent has an extra rook for two minor pieces"
        queen_diff = player["queens"] - opponent["queens"]
        if queen_diff == 1 and rook_diff == -2:
            return "player has a queen against two rooks"
        if queen_diff == -1 and rook_diff == 2:
            return "opponent has a queen against two rooks"
        return None


class ExchangeSacrificeDetector:
    """A rook was given for a minor piece and the engine still rates the position fine.

    This is deliberately conservative: it reports the *fact* that an exchange was
    given, only when the engine's own evaluation says the position remains acceptable.
    """

    name = "exchange_sacrifice"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        if ctx.evidence.expected_score_after < 0.45:
            return []
        for entry in ctx.played_line[:MATERIAL_WINDOW]:
            victim = entry.captured_piece()
            if victim is None or victim.color != ctx.pov or victim.piece_type != chess.ROOK:
                continue
            capturer = entry.board_before.piece_at(entry.move.from_square)
            if capturer is None or capturer.piece_type not in (chess.KNIGHT, chess.BISHOP):
                continue
            return [
                make_concept(
                    ConceptType.EXCHANGE_SACRIFICE,
                    0.5,
                    pieces=[piece_code(entry.board_before, entry.move.from_square)],
                    squares=[square_name(entry.move.to_square)],
                    evidence=[
                        "The engine line gives up a rook for a minor piece ({}).".format(
                            entry.san
                        ),
                        "The engine still evaluates the position as acceptable for the player.",
                    ],
                    metadata={"line_move": entry.san},
                )
            ]
        return []


DETECTORS = [
    MaterialLossDetector(),
    MissedCaptureDetector(),
    BishopPairDetector(),
    MaterialImbalanceDetector(),
    ExchangeSacrificeDetector(),
]

__all__ = [
    "MaterialLossDetector",
    "MissedCaptureDetector",
    "BishopPairDetector",
    "MaterialImbalanceDetector",
    "ExchangeSacrificeDetector",
    "DETECTORS",
]
