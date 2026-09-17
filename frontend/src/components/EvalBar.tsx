"use client";

import { clamp, formatEval, formatPercent } from "@/lib/labels";

interface EvalBarProps {
  /** Player-perspective evaluation in pawns (mate encoded as ±10 by the backend). */
  evaluation: number | null;
  mate: number | null;
  /** Expected score from the analyzed player's point of view. */
  expectedScore: number;
  orientation: "white" | "black";
  label?: string;
}

/**
 * Two related numbers, deliberately kept apart:
 *
 * * the bar is the *expected score* (win + 0.5·draw), which is what severity is based
 *   on, and
 * * the number is the raw engine evaluation, shown for reference.
 */
export default function EvalBar({
  evaluation,
  mate,
  expectedScore,
  orientation,
  label,
}: EvalBarProps) {
  const share = clamp(expectedScore, 0, 1);
  const whiteShare = orientation === "white" ? share : 1 - share;

  return (
    <div className="panel-soft p-3">
      <div className="mb-2 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
        <span>{label ?? "局面评估（你的一方）"}</span>
        <span className="mono">{formatEval(evaluation, mate)}</span>
      </div>
      <div className="flex h-3 w-full overflow-hidden rounded-full ring-1 ring-slate-700">
        <div style={{ width: `${whiteShare * 100}%`, background: "#e6ebf5" }} />
        <div style={{ width: `${(1 - whiteShare) * 100}%`, background: "#1b2438" }} />
      </div>
      <div className="mt-2 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
        <span>期望得分 {formatPercent(share)}</span>
        <span>（胜率 + ½ 和棋率）</span>
      </div>
    </div>
  );
}
