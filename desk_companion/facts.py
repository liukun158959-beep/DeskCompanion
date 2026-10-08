"""跨线程事实：一份 memory/facts.json。模型用工具写，人在记忆页写。

不做向量库，不从对话里再抽一次。对话窗口仍在 memory.py。
"""
from __future__ import annotations

import contextvars
import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
FACT_LIMIT = 30
FACT_MAX = 80
QUOTE_MAX = 200
WRITERS = ("user", "model")
BROKEN = (
    "memory/facts.json 坏了，这一轮不能开口。"
    "恢复：删掉或修好 desk-companion/memory/facts.json。"
)

from .resource_lock import ResourceLock
_LOCK = ResourceLock("facts")
_TURN_USER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "desk_fact_user", default=None
)


def facts_path() -> Path:
    from .memory import memory_path

    return memory_path().parent / "facts.json"


@contextmanager
def bind_turn_user(text: str | None):
    """这一轮用来核对原话的用户消息。时钟前缀和技能正文不要绑进来。"""
    token = _TURN_USER.set(text)
    try:
        yield
    finally:
        _TURN_USER.reset(token)


def read_facts() -> list[dict]:
    """缺文件是空列表。结构坏了抛 RuntimeError。"""
    with _LOCK:
        return [dict(item) for item in _read_unlocked()]


def facts_prompt() -> str:
    """拼进系统提示。空清单也要写明：嘴上说记住了不算。"""
    items = read_facts()
    lines = [
        "跨对话还在的事实在 memory/facts.json。"
        "只有 remember_fact 的返回里有「已记下」、forget_fact 的返回里有「已忘掉」，才算记住或忘掉。"
        "嘴上说记住了不算。日程、仓库数量、工具结果不要记。",
    ]
    if not items:
        lines.append("当前没有事实。")
    else:
        lines.append("已有事实：")
        for item in items:
            lines.append(f"- {item['text']}")
    return "\n".join(lines)


def remember_fact(args: dict) -> str:
    """工具：原话对不上、空句、重复、超长、写满，都不落盘。"""
    try:
        if not isinstance(args, dict):
            return _remember_fail("参数不是对象")
        text = args.get("text")
        quote = args.get("quote")
        if type(text) is not str or type(quote) is not str:
            return _remember_fail("事实和原话必须是字符串")
        user = _TURN_USER.get()
        if type(user) is not str or not user.strip():
            return _remember_fail("这一轮没有用户消息，不能记")
        problem = _fact_problem(text)
        if problem:
            return _remember_fail(problem)
        quote_text = quote.strip()
        if not quote_text:
            return _remember_fail("没有给出依据的用户原话")
        if len(quote_text) > QUOTE_MAX:
            return _remember_fail(f"依据的原话超过 {QUOTE_MAX} 字")
        if quote_text not in user:
            return _remember_fail("依据的原话不在这一轮用户消息里")
        fact = text.strip()
        with _LOCK:
            items = _read_unlocked()
            if any(item["text"] == fact for item in items):
                return _remember_fail("这句话已经在事实里")
            if len(items) >= FACT_LIMIT:
                return _remember_fail(f"事实已经写满 {FACT_LIMIT} 条，先删一条再记")
            items.append(
                {
                    "id": uuid.uuid4().hex,
                    "text": fact,
                    "writer": "model",
                    "quote": quote_text,
                    "updated": _now(),
                }
            )
            _write_unlocked(items)
        return f"已记下：{fact}"
    except Exception as exc:
        return _remember_fail(str(exc))


def forget_fact(args: dict) -> str:
    """工具：整句相等才删。"""
    try:
        if not isinstance(args, dict):
            return _forget_fail("参数不是对象")
        text = args.get("text")
        if type(text) is not str:
            return _forget_fail("要忘掉的句子必须是字符串")
        fact = text.strip()
        if not fact:
            return _forget_fail("要忘掉的句子是空的")
        with _LOCK:
            items = _read_unlocked()
            kept = [item for item in items if item["text"] != fact]
            if len(kept) == len(items):
                return _forget_fail("没有整句相同的事实")
            _write_unlocked(kept)
        return f"已忘掉：{fact}"
    except Exception as exc:
        return _forget_fail(str(exc))


def add_user_fact(text: str) -> None:
    """记忆页新增。失败抛出原因，不写盘。"""
    problem = _fact_problem(text)
    if problem:
        raise RuntimeError(problem + "。")
    fact = text.strip()
    with _LOCK:
        items = _read_unlocked()
        if any(item["text"] == fact for item in items):
            raise RuntimeError("这句话已经在事实里。")
        if len(items) >= FACT_LIMIT:
            raise RuntimeError(f"事实已经写满 {FACT_LIMIT} 条，先删一条再记。")
        items.append(
            {
                "id": uuid.uuid4().hex,
                "text": fact,
                "writer": "user",
                "quote": "",
                "updated": _now(),
            }
        )
        _write_unlocked(items)


def update_user_fact(fact_id: str, text: str) -> None:
    """人改一句。句子变了就把来源改成你，并清掉依据原话。"""
    if type(fact_id) is not str or not fact_id.strip():
        raise RuntimeError("没有这条事实。")
    problem = _fact_problem(text)
    if problem:
        raise RuntimeError(problem + "。")
    fact = text.strip()
    with _LOCK:
        items = _read_unlocked()
        idx = _find_id(items, fact_id.strip())
        if items[idx]["text"] == fact:
            return
        if any(item["text"] == fact for i, item in enumerate(items) if i != idx):
            raise RuntimeError("这句话已经在事实里。")
        items[idx]["text"] = fact
        items[idx]["writer"] = "user"
        items[idx]["quote"] = ""
        items[idx]["updated"] = _now()
        _write_unlocked(items)


def delete_user_fact(fact_id: str) -> None:
    if type(fact_id) is not str or not fact_id.strip():
        raise RuntimeError("没有这条事实。")
    with _LOCK:
        items = _read_unlocked()
        kept = [item for item in items if item["id"] != fact_id.strip()]
        if len(kept) == len(items):
            raise RuntimeError("没有这条事实。")
        _write_unlocked(kept)


REMEMBER_SPEC = {
    "func": remember_fact,
    "name": "remember_fact",
    "description": (
        "用户说出要跨对话记住的事实时调用。"
        "text 是一句不超过 80 字的事实。"
        "quote 必须是这一轮用户原话里的连续片段，不能是推断或工具结果。"
        "返回里没有「已记下」就不许说已经记住。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "一句事实，不超过 80 字"},
            "quote": {"type": "string", "description": "这一轮用户原话里的连续片段"},
        },
        "required": ["text", "quote"],
    },
    "isReadOnly": False,
    "retry_max": 0,
}

FORGET_SPEC = {
    "func": forget_fact,
    "name": "forget_fact",
    "description": (
        "用户要忘掉某条事实时调用。text 必须和已有事实整句相同。"
        "返回里没有「已忘掉」就不许说已经忘掉。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要忘掉的事实，必须整句相同"},
        },
        "required": ["text"],
    },
    "isReadOnly": False,
    "retry_max": 0,
}


def _remember_fail(reason: str) -> str:
    return f"{reason}，没有写入。不要说已经记住。"


def _forget_fail(reason: str) -> str:
    return f"{reason}，没有删除。不要说已经忘掉。"


def _fact_problem(text: str) -> str | None:
    if type(text) is not str:
        return "事实必须是字符串"
    fact = text.strip()
    if not fact:
        return "事实是空的"
    if len(fact) > FACT_MAX:
        return f"事实超过 {FACT_MAX} 字"
    return None


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _find_id(items: list[dict], fact_id: str) -> int:
    for idx, item in enumerate(items):
        if item["id"] == fact_id:
            return idx
    raise RuntimeError("没有这条事实。")


def _read_unlocked() -> list[dict]:
    path = facts_path()
    if not path.exists():
        return []
    if not path.is_file():
        raise RuntimeError(BROKEN)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(BROKEN) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise RuntimeError(BROKEN)
    items: list[dict] = []
    seen_id: set[str] = set()
    seen_text: set[str] = set()
    for row in raw["items"]:
        item = _checked_item(row)
        if item["id"] in seen_id or item["text"] in seen_text:
            raise RuntimeError(BROKEN)
        seen_id.add(item["id"])
        seen_text.add(item["text"])
        items.append(item)
    if len(items) > FACT_LIMIT:
        raise RuntimeError(BROKEN)
    return items


def _checked_item(row: object) -> dict:
    if not isinstance(row, dict):
        raise RuntimeError(BROKEN)
    fact_id = row.get("id")
    text = row.get("text")
    writer = row.get("writer")
    quote = row.get("quote")
    updated = row.get("updated")
    if type(fact_id) is not str or not fact_id.strip():
        raise RuntimeError(BROKEN)
    if type(text) is not str or not text.strip() or text != text.strip() or len(text) > FACT_MAX:
        raise RuntimeError(BROKEN)
    if writer not in WRITERS:
        raise RuntimeError(BROKEN)
    if type(quote) is not str or len(quote) > QUOTE_MAX:
        raise RuntimeError(BROKEN)
    if writer == "model" and not quote.strip():
        raise RuntimeError(BROKEN)
    if writer == "user" and quote != quote.strip():
        raise RuntimeError(BROKEN)
    if type(updated) is not str or not updated.strip():
        raise RuntimeError(BROKEN)
    try:
        stamp = datetime.fromisoformat(updated)
    except ValueError as exc:
        raise RuntimeError(BROKEN) from exc
    if stamp.tzinfo is None:
        raise RuntimeError(BROKEN)
    return {
        "id": fact_id,
        "text": text,
        "writer": writer,
        "quote": quote,
        "updated": updated,
    }


def _write_unlocked(items: list[dict]) -> None:
    path = facts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": items}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
