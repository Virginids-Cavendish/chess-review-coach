"""LLM provider boundary.

The rest of the application knows only :class:`LLMProvider`. DeepSeek is implemented
here because it speaks the OpenAI-compatible chat-completions protocol, so swapping in
any other OpenAI-compatible endpoint is a configuration change (``DEEPSEEK_BASE_URL`` /
``DEEPSEEK_MODEL``), not a code change.

The API key stays server-side: it is read from the environment and never leaves this
process.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

#: Guard against a provider returning a wall of text where JSON was requested.
MAX_RESPONSE_CHARS = 20000

_FENCE_PATTERN = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass
class LLMResult:
    """Outcome of one LLM call: data on success, a user-facing error otherwise."""

    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    model: Optional[str] = None
    raw_text: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.data is not None


class LLMProvider(Protocol):
    """Minimal interface every provider must satisfy."""

    name: str
    model: str

    def complete_json(  # pragma: no cover - protocol
        self, *, system: str, user: str, temperature: Optional[float] = None
    ) -> LLMResult:
        ...


class DeepSeekProvider:
    """DeepSeek (OpenAI-compatible) chat completions with JSON output."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 60.0,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete_json(
        self, *, system: str, user: str, temperature: Optional[float] = None
    ) -> LLMResult:
        if not self._api_key:
            return LLMResult(error="missing_api_key")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature if temperature is None else temperature,
            "max_tokens": self._max_tokens,
            # DeepSeek supports OpenAI-style JSON mode; the prompt already pins the schema.
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        url = "{}/chat/completions".format(self._base_url)

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    headers={
                        "Authorization": "Bearer {}".format(self._api_key),
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException:
            return LLMResult(error="timeout", model=self.model)
        except httpx.HTTPError as exc:
            logger.warning("DeepSeek request failed: %s", exc)
            return LLMResult(error="network_error: {}".format(exc), model=self.model)

        if response.status_code == 401:
            return LLMResult(error="unauthorized (check DEEPSEEK_API_KEY)", model=self.model)
        if response.status_code == 429:
            return LLMResult(error="rate_limited", model=self.model)
        if response.status_code >= 400:
            return LLMResult(
                error="http_{}: {}".format(response.status_code, response.text[:300]),
                model=self.model,
            )

        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return LLMResult(error="malformed_response: {}".format(exc), model=self.model)

        if not isinstance(text, str) or not text.strip():
            return LLMResult(error="empty_response", model=self.model)
        if len(text) > MAX_RESPONSE_CHARS:
            return LLMResult(error="response_too_large", model=self.model)

        parsed = _parse_json(text)
        if parsed is None:
            return LLMResult(error="invalid_json", model=self.model, raw_text=text[:2000])
        return LLMResult(data=parsed, model=self.model, raw_text=text)


class NullProvider:
    """The "no API key configured" provider: always fails, cheaply and explicitly."""

    name = "none"
    model = ""

    def complete_json(
        self, *, system: str, user: str, temperature: Optional[float] = None
    ) -> LLMResult:
        return LLMResult(error="llm_not_configured")


#: 把 provider 的英文错误翻译成"用户下一步该做什么"。
def humanize_error(error: Optional[str], timeout: float = 60.0) -> str:
    if not error:
        return "未知错误。"

    if error in ("missing_api_key", "llm_not_configured"):
        return (
            "还没有配置 DEEPSEEK_API_KEY。请在项目根目录创建 .env 文件并写入 "
            "DEEPSEEK_API_KEY=你的密钥，然后重启后端。"
        )
    if error.startswith("unauthorized"):
        return (
            "密钥无效（HTTP 401）。请确认：① 整串密钥都复制过来了，没有多余空格或换行；"
            "② 密钥没有过期或被删除；③ .env 里没有写成 DEEPSEEK_API_KEY=sk-xxx 之外的多余内容。"
        )
    if error == "rate_limited":
        return "请求过于频繁（HTTP 429）。稍等一会儿再试；如果一直这样，检查账户余额是否充足。"
    if error.startswith("http_402") or "insufficient balance" in error.lower():
        return "账户余额不足（HTTP 402）。请到 DeepSeek 控制台充值后再试。"
    if error.startswith("http_401"):
        return "密钥无效（HTTP 401），检查方式同上。"
    if error.startswith("http_403"):
        return "没有访问权限（HTTP 403）。可能是密钥被限制，或该模型未开通。"
    if error.startswith("http_404"):
        return (
            "接口地址或模型名不对（HTTP 404）。检查 DEEPSEEK_BASE_URL 是否写成 "
            "https://api.deepseek.com（结尾不要加 /v1/chat/completions），"
            "以及 DEEPSEEK_MODEL 是否是服务商支持的模型名。"
        )
    if error.startswith("http_5"):
        return "服务商返回了服务器错误（5xx）。这通常是对方临时故障，稍后重试。"
    if error.startswith("http_"):
        return "服务商返回了 HTTP 错误：{}".format(error)
    if error == "timeout":
        return (
            "请求超时（默认 {} 秒）。可以调大 .env 里的 LLM_TIMEOUT；"
            "如果本机需要代理才能访问外网，请确认代理对 Python 进程生效。".format(int(timeout))
        )
    if error.startswith("network_error"):
        return (
            "网络连接失败：{}。国内网络一般可以直连 api.deepseek.com；"
            "如果你在用代理，请设置 HTTPS_PROXY 环境变量后再启动后端。".format(error)
        )
    if error == "invalid_json":
        return "对方返回的内容不是合法 JSON。通常是模型名不对，或该服务不支持 JSON 输出模式。"
    if error == "empty_response":
        return "对方返回了空内容。稍后重试，或换一个模型。"
    if error.startswith("malformed_response"):
        return "返回结构不符合预期：{}。检查 DEEPSEEK_BASE_URL 是否指向 OpenAI 兼容接口。".format(error)
    if error == "response_too_large":
        return "返回内容过大，已拒绝。"
    return error


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON object, tolerating markdown fences and leading prose."""
    cleaned = _FENCE_PATTERN.sub("", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def build_provider(
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> LLMProvider:
    """Factory used by the service layer; returns NullProvider when unconfigured."""
    if not api_key.strip():
        return NullProvider()
    return DeepSeekProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
