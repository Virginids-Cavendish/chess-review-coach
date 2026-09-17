"""Score normalization and expected-score mathematics.

These are the numbers the whole product's severity judgment rests on, so they are
tested directly, including the perspective rules that are easy to get backwards.
"""

import chess
import pytest

from engine.scores import (
    MATE_DISPLAY_PAWNS,
    centipawn_loss,
    cp_and_mate,
    display_pawns,
    expected_score_from_cp,
    expected_score_loss,
    is_sign_flip,
    wdl_from_info,
)
from models.enums import Color
from models.evidence import WdlDistribution


def test_wdl_expected_score_is_win_plus_half_draw():
    distribution = WdlDistribution(win=0.41, draw=0.51, loss=0.08)
    assert distribution.expected_score() == pytest.approx(0.665)


def test_wdl_from_permille_normalizes_to_one():
    distribution = WdlDistribution.from_permille(412, 512, 76)
    assert distribution.win == pytest.approx(0.412)
    assert distribution.draw == pytest.approx(0.512)
    assert distribution.loss == pytest.approx(0.076)
    assert distribution.win + distribution.draw + distribution.loss == pytest.approx(1.0)


def test_wdl_from_permille_handles_rounding_drift():
    distribution = WdlDistribution.from_permille(333, 333, 333)
    assert distribution.win + distribution.draw + distribution.loss == pytest.approx(1.0)


def test_reversed_wdl_swaps_win_and_loss():
    distribution = WdlDistribution(win=0.41, draw=0.51, loss=0.08)
    flipped = distribution.reversed()
    assert flipped.win == pytest.approx(0.08)
    assert flipped.loss == pytest.approx(0.41)
    assert flipped.draw == pytest.approx(0.51)


def test_cp_and_mate_uses_the_requested_point_of_view():
    score = chess.engine.PovScore(chess.engine.Cp(120), chess.WHITE)
    assert cp_and_mate(score, Color.WHITE) == (120, None)
    # From Black's point of view the same evaluation is negative.
    assert cp_and_mate(score, Color.BLACK) == (-120, None)


def test_mate_scores_are_reported_as_distance_with_sign():
    white_mates = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    assert cp_and_mate(white_mates, Color.WHITE) == (None, 3)
    assert cp_and_mate(white_mates, Color.BLACK) == (None, -3)

    black_mates = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)
    assert cp_and_mate(black_mates, Color.WHITE) == (None, -2)
    assert cp_and_mate(black_mates, Color.BLACK) == (None, 2)


def test_display_pawns_marks_mate_with_a_signed_sentinel():
    assert display_pawns(35, None) == pytest.approx(0.35)
    assert display_pawns(None, 4) == pytest.approx(MATE_DISPLAY_PAWNS)
    assert display_pawns(None, -4) == pytest.approx(-MATE_DISPLAY_PAWNS)
    assert display_pawns(None, None) is None


def test_expected_score_from_cp_is_symmetric():
    assert expected_score_from_cp(0, None) == pytest.approx(0.5)
    assert expected_score_from_cp(100, None) + expected_score_from_cp(-100, None) == pytest.approx(1.0)
    assert expected_score_from_cp(None, 1) == 1.0
    assert expected_score_from_cp(None, -1) == 0.0
    assert expected_score_from_cp(100, None) > 0.5


def test_expected_score_loss_is_zero_when_nothing_was_given_away():
    before = WdlDistribution(win=0.4, draw=0.4, loss=0.2)
    after = WdlDistribution(win=0.5, draw=0.3, loss=0.2)
    # The played move turned out better than the engine's line at this depth.
    assert expected_score_loss(before, after) == 0.0


def test_expected_score_loss_matches_the_specification_example():
    before = WdlDistribution(win=0.41, draw=0.51, loss=0.08)
    after = WdlDistribution(win=0.085, draw=0.18, loss=0.735)
    # Spec example: 0.665 -> 0.175
    assert expected_score_loss(before, after) == pytest.approx(0.49, abs=0.001)


def test_centipawn_loss_ignores_mate_scores():
    assert centipawn_loss(50, -20) == 70
    assert centipawn_loss(50, 120) == 0
    assert centipawn_loss(None, 20) is None


def test_sign_flip_detects_the_winning_side_changing():
    assert is_sign_flip(0.62, 0.31)
    assert not is_sign_flip(0.62, 0.58)
    assert not is_sign_flip(0.30, 0.20)


def test_wdl_from_info_uses_engine_wdl_when_present():
    info = {
        "wdl": chess.engine.PovWdl(chess.engine.Wdl(500, 300, 200), chess.WHITE),
        "score": chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE),
    }
    distribution, estimated = wdl_from_info(info, Color.WHITE)
    assert estimated is False
    assert distribution.win == pytest.approx(0.5)
    assert distribution.draw == pytest.approx(0.3)
    assert distribution.loss == pytest.approx(0.2)


def test_wdl_from_info_falls_back_to_centipawns_and_says_so():
    info = {"score": chess.engine.PovScore(chess.engine.Cp(400), chess.WHITE)}
    distribution, estimated = wdl_from_info(info, Color.WHITE)
    assert estimated is True
    assert distribution.expected_score() > 0.8

    mirrored, _ = wdl_from_info(info, Color.BLACK)
    assert mirrored.expected_score() < 0.2


def test_wdl_from_info_without_any_score_is_neutral():
    distribution, estimated = wdl_from_info({}, Color.WHITE)
    assert estimated is True
    assert distribution.expected_score() == pytest.approx(0.5)
