"""本地对话记忆：jsonl，不做向量库。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
_LOCK = threading.Lock()


def memory_path() -> Path:
    return Path(__file__).resolve().parents[1] / "memory" / "chat.jsonl"


def append_chat(role: str, text: str) -> None:
    if role not in ("user", "pet"):
        raise RuntimeError(f"对话角色只能是 user/pet，收到 {role!r}。")
    text = (text or "").strip()
    if not text:
        raise RuntimeError("不能写入空对话。")
    rec = {
        "ts": datetime.now(TZ).isoformat(timespec="seconds"),
        "role": role,
        "text": text,
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
                try:
                    prev = json.loads(last_line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"{path} 有损坏行，无法写入记忆。请检查或删掉该文件。\n{last_line}"
                    ) from exc
                if (
                    isinstance(prev, dict)
                    and prev.get("role") == role
                    and str(prev.get("text") or "").strip() == text
                ):
                    return
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def clear_chat() -> None:
    path = memory_path()
    with _LOCK:
        if path.is_file():
            path.unlink()


def recent_chat(limit: int = 20) -> list[dict]:
    path = memory_path()
    if not path.is_file():
        return []
    with _LOCK:
        lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
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
        out.append(rec)
    return out


def list_chat() -> list[dict]:
    path = memory_path()
    if not path.is_file():
        return []
    with _LOCK:
        lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
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
        out.append(rec)
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


def history_for_model(limit: int) -> list[dict]:
    """喂给模型的窗口：相同 role+正文只留最近一次，从新往旧凑满 limit 条。"""
    if type(limit) is not int:
        raise RuntimeError("history_for_model 的条数必须是整数。")
    if limit <= 0:
        return []
    kept: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rec in reversed(list_chat()):
        key = (str(rec["role"]), str(rec["text"]).strip())
        if key in seen:
            continue
        seen.add(key)
        kept.append(rec)
        if len(kept) >= limit:
            break
    kept.reverse()
    return kept
