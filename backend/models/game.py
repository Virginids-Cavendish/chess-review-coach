"""PGN-derived game models."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.enums import Color


class ParsedMove(BaseModel):
    """One half-move straight from the PGN, with the FENs needed to render it."""

    ply: int  # 1-based: ply 1 is White's first move
    move_number: int
    color: Color
    san: str
    uci: str
    fen_before: str
    fen_after: str


class ParsedGame(BaseModel):
    headers: Dict[str, str] = Field(default_factory=dict)
    moves: List[ParsedMove] = Field(default_factory=list)
    player_color: Color = Color.WHITE
    #: "explicit" (user chose), "detected" (matched a known player name), or
    #: "default" (nobody knew — the UI must ask the user to confirm).
    player_color_source: str = "explicit"
    white: str = "White"
    black: str = "Black"
    result: str = "*"
    initial_fen: str = ""
    opening: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    @property
    def full_moves(self) -> int:
        return (len(self.moves) + 1) // 2

    def player_moves(self) -> List[ParsedMove]:
        return [move for move in self.moves if move.color is self.player_color]
