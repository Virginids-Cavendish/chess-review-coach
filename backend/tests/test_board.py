"""Board primitives: static exchange evaluation, pawn structure, tactics on rays."""

import chess
import pytest

from analysis.board import (
    doubled_pawns,
    isolated_pawns,
    material_balance,
    passed_pawns,
    piece_value,
    pseudo_safe_destinations,
    square_name,
    static_exchange_evaluation,
    to_chess_color,
    total_non_pawn_material,
    undefended_pieces,
    undeveloped_minors,
)
from concepts.scan import find_discovered_attacks, find_line_tactics, loose_pieces
from models.enums import Color


def see(fen: str, uci: str) -> int:
    board = chess.Board(fen)
    move = next(m for m in board.legal_moves if m.uci() == uci)
    return static_exchange_evaluation(board, move)


def test_color_conversion_accepts_enum_and_bool():
    assert to_chess_color(Color.WHITE) is chess.WHITE
    assert to_chess_color(Color.BLACK) is chess.BLACK
    assert to_chess_color(chess.WHITE) is chess.WHITE


def test_piece_values_use_standard_material():
    board = chess.Board()
    assert piece_value(board.piece_at(chess.A1)) == 5  # rook
    assert piece_value(board.piece_at(chess.B1)) == 3  # knight
    assert piece_value(board.piece_at(chess.A2)) == 1  # pawn
    assert piece_value(None) == 0


# ------------------------------------------------------------------------- SEE


def test_see_free_pawn_is_one():
    assert see("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5") == 1


def test_see_defended_pawn_is_zero():
    # The pawn on d5 is defended by the c6 pawn, so the exchange is neutral.
    assert see("4k3/8/2p5/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5") == 0


def test_see_undefended_knight_is_three():
    assert see("4k3/8/8/3n4/4P3/8/8/4K3 w - - 0 1", "e4d5") == 3


def test_see_defended_knight_taken_by_bishop_is_zero():
    assert see("4k3/8/2p5/3n4/8/1B6/8/4K3 w - - 0 1", "b3d5") == 0


def test_see_losing_capture_is_negative():
    # Rook takes a pawn defended by a pawn: win one, lose the rook.
    assert see("4k3/2p5/3p4/8/8/8/8/3RK3 w - - 0 1", "d1d6") == -4


def test_see_quiet_move_is_zero():
    assert see("4k3/8/8/8/8/8/8/4K2R w - - 0 1", "h1h5") == 0


# ------------------------------------------------------------- pawn structure


def test_isolated_pawn_detection():
    board = chess.Board("4k3/8/8/8/8/8/PP4P1/4K3 w - - 0 1")
    assert [square_name(sq) for sq in isolated_pawns(board, chess.WHITE)] == ["g2"]


def test_doubled_pawn_detection_returns_the_trailing_pawn():
    board = chess.Board("4k3/8/8/8/8/P7/P7/4K3 w - - 0 1")
    assert [square_name(sq) for sq in doubled_pawns(board, chess.WHITE)] == ["a2"]

    black_board = chess.Board("4k3/4p3/4p3/8/8/8/8/4K3 b - - 0 1")
    assert [square_name(sq) for sq in doubled_pawns(black_board, chess.BLACK)] == ["e7"]


def test_passed_pawn_detection():
    board = chess.Board("4k3/8/8/8/4P3/8/8/4K3 w - - 0 1")
    assert [square_name(sq) for sq in passed_pawns(board, chess.WHITE)] == ["e4"]

    blocked = chess.Board("4k3/4p3/8/4P3/8/8/8/4K3 w - - 0 1")
    assert passed_pawns(blocked, chess.WHITE) == []


def test_material_and_development_helpers():
    board = chess.Board()
    assert material_balance(board, chess.WHITE) == 0
    assert total_non_pawn_material(board) == 62
    assert len(undeveloped_minors(board, chess.WHITE)) == 4

    after = chess.Board()
    after.push_san("Nf3")
    assert len(undeveloped_minors(after, chess.WHITE)) == 3

    queen_up = chess.Board("4k3/8/8/3q4/8/8/8/4K3 w - - 0 1")
    assert material_balance(queen_up, chess.WHITE) == -9
    assert material_balance(queen_up, chess.BLACK) == 9


def test_undefended_pieces_ignores_kings_and_pawns():
    board = chess.Board("4k3/8/8/8/8/8/4P3/4K2R w - - 0 1")
    undefended = [square_name(sq) for sq in undefended_pieces(board, chess.WHITE)]
    assert "h1" in undefended  # the rook has no defender
    assert "e1" not in undefended  # the king is never reported
    assert "e2" not in undefended  # pawns are not reported


# ---------------------------------------------------------------- escape squares


def test_pseudo_safe_destinations_excludes_attacked_squares():
    # The rook on d1 cannot go to d5 (attacked by the black rook on d8, undefended).
    board = chess.Board("3r3k/8/8/8/8/8/8/3R2K1 w - - 0 1")
    safe = {square_name(sq) for sq in pseudo_safe_destinations(board, chess.D1)}
    assert "d5" not in safe
    assert "a1" in safe


# --------------------------------------------------------------------- tactics


def test_pin_detection_relative_and_absolute():
    board = chess.Board("3q3k/8/5n2/6B1/8/8/8/7K w - - 0 1")
    pins = find_line_tactics(board, chess.WHITE)
    assert len(pins) == 1
    assert pins[0].kind == "pin"
    assert square_name(pins[0].front_square) == "f6"
    assert square_name(pins[0].back_square) == "d8"
    assert pins[0].absolute is False

    absolute = chess.Board("4k3/8/8/8/8/8/4R3/4K3 w - - 0 1")
    absolute.set_piece_at(chess.E7, chess.Piece(chess.BISHOP, chess.BLACK))
    pins = find_line_tactics(absolute, chess.WHITE)
    assert any(pin.absolute for pin in pins)


def test_skewer_detection_puts_the_king_in_front():
    board = chess.Board("7r/8/8/4k3/8/8/8/K1B5 w - - 0 1")
    assert find_line_tactics(board, chess.WHITE) == []

    board.push_san("Bb2")
    tactics = find_line_tactics(board, chess.WHITE)
    assert len(tactics) == 1
    assert tactics[0].kind == "skewer"
    assert square_name(tactics[0].front_square) == "e5"  # the king is in front
    assert square_name(tactics[0].back_square) == "h8"


def test_loose_pieces_respects_defenders():
    board = chess.Board("7k/8/8/q7/8/8/8/1K5R w - - 0 1")
    board.push_san("Rh5")
    loose = loose_pieces(board, chess.WHITE)
    assert chess.H5 in loose
    assert loose[chess.H5].best_see == 5
    assert loose[chess.H5].defended is False


def test_discovered_attack_detection():
    # The white bishop on e4 blocks the rook's line to the black rook on e8. Moving the
    # bishop to d5 uncovers the attack along the e-file.
    board_before = chess.Board("k3r3/8/8/8/4B3/8/8/4R1K1 w - - 0 1")
    board_after = board_before.copy()
    board_after.push_san("Bd5")

    attacks = find_discovered_attacks(board_before, board_after, chess.WHITE)
    assert len(attacks) == 1
    assert square_name(attacks[0].slider_square) == "e1"
    assert square_name(attacks[0].target_square) == "e8"
    assert square_name(attacks[0].vacated_square) == "e4"


def test_no_discovered_attack_when_nothing_was_blocking():
    board_before = chess.Board("k3r3/8/8/8/8/8/8/4R1K1 w - - 0 1")
    board_after = board_before.copy()
    board_after.push_san("Ra1")
    # The rook itself moved, so nothing was *discovered*.
    assert find_discovered_attacks(board_before, board_after, chess.WHITE) == []


def test_line_tactics_empty_for_quiet_position():
    assert find_line_tactics(chess.Board(), chess.WHITE) == []
    assert find_line_tactics(chess.Board(), chess.BLACK) == []
