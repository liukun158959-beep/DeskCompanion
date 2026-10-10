"""联网搜索。走当前设置里的 API 地址 /v1/tool/search，和对话同一把 Key。"""
from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request

QUERY_MAX = 200
SOURCE_LIMIT = 5
TIMEOUT_S = 30
REQUEST_BUDGET_S = 60


class RetryableSearchError(RuntimeError):
    """仅用于网络或搜索服务的临时故障。"""

SEARCH_HINT = (
    "联网搜索走当前模型的 API。"
    "打开主窗「设置」，API 地址要以 /v1 结尾，Key 用现在这把。"
)


def search_endpoint(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url.endswith("/v1"):
        raise RuntimeError(SEARCH_HINT)
    return url + "/tool/search"


def format_search(payload: dict) -> str:
    """收成标题、摘要和链接。没有可用链接就失败。"""
    if not isinstance(payload, dict):
        raise RuntimeError("联网搜索返回不是对象。不要编。")
    if payload.get("error") and "results" not in payload:
        raise RuntimeError(f"联网搜索失败：{payload.get('error')} 不要编。")
    rows = payload.get("results")
    if type(rows) is not list or not rows:
        message = str(payload.get("message") or "").strip()
        if message:
            raise RuntimeError(f"联网搜索失败：{message} 不要编。")
        raise RuntimeError("没有搜到结果。不要编。")
    lines = ["来源："]
    kept = 0
    skipped = 0
    for row in rows:
        if kept >= SOURCE_LIMIT:
            break
        if not isinstance(row, dict):
            skipped += 1
            continue
        title = str(row.get("title") or "").strip()
        link = str(row.get("link") or "").strip()
        if not title or not (link.startswith("https://") or link.startswith("http://")):
            skipped += 1
            continue
        kept += 1
        lines.append(f"{kept}. {title}")
        lines.append(link)
        snippet = str(row.get("snippet") or "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + "（摘要后面没带上）"
        if snippet:
            lines.append(snippet)
        published = str(row.get("published_date") or "").strip()
        if published:
            lines.append(f"日期：{published}")
    if kept == 0:
        raise RuntimeError("搜索结果没有可用的标题和链接。不要编。")
    extra = len(rows) - kept - skipped
    if extra > 0:
        lines.append(f"还有 {extra} 条来源没列出。")
    if skipped:
        lines.append(f"有 {skipped} 条缺少标题或链接，没有列入。")
    lines.append("本次搜索只提供标题、摘要和链接，未读取来源全文。引用本次搜索时只用这些内容支持的结论，对不上就不要采用；与视频字幕等其他来源分开标明。")
    return "\n".join(lines)


def web_search(args: dict, *, on_status=None) -> str:
    cfg = {}
    try:
        if not isinstance(args, dict):
            raise RuntimeError("搜索参数不是对象，没有搜索。不要编。")
        query = args.get("query")
        if type(query) is not str or not query.strip():
            raise RuntimeError("搜索词是空的，没有搜索。不要编。")
        text = query.strip()
        if len(text) > QUERY_MAX:
            raise RuntimeError(f"搜索词超过 {QUERY_MAX} 字，没有搜索。不要编。")
        from .envconf import require_llm_env

        cfg = require_llm_env()
        endpoint = search_endpoint(cfg["ATLAS_BASE_URL"])
        payload = _post(endpoint, cfg["ATLAS_API_KEY"], text, on_status=on_status)
        return format_search(payload)
    except Exception as exc:
        message = str(exc).strip() or "联网搜索失败。"
        if cfg.get("ATLAS_API_KEY"):
            message = message.replace(cfg["ATLAS_API_KEY"], "[密钥已隐藏]")
        if "不要编" not in message:
            message += " 不要编。"
        # Atlas 根据异常记录真实失败，仍会把错误交给模型解释。
        raise RuntimeError(message) from None


WEB_SEARCH_SPEC = {
    "func": web_search,
    "name": "web_search",
    "description": (
        "搜索互联网上的实时信息。用户问天气、新闻、现在、最新、网上才有的事，"
        "或这一轮指定必须调用 web_search 时使用。"
        "也用于读取视频字幕后，核实关键争议或时效性事实，优先搜索官方资料；不能代替读取视频。"
        "query 是一句搜索词，不超过 200 字。"
        "只根据返回的来源标题、摘要和链接回答。失败或没有结果就原样说明，不要编。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索词，不超过 200 字"},
        },
        "required": ["query"],
    },
    "isReadOnly": True,
    "retry_max": 0,
}


def _post(endpoint: str, api_key: str, query: str, *, on_status=None) -> dict:
    deadline = time.monotonic() + REQUEST_BUDGET_S
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("联网搜索超时。恢复：稍后重试。")
        try:
            return _post_once(endpoint, api_key, query, min(TIMEOUT_S, remaining))
        except RetryableSearchError:
            if attempt == 1 or deadline - time.monotonic() <= .5:
                raise
            if on_status:
                on_status("联网搜索遇到临时网络错误，正在重试一次。")
            time.sleep(.5)
    raise RuntimeError("联网搜索失败。")


def _temporary_message(message: str) -> bool:
    text = message.lower()
    if any(term in text for term in ("certificate", "cert_verify", "invalid_client", "unauthorized", "forbidden")):
        return False
    return any(term in text for term in ("timeout", "timed out", "超时", "connection reset", "temporarily unavailable"))


def _post_once(endpoint: str, api_key: str, query: str, timeout: float) -> dict:
    body = {
        "crawl_results": 0,
        "max_results": SOURCE_LIMIT,
        "query": query,
        "search_service": "google",
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=raw,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except TimeoutError as exc:
        raise RetryableSearchError("联网搜索超时。恢复：稍后重试。") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        error = RetryableSearchError if exc.code in {408, 429, 500, 502, 503, 504} else RuntimeError
        raise error(_http_error(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        temporary = not isinstance(reason, ssl.SSLCertVerificationError) and (
            isinstance(reason, (TimeoutError, ConnectionResetError, socket.gaierror)) or _temporary_message(str(reason)))
        # TLS 握手超时可能是 TimeoutError 或文本；证书校验错误不能通过重试掩盖。
        error = RetryableSearchError if temporary else RuntimeError
        raise error(f"联网搜索连不上。恢复：检查网络后再说一次。\n{reason}") from exc
    except ConnectionResetError as exc:
        raise RetryableSearchError("联网搜索连接中断。恢复：稍后重试。") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("联网搜索没有返回 JSON。不要编。") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("联网搜索返回不是对象。不要编。")
    # 服务端自身搜索上游失败时可能仍返回 HTTP 200。
    if not payload.get("results"):
        message = str(payload.get("error") or payload.get("message") or "")
        if _temporary_message(message):
            raise RetryableSearchError(f"联网搜索失败：{message} 不要编。")
    return payload


def _http_error(status: int, detail: str) -> str:
    message = ""
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("error") or payload.get("code") or "").strip()
    if not message:
        message = detail.strip()[:300]
    return f"联网搜索失败（HTTP {status}）。{message}"
