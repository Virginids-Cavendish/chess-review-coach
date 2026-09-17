"""Deterministic explanations — the no-LLM path.

This module builds a complete :class:`LLMExplanation` from verified evidence alone,
using fixed Chinese templates. It exists for two reasons:

1. the app must be fully usable without a ``DEEPSEEK_API_KEY``,
2. when the LLM fails or returns something ungrounded, the review still shows a
   trustworthy explanation instead of nothing.

It is deliberately conservative: it states what the engine and the detectors found and
keeps interpretation to the reusable habit attached to the decision-error category. It
never invents a tactic the detectors did not verify.
"""

from collections import Counter
from typing import Dict, List

from analysis.thresholds import THRESHOLDS
from coaching.render import (
    ERROR_LESSON_ZH,
    ERROR_REASON_ZH,
    ERROR_THINKING_PROCESS_ZH,
    best_move_text_zh,
    key_facts_zh,
    move_label_zh,
    one_liner_zh,
)
from models.enums import DecisionErrorType, ExplanationSource, Severity
from models.evidence import AnalysisEvidence, EngineEvidence
from models.explanation import (
    GameSummaryExplanation,
    LLMExplanation,
    MomentExplanation,
)

#: Used when a move is a problem but the detectors found nothing reliable.
NO_MOTIF_ZH = "没有检测到可靠的战术 motif。"


def build_rule_explanation(evidence: AnalysisEvidence) -> LLMExplanation:
    """Compose the deterministic explanation for one critical moment."""
    engine = evidence.engine
    primary = _primary_error_type(evidence)
    facts = key_facts_zh(engine, evidence.concepts)

    summary = _summary(evidence)
    what_happened = _what_happened(evidence, facts)
    why_it_matters = _why_it_matters(evidence)
    likely_human_error = _likely_human_error(evidence, primary)
    better_thinking = "\n".join(ERROR_THINKING_PROCESS_ZH.get(primary, ERROR_THINKING_PROCESS_ZH[DecisionErrorType.UNKNOWN]))
    lesson = ERROR_LESSON_ZH.get(primary, ERROR_LESSON_ZH[DecisionErrorType.UNKNOWN])
    best_move_explanation = _best_move_explanation(evidence)

    return LLMExplanation(
        summary=summary,
        what_happened=what_happened,
        why_it_matters=why_it_matters,
        likely_human_error=likely_human_error,
        better_thinking_process=better_thinking,
        general_lesson=lesson,
        best_move_explanation=best_move_explanation,
        concept_tags=[concept.type.value for concept in evidence.concepts],
        confidence=_confidence(evidence),
    )


def build_rule_moment(evidence: AnalysisEvidence) -> MomentExplanation:
    return MomentExplanation(
        source=ExplanationSource.RULES,
        explanation=build_rule_explanation(evidence),
        model=None,
        grounded=True,
    )


def build_rule_summary(events: List[Dict[str, object]]) -> GameSummaryExplanation:
    """Game-level summary composed strictly from the stored mistake events."""
    if not events:
        return GameSummaryExplanation(
            summary="这盘棋没有出现需要复盘的明显失误，引擎评估全程平稳。",
            main_patterns=[],
            practice_advice=["继续保持每步先检查对手强制手的习惯。"],
            confidence=0.4,
        )

    counter: Counter = Counter()
    for event in events:
        tags = event.get("decision_error_tags") or []
        primary = tags[0] if tags else DecisionErrorType.UNKNOWN.value
        counter[str(primary)] += 1

    ranked = counter.most_common(3)
    patterns = ["{}（{} 次）".format(_error_label_safe(tag), count) for tag, count in ranked]
    advice = [
        ERROR_LESSON_ZH.get(_error_type_safe(tag), ERROR_LESSON_ZH[DecisionErrorType.UNKNOWN])
        for tag, _count in ranked[:2]
    ]
    summary = "本局有 {} 个值得复盘的失误。".format(len(events))
    if patterns:
        summary += "其中反复出现的是：" + "、".join(patterns) + "。"
    if len(events) < 3:
        summary += "（样本很少，只能作为本局的观察，不代表长期模式。）"

    return GameSummaryExplanation(
        summary=summary,
        main_patterns=patterns,
        practice_advice=advice,
        confidence=0.6 if len(events) >= 3 else 0.4,
    )


def _error_type_safe(value: str) -> DecisionErrorType:
    try:
        return DecisionErrorType(value)
    except ValueError:
        return DecisionErrorType.UNKNOWN


def _error_label_safe(value: str) -> str:
    from coaching.render import error_label_zh

    return error_label_zh(_error_type_safe(value))


# --------------------------------------------------------------------------- parts


def _summary(evidence: AnalysisEvidence) -> str:
    return "{}。{}".format(move_label_zh(evidence), one_liner_zh(evidence))


def _what_happened(evidence: AnalysisEvidence, facts: List[str]) -> str:
    engine = evidence.engine
    lines: List[str] = ["已核实的事实："]
    lines.extend("· {}".format(fact) for fact in facts)
    if engine.played_line_san:
        lines.append("引擎给出的后续（你实战走法之后）：{}".format(" ".join(engine.played_line_san[:6])))
    if engine.wdl_estimated:
        lines.append("（注意：该引擎未提供 WDL 数据，严重程度由评估分估算。）")
    return "\n".join(lines)


def _why_it_matters(evidence: AnalysisEvidence) -> str:
    engine = evidence.engine
    sentences: List[str] = []

    if engine.mate_after is not None and engine.mate_after < 0:
        sentences.append("这一步之后局面已经是必败：对手有 {} 步之内的强制将杀。".format(abs(engine.mate_after)))
    elif engine.mate_before is not None and engine.mate_before > 0 and not engine.is_engine_best:
        sentences.append("这一步放弃了 {} 步之内的强制将杀。".format(engine.mate_before))
    else:
        sentences.append(
            "你的胜率期望从 {} 变成 {}。".format(
                "{:.0f}%".format(engine.expected_score_before * 100),
                "{:.0f}%".format(engine.expected_score_after * 100),
            )
        )
        if engine.expected_score_before >= THRESHOLDS.detection.winning_expected_score:
            sentences.append("注意：这一步之前你是明显占优的一方，丢掉的是已经到手的优势。")
        elif engine.expected_score_after <= THRESHOLDS.detection.losing_expected_score:
            sentences.append("这一步把局面推到了明显劣势。")

    if engine.centipawn_loss is not None and engine.centipawn_loss > 0:
        sentences.append("（评估分变化 {} 分，仅作参考，严重程度以期望得分为准。）".format(engine.centipawn_loss))
    return " ".join(sentences)


def _likely_human_error(evidence: AnalysisEvidence, primary: DecisionErrorType) -> str:
    reason = ERROR_REASON_ZH.get(primary, ERROR_REASON_ZH[DecisionErrorType.UNKNOWN])
    if primary is DecisionErrorType.UNKNOWN:
        return "根据现有证据无法确定具体原因。" + NO_MOTIF_ZH
    concepts = ", ".join(sorted({concept.type.value for concept in evidence.concepts})[:5])
    if concepts:
        return "{}（对应的可核实概念：{}）".format(reason, concepts)
    return reason


def _best_move_explanation(evidence: AnalysisEvidence) -> str:
    engine = evidence.engine
    parts = [best_move_text_zh(engine)]
    if engine.alternatives:
        alternatives = "、".join(
            "{}（期望得分 {:.2f}）".format(candidate.san, candidate.expected_score)
            for candidate in engine.alternatives[:2]
        )
        parts.append("引擎的其他候选：{}。".format(alternatives))
    if engine.is_engine_best:
        parts.append("你走的这一手就是引擎的第一选择，问题出在后续的处理上。")
    if engine.best_move_unique:
        parts.append("这个局面的好棋很窄，引擎首选比第二选择明显更好。")
    return " ".join(parts)


def _confidence(evidence: AnalysisEvidence) -> float:
    """How much the deterministic layer trusts its own explanation."""
    if evidence.severity is Severity.GOOD:
        return 0.3
    concepts = evidence.concepts
    if not concepts:
        return 0.35
    best = max(concept.confidence for concept in concepts)
    has_engine_confirmation = any(
        concept.metadata.get("confirmed_by_engine_line") == "true"
        or concept.metadata.get("captured_in_engine_line") == "true"
        for concept in concepts
    )
    score = 0.5 + 0.3 * best + (0.1 if has_engine_confirmation else 0.0)
    return round(min(0.9, score), 2)


def _primary_error_type(evidence: AnalysisEvidence) -> DecisionErrorType:
    if not evidence.decision_errors:
        return DecisionErrorType.UNKNOWN
    best = max(evidence.decision_errors, key=lambda error: error.confidence)
    return best.type


__all__ = [
    "build_rule_explanation",
    "build_rule_moment",
    "build_rule_summary",
    "NO_MOTIF_ZH",
]
