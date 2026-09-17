"""Piece-activity concepts: mobility loss and files the pieces end up on."""

import chess
from typing import List

from analysis.board import pseudo_safe_destinations, square_name
from concepts.base import DetectionContext, DetectedConcept, make_concept, piece_code
from models.enums import ConceptType

#: Below this many safe squares a piece is effectively out of play.
PASSIVE_PIECE_SAFE_SQUARES = 2


class PieceActivityDetector:
    """The played move left its own piece with (almost) nowhere to go."""

    name = "piece_activity"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        from_square = ctx.played_move.from_square
        to_square = ctx.played_move.to_square
        moved_before = ctx.board_before.piece_at(from_square)
        moved_after = ctx.board_after.piece_at(to_square)
        if moved_before is None or moved_after is None:
            return []
        if moved_before.piece_type == chess.PAWN:
            return []

        before = len(pseudo_safe_destinations(ctx.board_before, from_square))
        after = len(pseudo_safe_destinations(ctx.board_after, to_square))
        if after > PASSIVE_PIECE_SAFE_SQUARES or after >= before:
            return []

        return [
            make_concept(
                ConceptType.PIECE_ACTIVITY,
                0.45,
                pieces=[piece_code(ctx.board_after, to_square)],
                squares=[square_name(to_square)],
                evidence=[
                    "{} moves to a square with {} safe continuation(s), down from {}.".format(
                        piece_code(ctx.board_after, to_square), after, before
                    ),
                    "This only becomes relevant together with an evaluation drop.",
                ],
                metadata={"safe_squares_before": str(before), "safe_squares_after": str(after)},
            )
        ]


class OpenFileDetector:
    """A rook or queen was placed on an open or semi-open file."""

    name = "open_file"

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:
        mover = ctx.board_before.piece_at(ctx.played_move.from_square)
        target = ctx.board_after.piece_at(ctx.played_move.to_square)
        if mover is None or target is None:
            return []
        if mover.piece_type not in (chess.ROOK, chess.QUEEN):
            return []

        file_index = chess.square_file(ctx.played_move.to_square)
        own_pawns = [
            sq
            for sq in ctx.board_after.pieces(chess.PAWN, ctx.pov)
            if chess.square_file(sq) == file_index
        ]
        enemy_pawns = [
            sq
            for sq in ctx.board_after.pieces(chess.PAWN, ctx.opponent)
            if chess.square_file(sq) == file_index
        ]
        if own_pawns or enemy_pawns:
            if own_pawns:
                return []
            return [
                make_concept(
                    ConceptType.SEMI_OPEN_FILE,
                    0.55,
                    pieces=[piece_code(ctx.board_after, ctx.played_move.to_square)],
                    squares=[square_name(ctx.played_move.to_square)],
                    evidence=[
                        "{} moves to the semi-open {} file (no player pawns on it).".format(
                            piece_code(ctx.board_after, ctx.played_move.to_square),
                            chess.FILE_NAMES[file_index],
                        )
                    ],
                )
            ]
        return [
            make_concept(
                ConceptType.OPEN_FILE,
                0.6,
                pieces=[piece_code(ctx.board_after, ctx.played_move.to_square)],
                squares=[square_name(ctx.played_move.to_square)],
                evidence=[
                    "{} moves to the fully open {} file.".format(
                        piece_code(ctx.board_after, ctx.played_move.to_square),
                        chess.FILE_NAMES[file_index],
                    )
                ],
            )
        ]


DETECTORS = [PieceActivityDetector(), OpenFileDetector()]

__all__ = ["PieceActivityDetector", "OpenFileDetector", "DETECTORS"]
