"""Chinese rendering of verified evidence.

One place that turns structured facts into Chinese sentences, used by the
deterministic fallback explanations and by the review UI (critical-moment one-liners).
Everything here is a pure function of stored evidence: no chess reasoning happens in
this module, only phrasing.

The English ``rationale`` fields produced by the taxonomy are deliberately *not*
translated verbatim — each decision-error category has its own concrete Chinese
wording so the text stays specific ("你没有重新检查 e1 的防守") instead of generic.
"""

from typing import List, Optional

from models.enums import (
    ConceptType,
    DecisionErrorType,
    Severity,
    SEVERITY_LABELS_ZH,
    concept_label_zh,
    decision_error_label_zh,
)
from models.evidence import AnalysisEvidence, DetectedConcept, EngineEvidence

MATE_SENTINEL = 10.0


def format_eval(evidence: EngineEvidence, before: bool = True) -> str:
    """Human-readable evaluation from the player's point of view."""
    mate = evidence.mate_before if before else evidence.mate_after
    value = evidence.evaluation_before if before else evidence.evaluation_after
    if mate is not None:
        if mate > 0:
            return "可在 {} 步内将杀".format(mate)
        return "将在 {} 步内被将杀".format(abs(mate))
    if value is None:
        return "未知"
    return "{:+.2f}".format(value)


def format_percent(value: float) -> str:
    return "{:.0f}%".format(round(value * 100))


def format_loss(evidence: EngineEvidence) -> str:
    """Expected-score loss, expressed the way a club player can feel it."""
    return "期望得分 {} → {}（损失 {:.2f}）".format(
        "{:.2f}".format(evidence.expected_score_before),
        "{:.2f}".format(evidence.expected_score_after),
        evidence.expected_score_loss,
    )


def concept_phrase_zh(concept: DetectedConcept) -> str:
    """A concrete Chinese phrase for one detected concept.

    ``square_list`` keeps the structured squares for positional access; ``squares`` is
    only the joined string for display. (Indexing the joined string would silently
    return single characters.)
    """
    meta = concept.metadata
    square_list = list(concept.squares)
    squares = "、".join(square_list)
    pieces = "、".join(concept.pieces)

    if concept.type is ConceptType.REMOVAL_OF_DEFENDER:
        return "移走了 {} 上的防守子，{} 因此失去保护".format(
            meta.get("vacated_square", "?"), meta.get("undefended_piece", "该子")
        )
    if concept.type is ConceptType.HANGING_PIECE:
        return "{} 会被直接吃掉（净赚 {} 分）".format(pieces or squares, meta.get("see_gain", "?"))
    if concept.type is ConceptType.UNDEFENDED_PIECE:
        return "{} 没有任何子力保护".format(pieces or squares)
    if concept.type is ConceptType.MATING_THREAT:
        return "对手有 {} 步之内的杀棋".format(meta.get("mate_in", "?"))
    if concept.type is ConceptType.BACK_RANK_WEAKNESS:
        return "底线存在弱点" + ("（引擎给出杀棋）" if meta.get("mate_move") else "")
    if concept.type is ConceptType.FORK:
        return "{} 形成叉子，同时攻击 {}".format(pieces, squares)
    if concept.type is ConceptType.DOUBLE_ATTACK:
        return "{} 形成双重攻击".format(pieces)
    if concept.type in (ConceptType.PIN, ConceptType.SKEWER):
        return "{}（{}）".format(concept_label_zh(concept.type), squares)
    if concept.type is ConceptType.DISCOVERED_ATTACK:
        # squares = [target, vacated]
        target = square_list[0] if square_list else "?"
        vacated = square_list[1] if len(square_list) > 1 else "?"
        return "闪击：{} 让出线路后 {} 被攻击".format(vacated, target)
    if concept.type is ConceptType.DEFLECTION:
        # squares = [defender square, the piece it was defending]
        target = square_list[-1] if square_list else "关键格"
        return "对手在引擎线路中引离了 {} 的防守子".format(target)
    if concept.type is ConceptType.MISSED_CAPTURE:
        return "漏掉了 {}（可净赚 {} 分）".format(
            meta.get("available_capture", "?"), meta.get("see_gain", "?")
        )
    if concept.type is ConceptType.MISSED_CHECK:
        return "漏掉了将军 {}".format(meta.get("best_move", "?"))
    if concept.type is ConceptType.MISSED_FORCING_MOVE:
        if meta.get("reason") == "missed_mate":
            return "漏掉了 {} 步的强制将杀".format(meta.get("mate_in", "?"))
        return "漏掉了强制手 {}".format(meta.get("best_move", "?"))
    if concept.type is ConceptType.MATERIAL_LOSS:
        return "局面继续下去会净亏 {} 分".format(meta.get("material_drop", "?"))
    if concept.type is ConceptType.TRAPPED_PIECE:
        return "{} 被攻击而且几乎没有安全格（仅 {} 个）".format(
            pieces, meta.get("safe_squares", "0")
        )
    if concept.type is ConceptType.INTERMEDIATE_MOVE:
        return "对手先走了中间着 {}".format(meta.get("intermediate_move", "?"))
    if concept.type is ConceptType.OVERLOADED_DEFENDER:
        return "{} 同时要防守 {} 个被攻击的目标".format(
            pieces, meta.get("defended_count", "多")
        )
    if concept.type is ConceptType.EXCHANGE_SACRIFICE:
        return "用车换轻子（交换弃子）"
    if concept.type is ConceptType.KING_SAFETY_DETERIORATION:
        return "王前面的兵形被削弱"
    if concept.type is ConceptType.ISOLATED_PAWN:
        return "产生孤兵（{}）".format(squares)
    if concept.type is ConceptType.DOUBLED_PAWN:
        return "产生叠兵（{}）".format(squares)
    if concept.type is ConceptType.PASSED_PAWN:
        return "{}出现通路兵（{}）".format(
            "对手" if meta.get("side") == "opponent" else "", squares
        )
    if concept.type is ConceptType.WEAK_SQUARE:
        return "{} 变成弱格".format(squares)
    if concept.type is ConceptType.UNDEVELOPED_PIECES:
        return "还有 {} 个轻子没有出动（{}）".format(
            meta.get("undeveloped_count", "多"), pieces
        )
    if concept.type is ConceptType.QUEEN_MOVED_REPEATEDLY:
        return "开局阶段后再次移动（之前走过 {}）".format(
            meta.get("previous_queen_moves", "?")
        )
    if concept.type is ConceptType.PIECE_ACTIVITY:
        return "子力走到安全格更少的位置（{}）".format(squares)
    if concept.type is ConceptType.OPEN_FILE:
        return "占据了开放线（{}）".format(squares)
    if concept.type is ConceptType.SEMI_OPEN_FILE:
        return "占据了半开放线（{}）".format(squares)
    if concept.type is ConceptType.BISHOP_PAIR:
        return "{}双象".format("获得" if meta.get("direction") == "gained" else "失去")
    if concept.type is ConceptType.MATERIAL_IMBALANCE:
        return "子力不平衡：{}".format(meta.get("imbalance", ""))
    if concept.type is ConceptType.PAWN_STRUCTURE_DAMAGE:
        return "兵形受损（{}）".format(squares)
    if concept.type is ConceptType.ATTACKED_PIECE:
        return "子力被攻击（{}）".format(pieces or squares)
    return concept_label_zh(concept.type)


def concept_phrases_zh(concepts: List[DetectedConcept], limit: int = 3) -> List[str]:
    """Phrases for the most confident concepts, most confident first."""
    ordered = sorted(concepts, key=lambda c: -c.confidence)
    return [concept_phrase_zh(concept) for concept in ordered[:limit]]


def key_facts_zh(evidence: EngineEvidence, concepts: List[DetectedConcept]) -> List[str]:
    """Bullet facts, in the order a coach would say them."""
    facts: List[str] = []
    facts.append(
        "评估（你的一方）：{} → {}".format(format_eval(evidence, True), format_eval(evidence, False))
    )
    facts.append(format_loss(evidence))
    if evidence.mate_after is not None and evidence.mate_after < 0:
        facts.append("引擎判定：你将在 {} 步内被将杀".format(abs(evidence.mate_after)))
    elif evidence.mate_before is not None and evidence.mate_before > 0 and not evidence.is_engine_best:
        facts.append("引擎判定：你原本可以在 {} 步内将杀对手".format(evidence.mate_before))
    facts.extend(concept_phrases_zh(concepts))
    if evidence.best_move_san:
        facts.append("引擎推荐：{}（{}）".format(evidence.best_move_san, " ".join(evidence.best_line_san[:5])))
    return facts


#: Chinese wording for "what the player probably failed to do", per category.
ERROR_REASON_ZH = {
    DecisionErrorType.FORCING_MOVES_NOT_CHECKED: (
        "你落子前没有重新检查对手的强制手：将军、吃子、以及一步就能成型的威胁。"
    ),
    DecisionErrorType.HANGING_PIECE: "你把子力放在了对手可以直接吃掉的位置，落子前没有确认这个格子是否安全。",
    DecisionErrorType.OPPONENT_THREAT_IGNORED: "你忽略了对手上一步留下的威胁，继续执行了自己的计划。",
    DecisionErrorType.DEFENDER_REMOVED: "你移动（或消除了）一个承担防守任务的棋子，但没有重新检查它原本守住的格子。",
    DecisionErrorType.TACTICAL_CALCULATION: "连续吃子的战术序列你没有算完，算到中途就停下来了。",
    DecisionErrorType.PREMATURE_ATTACK: "你在自己的王还不安全、子力还没展开的时候就发起了进攻。",
    DecisionErrorType.KING_SAFETY: "你动到了王周围的防守结构，没有先确认对方有没有直接的进攻手段。",
    DecisionErrorType.MATERIAL_JUDGMENT: "交换的子力价值判断有误：交换结束后你净亏了子力。",
    DecisionErrorType.PIECE_ACTIVITY: "子力走到了活动空间更小的地方，之后很难再参与进攻或防守。",
    DecisionErrorType.OPENING_DEVELOPMENT: "开局阶段没有优先出子，而是把时间花在了别的事情上。",
    DecisionErrorType.ENDGAME_TECHNIQUE: "残局的处理不够精确，残局里每一步的容错率都更低。",
    DecisionErrorType.ADVANTAGE_CONVERSION: "你在明显占优的局面下没有选择最稳的简化方式，把优势还了回去。",
    DecisionErrorType.TIME_PRESSURE_UNKNOWN: "PGN 中没有时间信息，无法判断是否与时间紧张有关。",
    DecisionErrorType.UNKNOWN: "目前掌握的证据不足以确定具体原因。",
}

#: The reusable habit attached to each category — the "general lesson" the product is
#: ultimately about.
ERROR_LESSON_ZH = {
    DecisionErrorType.FORCING_MOVES_NOT_CHECKED: "每走一步之前，先按固定顺序问三个问题：对手有没有将军？有没有吃子？有没有一步威胁？",
    DecisionErrorType.HANGING_PIECE: "落子前数一遍：这个格子被对方几个子攻击、被自己几个子保护。保护少于攻击就不要放。",
    DecisionErrorType.OPPONENT_THREAT_IGNORED: "先回答“对手上一步想干什么”，再考虑自己的计划。",
    DecisionErrorType.DEFENDER_REMOVED: "移动防守子之前，先确认它守住的格子/棋子还有没有别的保护。",
    DecisionErrorType.TACTICAL_CALCULATION: "遇到连续吃子的局面，把整条交换序列算到底再落子。",
    DecisionErrorType.PREMATURE_ATTACK: "进攻前先检查自己的王和未出动的子力。",
    DecisionErrorType.KING_SAFETY: "动王翼的兵或王前面的子之前，先看对手有几个子能靠近你的王。",
    DecisionErrorType.MATERIAL_JUDGMENT: "交换前先数清楚交换结束后的子力对比，而不是只看眼前这一步吃子。",
    DecisionErrorType.PIECE_ACTIVITY: "子力宁可放到看起来有点冒险但有出路的位置，也不要放到没有出路的位置。",
    DecisionErrorType.OPENING_DEVELOPMENT: "开局阶段尽量每步出动一个新子，避免重复动同一个子。",
    DecisionErrorType.ENDGAME_TECHNIQUE: "残局先算清王和兵的位置，再决定是否交换。",
    DecisionErrorType.ADVANTAGE_CONVERSION: "占优时优先简化、消除对手反击，而不是追求更快结束战斗。",
    DecisionErrorType.TIME_PRESSURE_UNKNOWN: "记录自己的用时，事后确认哪些失误发生在时间紧张时。",
    DecisionErrorType.UNKNOWN: "对照引擎推荐走法，自己先想一遍为什么，再决定是否接受这个结论。",
}

#: A short, ordered checklist to use on the next move.
ERROR_THINKING_PROCESS_ZH = {
    DecisionErrorType.FORCING_MOVES_NOT_CHECKED: [
        "1. 对手有没有将军？",
        "2. 对手有没有直接吃子的棋？",
        "3. 对手有没有下一步就成型的威胁？",
        "4. 确认之后再考虑自己的计划。",
    ],
    DecisionErrorType.HANGING_PIECE: [
        "1. 我这个子落下去之后，被几个对方棋子攻击？",
        "2. 被几个自己的棋子保护？",
        "3. 对方吃过来之后，交换的结果是多少分？",
    ],
    DecisionErrorType.OPPONENT_THREAT_IGNORED: [
        "1. 对手上一步为什么走那里？",
        "2. 他下一步最想走什么？",
        "3. 我这一步是否解决了那个威胁？",
    ],
    DecisionErrorType.DEFENDER_REMOVED: [
        "1. 这个子现在在防守什么？",
        "2. 它离开之后，哪些格子/棋子会失去保护？",
        "3. 对手有没有立刻利用这一点的强制手？",
    ],
    DecisionErrorType.TACTICAL_CALCULATION: [
        "1. 把交换序列按顺序写下来。",
        "2. 每一步都问对手有没有中间着。",
        "3. 算到安静局面再判断结果。",
    ],
    DecisionErrorType.PREMATURE_ATTACK: [
        "1. 我的王安全吗？",
        "2. 我还有子力没出动吗？",
        "3. 对手有没有比我更快的反击？",
    ],
    DecisionErrorType.KING_SAFETY: [
        "1. 这个子/兵原本在王周围起什么作用？",
        "2. 对手有几个子可以靠近我的王？",
        "3. 我能不能先用一步棋改善王的安全？",
    ],
    DecisionErrorType.MATERIAL_JUDGMENT: [
        "1. 交换结束后双方各剩什么子？",
        "2. 价值差多少？",
        "3. 位置上的补偿是否足以弥补子力差？",
    ],
    DecisionErrorType.PIECE_ACTIVITY: [
        "1. 这个子在新位置有多少安全格？",
        "2. 它能参与进攻还是只能被动防守？",
    ],
    DecisionErrorType.OPENING_DEVELOPMENT: [
        "1. 还有哪些子没出动？",
        "2. 这一步能出动新子吗？",
        "3. 是否应该先易位？",
    ],
    DecisionErrorType.ENDGAME_TECHNIQUE: [
        "1. 王的活跃程度够吗？",
        "2. 有没有通路兵？",
        "3. 交换后是赢、和还是输？",
    ],
    DecisionErrorType.ADVANTAGE_CONVERSION: [
        "1. 我现在的优势在哪里？",
        "2. 哪一步能最简单地把优势固定下来？",
        "3. 对手还有什么反击机会？",
    ],
    DecisionErrorType.TIME_PRESSURE_UNKNOWN: ["1. 复盘时记录自己每一步的用时。"],
    DecisionErrorType.UNKNOWN: [
        "1. 先看引擎推荐走法。",
        "2. 自己想一遍为什么它更好。",
        "3. 记住这个模式，下次遇到类似局面先检查。",
    ],
}


def severity_label_zh(severity: Severity) -> str:
    return SEVERITY_LABELS_ZH.get(severity, severity.value)


def error_label_zh(error_type: DecisionErrorType) -> str:
    return decision_error_label_zh(error_type)


def primary_error(evidence: AnalysisEvidence):
    """The highest-confidence decision error, or None when the list is empty."""
    if not evidence.decision_errors:
        return None
    return max(evidence.decision_errors, key=lambda error: error.confidence)


def one_liner_zh(evidence: AnalysisEvidence) -> str:
    """The one-sentence summary shown on a critical-moment card."""
    error = primary_error(evidence)
    facts = concept_phrases_zh(evidence.concepts, limit=1)
    if error is not None and error.type is not DecisionErrorType.UNKNOWN:
        sentence = ERROR_REASON_ZH[error.type]
        if facts:
            return "{}（{}）".format(sentence, facts[0])
        return sentence
    if facts:
        return "这一步的主要问题：{}".format(facts[0])
    return "这一步的期望得分明显下降，但没有检测到可靠的战术 motif。"


def move_label_zh(evidence: AnalysisEvidence) -> str:
    """e.g. ``"22. Bf4?? — 严重失误"`` for headings."""
    suffix = "??" if evidence.severity is Severity.BLUNDER else ("?" if evidence.severity.is_problem else "")
    return "{}. {}{} — {}".format(
        evidence.position.move_number,
        evidence.played_move.san,
        suffix,
        severity_label_zh(evidence.severity),
    )


def best_move_text_zh(evidence: EngineEvidence) -> str:
    if not evidence.best_move_san:
        return "引擎没有给出推荐走法。"
    line = " ".join(evidence.best_line_san[:6])
    return "引擎推荐 {}{}，对应期望得分 {:.2f}；实战走法只有 {:.2f}。".format(
        evidence.best_move_san,
        "（{}）".format(line) if line else "",
        evidence.expected_score_before,
        evidence.expected_score_after,
    )
