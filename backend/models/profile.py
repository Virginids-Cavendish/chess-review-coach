"""Long-term player-profile models.

Sample-size honesty is encoded in the data model: every recurring weakness carries a
confidence band and a ready-made Chinese sentence, so the UI cannot accidentally
claim "your stable weakness is X" after two games.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.enums import ConceptType, DecisionErrorType, GamePhase, Severity


class ExampleMoment(BaseModel):
    """A stored position the profile can show (and a future trainer can reuse)."""

    game_id: str
    ply: int
    move_number: int
    san: str
    opponent: str = ""
    severity: Severity
    one_liner_zh: str = ""
    fen: str = ""
    solution_san: Optional[str] = None


class RecurringWeakness(BaseModel):
    error_type: DecisionErrorType
    label_zh: str
    event_count: int
    share: float
    games: int
    average_expected_score_loss: float
    severity_mix: Dict[str, int] = Field(default_factory=dict)
    # "insufficient" | "low" | "medium" — never claim more than the data supports.
    confidence: str = "insufficient"
    statement_zh: str = ""
    examples: List[ExampleMoment] = Field(default_factory=list)


class PhaseBreakdown(BaseModel):
    phase: GamePhase
    label_zh: str
    events: int
    share: float
    average_expected_score_loss: float


class ConceptFrequency(BaseModel):
    concept: ConceptType
    label_zh: str
    count: int
    share: float


class TrendPoint(BaseModel):
    game_id: str
    created_at: Optional[datetime] = None
    average_expected_score_loss: float = 0.0
    problems: int = 0
    blunders: int = 0
    label: str = ""


class TrendSummary(BaseModel):
    """Only computed when there are enough games to say anything at all."""

    available: bool = False
    statement_zh: str = ""
    direction: str = "flat"  # "improving" | "worsening" | "flat"
    recent_average_loss: Optional[float] = None
    earlier_average_loss: Optional[float] = None


class ProfileSummary(BaseModel):
    total_games: int = 0
    total_player_moves: int = 0
    total_problems: int = 0
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0
    average_expected_score_loss: float = 0.0
    weaknesses: List[RecurringWeakness] = Field(default_factory=list)
    phases: List[PhaseBreakdown] = Field(default_factory=list)
    top_concepts: List[ConceptFrequency] = Field(default_factory=list)
    trend: TrendSummary = Field(default_factory=TrendSummary)
    trend_points: List[TrendPoint] = Field(default_factory=list)
    sample_size_note_zh: str = ""
    generated_at: Optional[datetime] = None
