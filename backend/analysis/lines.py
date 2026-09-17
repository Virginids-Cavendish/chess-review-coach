"""把引擎线路展开成可以逐步演示的序列。

关键局面里引擎给的不只是一手棋，还有一整条主变例（PV）。这个模块把那条线路变成
"每一步之后的局面" 列表，前端就能像播放器一样一格一格走过去，不需要自己实现棋规。

棋规只在 python-chess 这一处实现，前端永远不自己判断合法性——走不动就停在原地并
标记线路不完整。
"""

from typing import List, Sequence

import chess

from models.api import LineStep, LineWalk
from models.enums import Color


def walk_line(
    start_fen: str,
    uci_moves: Sequence[str],
    kind: str,
    label_zh: str,
    pv_limit_reached: bool = False,
) -> LineWalk:
    """从 ``start_fen`` 开始逐走着法，返回每一步之后的局面。

    ``pv_limit_reached`` 表示这条线路本身就是被截断保存的（引擎 PV 只留前若干步），
    和"走不动了"是两回事，所以分开标记。
    """
    board = chess.Board(start_fen)
    start_board = board.copy()
    steps: List[LineStep] = []
    complete = True

    for uci in uci_moves:
        move = next((candidate for candidate in board.legal_moves if candidate.uci() == uci), None)
        if move is None:
            # 线路里出现了在当前局面走不动的着法（数据不完整或局面被改动过）。
            complete = False
            break
        mover = Color.WHITE if board.turn == chess.WHITE else Color.BLACK
        san = board.san(move)
        board.push(move)
        steps.append(LineStep(uci=uci, san=san, fen_after=board.fen(), mover=mover))

    return LineWalk(
        kind=kind,
        label_zh=label_zh,
        steps=steps,
        complete=complete,
        truncated=pv_limit_reached,
        start_fen=start_board.fen(),
        final_fen=board.fen(),
        ends_in_mate=board.is_checkmate(),
    )
