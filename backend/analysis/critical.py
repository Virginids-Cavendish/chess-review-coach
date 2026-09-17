"""Critical-moment selection.

The review screen must not comment on every move. This module scores how much a
position *mattered* — expected-score loss dominates, but a missed forced mate, a sign
flip or a unique-only-move position get promoted because they teach more than their
numeric swing suggests.

Ranking is configurable in ``analysis/thresholds.py``; nothing here is a claim that
these weights are optimal.
"""

from dataclasses import dataclass, field
from typing import List, Sequence

from analysis.thresholds import THRESHOLDS, AnalysisThresholds
from engine.scores import is_sign_flip
from models.enums import Severity
from models.evidence import EngineEvidence
from models.review import CriticalityReason


@dataclass
class CriticalityAssessment:
    score: float = 0.0
    reasons: List[CriticalityReason] = field(default_factory=list)

    def add(self, reason: CriticalityReason, weight: float) -> None:
        if reason not in self.reasons:
            self.reasons.append(reason)
        self.score += weight


def assess_criticality(
    evidence: EngineEvidence,
    severity: Severity,
    thresholds: AnalysisThresholds = THRESHOLDS,
) -> CriticalityAssessment:
    """Score how much this move mattered, with the reasons that produced the score."""
    weights = thresholds.criticality
    assessment = CriticalityAssessment()

    if severity.is_problem:
        assessment.add(CriticalityReason.HIGH_LOSS, evidence.expected_score_loss * weights.expected_score_loss)

    before = evidence.expected_score_before
    after = evidence.expected_score_after

    if is_sign_flip(before, after):
        assessment.add(CriticalityReason.SIGN_FLIP, weights.sign_flip)

    if before >= thresholds.detection.winning_expected_score > after:
        assessment.add(CriticalityReason.MISSED_WIN, weights.missed_win)
    elif before >= thresholds.detection.winning_expected_score and after < before - 0.15:
        assessment.add(CriticalityReason.MISSED_WIN, weights.missed_win * 0.6)

    if evidence.mate_after is not None and evidence.mate_after < 0:
        if evidence.mate_before is None or evidence.mate_before >= 0:
            assessment.add(CriticalityReason.MATE_APPEARS, weights.mate_appears)
        else:
            assessment.add(CriticalityReason.MATE_APPEARS, weights.mate_appears * 0.5)
    if evidence.mate_before is not None and evidence.mate_before > 0:
        if evidence.mate_after is None or evidence.mate_after <= 0:
            assessment.add(CriticalityReason.MATE_DISAPPEARS, weights.mate_disappears)

    if before >= 0.5 and after <= thresholds.detection.losing_expected_score:
        assessment.add(CriticalityReason.POSITION_COLLAPSE, weights.position_collapse)

    if _enters_forced_sequence(evidence):
        assessment.add(CriticalityReason.FORCED_SEQUENCE, weights.forced_sequence)

    if evidence.best_move_unique and severity.is_problem:
        assessment.add(CriticalityReason.UNIQUE_BEST_MOVE, weights.best_move_uniqueness)

    return assessment


def _enters_forced_sequence(evidence: EngineEvidence, plies: int = 2) -> bool:
    """True when the engine's continuation starts with a capture or a check."""
    line = evidence.played_line_san[1 : 1 + plies]
    if not line:
        return False
    return any(token.endswith(("+", "#")) for token in line) or any(
        "x" in token for token in line
    )


def select_review_moments(
    candidates: Sequence[tuple],
    max_moments: int,
) -> List[tuple]:
    """Pick the positions worth reviewing from ``(key, assessment, severity)`` tuples.

    Only moves that are actually problems (inaccuracy or worse) qualify: padding the
    list with good moves so it always shows "4 positions" would misrepresent the game,
    so a clean game honestly reports fewer, or none.
    """
    problems = [
        (key, assessment, severity)
        for key, assessment, severity in candidates
        if severity.is_problem and assessment.score > 0
    ]
    problems.sort(key=lambda item: (-item[1].score, item[0]))
    return problems[:max_moments]
