"""A small, honest opening-name lookup.

This is **not** an opening book and makes no attempt at ECO coverage. It matches the
opening moves of a game against a short curated list of lines a club player is likely
to meet, longest prefix first. If nothing matches, no name is shown — which is better
than a confident wrong label.

PGN files exported from Lichess/Chess.com usually carry an ``[Opening]`` header;
``analysis/pgn.py`` prefers that and only falls back to this table.
"""

from typing import Dict, List, Optional, Tuple

OpeningEntry = Tuple[Tuple[str, ...], str]

#: (SAN prefix, Chinese name). The prefix must match the game's opening moves exactly.
_OPENINGS: List[OpeningEntry] = [
    # --- 1.e4 e5 ---
    (("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "b4"), "伊文斯弃兵"),
    (("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"), "双马防御"),
    (("e4", "e5", "Nf3", "Nc6", "Bc4", "Be7"), "匈牙利防御"),
    (("e4", "e5", "Nf3", "Nc6", "Bc4"), "意大利开局"),
    (("e4", "e5", "Nf3", "Nc6", "Bb5"), "西班牙开局"),
    (("e4", "e5", "Nf3", "Nc6", "d4"), "苏格兰开局"),
    (("e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6"), "四马开局"),
    (("e4", "e5", "Nf3", "Nf6"), "俄罗斯防御（彼得罗夫）"),
    (("e4", "e5", "Nf3", "d6"), "菲利多尔防御"),
    (("e4", "e5", "Bc4"), "飞象开局"),
    (("e4", "e5", "Nc3"), "维也纳开局"),
    (("e4", "e5", "f4"), "王翼弃兵"),
    (("e4", "e5", "d4"), "中心开局"),
    (("e4", "e5"), "王兵开局（开放局面）"),
    # --- 1.e4, other replies ---
    (("e4", "c5", "Nf3", "d6", "d4"), "西西里防御（现代变例）"),
    (("e4", "c5", "Nf3", "Nc6", "d4"), "西西里防御（公开变例）"),
    (("e4", "c5", "Nc3"), "西西里防御（封闭变例）"),
    (("e4", "c5"), "西西里防御"),
    (("e4", "e6"), "法兰西防御"),
    (("e4", "c6"), "卡罗-卡恩防御"),
    (("e4", "d5"), "斯堪的纳维亚防御"),
    (("e4", "Nf6"), "阿廖欣防御"),
    (("e4", "d6"), "皮尔茨防御"),
    (("e4", "g6"), "现代防御"),
    (("e4", "b6"), "欧文防御"),
    # --- 1.d4 ---
    (("d4", "d5", "c4", "e6"), "拒后翼弃兵（含尼姆佐体系）"),
    (("d4", "d5", "c4", "c6"), "斯拉夫防御"),
    (("d4", "d5", "c4", "dxc4"), "接受后翼弃兵"),
    (("d4", "d5", "c4", "e5"), "阿尔宾弃兵"),
    (("d4", "d5", "c4"), "后翼弃兵"),
    (("d4", "d5", "Nf3", "Nf6", "Bf4"), "伦敦体系"),
    (("d4", "Nf6", "Nf3", "e6", "Bf4"), "伦敦体系"),
    (("d4", "Nf6", "Nf3", "g6", "Bf4"), "伦敦体系"),
    (("d4", "Nf6", "c4", "e6", "Nc3", "Bb4"), "尼姆佐-印度防御"),
    (("d4", "Nf6", "c4", "g6", "Nc3", "Bg7"), "王印度防御"),
    (("d4", "Nf6", "c4", "g6", "Nc3", "d5"), "格林菲尔德防御"),
    (("d4", "Nf6", "c4", "e6", "g3"), "卡塔兰开局"),
    (("d4", "Nf6", "c4", "e6"), "后兵开局（印度体系）"),
    (("d4", "Nf6", "c4", "g6"), "王印度体系"),
    (("d4", "Nf6", "Bg5"), "特罗姆波夫斯基攻击"),
    (("d4", "f5"), "荷兰防御"),
    (("d4", "d5"), "后兵开局（封闭）"),
    (("d4", "Nf6"), "后兵开局（印度防御体系）"),
    (("d4", "e6"), "后兵开局"),
    (("d4",), "后兵开局"),
    # --- others ---
    (("c4",), "英格兰开局"),
    (("Nf3", "d5", "g3"), "列蒂开局"),
    (("Nf3",), "列蒂开局"),
    (("f4",), "伯德开局"),
    (("b3",), "尼姆佐维奇-拉森攻击"),
    (("g3",), "匈牙利开局"),
    (("b4",), "索科尔斯基开局"),
]


def identify_opening(san_moves: List[str]) -> Optional[str]:
    """Longest-prefix match against the curated table; None when nothing fits."""
    best: Optional[OpeningEntry] = None
    for prefix, name in _OPENINGS:
        if len(prefix) > len(san_moves):
            continue
        if tuple(san_moves[: len(prefix)]) != prefix:
            continue
        if best is None or len(prefix) > len(best[0]):
            best = (prefix, name)
    return best[1] if best else None


def table_size() -> int:
    return len(_OPENINGS)


def as_dict() -> Dict[str, str]:
    """Read-only view used by tests and documentation."""
    return {" ".join(prefix): name for prefix, name in _OPENINGS}
