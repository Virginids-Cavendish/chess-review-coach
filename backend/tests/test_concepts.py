"""Concept detectors against known FEN test cases.

Two kinds of assertion matter here:

* **positive** — a detector fires on a position where the concept demonstrably exists,
* **negative** — detectors stay silent on positions where the concept does *not* exist.

The negative cases are the important ones: a detector that reports a motif the board
does not contain is worse than a detector that stays quiet.
"""

import chess
import pytest

from concepts.activity import OpenFileDetector, PieceActivityDetector
from concepts.hanging import AttackedPieceDetector, HangingPieceDetector
from concepts.material import MaterialLossDetector, MissedCaptureDetector
from concepts.registry import detect_concepts
from concepts.threats import BackRankWeaknessDetector, TrappedPieceDetector
from concepts.zwischenzug import IntermediateMoveDetector
from models.enums import Color, GamePhase, Severity
from tests.conftest import concept_types, detect, make_context

START_FEN = chess.STARTING_FEN


# --------------------------------------------------------------- hanging pieces


def test_hanging_piece_fires_when_a_rook_moves_into_a_queens_attack():
    # 1.Rh5?? puts the rook on the 5th rank in front of the black queen; nothing
    # defends h5, so the queen simply takes it.
    ctx = make_context("7k/8/8/q7/8/8/8/1K5R w - - 0 1", "h1h5")
    concepts = HangingPieceDetector().detect(ctx)
    types = concept_types(concepts)
    assert "hanging_piece" in types
    assert "undefended_piece" in types

    hanging = next(c for c in concepts if c.type.value == "hanging_piece")
    assert hanging.squares == ["h5"]
    assert hanging.metadata["see_gain"] == "5"
    assert hanging.confidence >= 0.6


def test_hanging_piece_does_not_fire_for_a_defended_piece():
    # The g4 pawn defends h5, so ...Qxh5 just loses the queen for a rook.
    ctx = make_context("7k/8/8/q7/6P1/8/8/1K5R w - - 0 1", "h1h5")
    assert "hanging_piece" not in detect(ctx)


def test_hanging_piece_does_not_fire_when_the_piece_was_already_loose():
    # The rook on h1 is already attacked by the rook on h8 (nothing defends h1). Moving
    # it to h5 keeps it loose, but the move did not create the problem.
    ctx = make_context("k6r/8/8/8/8/8/8/1K5R w - - 0 1", "h1h5")
    assert "hanging_piece" not in detect(ctx)


def test_hanging_piece_confirmed_by_the_engine_line_gets_high_confidence():
    ctx = make_context(
        "7k/8/8/q7/8/8/8/1K5R w - - 0 1",
        "h1h5",
        played_line_uci=["h1h5", "a5h5"],
        expected_before=0.6,
        expected_after=0.1,
    )
    hanging = next(
        c for c in HangingPieceDetector().detect(ctx) if c.type.value == "hanging_piece"
    )
    assert hanging.metadata["captured_in_engine_line"] == "true"
    assert hanging.confidence >= 0.9


# ---------------------------------------------------------- removal of defender


def test_removal_of_defender_fires_when_the_sole_defender_moves_away():
    # The bishop on b5 is the only defender of the rook on e2. Moving it to a4 leaves
    # the rook attacked and undefended.
    ctx = make_context("4r2k/8/8/1B6/8/8/4R3/6K1 w - - 0 1", "b5a4")
    concepts = detect_concepts(ctx)
    types = concept_types(concepts)
    assert "removal_of_defender" in types

    concept = next(c for c in concepts if c.type.value == "removal_of_defender")
    assert concept.metadata["vacated_square"] == "b5"
    assert "e2" in concept.squares
    assert concept.confidence >= 0.6


def test_removal_of_defender_not_reported_when_the_piece_moved_but_still_defends():
    # The bishop stays on the b5-e2 diagonal after moving to c4, so nothing is lost.
    ctx = make_context("4r2k/8/8/1B6/8/8/2B1R3/6K1 w - - 0 1", "b5c4")
    assert "removal_of_defender" not in detect(ctx)


def test_removal_of_defender_skipped_when_the_piece_was_already_lost():
    # The pawn on f3 already wins the rook on e2 (the bishop cannot save it), so moving
    # the bishop away is not what created the problem.
    ctx = make_context("7k/8/8/1B6/8/5p2/4R3/6K1 w - - 0 1", "b5a4")
    assert "removal_of_defender" not in detect(ctx)


# ------------------------------------------------------------------ forks


def test_fork_fires_for_the_engines_available_knight_fork():
    # Nd5 would attack the rook on c7 and the queen on f6 at the same time.
    ctx = make_context(
        "4k3/2r5/5q2/8/8/4N3/8/4K3 w - - 0 1",
        "e1d1",
        best_uci="e3d5",
        best_line_uci=["e3d5"],
    )
    concepts = detect_concepts(ctx)
    types = concept_types(concepts)
    assert "fork" in types
    concept = next(c for c in concepts if c.type.value == "fork")
    assert set(concept.squares) >= {"d5", "c7", "f6"}
    assert concept.metadata["side"] == "player"


def test_fork_does_not_fire_for_a_single_attacked_piece():
    # Nd5 attacks only the rook on c7; one target is not a fork.
    ctx = make_context(
        "4k3/2r5/8/8/8/4N3/8/4K3 w - - 0 1",
        "e1d1",
        best_uci="e3d5",
        best_line_uci=["e3d5"],
    )
    assert "fork" not in detect(ctx)


def test_fork_does_not_fire_on_undefended_pawns():
    # Attacking two pawns is not a fork worth reporting.
    ctx = make_context(
        "4k3/2p5/5p2/8/8/4N3/8/4K3 w - - 0 1",
        "e1d1",
        best_uci="e3d5",
        best_line_uci=["e3d5"],
    )
    assert "fork" not in detect(ctx)


# --------------------------------------------------------------- pins / skewers


def test_pin_fires_when_the_move_creates_a_pin():
    ctx = make_context("3q3k/8/5n2/8/8/8/8/2B4K w - - 0 1", "c1g5")
    concepts = detect_concepts(ctx)
    assert "pin" in concept_types(concepts)
    concept = next(c for c in concepts if c.type.value == "pin")
    assert concept.metadata["side"] == "player"


def test_pin_not_reported_when_it_already_existed():
    # Bg5 is already played; moving the bishop elsewhere must not "create" the pin.
    ctx = make_context("3q3k/8/5n2/6B1/8/8/8/7K w - - 0 1", "g5h4")
    assert "pin" not in detect(ctx)


def test_skewer_fires_when_the_move_attacks_a_king_with_a_rook_behind():
    ctx = make_context("7r/8/8/4k3/8/8/8/K1B5 w - - 0 1", "c1b2")
    concepts = detect_concepts(ctx)
    assert "skewer" in concept_types(concepts)
    concept = next(c for c in concepts if c.type.value == "skewer")
    assert set(concept.squares) == {"e5", "h8"}


def test_skewer_does_not_fire_for_a_plain_check():
    # Bb2 is a check but there is nothing behind the king on the ray.
    ctx = make_context("7k/8/8/4q3/8/8/8/K1B5 w - - 0 1", "c1b2")
    assert "skewer" not in detect(ctx)


# ----------------------------------------------------------------- back rank


def test_back_rank_weakness_fires_when_the_engine_line_mates_on_the_back_rank():
    ctx = make_context(
        "6k1/p4ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1",
        "a7a5",
        pov=Color.BLACK,
        played_line_uci=["a7a5", "d1d8"],
        expected_before=0.5,
        expected_after=0.0,
    )
    concepts = BackRankWeaknessDetector().detect(ctx)
    assert concept_types(concepts) == {"back_rank_weakness"}
    assert concepts[0].confidence >= 0.9


def test_back_rank_weakness_absent_when_there_is_luft():
    # The h-pawn has moved, so the king has an escape square and no back-rank mate.
    ctx = make_context(
        "6k1/p4pp1/7p/8/8/8/5PPP/3R2K1 b - - 0 1",
        "a7a5",
        pov=Color.BLACK,
        played_line_uci=["a7a5", "d1d8"],
        expected_before=0.5,
        expected_after=0.5,
    )
    assert BackRankWeaknessDetector().detect(ctx) == []


# -------------------------------------------------------------- material loss


def test_material_loss_compares_the_played_line_with_the_engine_line():
    # Rh5 walks into ...Qxh5; the engine's Rh2 keeps the rook.
    ctx = make_context(
        "7k/8/8/q7/8/8/8/1K5R w - - 0 0",
        "h1h5",
        best_uci="h1h2",
        best_line_uci=["h1h2"],
        played_line_uci=["h1h5", "a5h5"],
        expected_before=0.6,
        expected_after=0.05,
    )
    concepts = MaterialLossDetector().detect(ctx)
    assert concept_types(concepts) == {"material_loss"}
    assert concepts[0].metadata["material_drop"] == "5"
    # The engine's line keeps the rook (-4 = the starting queen deficit); the played
    # move drops it to -9.
    assert concepts[0].metadata["balance_if_engine_move"] == "-4"
    assert concepts[0].metadata["balance_after_played"] == "-9"


def test_material_loss_absent_when_both_lines_end_level():
    ctx = make_context(
        "7k/8/8/8/8/8/8/1K5R w - - 0 1",
        "h1h2",
        best_uci="h1h3",
        best_line_uci=["h1h3"],
        played_line_uci=["h1h2"],
        expected_before=0.5,
        expected_after=0.48,
    )
    assert MaterialLossDetector().detect(ctx) == []


def test_missed_capture_fires_when_a_free_piece_is_left_hanging():
    # Bxd5 wins the queen outright; the player moved the king instead.
    ctx = make_context(
        "7k/8/8/3q4/2B5/8/8/K7 w - - 0 1",
        "a1b1",
        best_uci="c4d5",
        best_line_uci=["c4d5"],
        expected_before=0.9,
        expected_after=0.1,
    )
    concepts = MissedCaptureDetector().detect(ctx)
    assert concept_types(concepts) == {"missed_capture"}
    assert concepts[0].metadata["available_capture"] == "Bxd5"
    assert concepts[0].metadata["engine_preferred_it"] == "true"


def test_missed_capture_absent_when_the_player_took_the_piece():
    ctx = make_context(
        "7k/8/8/3q4/2B5/8/8/K7 w - - 0 1",
        "c4d5",
        best_uci="c4d5",
        expected_before=0.9,
        expected_after=0.9,
    )
    assert MissedCaptureDetector().detect(ctx) == []


# ------------------------------------------------------------- zwischenzug


def test_intermediate_move_fires_when_the_opponent_checks_instead_of_recapturing():
    # Rxd5 looks like a clean win, but Black has ...Re1+ first: an in-between check
    # before dealing with the recapture.
    ctx = make_context(
        "4r1k1/8/2p5/3n4/8/8/5PP1/3R2K1 w - - 0 1",
        "d1d5",
        played_line_uci=["d1d5", "e8e1"],
        expected_before=0.6,
        expected_after=0.2,
    )
    concepts = IntermediateMoveDetector().detect(ctx)
    assert concept_types(concepts) == {"intermediate_move"}
    assert concepts[0].metadata["intermediate_move"] == "Re1+"


def test_intermediate_move_absent_on_a_plain_recapture():
    ctx = make_context(
        "4r1k1/8/2p5/3n4/8/8/5PP1/3R2K1 w - - 0 1",
        "d1d5",
        played_line_uci=["d1d5", "c6d5"],
        expected_before=0.6,
        expected_after=0.4,
    )
    assert IntermediateMoveDetector().detect(ctx) == []


# ------------------------------------------------------------------- context


def test_trapped_piece_reports_the_players_piece_with_no_escape():
    # The white knight on a8 is attacked by the bishop on d5, and the black king covers
    # c7, so b6 is its only safe square.
    ctx = make_context(
        "N2k4/8/8/3b4/8/8/8/4K3 w - - 0 1",
        "e1d1",
        played_line_uci=["e1d1", "d5a8"],
        expected_before=0.1,
        expected_after=0.05,
    )
    concepts = TrappedPieceDetector().detect(ctx)
    assert "trapped_piece" in concept_types(concepts)
    concept = next(c for c in concepts if c.type.value == "trapped_piece")
    assert concept.squares[0] == "a8"


def test_trapped_piece_absent_when_the_piece_has_room():
    ctx = make_context(
        "N2k4/8/8/3b4/8/8/8/4K3 b - - 0 1",
        "d8e8",
        pov=Color.BLACK,
        expected_before=0.1,
        expected_after=0.1,
    )
    # The trapped knight belongs to the other side, so nothing is reported for Black.
    assert TrappedPieceDetector().detect(ctx) == []


def test_open_file_detector_reports_a_rook_on_an_open_file():
    ctx = make_context("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "a1d1")
    concepts = OpenFileDetector().detect(ctx)
    assert concept_types(concepts) == {"open_file"}


def test_piece_activity_ignores_pawn_moves():
    ctx = make_context("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", "e2e3")
    assert PieceActivityDetector().detect(ctx) == []


def test_piece_activity_stays_quiet_when_the_piece_keeps_its_options():
    ctx = make_context("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "a1d1")
    assert PieceActivityDetector().detect(ctx) == []


def test_attacked_piece_detector_skips_pieces_that_can_simply_be_taken():
    # Rxe2 wins a rook for nothing; that is a hanging piece, not merely "attacked".
    ctx = make_context("4r2k/8/8/8/8/8/4R3/6K1 w - - 0 1", "g1h1")
    types = concept_types(AttackedPieceDetector().detect(ctx))
    assert "attacked_piece" not in types


# ------------------------------------------------- the "no false motifs" test


def test_quiet_developing_move_produces_no_tactical_concepts():
    """The single most important negative test in the suite."""
    from models.enums import GamePhase

    ctx = make_context(START_FEN, "g1f3", phase=GamePhase.OPENING, move_number=1)
    types = detect(ctx)
    for concept in (
        "hanging_piece",
        "removal_of_defender",
        "fork",
        "pin",
        "skewer",
        "discovered_attack",
        "double_attack",
        "back_rank_weakness",
        "mating_threat",
        "material_loss",
        "deflection",
        "overloaded_defender",
        "intermediate_move",
        "trapped_piece",
        "exchange_sacrifice",
    ):
        assert concept not in types, "unexpected concept {} on a quiet move".format(concept)


def test_detectors_never_raise_and_return_serializable_concepts():
    from models.enums import GamePhase

    ctx = make_context(START_FEN, "e2e4", phase=GamePhase.OPENING, move_number=1)
    for concept in detect_concepts(ctx):
        payload = concept.model_dump()
        assert payload["confidence"] >= 0.0
        assert all(isinstance(line, str) for line in payload["evidence"])
