"use client";

import type { CriticalMoment } from "@/lib/types";
import {
  CRITICALITY_REASON_LABELS,
  SEVERITY_BADGE,
  conceptLabel,
  decisionErrorLabel,
  formatEval,
  formatLoss,
  severityLabel,
} from "@/lib/labels";

interface CriticalMomentCardProps {
  moment: CriticalMoment;
  index: number;
  selected: boolean;
  onSelect: (ply: number) => void;
}

/**
 * One card per position worth reviewing.
 *
 * The card shows the verified facts only (played move, severity, expected-score change,
 * detected concepts). The prose lives in the explanation panel, so a user can always
 * tell which part is a fact and which part is coaching.
 */
export default function CriticalMomentCard({
  moment,
  index,
  selected,
  onSelect,
}: CriticalMomentCardProps) {
  const engine = moment.evidence.engine;
  const concepts = moment.evidence.concepts.slice(0, 4);
  const errors = moment.evidence.decision_errors.slice(0, 2);

  return (
    <button
      type="button"
      onClick={() => onSelect(moment.ply)}
      className={`w-full rounded-lg border p-3 text-left transition ${
        selected ? "ring-2 ring-amber-500/70" : "hover:border-slate-500"
      }`}
      style={{ background: "var(--panel)", borderColor: "var(--border)" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            关键局面 {index + 1}
          </span>
          <span className="mono text-base font-semibold">
            {moment.move_number}. {moment.played_move_san}
          </span>
          <span
            className={`rounded px-1.5 py-0.5 text-xs ring-1 ${SEVERITY_BADGE[moment.severity]}`}
          >
            {severityLabel(moment.severity)}
          </span>
        </div>
        <span className="mono text-xs" style={{ color: "var(--muted)" }}>
          {formatEval(engine.evaluation_before, engine.mate_before)} →{" "}
          {formatEval(engine.evaluation_after, engine.mate_after)}
        </span>
      </div>

      <p className="mt-2 text-sm leading-relaxed">{moment.one_liner_zh}</p>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: "var(--muted)" }}>
        <span>
          期望得分损失 <span className="mono">{formatLoss(engine.expected_score_loss)}</span>
        </span>
        {engine.best_move_san ? (
          <span>
            引擎推荐 <span className="mono">{engine.best_move_san}</span>
          </span>
        ) : null}
        {moment.reasons.length > 0 ? (
          <span>
            {moment.reasons
              .map((reason) => CRITICALITY_REASON_LABELS[reason] ?? reason)
              .join(" · ")}
          </span>
        ) : null}
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {errors.map((error) => (
          <span key={error.type} className="tag tag-coach">
            {decisionErrorLabel(error.type)}
          </span>
        ))}
        {concepts.map((concept) => (
          <span key={concept.type} className="tag">
            {conceptLabel(concept.type)}
          </span>
        ))}
      </div>
    </button>
  );
}
