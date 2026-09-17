"use client";

import { Chessboard, type Arrow } from "react-chessboard";

import type { Color } from "@/lib/types";

export interface BoardArrow {
  from: string;
  to: string;
  color?: string;
}

interface BoardProps {
  fen: string;
  orientation: Color;
  squareColors?: Record<string, string>;
  /** Last move actually played on this position (red square highlight). */
  lastMove?: { from: string; to: string } | null;
  /** Engine recommendation. Only valid on the position it was computed for. */
  bestMoveArrow?: BoardArrow | null;
  /** The move that was actually played, drawn as an arrow (used at a decision point). */
  playedArrow?: BoardArrow | null;
}

const ENGINE_ARROW_COLOR = "#4f9cf9";
const PLAYED_ARROW_COLOR = "#f2645a";

/**
 * The chessboard.
 *
 * Dragging is disabled on purpose: this is a review tool, so the board only ever
 * *shows* verified positions.
 *
 * Arrow convention: blue = the engine's recommendation, red = the move that was
 * actually played. Both arrows are only ever drawn on the position they belong to —
 * an engine move computed for "before the move" is not legal after it, so the caller
 * must not pass it while showing a later position.
 */
export default function Board({
  fen,
  orientation,
  squareColors = {},
  lastMove = null,
  bestMoveArrow = null,
  playedArrow = null,
}: BoardProps) {
  const squareStyles: Record<string, React.CSSProperties> = {};
  for (const [square, color] of Object.entries(squareColors)) {
    squareStyles[square] = { backgroundColor: color };
  }
  if (lastMove) {
    squareStyles[lastMove.from] = {
      ...(squareStyles[lastMove.from] ?? {}),
      backgroundColor: "rgba(242, 100, 90, 0.45)",
    };
    squareStyles[lastMove.to] = {
      ...(squareStyles[lastMove.to] ?? {}),
      backgroundColor: "rgba(242, 100, 90, 0.55)",
    };
  }

  const boardArrows: Arrow[] = [];
  if (playedArrow) {
    boardArrows.push({
      startSquare: playedArrow.from,
      endSquare: playedArrow.to,
      color: playedArrow.color ?? PLAYED_ARROW_COLOR,
    });
  }
  if (bestMoveArrow) {
    boardArrows.push({
      startSquare: bestMoveArrow.from,
      endSquare: bestMoveArrow.to,
      color: bestMoveArrow.color ?? ENGINE_ARROW_COLOR,
    });
  }

  return (
    <div className="w-full">
      <Chessboard
        options={{
          id: "review-board",
          position: fen,
          boardOrientation: orientation,
          allowDragging: false,
          allowDrawingArrows: false,
          showAnimations: false,
          animationDurationInMs: 0,
          showNotation: true,
          arrows: boardArrows,
          squareStyles,
          darkSquareStyle: { backgroundColor: "#4a5a78" },
          lightSquareStyle: { backgroundColor: "#c8d2e3" },
          darkSquareNotationStyle: { color: "#c8d2e3" },
          lightSquareNotationStyle: { color: "#4a5a78" },
          boardStyle: {
            borderRadius: "0.5rem",
            overflow: "hidden",
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
          },
        }}
      />
      <div
        className="mt-2 flex flex-wrap items-center gap-3 text-xs"
        style={{ color: "var(--muted)" }}
      >
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2 w-4 rounded"
            style={{ background: ENGINE_ARROW_COLOR }}
          />
          引擎推荐走法
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2 w-4 rounded"
            style={{ background: PLAYED_ARROW_COLOR }}
          />
          实战走法
        </span>
      </div>
    </div>
  );
}
