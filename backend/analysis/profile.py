"""Player-profile aggregation.

Turns stored mistake events into "what kind of mistakes does this player repeat?".

The statistics are deliberately humble. With a handful of games, a category share is a
description of *those games*, not a diagnosis, so every weakness carries a confidence
band and wording that matches it ("目前观察到" instead of "你的稳定弱点是"), and the trend
line only appears once there are enough games to mean anything.
"""

from datetime import datetime
from typing import Dict, List, Optional

from analysis.thresholds import THRESHOLDS, AnalysisThresholds
from models.enums import (
    DecisionErrorType,
    GamePhase,
    PHASE_LABELS_ZH,
    Severity,
    decision_error_label_zh,
    concept_label_zh,
    ConceptType,
)
from models.profile import (
    ConceptFrequency,
    PhaseBreakdown,
    ProfileSummary,
    RecurringWeakness,
    TrendPoint,
    TrendSummary,
)
from storage.repository import ProfileInput, example_moment_from_row

MAJOR_SEVERITIES = (Severity.MISTAKE, Severity.BLUNDER)

#: How many examples to keep per weakness (they double as future puzzle material).
MAX_EXAMPLES_PER_WEAKNESS = 3

#: Number of recent games compared against earlier ones for the trend line.
TREND_WINDOW = 3


def build_profile(
    data: ProfileInput, thresholds: AnalysisThresholds = THRESHOLDS
) -> ProfileSummary:
    events = data.mistake_events
    major = [event for event in events if event.get("severity") in _major_values()]
    total_major = len(major)

    weaknesses = _build_weaknesses(data, major, total_major, thresholds)
    phases = _build_phases(data, len(events))
    concepts = _build_concepts(data, len(events))
    trend_points, trend = _build_trend(data)

    severity_counts = data.severity_counts
    return ProfileSummary(
        total_games=data.total_games,
        total_player_moves=data.total_player_moves,
        total_problems=len(events),
        blunders=int(severity_counts.get(Severity.BLUNDER.value, 0)),
        mistakes=int(severity_counts.get(Severity.MISTAKE.value, 0)),
        inaccuracies=int(severity_counts.get(Severity.INACCURACY.value, 0)),
        average_expected_score_loss=round(data.average_loss or 0.0, 4),
        weaknesses=weaknesses,
        phases=phases,
        top_concepts=concepts,
        trend=trend,
        trend_points=trend_points,
        sample_size_note_zh=_sample_note(data.total_games, len(events)),
        generated_at=datetime.utcnow(),
    )


def _major_values():
    return {severity.value for severity in MAJOR_SEVERITIES}


def _build_weaknesses(
    data: ProfileInput,
    major: List[Dict[str, object]],
    total_major: int,
    thresholds: AnalysisThresholds,
) -> List[RecurringWeakness]:
    grouped: Dict[str, Dict[str, object]] = {}
    for event in data.mistake_events:
        error_type = str(event.get("primary_error") or DecisionErrorType.UNKNOWN.value)
        bucket = grouped.setdefault(
            error_type,
            {
                "events": [],
                "games": set(),
                "major": 0,
                "loss_sum": 0.0,
                "severity_mix": {},
            },
        )
        events_list: List[Dict[str, object]] = bucket["events"]  # type: ignore[assignment]
        events_list.append(event)
        games: set = bucket["games"]  # type: ignore[assignment]
        games.add(str(event.get("game_id")))
        bucket["loss_sum"] = float(bucket["loss_sum"]) + float(
            event.get("expected_score_loss") or 0.0
        )
        severity = str(event.get("severity"))
        mix: Dict[str, int] = bucket["severity_mix"]  # type: ignore[assignment]
        mix[severity] = mix.get(severity, 0) + 1
        if severity in _major_values():
            bucket["major"] = int(bucket["major"]) + 1

    denominator = total_major if total_major else max(1, len(data.mistake_events))

    weaknesses: List[RecurringWeakness] = []
    for error_type, bucket in grouped.items():
        events_list = bucket["events"]  # type: ignore[assignment]
        games = bucket["games"]  # type: ignore[assignment]
        games_count = len(games)
        event_count = len(events_list)
        share = (int(bucket["major"]) / denominator) if denominator else 0.0
        average_loss = (
            float(bucket["loss_sum"]) / event_count if event_count else 0.0
        )
        confidence = _confidence(games_count, event_count, thresholds)
        label = decision_error_label_zh(_error_type(error_type))
        examples = [
            example_moment_from_row(row)
            for row in sorted(
                events_list, key=lambda item: -float(item.get("expected_score_loss") or 0.0)
            )[:MAX_EXAMPLES_PER_WEAKNESS]
        ]
        weaknesses.append(
            RecurringWeakness(
                error_type=_error_type(error_type),
                label_zh=label,
                event_count=event_count,
                share=round(share, 4),
                games=games_count,
                average_expected_score_loss=round(average_loss, 4),
                severity_mix=dict(bucket["severity_mix"]),  # type: ignore[arg-type]
                confidence=confidence,
                statement_zh=_statement(
                    label,
                    share,
                    games_count,
                    event_count,
                    confidence,
                    major_count=int(bucket["major"]),
                ),
                examples=examples,
            )
        )

    weaknesses.sort(
        key=lambda item: (
            -item.share,
            -item.event_count,
            -item.average_expected_score_loss,
        )
    )
    return weaknesses


def _confidence(games: int, events: int, thresholds: AnalysisThresholds) -> str:
    if games < thresholds.profile_recurring_min_games or events < thresholds.profile_recurring_min_events:
        return "insufficient"
    if games >= 8 and events >= 15:
        return "medium"
    return "low"


def _statement(
    label: str,
    share: float,
    games: int,
    events: int,
    confidence: str,
    major_count: int = 0,
) -> str:
    prefix = {
        "insufficient": "目前观察到",
        "low": "初步来看",
        "medium": "从数据看",
    }.get(confidence, "目前观察到")
    if major_count == 0:
        return "{}：{}，目前只出现在「不够精确」的着法里，还没有造成重大失误（{} 局中共 {} 次）。".format(
            prefix, label, games, events
        )
    return "{}：{}，占重大失误的 {:.0f}%（{} 局游戏中共 {} 次）。".format(
        prefix, label, share * 100, games, events
    )


def _error_type(value: str) -> DecisionErrorType:
    try:
        return DecisionErrorType(value)
    except ValueError:
        return DecisionErrorType.UNKNOWN


def _build_phases(data: ProfileInput, total_events: int) -> List[PhaseBreakdown]:
    result: List[PhaseBreakdown] = []
    by_phase = {str(row["phase"]): row for row in data.phase_counts}
    for phase in GamePhase:
        row = by_phase.get(phase.value)
        events = int(row["events"]) if row else 0
        result.append(
            PhaseBreakdown(
                phase=phase,
                label_zh=PHASE_LABELS_ZH.get(phase, phase.value),
                events=events,
                share=round(events / total_events, 4) if total_events else 0.0,
                average_expected_score_loss=round(
                    float(row["average_loss"]) if row else 0.0, 4
                ),
            )
        )
    return result


def _build_concepts(data: ProfileInput, total_events: int) -> List[ConceptFrequency]:
    result: List[ConceptFrequency] = []
    for row in data.concept_counts[:12]:
        try:
            concept = ConceptType(str(row["concept"]))
        except ValueError:
            continue
        count = int(row["count"])
        result.append(
            ConceptFrequency(
                concept=concept,
                label_zh=concept_label_zh(concept),
                count=count,
                share=round(count / total_events, 4) if total_events else 0.0,
            )
        )
    return result


def _build_trend(data: ProfileInput) -> tuple:
    points = [
        TrendPoint(
            game_id=str(row["game_id"]),
            created_at=row.get("created_at"),  # type: ignore[arg-type]
            average_expected_score_loss=round(float(row["average_loss"] or 0.0), 4),
            problems=int(row["problems"] or 0),
            blunders=int(row["blunders"] or 0),
            label=str(row.get("label", "")),
        )
        for row in data.game_trend
    ]

    if len(points) < TREND_WINDOW * 2:
        return points, TrendSummary(
            available=False,
            statement_zh="目前只有 {} 局数据，样本不足以判断趋势（至少需要 {} 局）。".format(
                len(points), TREND_WINDOW * 2
            ),
        )

    recent = points[-TREND_WINDOW:]
    earlier = points[-TREND_WINDOW * 2 : -TREND_WINDOW]
    recent_avg = sum(point.average_expected_score_loss for point in recent) / len(recent)
    earlier_avg = sum(point.average_expected_score_loss for point in earlier) / len(earlier)
    delta = recent_avg - earlier_avg
    if delta <= -0.01:
        direction, wording = "improving", "最近 {} 局的期望得分损失比之前更低"
    elif delta >= 0.01:
        direction, wording = "worsening", "最近 {} 局的期望得分损失比之前更高"
    else:
        direction, wording = "flat", "最近 {} 局的期望得分损失与之前基本持平"

    return points, TrendSummary(
        available=True,
        statement_zh="{}（{:.3f} vs {:.3f}）。".format(
            wording.format(TREND_WINDOW), recent_avg, earlier_avg
        ),
        direction=direction,
        recent_average_loss=round(recent_avg, 4),
        earlier_average_loss=round(earlier_avg, 4),
    )


def _sample_note(total_games: int, total_events: int) -> str:
    if total_games == 0:
        return "还没有分析过对局。"
    if total_games < 3 or total_events < 5:
        return (
            "目前只分析了 {} 局、{} 个失误，样本太少，下面的分类只能作为观察，"
            "不能当作稳定结论。".format(total_games, total_events)
        )
    if total_games < 8:
        return (
            "已分析 {} 局、{} 个失误。样本量仍偏小，结论仅供参考；"
            "继续积累后趋势判断会更可靠。".format(total_games, total_events)
        )
    return "已分析 {} 局、{} 个失误，统计有一定的参考价值。".format(total_games, total_events)
