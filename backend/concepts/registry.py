"""The detector registry.

One list of every concept detector. ``detect_concepts`` runs them all, isolates
failures (a broken detector degrades the review, it never breaks it), de-duplicates
overlapping reports and returns them in a stable, explainable order.
"""

import logging
from typing import Dict, List, Tuple

from concepts import activity, defenders, development, forcing, hanging, material, structure, tactics, threats, zwischenzug
from concepts.base import ConceptDetector, DetectionContext
from models.evidence import DetectedConcept

logger = logging.getLogger(__name__)

#: Detector order is the tie-breaker for equally confident concepts: concrete tactics
#: are listed before structural context so the UI leads with what actually happened.
ALL_DETECTORS: List[ConceptDetector] = [
    *hanging.DETECTORS,
    *material.DETECTORS,
    *forcing.DETECTORS,
    *tactics.DETECTORS,
    *defenders.DETECTORS,
    *threats.DETECTORS,
    *zwischenzug.DETECTORS,
    *structure.DETECTORS,
    *development.DETECTORS,
    *activity.DETECTORS,
]

#: Upper bound on concepts attached to one move; beyond this the card becomes noise.
MAX_CONCEPTS_PER_MOVE = 12


def detector_names() -> List[str]:
    return [detector.name for detector in ALL_DETECTORS]


def detect_concepts(ctx: DetectionContext) -> List[DetectedConcept]:
    """Run every detector and merge the results."""
    collected: List[DetectedConcept] = []
    for detector in ALL_DETECTORS:
        try:
            collected.extend(detector.detect(ctx))
        except Exception:  # pragma: no cover - defensive: one bad detector must not
            # abort the whole review.
            logger.exception("Concept detector %s failed", detector.name)

    merged = _deduplicate(collected)
    merged.sort(key=lambda concept: (-concept.confidence, concept.type.value))
    return merged[:MAX_CONCEPTS_PER_MOVE]


def _deduplicate(concepts: List[DetectedConcept]) -> List[DetectedConcept]:
    """Keep the most confident report when two detectors describe the same thing.

    Identity is (concept type, touched squares); the evidence lines of the weaker
    report are folded into the survivor so nothing verifiable is thrown away.
    """
    best: Dict[Tuple[str, Tuple[str, ...]], DetectedConcept] = {}
    order: List[Tuple[str, Tuple[str, ...]]] = []
    for concept in concepts:
        key = (concept.type.value, tuple(sorted(concept.squares)))
        existing = best.get(key)
        if existing is None:
            best[key] = concept
            order.append(key)
            continue
        if concept.confidence > existing.confidence:
            concept.evidence = list(dict.fromkeys(existing.evidence + concept.evidence))
            concept.pieces = list(dict.fromkeys(existing.pieces + concept.pieces))
            best[key] = concept
        else:
            existing.evidence = list(dict.fromkeys(existing.evidence + concept.evidence))
            existing.pieces = list(dict.fromkeys(existing.pieces + concept.pieces))
    return [best[key] for key in order]
