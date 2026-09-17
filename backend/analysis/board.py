"""Pure board primitives: material, attackers, SEE, pawn structure, mobility.

No chess *judgment* lives here and no project models are imported — just facts that
can be computed from a position (and, where noted, its move history). Both the
feature extractor in ``analysis/`` and the concept detectors in ``concepts/`` build
on these, so a rule like "this piece is undefended" is implemented exactly once.
"""

from typing import Dict, List, Optional, Sequence, Set

import chess

#: Standard material values in pawns. The king is given 0 because it can never be
#: captured; an attacked king is check, which other code detects structurally.
PIECE_VALUES: Dict[int, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

PIECE_NAMES: Dict[int, str] = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

#: Squares a minor piece must leave to count as developed.
MINOR_HOME_SQUARES: Dict[bool, Set[int]] = {
    chess.WHITE: {chess.B1, chess.G1, chess.C1, chess.F1},
    chess.BLACK: {chess.B8, chess.G8, chess.C8, chess.F8},
}

CENTER_SQUARES = {chess.D4, chess.E4, chess.D5, chess.E5}


def to_chess_color(color: object) -> bool:
    """Accept our ``Color`` enum or a plain bool and return python-chess's bool."""
    value = getattr(color, "value", color)
    if isinstance(value, bool):
        return value
    return str(value).lower() == "white"


def square_name(square: Optional[int]) -> str:
    return "-" if square is None else chess.square_name(square)


def piece_value(piece: Optional[chess.Piece]) -> int:
    return 0 if piece is None else PIECE_VALUES.get(piece.piece_type, 0)

def side_material(board: chess.Board, color: bool) -> int:
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        if piece_type == chess.KING:
            continue
        total += len(board.pieces(piece_type, color)) * value
    return total


def material_balance(board: chess.Board, color: bool) -> int:
    """Material difference in pawns from ``color``'s point of view."""
    return side_material(board, color) - side_material(board, not color)


def total_non_pawn_material(board: chess.Board) -> int:
    """Queens + rooks + minors for both sides; drives phase classification."""
    total = 0
    for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
        total += (len(board.pieces(piece_type, chess.WHITE)) + len(board.pieces(piece_type, chess.BLACK))) * PIECE_VALUES[piece_type]
    return total


def defenders(board: chess.Board, square: int) -> Set[int]:
    """Squares of friendly pieces defending ``square`` (empty if unoccupied)."""
    piece = board.piece_at(square)
    if piece is None:
        return set()
    return set(board.attackers(piece.color, square))


def is_defended(board: chess.Board, square: int) -> bool:
    return bool(defenders(board, square))

def undefended_pieces(board: chess.Board, color: bool) -> List[int]:
    """Own pieces (excluding king and pawns) with no friendly defender."""
    result: List[int] = []
    for square in chess.scan_reversed(board.occupied_co[color]):
        piece = board.piece_at(square)
        if piece is None or piece.piece_type in (chess.KING, chess.PAWN):
            continue
        if not is_defended(board, square):
            result.append(square)
    return sorted(result)


def attacked_pieces(board: chess.Board, color: bool) -> List[int]:
    """Own pieces (excluding king) currently attacked by the opponent."""
    result: List[int] = []
    for square in chess.scan_reversed(board.occupied_co[color]):
        piece = board.piece_at(square)
        if piece is None or piece.piece_type == chess.KING:
            continue
        if board.attackers(not color, square):
            result.append(square)
    return sorted(result)


def static_exchange_evaluation(board: chess.Board, move: chess.Move) -> int:
    """Material (in pawns) the side to move wins by starting the exchange on ``move``.

    This is the classic swap-off / SEE: both sides keep recapturing on the target
    square with their least valuable piece, and either side may stop when continuing
    would lose material. The first capture is mandatory (SEE of a bad capture is
    negative — that is exactly what makes it useful).

    Pins are ignored, as is customary: SEE is a fast approximation used as *evidence
    for a detector*, never as a final judgment. Engine lines always have the last word.
    """
    target = move.to_square
    board_after = board.copy(stack=False)
    mover = board.piece_at(move.from_square)
    if mover is not None:
        # SEE is frequently asked about a capture made by the side that is *not* to move
        # (``loose_pieces`` asks "what could the opponent take right now?"). python-chess
        # validates legality against the side to move, so the turn is aligned with the
        # mover first; otherwise the recapture below would be rejected as illegal.
        board_after.turn = mover.color
    if board_after.is_en_passant(move):
        first_gain = PIECE_VALUES[chess.PAWN]
    else:
        victim = board_after.piece_at(target)
        first_gain = piece_value(victim)
    try:
        board_after.push(move)
    except (ValueError, AssertionError):  # pragma: no cover - caller passes legal moves
        return 0
    return first_gain - _see_reply(board_after, target)


def _see_reply(board_after: chess.Board, target: int) -> int:
    """Best material the opponent can win by continuing the exchange on ``target``.

    The recapturing side is derived from the piece standing on ``target`` rather than
    from ``board_after.turn``: SEE is frequently asked about a capture by the side that
    is *not* to move (for example when checking whether an enemy piece is loose), and
    ``push`` flips the turn regardless of the mover's colour.
    """
    occupant = board_after.piece_at(target)
    if occupant is None:
        return 0
    if occupant.piece_type == chess.KING:
        # Capturing a king is not a legal continuation; the exchange ends here.
        return 0
    side = not occupant.color
    attackers = board_after.attackers(side, target)
    if not attackers:
        return 0
    attacker_square = min(
        attackers, key=lambda sq: piece_value(board_after.piece_at(sq)) or 99
    )
    gain = piece_value(occupant)
    next_board = board_after.copy(stack=False)
    next_board.turn = side
    try:
        next_board.push(chess.Move(attacker_square, target))
    except (ValueError, AssertionError):
        # Pinned or otherwise illegal recapture: the exchange stops.
        return 0
    return max(0, gain - _see_reply(next_board, target))

def pawn_attack_squares(board: chess.Board, color: bool) -> Set[int]:
    """All squares attacked by ``color``'s pawns."""
    squares: Set[int] = set()
    for pawn in board.pieces(chess.PAWN, color):
        squares |= set(board.attacks(pawn))
    return squares


def safe_destinations(board: chess.Board, square: int) -> List[int]:
    """Squares the piece on ``square`` can move to without being lost immediately.

    A destination is "safe" when the move is legal and, after it, the moving piece is
    neither en prise to a cheaper attacker nor simply hanging.
    """
    piece = board.piece_at(square)
    if piece is None:
        return []
    safe: List[int] = []
    for target in board.attacks(square):
        move = chess.Move(square, target)
        if piece.piece_type == chess.PAWN and chess.square_rank(target) in (0, 7):
            move = chess.Move(square, target, promotion=chess.QUEEN)
        if move not in board.legal_moves:
            continue
        next_board = board.copy(stack=False)
        next_board.push(move)
        if _would_lose_piece(next_board, target):
            continue
        safe.append(target)
    return safe


def _would_lose_piece(board_after: chess.Board, square: int) -> bool:
    """True if the piece now on ``square`` can be captured profitably."""
    piece = board_after.piece_at(square)
    if piece is None:
        return False
    attackers = board_after.attackers(not piece.color, square)
    if not attackers:
        return False
    cheapest = min(piece_value(board_after.piece_at(sq)) or 99 for sq in attackers)
    defenders = board_after.attackers(piece.color, square)
    if not defenders:
        return True
    return cheapest < PIECE_VALUES.get(piece.piece_type, 0)


def pseudo_safe_destinations(board: chess.Board, square: int) -> List[int]:
    """Approximate escape squares for the piece on ``square``, on either turn.

    ``safe_destinations`` needs the piece's owner to be the side to move; detectors
    often inspect the position *after* the player's move, when the opponent is to
    move. This variant therefore works from attack maps alone:

    * a destination is safe when no enemy piece attacks it, or
    * when the moving piece would be defended there and only attacked by pieces worth
      at least as much as itself.

    Pins are ignored — this is a mobility estimate used as supporting evidence, and
    every caller documents that limitation.
    """
    piece = board.piece_at(square)
    if piece is None:
        return []
    value = PIECE_VALUES.get(piece.piece_type, 0)
    result: List[int] = []
    for target in board.attacks(square):
        occupant = board.piece_at(target)
        if occupant is not None and occupant.color == piece.color:
            continue
        attackers = board.attackers(not piece.color, target)
        if not attackers:
            result.append(target)
            continue
        defenders = board.attackers(piece.color, target) - {square}
        if not defenders:
            continue
        cheapest = min(piece_value(board.piece_at(sq)) or 99 for sq in attackers)
        if cheapest >= value:
            result.append(target)
    return result


def all_legal_destinations(board: chess.Board, square: int) -> List[int]:
    return [
        move.to_square for move in board.legal_moves if move.from_square == square
    ]


def mobility(board: chess.Board, square: int) -> int:
    return len(all_legal_destinations(board, square))


def isolated_pawns(board: chess.Board, color: bool) -> List[int]:
    """Pawns with no friendly pawn on either adjacent file."""
    files = {chess.square_file(sq) for sq in board.pieces(chess.PAWN, color)}
    result = []
    for square in sorted(board.pieces(chess.PAWN, color)):
        file_index = chess.square_file(square)
        neighbours = {file_index - 1, file_index + 1}
        if not (neighbours & files):
            result.append(square)
    return result


def doubled_pawns(board: chess.Board, color: bool) -> List[int]:
    """The *trailing* pawn on each file that holds more than one friendly pawn.

    The trailing pawn is the one that cannot advance because its own colleague blocks
    it — the pawn that actually makes the structure weak.
    """
    result: List[int] = []
    for file_index in range(8):
        file_pawns = sorted(
            square
            for square in board.pieces(chess.PAWN, color)
            if chess.square_file(square) == file_index
        )
        if len(file_pawns) > 1:
            result.extend(file_pawns[:-1] if color == chess.WHITE else file_pawns[1:])
    return result


def passed_pawns(board: chess.Board, color: bool) -> List[int]:
    """Pawns with no enemy pawn on their file or the two adjacent files ahead of them."""
    enemy_pawns = board.pieces(chess.PAWN, not color)
    enemy_by_file: Dict[int, Set[int]] = {}
    for square in enemy_pawns:
        enemy_by_file.setdefault(chess.square_file(square), set()).add(chess.square_rank(square))

    result: List[int] = []
    for square in sorted(board.pieces(chess.PAWN, color)):
        file_index = chess.square_file(square)
        rank = chess.square_rank(square)
        blocked = False
        for neighbour in (file_index - 1, file_index, file_index + 1):
            if neighbour < 0 or neighbour > 7:
                continue
            for enemy_rank in enemy_by_file.get(neighbour, set()):
                ahead = enemy_rank > rank if color == chess.WHITE else enemy_rank < rank
                if ahead:
                    blocked = True
                    break
            if blocked:
                break
        if not blocked:
            result.append(square)
    return result


def has_castled(board: chess.Board, color: bool) -> bool:
    """True when the move history contains a castling move by ``color``."""
    for move in board.move_stack:
        piece = board.piece_at(move.from_square)
        if piece is not None and piece.color == color and board.is_castling(move):
            return True
    # The board may have been reconstructed from a FEN without history.
    king_square = board.king(color)
    if king_square is None:
        return False
    back_rank = 0 if color == chess.WHITE else 7
    if chess.square_rank(king_square) != back_rank:
        return False
    # Castled kings stand on the g- or c-file (indices 6 and 2).
    return chess.square_file(king_square) in (6, 2)


def undeveloped_minors(board: chess.Board, color: bool) -> List[int]:
    """Minor pieces still sitting on their starting squares."""
    result = []
    for square in MINOR_HOME_SQUARES[color]:
        piece = board.piece_at(square)
        if piece is not None and piece.color == color and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            result.append(square)
    return sorted(result)


def king_ring(board: chess.Board, color: bool) -> Set[int]:
    """King square plus its neighbours — the squares relevant to king safety."""
    king_square = board.king(color)
    if king_square is None:
        return set()
    return set(chess.SquareSet(chess.BB_KING_ATTACKS[king_square])) | {king_square}


def pawns_in_front_of_king(board: chess.Board, color: bool, max_rank_distance: int = 2) -> Set[int]:
    """Own pawns shielding the king, used to spot pawn-shield damage."""
    king_square = board.king(color)
    if king_square is None:
        return set()
    file_index = chess.square_file(king_square)
    rank = chess.square_rank(king_square)
    direction = 1 if color == chess.WHITE else -1
    result: Set[int] = set()
    for df in (-1, 0, 1):
        target_file = file_index + df
        if not 0 <= target_file <= 7:
            continue
        for step in range(1, max_rank_distance + 1):
            target_rank = rank + direction * step
            if not 0 <= target_rank <= 7:
                continue
            square = chess.square(target_file, target_rank)
            piece = board.piece_at(square)
            if piece is not None and piece.color == color and piece.piece_type == chess.PAWN:
                result.add(square)
    return result

def find_move_by_uci(board: chess.Board, uci: str) -> Optional[chess.Move]:
    for move in board.legal_moves:
        if move.uci() == uci:
            return move
    return None
