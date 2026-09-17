"""Board scanning helpers shared by detectors.

Each function answers one narrow, checkable question about a position (what is loose,
what is pinned, what a piece attacks). Keeping them here means the *definition* of
"hanging" or "pinned" exists in exactly one place and can be unit-tested directly.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import chess

from analysis.board import PIECE_VALUES, piece_value, square_name, static_exchange_evaluation
from concepts.base import piece_code


@dataclass
class LoosePiece:
    """A piece of one colour that the opponent can profitably capture."""

    square: int
    value: int
    attackers: List[int] = field(default_factory=list)
    defenders: List[int] = field(default_factory=list)
    best_see: int = 0

    @property
    def defended(self) -> bool:
        return bool(self.defenders)


def loose_pieces(board: chess.Board, color: bool) -> Dict[int, LoosePiece]:
    """Pieces of ``color`` (kings excluded) that ``color``'s opponent wins material on.

    "Loose" is decided by static exchange evaluation from the opponent's point of
    view, so a defended piece that is simply attacked is *not* included, while an
    undefended piece always is.
    """
    result: Dict[int, LoosePiece] = {}
    enemy = not color
    for square in chess.scan_reversed(board.occupied_co[color]):
        piece = board.piece_at(square)
        if piece is None or piece.piece_type == chess.KING:
            continue
        attackers = sorted(board.attackers(enemy, square))
        if not attackers:
            continue
        defenders = sorted(board.attackers(color, square))
        best = 0
        for attacker_square in attackers:
            see = static_exchange_evaluation(board, chess.Move(attacker_square, square))
            best = max(best, see)
        if best <= 0:
            continue
        result[square] = LoosePiece(
            square=square,
            value=PIECE_VALUES.get(piece.piece_type, 0),
            attackers=attackers,
            defenders=defenders,
            best_see=best,
        )
    return result


def attacked_piece_squares(board: chess.Board, color: bool) -> Set[int]:
    """Squares of ``color``'s pieces (kings excluded) attacked by the opponent."""
    enemy = not color
    return {
        square
        for square in chess.scan_reversed(board.occupied_co[color])
        if board.piece_at(square) is not None
        and board.piece_at(square).piece_type != chess.KING
        and board.attackers(enemy, square)
    }


@dataclass
class LineTactic:
    """A pin or skewer found along one ray."""

    kind: str  # "pin" | "skewer"
    slider_square: int
    front_square: int
    back_square: int
    absolute: bool  # a pin against the king

    def describe(self, board: chess.Board, attacker_color: bool) -> str:
        side = "white" if attacker_color else "black"
        return (
            "{} {} on {} lines up against {} on {} behind {} on {}".format(
                side,
                "slider",
                square_name(self.slider_square),
                piece_code(board, self.front_square),
                square_name(self.front_square),
                piece_code(board, self.back_square),
                square_name(self.back_square),
            )
        )


_DIRECTIONS: Dict[int, List[Tuple[int, int]]] = {
    chess.BISHOP: [(1, 1), (1, -1), (-1, 1), (-1, -1)],
    chess.ROOK: [(1, 0), (-1, 0), (0, 1), (0, -1)],
    chess.QUEEN: [
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
    ],
}


def occupied_squares_along(
    board: chess.Board, from_square: int, direction: Tuple[int, int]
) -> List[int]:
    """Occupied squares walking from ``from_square`` along ``direction``, in order."""
    file_index = chess.square_file(from_square) + direction[0]
    rank_index = chess.square_rank(from_square) + direction[1]
    found: List[int] = []
    while 0 <= file_index <= 7 and 0 <= rank_index <= 7:
        square = chess.square(file_index, rank_index)
        if board.piece_at(square) is not None:
            found.append(square)
        file_index += direction[0]
        rank_index += direction[1]
    return found


def find_line_tactics(board: chess.Board, attacker_color: bool) -> List[LineTactic]:
    """All pins and skewers the pieces of ``attacker_color`` currently create.

    Definition used: walking outward from a slider, the first two occupied squares must
    both hold enemy pieces. The king is ordered above every other piece for this
    comparison: a king "in front" cannot be captured and must step aside — that is a
    skewer — while a king "behind" makes the pin absolute.
    """
    results: List[LineTactic] = []
    for square in chess.scan_reversed(board.occupied_co[attacker_color]):
        piece = board.piece_at(square)
        if piece is None or piece.piece_type not in _DIRECTIONS:
            continue
        for direction in _DIRECTIONS[piece.piece_type]:
            occupied = occupied_squares_along(board, square, direction)
            if len(occupied) < 2:
                continue
            front, back = occupied[0], occupied[1]
            front_piece = board.piece_at(front)
            back_piece = board.piece_at(back)
            if front_piece is None or back_piece is None:
                continue
            if front_piece.color != (not attacker_color) or back_piece.color != (not attacker_color):
                continue
            front_rank = _ordering_value(front_piece)
            back_rank = _ordering_value(back_piece)
            if back_rank > front_rank:
                results.append(
                    LineTactic("pin", square, front, back, back_piece.piece_type == chess.KING)
                )
            elif front_rank > back_rank:
                results.append(LineTactic("skewer", square, front, back, False))
    return results


#: A king cannot be captured, so it outranks every piece when ordering a ray.
KING_ORDER = 100


def _ordering_value(piece: chess.Piece) -> int:
    if piece.piece_type == chess.KING:
        return KING_ORDER
    return PIECE_VALUES.get(piece.piece_type, 0)


def tactic_signature(tactic: LineTactic) -> Tuple[str, int, int]:
    """Identity of a pin/skewer for "was this already there?" comparisons.

    The slider's square is deliberately excluded: moving a bishop to another square on
    the same diagonal keeps the same piece pinned, and reporting that as a new pin
    created by the move would be wrong.
    """
    return (tactic.kind, tactic.front_square, tactic.back_square)


@dataclass
class DiscoveredAttack:
    slider_square: int
    target_square: int
    vacated_square: int


def find_discovered_attacks(
    board_before: chess.Board, board_after: chess.Board, mover: bool
) -> List[DiscoveredAttack]:
    """Attacks that appeared because a piece vacated a line.

    Requires that the slider did not itself move and that the vacated square was the
    first blocker on the ray towards the newly attacked enemy piece.
    """
    results: List[DiscoveredAttack] = []
    vacated = _vacated_square(board_before, board_after, mover)
    if vacated is None:
        return results

    for slider_square in chess.scan_reversed(board_after.occupied_co[mover]):
        slider = board_after.piece_at(slider_square)
        if slider is None or slider.piece_type not in _DIRECTIONS:
            continue
        if slider_square == vacated:
            continue
        before_targets = _enemy_attack_targets(board_before, slider_square, mover)
        after_targets = _enemy_attack_targets(board_after, slider_square, mover)
        for target in sorted(after_targets - before_targets):
            if _vacated_blocks(board_before, slider_square, target, vacated):
                results.append(
                    DiscoveredAttack(
                        slider_square=slider_square,
                        target_square=target,
                        vacated_square=vacated,
                    )
                )
    return results


def _vacated_square(
    board_before: chess.Board, board_after: chess.Board, mover: bool
) -> Optional[int]:
    """The square the mover's piece left, derived by diffing occupied squares."""
    before = set(chess.scan_reversed(board_before.occupied_co[mover]))
    after = set(chess.scan_reversed(board_after.occupied_co[mover]))
    left = before - after
    if len(left) == 1:
        return left.pop()
    return None


def _enemy_attack_targets(board: chess.Board, slider_square: int, mover: bool) -> Set[int]:
    piece = board.piece_at(slider_square)
    if piece is None:
        return set()
    targets = set()
    for square in board.attacks(slider_square):
        victim = board.piece_at(square)
        if victim is not None and victim.color != mover and victim.piece_type != chess.KING:
            targets.add(square)
    return targets


def _vacated_blocks(
    board_before: chess.Board, slider_square: int, target: int, vacated: int
) -> bool:
    """True when ``vacated`` was the first occupied square on the slider->target ray."""
    piece = board_before.piece_at(slider_square)
    if piece is None:
        return False
    for direction in _DIRECTIONS.get(piece.piece_type, []):
        occupied = occupied_squares_along(board_before, slider_square, direction)
        if not occupied:
            continue
        if occupied[0] == vacated and _on_ray(slider_square, direction, target):
            return True
    return False


def _on_ray(from_square: int, direction: Tuple[int, int], target: int) -> bool:
    file_index = chess.square_file(from_square) + direction[0]
    rank_index = chess.square_rank(from_square) + direction[1]
    while 0 <= file_index <= 7 and 0 <= rank_index <= 7:
        if chess.square(file_index, rank_index) == target:
            return True
        file_index += direction[0]
        rank_index += direction[1]
    return False

def material_signature(board: chess.Board, color: bool) -> Dict[str, int]:
    """Piece counts for one side, used for imbalance claims."""
    return {
        "queens": len(board.pieces(chess.QUEEN, color)),
        "rooks": len(board.pieces(chess.ROOK, color)),
        "bishops": len(board.pieces(chess.BISHOP, color)),
        "knights": len(board.pieces(chess.KNIGHT, color)),
        "pawns": len(board.pieces(chess.PAWN, color)),
    }
