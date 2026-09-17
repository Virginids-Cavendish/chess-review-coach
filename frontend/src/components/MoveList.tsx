"use client";

import type { MoveAssessment } from "@/lib/types";
import { SEVERITY_BADGE, SEVERITY_DOT, severityLabel } from "@/lib/labels";

interface MoveListProps {
  moves: MoveAssessment[];
  currentPly: number;
  onSelect: (ply: number) => void;
}

/**
 * The full move list with lightweight labels.
 *
 * Every move gets a severity dot so the game can be scanned quickly, but only the
 * critical ones carry a marker — the review deliberately does not comment on every move.
 */
export default function MoveList({ moves, currentPly, onSelect }: MoveListProps) {
  const rows: { number: number; white?: MoveAssessment; black?: MoveAssessment }[] = [];
  for (const move of moves) {
    const index = move.move_number - 1;
    if (!rows[index]) rows[index] = { number: move.move_number };
    if (move.color === "white") rows[index].white = move;
    else rows[index].black = move;
  }

  return (
    <div className="panel overflow-hidden">
      <div
        className="flex items-center justify-between border-b px-3 py-2 text-xs"
        style={{ borderColor: "var(--border)", color: "var(--muted)" }}
      >
        <span>着法列表</span>
        <span>{moves.length} 个半回合</span>
      </div>
      <div className="max-h-[420px] overflow-y-auto">
        <table className="w-full text-sm">
          <tbody>
            {rows.map((row) => (
              <tr key={row.number} className="border-b last:border-b-0" style={{ borderColor: "var(--border)" }}>
                <td className="w-10 px-2 py-1 text-right text-xs" style={{ color: "var(--muted)" }}>
                  {row.number}.
                </td>
                {[row.white, row.black].map((move, index) => (
                  <td key={index} className="px-1 py-1">
                    {move ? (
                      <button
                        type="button"
                        onClick={() => onSelect(move.ply)}
                        title={
                          move.best_move_san
                            ? move.is_engine_best
                              ? "引擎首选就是这一手"
                              : "引擎推荐 " + move.best_move_san
                            : undefined
                        }
                        className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left transition ${
                          currentPly === move.ply ? "bg-slate-700/60" : "hover:bg-slate-800/60"
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${SEVERITY_DOT[move.severity ?? "good"]}`} />
                        <span className="mono">{move.san}</span>
                        {move.is_critical ? (
                          <span className="tag tag-coach ml-auto">关键</span>
                        ) : move.severity && move.severity !== "best" && move.severity !== "good" ? (
                          <span
                            className={`ml-auto rounded px-1.5 py-0.5 text-[10px] ring-1 ${
                              SEVERITY_BADGE[move.severity]
                            }`}
                          >
                            {severityLabel(move.severity)}
                          </span>
                        ) : null}
                      </button>
                    ) : (
                      <span className="block px-2 py-1" style={{ color: "var(--muted)" }}>
                        …
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
