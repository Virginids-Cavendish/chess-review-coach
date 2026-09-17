"""Geometric tactical motifs: forks, double attacks, pins, skewers, discovered attacks.

Every motif is searched only in positions that are actually part of the evidence — the
position after the played move, the engine's continuation, and the engine's own best
line. A motif the engine never plays is not reported, which is what keeps these
detectors from "discovering" tactics nobody could have used.
"""

import chess
from typing import List, Optional, Tuple

from analysis.board import PIECE_VALUES, piece_value, square_name
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from concepts.scan import (
    DiscoveredAttack,
    LineTactic,
    find_discovered_attacks,
    find_line_tactics,
    loose_pieces,
    tactic_signature,
)
from models.enums import ConceptType

#: A motif has to win something to be worth mentioning.
FORK_MIN_TARGET_VALUE = 3


def _apply_move(board: chess.Board, move: chess.Move) -> chess.Board:
    after = board.copy(stack=False)
    after.push(move)
    return after


def _fork_targets(board_before: chess.Board, move: chess.Move, mover: bool) -> List[int]:
    """Enemy pieces a single move attacks that are worth forking.

    Requires at least two targets worth a minor piece or more, and that at least one of
    them can actually be won (static exchange evaluation), so double attacks on
    well-defended pieces do not fire.
    """
    moved_piece = board_before.piece_at(move.from_square)
    if moved_piece is None:
        return []
    board_after = _apply_move(board_before, move)
    forker_value = PIECE_VALUES.get(moved_piece.piece_type, 0)
    loose = loose_pieces(board_after, not mover)

    targets: List[int] = []
    for target in board_after.attacks(move.to_square):
        victim = board_after.piece_at(target)
        if victim is None or victim.color == mover or victim.piece_type == chess.KING:
            continue
        if piece_value(victim) < FORK_MIN_TARGET_VALUE:
            continue
        targets.append(target)

    if len(targets) < 2:
        return []
    if forker_value >= min(piece_value(board_after.piece_at(sq)) for sq in targets):
        # The forking piece is at least as valuable as everything it attacks; that is an
        # attack, not a fork.
        return []
    if not any(square in loose for square in targets):
        return []
    return targets


def _double_attack_targets(
    board_before: chess.Board, move: chess.Move, mover: bool
) -> List[int]:
    """Enemy *undefended* pieces attacked by one move (broader than a fork)."""
    board_after = _apply_move(board_before, move)
    targets: List[int] = []
    for target in board_after.attacks(move.to_square):
        victim = board_after.piece_at(target)
        if victim is None or victim.color == mover or victim.piece_type == chess.KING:
            continue
        if board_after.attackers(victim.color, target):
            continue
        targets.append(target)
    if len(targets) < 2:
        return []
    total = sum(piece_value(board_after.piece_at(sq)) for sq in targets)
    return targets if total >= 2 else []


class ForkDetector:
    """A single piece attacks two or more valuable enemy pieces.

    Reported for the opponent's play inside the engine line (the classic "you walked
    into a fork") and for the engine's own recommendation (where a fork was available).
    """

    name = "fork"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        results: List[DetectedConcept] = []

        opponent_fork = self._first_fork(ctx, ctx.played_line[:4], ctx.opponent)
        if opponent_fork is not None:
            board, move, targets = opponent_fork
            results.append(
                make_concept(
                    ConceptType.FORK,
                    0.85,
                    pieces=[piece_code(board, move.from_square)],
                    squares=[square_name(move.to_square)] + [square_name(sq) for sq in targets],
                    evidence=[
                        "In the engine continuation the opponent plays {}, forking {}.".format(
                            self._san(board, move),
                            " and ".join(piece_code(board, sq) for sq in targets),
                        )
                    ],
                    metadata={"side": "opponent", "line_move": self._san(board, move)},
                )
            )

        best_fork = self._first_fork(ctx, ctx.best_line[:1], ctx.pov)
        if best_fork is not None and not ctx.evidence.is_engine_best:
            board, move, targets = best_fork
            results.append(
                make_concept(
                    ConceptType.FORK,
                    0.7 if ctx.is_problem else 0.45,
                    pieces=[piece_code(board, move.from_square)],
                    squares=[square_name(move.to_square)] + [square_name(sq) for sq in targets],
                    evidence=[
                        "The engine's first choice {} forks {}.".format(
                            self._san(board, move),
                            " and ".join(piece_code(board, sq) for sq in targets),
                        )
                    ],
                    metadata={"side": "player", "available": "true"},
                )
            )
        return results

    @staticmethod
    def _first_fork(ctx: DetectionContext, line, mover: bool):
        for entry in line:
            if entry.mover != mover:
                continue
            targets = _fork_targets(entry.board_before, entry.move, mover)
            if targets:
                return entry.board_before, entry.move, targets
        return None

    @staticmethod
    def _san(board: chess.Board, move: chess.Move) -> str:
        try:
            return board.san(move)
        except (ValueError, AssertionError):  # pragma: no cover
            return move.uci()


class DoubleAttackDetector:
    """One move attacks two or more *undefended* enemy pieces.

    Overlaps deliberately with :class:`ForkDetector` only for undefended targets; a
    fork on defended-but-loose pieces is reported once, by the fork detector.
    """

    name = "double_attack"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        candidates: List[Tuple[str, chess.Board, chess.Move, List[int]]] = []
        for entry in ctx.played_line[:4]:
            if entry.mover != ctx.opponent:
                continue
            targets = _double_attack_targets(entry.board_before, entry.move, ctx.opponent)
            if targets:
                candidates.append(("opponent", entry.board_before, entry.move, targets))
                break
        if not candidates:
            return []

        side, board, move, targets = candidates[0]
        if _fork_targets(board, move, ctx.opponent):
            # Already covered as a fork; do not report the same move twice.
            return []
        return [
            make_concept(
                ConceptType.DOUBLE_ATTACK,
                0.7,
                pieces=[piece_code(board, move.from_square)],
                squares=[square_name(move.to_square)] + [square_name(sq) for sq in targets],
                evidence=[
                    "In the engine continuation the opponent's {} attacks two undefended "
                    "pieces: {}.".format(
                        ForkDetector._san(board, move),
                        " and ".join(piece_code(board, sq) for sq in targets),
                    )
                ],
                metadata={"side": side},
            )
        ]


class PinSkewerDetector:
    """Pins and skewers created by the played move (for either side)."""

    name = "pin_skewer"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        results: List[DetectedConcept] = []

        player_created = self._new_tactics(ctx, ctx.pov)
        for tactic in player_created:
            results.append(self._concept(ctx, tactic, ctx.pov, positive=True))

        opponent_created = self._new_tactics(ctx, ctx.opponent)
        for tactic in opponent_created:
            results.append(self._concept(ctx, tactic, ctx.opponent, positive=False))
        return results

    @staticmethod
    def _new_tactics(ctx: DetectionContext, side: bool) -> List[LineTactic]:
        before = {tactic_signature(t) for t in find_line_tactics(ctx.board_before, side)}
        after = find_line_tactics(ctx.board_after, side)
        return [tactic for tactic in after if tactic_signature(tactic) not in before]

    def _concept(
        self, ctx: DetectionContext, tactic: LineTactic, side: bool, positive: bool
    ) -> DetectedConcept:
        concept_type = ConceptType.PIN if tactic.kind == "pin" else ConceptType.SKEWER
        who = "the player" if side == ctx.pov else "the opponent"
        detail = "absolute " if tactic.absolute else ""
        evidence = [
            "After the move, {who} has {article}{kind} on {front} against {back} ({slider}).".format(
                who=who,
                article="an " if detail else "a ",
                kind=detail + tactic.kind,
                front=piece_code(ctx.board_after, tactic.front_square),
                back=piece_code(ctx.board_after, tactic.back_square),
                slider=piece_code(ctx.board_after, tactic.slider_square),
            )
        ]
        confidence = 0.75 if positive else (0.8 if ctx.is_problem else 0.5)
        return make_concept(
            concept_type,
            confidence,
            pieces=[piece_code(ctx.board_after, tactic.slider_square)],
            squares=[square_name(tactic.front_square), square_name(tactic.back_square)],
            evidence=evidence,
            metadata={
                "side": "player" if side == ctx.pov else "opponent",
                "absolute": str(tactic.absolute).lower(),
            },
        )


class DiscoveredAttackDetector:
    """Attacks that opened up because a piece vacated a line."""

    name = "discovered_attack"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        results: List[DetectedConcept] = []

        player_attacks = find_discovered_attacks(ctx.board_before, ctx.board_after, ctx.pov)
        for attack in player_attacks[:2]:
            results.append(self._concept(ctx, attack, ctx.pov))

        for entry in ctx.played_line[:4]:
            if entry.mover != ctx.opponent:
                continue
            opponent_attacks = find_discovered_attacks(
                entry.board_before, entry.board_after, ctx.opponent
            )
            if opponent_attacks:
                results.append(self._concept(ctx, opponent_attacks[0], ctx.opponent, line=entry.san))
                break
        return results

    def _concept(
        self, ctx: DetectionContext, attack: DiscoveredAttack, side: bool, line: Optional[str] = None
    ) -> DetectedConcept:
        board = ctx.board_after
        who = "the player" if side == ctx.pov else "the opponent"
        evidence = [
            "{who} discovered an attack: {slider} now attacks {target} after the piece "
            "left {vacated}.".format(
                who=who,
                slider=piece_code(board, attack.slider_square),
                target=piece_code(board, attack.target_square),
                vacated=square_name(attack.vacated_square),
            )
        ]
        if line:
            evidence.append("This happens inside the engine line with {}.".format(line))
        return make_concept(
            ConceptType.DISCOVERED_ATTACK,
            0.7 if side == ctx.pov else 0.75,
            pieces=[piece_code(board, attack.slider_square)],
            squares=[square_name(attack.target_square), square_name(attack.vacated_square)],
            evidence=evidence,
            metadata={"side": "player" if side == ctx.pov else "opponent"},
        )


DETECTORS = [
    ForkDetector(),
    DoubleAttackDetector(),
    PinSkewerDetector(),
    DiscoveredAttackDetector(),
]

__all__ = [
    "ForkDetector",
    "DoubleAttackDetector",
    "PinSkewerDetector",
    "DiscoveredAttackDetector",
    "DETECTORS",
]
