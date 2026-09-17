"""The structured evidence contract.

Everything downstream of the engine (concept detectors, decision-error taxonomy,
LLM prompt, UI) consumes these models. The LLM never sees a raw FEN asking for a
judgment: it sees this object, which contains only values Stockfish produced and
facts deterministic code verified.

Score-perspective rule, enforced structurally: every evaluation, WDL and
expected score stored here is from ``pov_color``'s point of view (the analyzed
player). The engine adapter is the only place allowed to flip a sign.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from models.enums import (
    Color,
    ConceptType,
    DecisionErrorType,
    GamePhase,
    Severity,
    concept_label_zh,
    decision_error_label_zh,
)


class WdlDistribution(BaseModel):
    """Win/draw/loss probabilities (0..1) from an explicit point of view."""

    win: float
    draw: float
    loss: float

    @field_validator("win", "draw", "loss")
    @classmethod
    def _clamp(cls, value: float) -> float:
        return min(1.0, max(0.0, value))

    @classmethod
    def from_permille(cls, win: int, draw: int, loss: int) -> "WdlDistribution":
        """Stockfish reports WDL in permille; normalize so the three sum to 1."""
        total = float(win + draw + loss)
        if total <= 0:
            return cls(win=0.0, draw=1.0, loss=0.0)
        return cls(win=win / total, draw=draw / total, loss=loss / total)

    @classmethod
    def from_expected_score(cls, expected_score: float) -> "WdlDistribution":
        """Fallback when an engine line carries no WDL: assume no draws.

        Used only for engines/positions where WDL is unavailable; the analysis
        pipeline records a warning when this happens so the UI can say the
        severity is estimated from centipawns.
        """
        es = min(1.0, max(0.0, expected_score))
        return cls(win=es, draw=0.0, loss=1.0 - es)

    def expected_score(self) -> float:
        """P(win) + 0.5 * P(draw): the primary severity metric's input."""
        return self.win + 0.5 * self.draw

    def reversed(self) -> "WdlDistribution":
        return WdlDistribution(win=self.loss, draw=self.draw, loss=self.win)

    def as_dict(self) -> Dict[str, float]:
        return {"win": round(self.win, 4), "draw": round(self.draw, 4), "loss": round(self.loss, 4)}


class CandidateMove(BaseModel):
    """One engine line for one position, normalized to the player's point of view."""

    uci: str
    san: str
    cp: Optional[int] = None
    mate: Optional[int] = None
    wdl: WdlDistribution
    expected_score: float
    pv_uci: List[str] = Field(default_factory=list)
    pv_san: List[str] = Field(default_factory=list)

    @property
    def is_mate(self) -> bool:
        return self.mate is not None

    def reversed(self) -> "CandidateMove":
        """The same line seen from the other player's point of view.

        Needed because every position is searched once (with the analyzed player as the
        point of view) but severity is also reported for the opponent's moves.
        """
        return CandidateMove(
            uci=self.uci,
            san=self.san,
            cp=None if self.cp is None else -self.cp,
            mate=None if self.mate is None else -self.mate,
            wdl=self.wdl.reversed(),
            expected_score=round(1.0 - self.expected_score, 6),
            pv_uci=list(self.pv_uci),
            pv_san=list(self.pv_san),
        )


class PositionEval(BaseModel):
    """Normalized result of one engine search on one position.

    ``candidates`` is ordered best-first. Pass 1 stores a single candidate
    (MultiPV=1); pass 2 stores up to ``pass2_multipv`` of them.
    """

    fen: str
    pov_color: Color
    depth: int
    multipv: int
    engine_name: str
    nodes: Optional[int] = None
    time_s: Optional[float] = None
    candidates: List[CandidateMove] = Field(default_factory=list)
    complete: bool = True
    warnings: List[str] = Field(default_factory=list)

    @property
    def best(self) -> Optional[CandidateMove]:
        return self.candidates[0] if self.candidates else None


class EngineEvidence(BaseModel):
    """Everything Stockfish said about one played move.

    Units: ``evaluation_*`` are pawns (positive = good for the analyzed player);
    ``mate_*`` are signed moves-to-mate from the player's point of view
    (negative = the player is getting mated).
    """

    pov_color: Color

    evaluation_before: Optional[float] = None
    evaluation_after: Optional[float] = None
    mate_before: Optional[int] = None
    mate_after: Optional[int] = None

    wdl_before: WdlDistribution
    wdl_after: WdlDistribution
    expected_score_before: float
    expected_score_after: float
    expected_score_loss: float
    centipawn_loss: Optional[int] = None

    best_move_uci: Optional[str] = None
    best_move_san: Optional[str] = None
    best_line_uci: List[str] = Field(default_factory=list)
    best_line_san: List[str] = Field(default_factory=list)
    played_line_uci: List[str] = Field(default_factory=list)
    played_line_san: List[str] = Field(default_factory=list)

    depth_before: int = 0
    depth_after: int = 0
    nodes_before: Optional[int] = None
    nodes_after: Optional[int] = None
    multipv_before: int = 1
    multipv_after: int = 1

    # Pass-2 alternatives for the position the player was facing.
    alternatives: List[CandidateMove] = Field(default_factory=list)
    # True when the played move equals the engine's first choice.
    is_engine_best: bool = False
    # True when the top move is meaningfully better than the runner-up.
    best_move_unique: bool = False
    # Set when the engine's WDL came from a centipawn fallback, not from Stockfish.
    wdl_estimated: bool = False

class DetectedConcept(BaseModel):
    """A concept a deterministic detector verified on the board or in the engine line.

    ``evidence`` holds short machine-checkable statements (English) so a human can
    audit *why* the concept fired. Detectors must not emit a concept they cannot
    back with such a statement.
    """

    type: ConceptType
    confidence: float = Field(ge=0.0, le=1.0)
    pieces: List[str] = Field(default_factory=list)
    squares: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)

    @property
    def label_zh(self) -> str:
        return concept_label_zh(self.type)


class DecisionError(BaseModel):
    """The human decision failure inferred from verified concepts + evidence."""

    type: DecisionErrorType
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    supporting_concepts: List[ConceptType] = Field(default_factory=list)

    @property
    def label_zh(self) -> str:
        return decision_error_label_zh(self.type)


class PositionContext(BaseModel):
    fen: str
    ply: int
    move_number: int
    player_color: Color
    phase: GamePhase


class PlayedMove(BaseModel):
    uci: str
    san: str


class BoardContext(BaseModel):
    """Deterministic board facts (no chess judgment) attached to every analysis."""

    material_balance: float = 0.0
    total_non_pawn_material: int = 0
    player_king_square: Optional[str] = None
    player_has_castled: bool = False
    player_undeveloped_minors: int = 0
    player_legal_moves: int = 0
    opponent_legal_moves: int = 0
    player_isolated_pawns: List[str] = Field(default_factory=list)
    player_doubled_pawns: List[str] = Field(default_factory=list)
    player_passed_pawns: List[str] = Field(default_factory=list)
    opponent_passed_pawns: List[str] = Field(default_factory=list)
    player_undefended_pieces: List[str] = Field(default_factory=list)
    player_attacked_pieces: List[str] = Field(default_factory=list)


class AnalysisEvidence(BaseModel):
    """The complete, verified evidence object for one played move."""

    position: PositionContext
    played_move: PlayedMove
    engine: EngineEvidence
    concepts: List[DetectedConcept] = Field(default_factory=list)
    decision_errors: List[DecisionError] = Field(default_factory=list)
    severity: Severity = Severity.GOOD
    board_context: BoardContext = Field(default_factory=BoardContext)
    move_history_san: List[str] = Field(default_factory=list)

    def to_llm_payload(self) -> Dict[str, object]:
        """The exact JSON handed to the LLM: verified facts only, no board to judge."""
        engine = self.engine
        return {
            "position": {
                "fen": self.position.fen,
                "move_number": self.position.move_number,
                "player_color": self.position.player_color.value,
                "phase": self.position.phase.value,
            },
            "played_move": {"san": self.played_move.san, "uci": self.played_move.uci},
            "engine": {
                "units": "pawns; all values are from the player's point of view unless stated",
                "evaluation_before": _round(engine.evaluation_before),
                "evaluation_after": _round(engine.evaluation_after),
                "mate_before": engine.mate_before,
                "mate_after": engine.mate_after,
                "wdl_before": engine.wdl_before.as_dict(),
                "wdl_after": engine.wdl_after.as_dict(),
                "expected_score_before": round(engine.expected_score_before, 4),
                "expected_score_after": round(engine.expected_score_after, 4),
                "expected_score_loss": round(engine.expected_score_loss, 4),
                "centipawn_loss": engine.centipawn_loss,
                "best_move": engine.best_move_san,
                "best_line": engine.best_line_san,
                "played_line": engine.played_line_san,
                "is_engine_best": engine.is_engine_best,
                "best_move_unique": engine.best_move_unique,
                "depth_before": engine.depth_before,
                "depth_after": engine.depth_after,
                "wdl_estimated_from_centipawns": engine.wdl_estimated,
                "alternatives": [
                    {
                        "san": cand.san,
                        "evaluation": _round(cand.cp / 100.0) if cand.cp is not None else None,
                        "mate": cand.mate,
                        "expected_score": round(cand.expected_score, 4),
                        "line": cand.pv_san[:6],
                    }
                    for cand in engine.alternatives
                ],
            },
            "concepts": [
                {
                    "type": concept.type.value,
                    "confidence": round(concept.confidence, 2),
                    "pieces": concept.pieces,
                    "squares": concept.squares,
                    "evidence": concept.evidence,
                }
                for concept in self.concepts
            ],
            "decision_errors": [
                {
                    "type": error.type.value,
                    "confidence": round(error.confidence, 2),
                    "rationale": error.rationale,
                }
                for error in self.decision_errors
            ],
            "severity": self.severity.value,
            "board_context": self.board_context.model_dump(),
            "move_history_san": self.move_history_san[-16:],
        }


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 2)
