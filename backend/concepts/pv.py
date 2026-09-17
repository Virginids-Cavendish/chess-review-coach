"""Engine-line parsing helpers.

Several detectors need to check *what actually happens* after a move, not just what
the board looks like right now. The engine's principal variation is the only source
of that information available to deterministic code, so it is parsed once here into
a walkable list of positions.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

import chess


@dataclass
class LineMove:
    """One ply of an engine line, with the position before and after it."""

    move: chess.Move
    san: str
    board_before: chess.Board
    board_after: chess.Board
    mover: bool  # python-chess colour bool of the side that played it
    index: int  # 0-based index inside the line

    @property
    def is_capture(self) -> bool:
        return self.board_before.is_capture(self.move)

    @property
    def is_check(self) -> bool:
        return self.board_after.is_check()

    @property
    def is_mate(self) -> bool:
        return self.board_after.is_checkmate()

    def captured_piece(self) -> Optional[chess.Piece]:
        """The piece removed by this move (handles en passant)."""
        if not self.is_capture:
            return None
        if self.board_before.is_en_passant(self.move):
            victim_square = self.move.to_square + (-8 if self.mover == chess.WHITE else 8)
            return self.board_before.piece_at(victim_square)
        return self.board_before.piece_at(self.move.to_square)


def parse_line(
    board: chess.Board, uci_moves: Sequence[str], san_moves: Optional[Sequence[str]] = None
) -> List[LineMove]:
    """Walk an engine PV, stopping at the first move that is not legal in context.

    A truncated line is normal (the PV is capped) and never an error: callers treat a
    shorter line as "no further evidence available".
    """
    current = board.copy(stack=False)
    result: List[LineMove] = []
    for index, uci in enumerate(uci_moves):
        move = _find_move(current, uci)
        if move is None:
            break
        before = current.copy(stack=False)
        mover = current.turn
        try:
            san = san_moves[index] if san_moves and index < len(san_moves) else current.san(move)
        except (ValueError, AssertionError):  # pragma: no cover
            san = uci
        current.push(move)
        result.append(
            LineMove(
                move=move,
                san=san,
                board_before=before,
                board_after=current.copy(stack=False),
                mover=bool(mover),
                index=index,
            )
        )
    return result


def _find_move(board: chess.Board, uci: str) -> Optional[chess.Move]:
    for move in board.legal_moves:
        if move.uci() == uci:
            return move
    return None
