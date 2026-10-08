"""飞书云文档：列出我创建的 docx、覆盖写入、新建。复盘落盘用。"""
from __future__ import annotations

import json

from .feishu_auth import _first_json, create_markdown_doc
from .feishu_tools import AUTH_HINT, _run_lark


def list_my_docx() -> list[dict]:
    raw = _run_lark(
        [
            "drive",
            "+search",
            "--as",
            "user",
            "--query",
            "",
            "--created-by-me",
            "--doc-types",
            "docx",
            "--sort",
            "edit_time",
            "--page-size",
            "20",
            "--format",
            "json",
        ],
        timeout=60,
    )
    env = _as_object(raw, "搜索飞书文档")
    if env.get("ok") is False:
        raise RuntimeError(f"搜索飞书文档失败。{AUTH_HINT}\n{raw}")
    data = env.get("data")
    if not isinstance(data, dict):
        data = env
    rows = data.get("results")
    if rows is None:
        rows = data.get("items")
    if rows is None:
        rows = data.get("entities")
    if not isinstance(rows, list):
        raise RuntimeError(f"搜索飞书文档成功信封缺少 results。\n{raw}")
    out = []
    for item in rows:
        if not isinstance(item, dict):
            raise RuntimeError("搜索飞书文档的每一项必须是对象。")
        rec = _parse_search_hit(item)
        if rec is None:
            continue
        out.append(rec)
    return out


def overwrite_markdown_doc(doc: str, markdown: str) -> dict:
    target = (doc or "").strip()
    body = (markdown or "").strip()
    if not target:
        raise RuntimeError("覆盖写入需要飞书文档 URL 或 token。")
    if not body:
        raise RuntimeError("覆盖写入的正文为空。")
    raw = _run_lark(
        [
            "docs",
            "+update",
            "--as",
            "user",
            "--doc",
            target,
            "--command",
            "overwrite",
            "--doc-format",
            "markdown",
            "--content",
            "-",
        ],
        timeout=90,
        stdin=body,
    )
    env = _as_object(raw, "覆盖飞书文档")
    if env.get("ok") is False:
        raise RuntimeError(f"覆盖飞书文档失败。{AUTH_HINT}\n{raw}")
    url = target if target.startswith("http") else ""
    data = env.get("data")
    if isinstance(data, dict):
        url = str(data.get("url") or url)
    return {"ok": True, "url": url, "message": "复盘已覆盖写入所选飞书文档。"}


def create_or_overwrite_markdown(
    *, markdown: str, doc: str = "", title: str = ""
) -> dict:
    """选中文档则覆盖；否则必须有标题才新建。两者都空则失败。"""
    body = (markdown or "").strip()
    if not body:
        raise RuntimeError("还没有复盘正文。先在自动化任务「周复盘」里生成。")
    target = (doc or "").strip()
    heading = (title or "").strip()
    if target and heading:
        raise RuntimeError("覆盖已有文档时不要同时填新标题。选一篇，或只填标题新建。")
    if target:
        return overwrite_markdown_doc(target, body)
    if heading:
        created = create_markdown_doc(heading, body)
        return {
            "ok": True,
            "url": created["url"],
            "message": "复盘已写到新建的飞书文档，并打开了链接。",
        }
    raise RuntimeError("写入飞书要先选一篇已有文档，或填写新文档标题。")


def _as_object(raw: str, what: str) -> dict:
    try:
        env = json.loads(_first_json(raw))
    except (json.JSONDecodeError, RuntimeError) as exc:
        raise RuntimeError(f"{what}未返回 JSON。\n{raw}") from exc
    if not isinstance(env, dict):
        raise RuntimeError(f"{what}根节点不是对象。\n{raw}")
    return env


def _plain(text) -> str:
    if type(text) is not str:
        return ""
    return text.replace("<em>", "").replace("</em>", "").strip()


def _parse_search_hit(item: dict) -> dict | None:
    """drive +search 的 url/token 在 result_meta 里；知识库里的 docx 也算。"""
    meta = item.get("result_meta")
    if not isinstance(meta, dict):
        meta = {}
    entity = str(item.get("entity_type") or "").lower()
    doc_types = str(meta.get("doc_types") or item.get("doc_type") or "").lower()
    if entity in {"sheet", "bitable", "folder", "file", "slides", "mindnote"}:
        return None
    if doc_types and doc_types not in {"docx", "doc"}:
        return None
    url = (
        item.get("url")
        or meta.get("url")
        or item.get("docs_url")
        or item.get("link")
        or ""
    )
    token = (
        item.get("token")
        or meta.get("token")
        or item.get("doc_token")
        or item.get("docs_token")
        or item.get("obj_token")
        or ""
    )
    title = (
        item.get("title")
        or _plain(item.get("title_highlighted"))
        or meta.get("title")
        or item.get("name")
        or item.get("file_name")
        or ""
    )
    if not url and not token:
        raise RuntimeError(f"搜索结果缺少 url/token。\n{item}")
    return {
        "title": str(title) or "（无标题）",
        "url": str(url),
        "token": str(token),
    }


def fetch_docx_markdown(doc: str, label: str) -> str:
    """读一整篇 docx 的 markdown。没有正文就失败，不截断。"""
    target = (doc or "").strip()
    title = (label or "").strip() or "（无标题）"
    if not target or any(ch.isspace() for ch in target):
        raise RuntimeError(f"《{title}》没有可用的文档地址。")
    raw = _run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            target,
            "--doc-format",
            "markdown",
            "--detail",
            "simple",
            "--format",
            "json",
        ],
        timeout=60,
    )
    return markdown_from_fetch(raw, title)


def markdown_from_fetch(raw: str, label: str) -> str:
    title = (label or "").strip() or "（无标题）"
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"读取《{title}》未返回 JSON。\n{raw}")
    try:
        env, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"读取《{title}》未返回 JSON。\n{raw}") from exc
    if not isinstance(env, dict):
        raise RuntimeError(f"读取《{title}》根节点不是对象。\n{raw}")
    if env.get("ok") is False:
        raise RuntimeError(f"读取《{title}》失败。{AUTH_HINT}\n{raw}")
    data = env.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"读取《{title}》成功信封缺少 data。\n{raw}")
    document = data.get("document")
    if not isinstance(document, dict):
        raise RuntimeError(f"读取《{title}》成功信封缺少 document。\n{raw}")
    content = document.get("content")
    if type(content) is not str or not content.strip():
        raise RuntimeError(f"《{title}》没有正文。")
    return content


def doc_turn_block(docs: list) -> str:
    """点名文档的正文。只拼进发给模型的这一轮，不写入对话记录。"""
    if type(docs) is not list or not docs:
        raise RuntimeError("飞书文档点选必须是非空列表。")
    parts = ["【文档正文】"]
    for item in docs:
        if not isinstance(item, dict):
            raise RuntimeError("飞书文档点选的每一项必须是对象。")
        body = fetch_docx_markdown(str(item.get("id") or ""), str(item.get("label") or ""))
        title = str(item.get("label") or "").strip() or "（无标题）"
        parts.append(f"# {title}\n{body}")
    parts.append("以上就是飞书文档正文。只根据正文回答，不要编文档里没有的内容。")
    return "\n\n".join(parts)
