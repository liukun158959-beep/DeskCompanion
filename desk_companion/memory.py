"""本地对话记忆：jsonl，按 session 分线程。不做向量库。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
_LOCK = threading.Lock()


def memory_path() -> Path:
    return Path(__file__).resolve().parents[1] / "memory" / "chat.jsonl"


def stamp_missing_session(session_id: str) -> None:
    """旧行没有 session_id 时一次性打上当前线程，再写回。不删文件。"""
    if type(session_id) is not str or not session_id.strip():
        raise RuntimeError("stamp_missing_session 需要非空 session_id。")
    sid = session_id.strip()
    path = memory_path()
    with _LOCK:
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = []
        changed = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            rec = _parse_line(path, line)
            if not rec.get("session_id"):
                rec["session_id"] = sid
                changed = True
            rows.append(rec)
        if changed:
            _write_rows_locked(path, rows)


def append_chat(role: str, text: str, session_id: str) -> None:
    if role not in ("user", "pet"):
        raise RuntimeError(f"对话角色只能是 user/pet，收到 {role!r}。")
    text = (text or "").strip()
    if not text:
        raise RuntimeError("不能写入空对话。")
    if type(session_id) is not str or not session_id.strip():
        raise RuntimeError("写入对话需要非空 session_id。")
    rec = {
        "ts": datetime.now(TZ).isoformat(timespec="seconds"),
        "role": role,
        "text": text,
        "session_id": session_id.strip(),
    }
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    path = memory_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            raw_lines = path.read_text(encoding="utf-8").splitlines()
            last_line = ""
            for item in reversed(raw_lines):
                if item.strip():
                    last_line = item.strip()
                    break
            if last_line:
                prev = _parse_line(path, last_line)
                if (
                    prev.get("role") == role
                    and str(prev.get("text") or "").strip() == text
                    and str(prev.get("session_id") or "") == rec["session_id"]
                ):
                    return
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def clear_chat() -> None:
    path = memory_path()
    with _LOCK:
        if path.is_file():
            path.unlink()


def clear_session(session_id: str) -> None:
    if type(session_id) is not str or not session_id.strip():
        raise RuntimeError("clear_session 需要非空 session_id。")
    sid = session_id.strip()
    path = memory_path()
    with _LOCK:
        if not path.is_file():
            return
        rows = [
            rec
            for rec in _read_rows_locked(path)
            if str(rec.get("session_id") or "") != sid
        ]
        if rows:
            _write_rows_locked(path, rows)
        else:
            path.unlink()


def recent_chat(limit: int = 20, session_id: str | None = None) -> list[dict]:
    rows = list_chat(session_id)
    if limit <= 0:
        return []
    return rows[-limit:]


def list_chat(session_id: str | None = None) -> list[dict]:
    path = memory_path()
    if not path.is_file():
        return []
    with _LOCK:
        rows = _read_rows_locked(path)
    if session_id is None:
        return rows
    if type(session_id) is not str or not session_id.strip():
        raise RuntimeError("list_chat 的 session_id 必须是非空字符串或省略。")
    sid = session_id.strip()
    return [rec for rec in rows if str(rec.get("session_id") or "") == sid]


def list_sessions() -> list[dict]:
    """按最后一条时间倒序。标题取该线程第一条用户话。"""
    groups: dict[str, dict] = {}
    order: list[str] = []
    for rec in list_chat():
        sid = str(rec.get("session_id") or "").strip()
        if not sid:
            raise RuntimeError(
                f"{memory_path()} 有记录缺少 session_id。重启桌宠以打上当前线程，或检查该文件。"
            )
        if sid not in groups:
            groups[sid] = {
                "id": sid,
                "title": "",
                "updated": rec.get("ts") or "",
                "count": 0,
            }
            order.append(sid)
        item = groups[sid]
        item["count"] += 1
        item["updated"] = rec.get("ts") or item["updated"]
        if not item["title"] and rec.get("role") == "user":
            title = str(rec.get("text") or "").strip().replace("\n", " ")
            if title.startswith("【本轮指定】"):
                rest = title.split("\n\n", 1)
                title = rest[1].strip() if len(rest) > 1 else title
            item["title"] = title[:40] or "（无标题）"
    out = []
    for sid in order:
        item = groups[sid]
        if not item["title"]:
            item["title"] = "新对话"
        out.append(item)
    out.sort(key=lambda row: str(row.get("updated") or ""), reverse=True)
    return out


def chat_on_date(day: str) -> list[dict]:
    """当天对话：ts 以东八区 YYYY-MM-DD 开头。"""
    if type(day) is not str or not day:
        raise RuntimeError("chat_on_date 需要 YYYY-MM-DD。")
    return [rec for rec in list_chat() if str(rec.get("ts") or "").startswith(day)]


def format_recent(limit: int = 20) -> str:
    rows = recent_chat(limit)
    if not rows:
        return "（还没有本地对话）"
    parts = []
    for rec in rows:
        who = "用户" if rec["role"] == "user" else "凯尔希"
        parts.append(f"{who}: {rec['text']}")
    return "\n".join(parts)


def history_for_model(limit: int, session_id: str) -> list[dict]:
    """喂给模型的窗口：当前 session 内，相同 role+正文只留最近一次。"""
    if type(limit) is not int:
        raise RuntimeError("history_for_model 的条数必须是整数。")
    if limit <= 0:
        return []
    if type(session_id) is not str or not session_id.strip():
        raise RuntimeError("history_for_model 需要非空 session_id。")
    kept: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rec in reversed(list_chat(session_id.strip())):
        key = (str(rec["role"]), str(rec["text"]).strip())
        if key in seen:
            continue
        seen.add(key)
        kept.append(rec)
        if len(kept) >= limit:
            break
    kept.reverse()
    return kept


def _parse_line(path: Path, line: str) -> dict:
    try:
        rec = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{path} 有损坏行，无法作为记忆读取。请检查或删掉该文件。\n{line}"
        ) from exc
    if not isinstance(rec, dict) or "role" not in rec or "text" not in rec:
        raise RuntimeError(
            f"{path} 记录缺 role/text。请检查或删掉该文件。\n{line}"
        )
    return rec


def _read_rows_locked(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        out.append(_parse_line(path, line))
    return out


def _write_rows_locked(path: Path, rows: list[dict]) -> None:
    text = "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in rows)
    path.write_text(text, encoding="utf-8")
