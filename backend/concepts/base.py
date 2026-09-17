"""Concept-detector framework.

A detector is a small, independent object that answers one question about a verified
position ("did this move leave a piece hanging?") and returns zero or more
:class:`DetectedConcept` values with the deterministic evidence for each.

Rules every detector must follow:

* never report a concept it cannot back with a checkable statement,
* prefer silence over a speculative motif (the UI says "no reliable tactical motif
  detected" rather than inventing one),
* express consequences in the player's terms, using the engine line as evidence when
  a claim needs a continuation to be true.

Adding a detector means writing one class and adding it to ``registry.py``.
"""

import chess
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple

from analysis.thresholds import THRESHOLDS, DetectionThresholds
from concepts.pv import LineMove, parse_line
from models.enums import Color, ConceptType, GamePhase, Severity
from models.evidence import DetectedConcept, EngineEvidence

#: SAN-like piece codes used in ``DetectedConcept.pieces`` (e.g. "Bf4"), which are
#: language-neutral so the UI can label them in any language.
PIECE_LETTERS = {
    chess.PAWN: "",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK: "R",
    chess.QUEEN: "Q",
    chess.KING: "K",
}


def piece_code(board: chess.Board, square: int) -> str:
    """e.g. ``"Bf4"``; empty string when the square is empty."""
    piece = board.piece_at(square)
    if piece is None:
        return ""
    return "{}{}".format(PIECE_LETTERS.get(piece.piece_type, "?"), chess.square_name(square))


@dataclass
class DetectionContext:
    """Everything a detector may look at. Built once per analyzed move."""

    board_before: chess.Board
    board_after: chess.Board
    played_move: chess.Move
    played_san: str
    player_color: Color
    evidence: EngineEvidence
    severity: Severity
    phase: GamePhase
    move_number: int = 1
    move_history: List[Tuple[Color, str]] = field(default_factory=list)
    thresholds: DetectionThresholds = THRESHOLDS.detection

    # Derived once in __post_init__ so detectors do not repeat the work.
    pov: bool = False
    opponent: bool = False
    best_move: Optional[chess.Move] = None
    played_line: List[LineMove] = field(default_factory=list)
    best_line: List[LineMove] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.pov = self.player_color is Color.WHITE
        self.opponent = not self.pov
        if self.evidence.best_move_uci:
            for move in self.board_before.legal_moves:
                if move.uci() == self.evidence.best_move_uci:
                    self.best_move = move
                    break
        # The played line starts with the move that was just played, so the parsed
        # continuation is applied to the position *after* it.
        self.played_line = parse_line(
            self.board_after, self.evidence.played_line_uci[1:], self.evidence.played_line_san[1:]
        )
        self.best_line = parse_line(
            self.board_before, self.evidence.best_line_uci, self.evidence.best_line_san
        )

    @property
    def is_problem(self) -> bool:
        return self.severity.is_problem

    def san(self, board: chess.Board, move: chess.Move) -> str:
        try:
            return board.san(move)
        except (ValueError, AssertionError):  # pragma: no cover - defensive
            return move.uci()


class ConceptDetector(Protocol):
    """Interface every detector implements."""

    #: Stable identifier, matching the detector's class name in logs.
    name: str

    def detect(self, ctx: DetectionContext) -> List[DetectedConcept]:  # pragma: no cover
        ...


def make_concept(
    concept_type: ConceptType,
    confidence: float,
    *,
    pieces: Optional[List[str]] = None,
    squares: Optional[List[str]] = None,
    evidence: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
) -> DetectedConcept:
    """Build a concept with clamped confidence and de-duplicated evidence lines."""
    seen = set()
    unique_evidence: List[str] = []
    for line in evidence or []:
        if line and line not in seen:
            seen.add(line)
            unique_evidence.append(line)
    return DetectedConcept(
        type=concept_type,
        confidence=max(0.0, min(1.0, round(confidence, 2))),
        pieces=pieces or [],
        squares=squares or [],
        evidence=unique_evidence,
        metadata={str(key): str(value) for key, value in (metadata or {}).items()},
    )
