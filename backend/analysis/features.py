"""Deterministic board-feature extraction.

Turns a position into the flat, purely factual :class:`BoardContext` that travels
with every analyzed move. Nothing here is an evaluation — a shallow bishop does not
appear as "bad", only as "this piece has 2 safe squares".
"""

import chess

from analysis.board import (
    attacked_pieces,
    doubled_pawns,
    has_castled,
    isolated_pawns,
    material_balance,
    passed_pawns,
    square_name,
    to_chess_color,
    total_non_pawn_material,
    undefended_pieces,
    undeveloped_minors,
)
from models.enums import Color
from models.evidence import BoardContext


def build_board_context(board: chess.Board, player_color: Color) -> BoardContext:
    """Summarize ``board`` (the position the player is about to move in)."""
    player = to_chess_color(player_color)
    opponent = not player

    king_square = board.king(player)

    return BoardContext(
        material_balance=float(material_balance(board, player)),
        total_non_pawn_material=total_non_pawn_material(board),
        player_king_square=square_name(king_square) if king_square is not None else None,
        player_has_castled=has_castled(board, player),
        player_undeveloped_minors=len(undeveloped_minors(board, player)),
        player_legal_moves=board.legal_moves.count(),
        opponent_legal_moves=_opponent_legal_moves(board),
        player_isolated_pawns=[square_name(sq) for sq in isolated_pawns(board, player)],
        player_doubled_pawns=[square_name(sq) for sq in doubled_pawns(board, player)],
        player_passed_pawns=[square_name(sq) for sq in passed_pawns(board, player)],
        opponent_passed_pawns=[square_name(sq) for sq in passed_pawns(board, opponent)],
        player_undefended_pieces=[square_name(sq) for sq in undefended_pieces(board, player)],
        player_attacked_pieces=[square_name(sq) for sq in attacked_pieces(board, player)],
    )


def _opponent_legal_moves(board: chess.Board) -> int:
    """Legal-move count for the other side (a cheap proxy for their activity).

    Implemented by passing for one ply, which python-chess forbids while in check —
    in that case the count is reported as 0 rather than guessed.
    """
    mirrored = board.copy(stack=False)
    try:
        mirrored.push(chess.Move.null())
    except (ValueError, AssertionError):
        return 0
    return mirrored.legal_moves.count()
