"""Grounding guards for LLM output.

Faithfulness is enforced structurally, not by trusting the prompt:

* the response must validate against :class:`LLMExplanation`,
* every move the model names in a *factual* field must exist in the evidence,
* concept tags the evidence does not contain are dropped,
* the model may never claim a best move other than the engine's,
* reported confidence is capped, because prose is not evidence.

A rejected response is never shown: the caller falls back to the deterministic
explanation, so a hallucination can cost an explanation but never the review.
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from models.evidence import AnalysisEvidence
from models.explanation import LLMExplanation

#: Unambiguous SAN tokens: piece moves, pawn captures, promotions, castling. Bare pawn
#: pushes ("e4") are excluded on purpose because they are indistinguishable from square
#: names in prose, and flagging every square would produce false rejections.
MOVE_TOKEN_PATTERN = re.compile(
    r"\b(?:"
    r"[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?"
    r"|[a-h][1-8]x[a-h][1-8](?:=[QRBN])?[+#]?"
    r"|[a-h][1-8]=[QRBN][+#]?"
    r"|[O0]-[O0](?:-[O0])?[+#]?"
    r")\b"
)

#: Confidence can never exceed this: prose cannot be more certain than the evidence.
MAX_REPORTED_CONFIDENCE = 0.9

#: Fields that state facts about the game and therefore must not invent moves.
FACTUAL_FIELDS = ("what_happened", "best_move_explanation", "summary")

#: 只在"模型明确给出建议"的句式里抓着法。
#:
#: 早期版本是"best_move_explanation 里出现的任何着法都必须是引擎着法"，结果把这类完全正确的
#: 句子也判成了幻觉：「对手走 Ba6 之后 Rd3 受攻，你走了 Rd1，但引擎推荐 g6」——Ba6 是对手的
#: 着法，本来就在我们给它的概念证据里。所以现在只在下面这些"推荐/建议"句式后面抓，
#: 抓到的着法必须是引擎给的、或者是实战走法（用于对比）。
_SAN = r"[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?|[a-h][1-8]x[a-h][1-8](?:=[QRBN])?[+#]?|[a-h][1-8]=[QRBN][+#]?|[O0]-[O0](?:-[O0])?[+#]?"
RECOMMENDATION_PATTERNS = [
    re.compile(r"推荐\s*(?:走|着法|着|的是|是|为|：|:)?\s*(" + _SAN + r")"),
    re.compile(r"建议\s*(?:走|着法|着|的是|是|为|：|:)?\s*(" + _SAN + r")"),
    re.compile(r"(?:更好|最佳|正确|最优)的?(?:走法|着法|选择|一步)\s*(?:是|为|：|:)?\s*(" + _SAN + r")"),
    re.compile(r"(?:应该|应当|应|可以|不如)\s*走\s*(" + _SAN + r")"),
    re.compile(r"正着\s*(?:是|为|：|:)?\s*(" + _SAN + r")"),
]


@dataclass
class GroundingReport:
    ok: bool
    explanation: Optional[LLMExplanation] = None
    warnings: List[str] = field(default_factory=list)
    reason: Optional[str] = None
    dropped_concepts: List[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return not self.ok


def validate_explanation(
    explanation: LLMExplanation, evidence: AnalysisEvidence
) -> GroundingReport:
    """Check an LLM explanation against the evidence it was given."""
    # 两个不同的集合，管两件不同的事：
    #   * evidence_moves —— 模型可以在叙述里提到的着法。凡是它收到的证据里出现过的着法都算，
    #     包括概念证据里的句子（例如 "Ba6 now attacks Rd3"）和这盘棋的历史着法。
    #   * engine_moves  —— 只有这些着法可以被当作"引擎推荐"。模型不能自己发明一个更好的走法。
    evidence_moves = _evidence_moves(evidence)
    engine_moves = _allowed_moves(evidence)
    allowed_concepts = {concept.type.value for concept in evidence.concepts}

    unknown_in_facts = _unknown_moves(
        " ".join(getattr(explanation, name) for name in FACTUAL_FIELDS), evidence_moves
    )
    if unknown_in_facts:
        return GroundingReport(
            ok=False,
            reason=(
                "解释中出现了证据里不存在的着法：{}".format(", ".join(sorted(unknown_in_facts)))
            ),
        )

    contradiction = _contradicts_engine(explanation, evidence, engine_moves)
    if contradiction:
        return GroundingReport(ok=False, reason=contradiction)

    warnings: List[str] = []
    dropped: List[str] = []
    kept_tags: List[str] = []
    for tag in explanation.concept_tags:
        normalized = tag.strip().lower()
        if normalized in allowed_concepts and normalized not in kept_tags:
            kept_tags.append(normalized)
        elif normalized:
            dropped.append(normalized)
    if dropped:
        warnings.append(
            "已移除证据不支持的概念标签：{}".format(", ".join(sorted(set(dropped))))
        )

    unknown_elsewhere = _unknown_moves(
        " ".join(
            [
                explanation.why_it_matters,
                explanation.likely_human_error,
                explanation.better_thinking_process,
                explanation.general_lesson,
            ]
        ),
        evidence_moves,
    )
    if unknown_elsewhere:
        warnings.append(
            "解释的推理部分提到了证据之外的着法：{}（已保留但请注意核对）".format(
                ", ".join(sorted(unknown_elsewhere))
            )
        )

    confidence = min(MAX_REPORTED_CONFIDENCE, max(0.0, explanation.confidence))
    if len(warnings) and confidence > 0.7:
        confidence = 0.7
    if not evidence.concepts:
        warnings.append("该局面没有检测到可靠的概念，AI 解释只能基于数值。")
        confidence = min(confidence, 0.5)

    sanitized = explanation.model_copy(
        update={"concept_tags": kept_tags, "confidence": round(confidence, 2)}
    )
    return GroundingReport(
        ok=True, explanation=sanitized, warnings=warnings, dropped_concepts=dropped
    )


def validate_game_summary(
    summary_text: str, allowed_moves: Set[str], event_count: int
) -> List[str]:
    """Warnings for a game-level summary (no hard rejection: it is prose over a list)."""
    warnings: List[str] = []
    unknown = _unknown_moves(summary_text, allowed_moves)
    if unknown:
        warnings.append(
            "整体总结提到了清单之外的着法：{}".format(", ".join(sorted(unknown)))
        )
    if event_count < 3:
        warnings.append("失误样本过少，整体结论仅供参考。")
    return warnings


def _contradicts_engine(
    explanation: LLMExplanation, evidence: AnalysisEvidence, engine_moves: Set[str]
) -> Optional[str]:
    """模型有没有把"引擎之外的着法"说成是自己推荐的走法。

    只看明确的建议句式（见 RECOMMENDATION_PATTERNS），并且允许实战走法本身出现在句子里
    （"引擎推荐 Rdd1，而不是你走的 Rad1" 是正常的对比）。
    """
    if not evidence.engine.best_move_san:
        return None
    played = _normalize(evidence.played_move.san)
    for field_name in ("best_move_explanation", "summary", "what_happened"):
        text = getattr(explanation, field_name, "") or ""
        for pattern in RECOMMENDATION_PATTERNS:
            for match in pattern.finditer(text):
                token = _normalize(match.group(1))
                if not token or token in engine_moves or token == played:
                    continue
                return (
                    "AI 把「{}」说成了推荐走法，但引擎给出的不是这一手（引擎：{}）。".format(
                        match.group(1), evidence.engine.best_move_san
                    )
                )
    return None


def _evidence_moves(evidence: AnalysisEvidence) -> Set[str]:
    """模型可以在叙述里提到的所有着法。

    做法就是把"发出去的证据"整份扫一遍：只要某个着法在证据文本里出现过，模型引用它就不算
    编造。FEN 里不含 SAN 形状的记号，所以不会被误判成着法。
    """
    payload_text = json.dumps(evidence.to_llm_payload(), ensure_ascii=False)
    tokens = {_normalize(match.group(0)) for match in MOVE_TOKEN_PATTERN.finditer(payload_text)}
    tokens.discard("")
    return tokens | _allowed_moves(evidence)


def _allowed_moves(evidence: AnalysisEvidence) -> Set[str]:
    """引擎真正给出过的着法（推荐着法及其线路、实战着法、候选着法）。"""
    tokens: Set[str] = set()
    engine = evidence.engine
    for token in [engine.best_move_san, evidence.played_move.san]:
        if token:
            tokens.add(_normalize(token))
    for line in (engine.best_line_san, engine.played_line_san):
        tokens.update(_normalize(token) for token in line if token)
    for candidate in engine.alternatives:
        tokens.add(_normalize(candidate.san))
        tokens.update(_normalize(token) for token in candidate.pv_san)
    tokens.discard("")
    return tokens


def _unknown_moves(text: str, allowed: Set[str]) -> Set[str]:
    if not text:
        return set()
    found = set()
    for match in MOVE_TOKEN_PATTERN.finditer(text):
        token = _normalize(match.group(0))
        if token and token not in allowed:
            found.add(match.group(0).strip())
    return found


def _normalize(token: str) -> str:
    return token.strip().replace("0", "O").replace("+", "").replace("#", "").replace("!", "").replace("?", "")
