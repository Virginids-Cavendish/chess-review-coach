"""PGN parsing: strictness, side detection, opening names."""

import pytest

from analysis.openings import identify_opening, table_size
from analysis.pgn import count_games, detect_player_color, parse_pgn
from engine.errors import PgnError
from models.enums import Color

ITALIAN = """[Event "Casual Game"]
[Site "Somewhere"]
[Date "2024.01.01"]
[White "Alpha"]
[Black "Beta"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 1-0
"""

SCHOLARS = """[White "W"]
[Black "B"]
[Result "0-1"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 0-1
"""


def test_parses_headers_moves_and_fens():
    game = parse_pgn(ITALIAN, player_color=Color.WHITE)
    assert game.white == "Alpha"
    assert game.black == "Beta"
    assert game.result == "1-0"
    assert len(game.moves) == 8
    assert game.player_color is Color.WHITE
    assert game.player_color_source == "explicit"

    first = game.moves[0]
    assert first.san == "e4"
    assert first.uci == "e2e4"
    assert first.color is Color.WHITE
    assert first.move_number == 1
    assert first.fen_before.startswith("rnbqkbnr/pppppppp")
    assert "4P3" in first.fen_after

    black_move = game.moves[1]
    assert black_move.color is Color.BLACK

    # Every move's fen_before must equal the previous move's fen_after.
    for previous, current in zip(game.moves, game.moves[1:]):
        assert current.fen_before == previous.fen_after


def test_player_moves_filter_and_full_move_count():
    game = parse_pgn(ITALIAN, player_color=Color.BLACK)
    assert game.full_moves == 4
    assert [move.san for move in game.player_moves()] == ["e5", "Nc6", "Bc5", "Nf6"]


def test_checkmate_sign_in_san_is_preserved():
    game = parse_pgn(SCHOLARS, player_color=Color.BLACK)
    assert game.moves[-1].san == "Qxf7#"


def test_side_detection_from_known_player_names():
    headers = {"White": "Alpha", "Black": "Beta"}
    assert detect_player_color(headers, ["Alpha"]) is Color.WHITE
    assert detect_player_color(headers, ["beta"]) is Color.BLACK
    assert detect_player_color(headers, ["Someone else"]) is None
    assert detect_player_color(headers, []) is None
    assert detect_player_color(headers, None) is None
    # Ambiguous when both names are known: ask the user instead of guessing.
    assert detect_player_color(headers, ["Alpha", "Beta"]) is None


def test_pgn_uses_known_names_when_no_side_is_selected():
    game = parse_pgn(ITALIAN, known_player_names=["Beta"])
    assert game.player_color is Color.BLACK
    assert game.player_color_source == "detected"
    assert game.warnings == []


def test_pgn_defaults_to_white_and_says_so():
    game = parse_pgn(ITALIAN)
    assert game.player_color is Color.WHITE
    assert game.player_color_source == "default"
    assert game.warnings and "无法自动判断" in game.warnings[0]


def test_illegal_move_is_rejected():
    broken = "[White \"A\"]\n[Black \"B\"]\n\n1. e4 e5 2. Nf3 Nf3 *"
    with pytest.raises(PgnError) as excinfo:
        parse_pgn(broken)
    assert "error" in str(excinfo.value).lower() or "legal" in str(excinfo.value).lower()


def test_garbage_and_empty_input_are_rejected():
    with pytest.raises(PgnError):
        parse_pgn("")
    with pytest.raises(PgnError):
        parse_pgn("   \n  ")
    with pytest.raises(PgnError):
        parse_pgn("hello world, this is not pgn")


def test_game_without_moves_is_rejected():
    with pytest.raises(PgnError):
        parse_pgn('[White "A"]\n[Black "B"]\n\n*')


def test_multiple_games_are_counted():
    assert count_games(ITALIAN) == 1
    assert count_games(ITALIAN + "\n\n" + SCHOLARS) == 2
    assert count_games("") == 0


def test_bom_and_whitespace_are_tolerated():
    game = parse_pgn("\ufeff\n\n" + ITALIAN.strip() + "\n\n", player_color=Color.WHITE)
    assert len(game.moves) == 8


def test_custom_start_position_is_supported():
    pgn = '[SetUp "1"]\n[FEN "7k/8/8/8/8/8/8/K6R w - - 0 1"]\n\n1. Rb1 Kg7 *'
    game = parse_pgn(pgn, player_color=Color.WHITE)
    assert game.moves[0].san == "Rb1"
    assert game.initial_fen.startswith("7k")


# --------------------------------------------------------------------- openings


def test_opening_name_comes_from_the_header_when_present():
    pgn = '[Opening "My Custom Line"]\n[White "A"]\n[Black "B"]\n\n1. e4 *'
    assert parse_pgn(pgn).opening == "My Custom Line"


def test_opening_falls_back_to_the_lookup_table():
    assert identify_opening(["e4", "e5", "Nf3", "Nc6", "Bc4"]) == "意大利开局"
    assert identify_opening(["e4", "c5"]) == "西西里防御"
    assert identify_opening(["e4", "e5", "Nf3", "Nc6", "Bb5"]) == "西班牙开局"


def test_opening_lookup_prefers_the_longest_match():
    assert identify_opening(["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "b4"]) == "伊文斯弃兵"
    assert identify_opening(["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]) == "双马防御"


def test_unknown_opening_returns_none_rather_than_a_guess():
    assert identify_opening(["a3", "a6", "h3", "h6"]) is None
    assert identify_opening([]) is None
    assert table_size() > 20
