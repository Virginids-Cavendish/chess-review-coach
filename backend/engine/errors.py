"""Engine-layer exceptions with user-facing Chinese hints.

The API maps these to HTTP responses; the pipeline treats them as recoverable
(a game can be partially analyzed) rather than as fatal.
"""

from typing import Optional


class EngineError(Exception):
    """Base class for every engine problem."""

    #: Chinese, shown directly in the UI.
    hint_zh = "引擎出现问题。"
    http_status = 500

    def __init__(self, message: str, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class EngineNotFoundError(EngineError):
    hint_zh = (
        "没有找到 Stockfish。请运行 `python scripts/install_stockfish.py`，"
        "或在 .env 中设置 STOCKFISH_PATH 指向引擎可执行文件。"
    )
    http_status = 503


class EngineStartupError(EngineError):
    hint_zh = "Stockfish 无法启动，请检查文件是否可执行。"
    http_status = 503


class EngineTimeoutError(EngineError):
    hint_zh = "引擎分析超时（该局面可能过于复杂）。可以降低分析深度后重试。"
    http_status = 504


class EngineCrashedError(EngineError):
    hint_zh = "引擎进程异常退出，已自动重启。已完成的局面分析不会丢失。"
    http_status = 503


class PgnError(EngineError):
    """Kept in this module so callers have a single import for user-facing failures."""

    hint_zh = "PGN 无法解析，请检查文本是否完整、是否为标准 PGN 格式。"
    http_status = 400
