"""The human decision-error taxonomy.

Separates two different claims that are easy to blur:

* **what happened on the board** — a bishop was lost (``DetectedConcept``),
* **what decision failure produced it** — a defender was moved without re-checking
  forcing moves (``DecisionError``).

Rules run most-specific-first and return at most a few categories, each with a
separate confidence. When nothing fires the result is explicitly ``UNKNOWN`` rather
than a confident guess, which is a deliberate product choice: a wrong diagnosis is
worse than "we could not tell from the evidence".
"""

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set

from analysis.thresholds import AnalysisThresholds, THRESHOLDS
from models.enums import ConceptType, DecisionErrorType, GamePhase, Severity
from models.evidence import BoardContext, DecisionError, DetectedConcept, EngineEvidence

logger = logging.getLogger(__name__)

#: How many decision errors to report for one move. More than two is noise.
MAX_ERRORS_PER_MOVE = 3

#: Concepts that count as a concrete tactical motif. Their presence suppresses the
#: vaguer categories (material judgment, calculation) so the report stays specific.
TACTICAL_CONCEPTS: Set[ConceptType] = {
    ConceptType.HANGING_PIECE,
    ConceptType.FORK,
    ConceptType.PIN,
    ConceptType.SKEWER,
    ConceptType.DISCOVERED_ATTACK,
    ConceptType.DOUBLE_ATTACK,
    ConceptType.REMOVAL_OF_DEFENDER,
    ConceptType.DEFLECTION,
    ConceptType.OVERLOADED_DEFENDER,
    ConceptType.BACK_RANK_WEAKNESS,
    ConceptType.MISSED_CAPTURE,
    ConceptType.TRAPPED_PIECE,
    ConceptType.INTERMEDIATE_MOVE,
    ConceptType.MATING_THREAT,
}

DEV_ERROR_FORCING_CONCEPTS = {
    ConceptType.MISSED_CHECK,
    ConceptType.MISSED_FORCING_MOVE,
}


@dataclass
class TaxonomyContext:
    """Everything a decision-error rule may look at (all verified upstream)."""

    evidence: EngineEvidence
    concepts: List[DetectedConcept]
    severity: Severity
    phase: GamePhase
    board_context: BoardContext
    played_san: str
    move_number: int
    thresholds: AnalysisThresholds = THRESHOLDS

    @property
    def types(self) -> Set[ConceptType]:
        return {concept.type for concept in self.concepts}

    def confidence_of(self, concept_type: ConceptType) -> float:
        for concept in self.concepts:
            if concept.type is concept_type:
                return concept.confidence
        return 0.0

    def supporting(self, *concept_types: ConceptType) -> List[ConceptType]:
        return [c for c in concept_types if c in self.types]


RuleFn = Callable[[TaxonomyContext], Optional[DecisionError]]


@dataclass
class Rule:
    name: str
    error_type: DecisionErrorType
    evaluate: RuleFn


def _error(
    error_type: DecisionErrorType,
    confidence: float,
    rationale: str,
    supporting: Sequence[ConceptType] = (),
) -> DecisionError:
    return DecisionError(
        type=error_type,
        confidence=max(0.05, min(0.95, round(confidence, 2))),
        rationale=rationale,
        supporting_concepts=list(supporting),
    )


# --------------------------------------------------------------------------- rules


def _advantage_conversion(ctx: TaxonomyContext):
    if not ctx.severity.is_problem:
        return None
    if ctx.evidence.expected_score_before < ctx.thresholds.detection.winning_expected_score:
        return None
    if ctx.evidence.expected_score_after > 0.60:
        return None
    return _error(
        DecisionErrorType.ADVANTAGE_CONVERSION,
        0.75,
        "The player was clearly winning (expected score {:.2f}) and the move drops it to "
        "{:.2f}.".format(ctx.evidence.expected_score_before, ctx.evidence.expected_score_after),
    )


def _defender_removed(ctx: TaxonomyContext):
    for concept_type in (
        ConceptType.REMOVAL_OF_DEFENDER,
        ConceptType.DEFLECTION,
    ):
        confidence = ctx.confidence_of(concept_type)
        if confidence:
            return _error(
                DecisionErrorType.DEFENDER_REMOVED,
                confidence * 0.95,
                "A defensive duty was given up: the evidence shows {}".format(
                    concept_type.value
                ),
                ctx.supporting(concept_type),
            )
    if ConceptType.OVERLOADED_DEFENDER in ctx.types and ConceptType.MATERIAL_LOSS in ctx.types:
        return _error(
            DecisionErrorType.DEFENDER_REMOVED,
            0.6,
            "One defender was responsible for two attacked pieces, and material was lost.",
            ctx.supporting(ConceptType.OVERLOADED_DEFENDER, ConceptType.MATERIAL_LOSS),
        )
    return None


def _hanging_piece(ctx: TaxonomyContext):
    confidence = ctx.confidence_of(ConceptType.HANGING_PIECE)
    if not confidence or ctx.severity not in (Severity.MISTAKE, Severity.BLUNDER):
        return None
    return _error(
        DecisionErrorType.HANGING_PIECE,
        confidence * 0.9,
        "The move leaves a piece where the opponent can take it for free.",
        ctx.supporting(ConceptType.HANGING_PIECE),
    )


def _king_safety(ctx: TaxonomyContext):
    if not ctx.severity.is_problem:
        return None
    for concept_type, weight in (
        (ConceptType.BACK_RANK_WEAKNESS, 0.85),
        (ConceptType.MATING_THREAT, 0.85),
        (ConceptType.KING_SAFETY_DETERIORATION, 0.6),
    ):
        confidence = ctx.confidence_of(concept_type)
        if confidence:
            return _error(
                DecisionErrorType.KING_SAFETY,
                confidence * weight,
                "The move affects the safety of the player's own king ({}).".format(
                    concept_type.value
                ),
                ctx.supporting(concept_type),
            )
    return None


def _forcing_moves_not_checked(ctx: TaxonomyContext):
    for concept_type, weight in (
        (ConceptType.MISSED_FORCING_MOVE, 0.9),
        (ConceptType.MISSED_CHECK, 0.85),
    ):
        confidence = ctx.confidence_of(concept_type)
        if confidence:
            return _error(
                DecisionErrorType.FORCING_MOVES_NOT_CHECKED,
                confidence * weight,
                "A forcing resource was available ({}) and was not played.".format(
                    concept_type.value
                ),
                ctx.supporting(concept_type),
            )
    # A mate threat is the most forcing reply there is: allowing one means the
    # opponent's forcing options were not scanned.
    if ConceptType.MATING_THREAT in ctx.types and ctx.severity.is_problem:
        return _error(
            DecisionErrorType.FORCING_MOVES_NOT_CHECKED,
            0.85,
            "The opponent's forcing reply (a mating threat) was not addressed.",
            ctx.supporting(ConceptType.MATING_THREAT),
        )
    # Weaker version: the opponent's immediate answer is a capture or a check, which is
    # what a forcing-move scan would have found.
    if ctx.severity in (Severity.MISTAKE, Severity.BLUNDER) and _reply_is_forcing(ctx):
        return _error(
            DecisionErrorType.FORCING_MOVES_NOT_CHECKED,
            0.55,
            "The opponent's immediate answer in the engine line is a capture or a check.",
        )
    return None


def _opponent_threat_ignored(ctx: TaxonomyContext):
    if ctx.severity not in (Severity.MISTAKE, Severity.BLUNDER):
        return None
    if not (ctx.types & TACTICAL_CONCEPTS) and not _reply_is_forcing(ctx):
        return None
    if ctx.types & DEV_ERROR_FORCING_CONCEPTS:
        return None
    supporting = ctx.supporting(*sorted(ctx.types & TACTICAL_CONCEPTS, key=lambda c: c.value))
    return _error(
        DecisionErrorType.OPPONENT_THREAT_IGNORED,
        0.55,
        "After the move the opponent has an immediate forcing continuation that the played "
        "move did not address.",
        supporting,
    )


def _tactical_calculation(ctx: TaxonomyContext):
    if ctx.severity not in (Severity.MISTAKE, Severity.BLUNDER):
        return None
    if not _has_capture_sequence(ctx):
        return None
    return _error(
        DecisionErrorType.TACTICAL_CALCULATION,
        0.5,
        "The engine line contains a short forcing sequence that the move walked into.",
    )


def _material_judgment(ctx: TaxonomyContext):
    if ConceptType.MATERIAL_LOSS not in ctx.types:
        return None
    if ctx.types & TACTICAL_CONCEPTS:
        return None
    return _error(
        DecisionErrorType.MATERIAL_JUDGMENT,
        0.5,
        "Material was lost without a concrete tactical motif in the evidence: the exchange "
        "itself was misjudged.",
        ctx.supporting(ConceptType.MATERIAL_LOSS),
    )


def _premature_attack(ctx: TaxonomyContext):
    if not ctx.severity.is_problem:
        return None
    attacking = bool(
        ctx.types
        & {
            ConceptType.MISSED_CAPTURE,
            ConceptType.MATING_THREAT,
            ConceptType.KING_SAFETY_DETERIORATION,
        }
    )
    if not attacking:
        return None
    undeveloped = ConceptType.UNDEVELOPED_PIECES in ctx.types
    exposed_king = ConceptType.KING_SAFETY_DETERIORATION in ctx.types
    if not (undeveloped or exposed_king):
        return None
    return _error(
        DecisionErrorType.PREMATURE_ATTACK,
        0.45,
        "The move starts activity while the player's own position is not ready "
        "(development or king safety is incomplete).",
        ctx.supporting(ConceptType.UNDEVELOPED_PIECES, ConceptType.KING_SAFETY_DETERIORATION),
    )


def _piece_activity(ctx: TaxonomyContext):
    confidence = ctx.confidence_of(ConceptType.PIECE_ACTIVITY)
    if not confidence or not ctx.severity.is_problem:
        return None
    return _error(
        DecisionErrorType.PIECE_ACTIVITY,
        0.4,
        "The piece ends up with fewer safe squares than before, reducing its activity.",
        ctx.supporting(ConceptType.PIECE_ACTIVITY),
    )


def _opening_development(ctx: TaxonomyContext):
    if ctx.phase is not GamePhase.OPENING or not ctx.severity.is_problem:
        return None
    if not (
        ctx.types & {ConceptType.UNDEVELOPED_PIECES, ConceptType.QUEEN_MOVED_REPEATEDLY}
    ):
        return None
    return _error(
        DecisionErrorType.OPENING_DEVELOPMENT,
        0.6,
        "This is still the opening and the move does not improve development.",
        ctx.supporting(ConceptType.UNDEVELOPED_PIECES, ConceptType.QUEEN_MOVED_REPEATEDLY),
    )


def _endgame_technique(ctx: TaxonomyContext):
    if ctx.phase is not GamePhase.ENDGAME or ctx.severity not in (
        Severity.MISTAKE,
        Severity.BLUNDER,
    ):
        return None
    return _error(
        DecisionErrorType.ENDGAME_TECHNIQUE,
        0.45,
        "The mistake happens in an endgame position, where accuracy matters more than speed.",
    )


#: Ordered most specific first. The first rule to fire for a category wins; the final
#: list is sorted by confidence.
RULES: List[Rule] = [
    Rule("defender_removed", DecisionErrorType.DEFENDER_REMOVED, _defender_removed),
    Rule("hanging_piece", DecisionErrorType.HANGING_PIECE, _hanging_piece),
    Rule("king_safety", DecisionErrorType.KING_SAFETY, _king_safety),
    Rule("forcing_moves_not_checked", DecisionErrorType.FORCING_MOVES_NOT_CHECKED, _forcing_moves_not_checked),
    Rule("advantage_conversion", DecisionErrorType.ADVANTAGE_CONVERSION, _advantage_conversion),
    Rule("opening_development", DecisionErrorType.OPENING_DEVELOPMENT, _opening_development),
    Rule("opponent_threat_ignored", DecisionErrorType.OPPONENT_THREAT_IGNORED, _opponent_threat_ignored),
    Rule("tactical_calculation", DecisionErrorType.TACTICAL_CALCULATION, _tactical_calculation),
    Rule("premature_attack", DecisionErrorType.PREMATURE_ATTACK, _premature_attack),
    Rule("material_judgment", DecisionErrorType.MATERIAL_JUDGMENT, _material_judgment),
    Rule("piece_activity", DecisionErrorType.PIECE_ACTIVITY, _piece_activity),
    Rule("endgame_technique", DecisionErrorType.ENDGAME_TECHNIQUE, _endgame_technique),
]


def classify_decision_errors(ctx: TaxonomyContext) -> List[DecisionError]:
    """Run the taxonomy; always returns at least one entry (``UNKNOWN`` if nothing fits)."""
    found: Dict[DecisionErrorType, DecisionError] = {}
    for rule in RULES:
        try:
            result = rule.evaluate(ctx)
        except Exception:  # pragma: no cover - a broken rule must not break a review
            logger.exception("Decision-error rule %s failed", rule.name)
            continue
        if result is None:
            continue
        existing = found.get(result.type)
        if existing is None or result.confidence > existing.confidence:
            found[result.type] = result

    if not found:
        return [
            _error(
                DecisionErrorType.UNKNOWN,
                0.3,
                "No reliable cause could be derived from the available engine evidence and "
                "detected concepts for this move.",
            )
        ]

    ranked = sorted(found.values(), key=lambda error: (-error.confidence, error.type.value))
    return ranked[:MAX_ERRORS_PER_MOVE]


def _reply_is_forcing(ctx: TaxonomyContext) -> bool:
    line = ctx.evidence.played_line_san
    if len(line) < 2:
        return False
    reply = line[1]
    return "x" in reply or reply.endswith(("+", "#"))


def _has_capture_sequence(ctx: TaxonomyContext, plies: int = 4) -> bool:
    line = ctx.evidence.played_line_san[1 : 1 + plies]
    return sum(1 for token in line if "x" in token) >= 2
