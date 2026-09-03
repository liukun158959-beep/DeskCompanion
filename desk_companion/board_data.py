"""看板数据：解析 lark-cli JSON 信封，失败不装空。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .feishu_tools import AUTH_HINT, _run_lark

TZ = timezone(timedelta(hours=8))
TODAY_KEYS = (
    "date",
    "fetched_at",
    "agenda",
    "tasks",
    "summary",
    "summary_at",
    "doc_url",
)
_LOCK = threading.Lock()


def today_path() -> Path:
    return Path(__file__).resolve().parents[1] / "memory" / "today.json"


def today_date() -> str:
    return datetime.now(TZ).date().isoformat()


def week_range() -> tuple[datetime, datetime]:
    """东八区本周一 00:00 到此刻。"""
    now = datetime.now(TZ)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday, now


def fetch_week_feishu(monday: datetime, now: datetime) -> dict:
    start = monday.strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    agenda = _section(
        lambda: parse_agenda(
            _lark_data(["calendar", "+agenda", "--start", start, "--end", end]),
            with_date=True,
        )
    )
    tasks = _section(
        lambda: parse_tasks(
            _lark_data(["task", "+get-my-tasks", "--complete=false", "--page-all"])
        )
    )
    return {"agenda": agenda, "tasks": tasks}


def fetch_board() -> dict:
    agenda = _section(lambda: parse_agenda(_lark_data(["calendar", "+agenda"])))
    due = datetime.now(TZ).replace(hour=23, minute=59, second=59, microsecond=0)
    due_s = due.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    tasks = _section(
        lambda: parse_tasks(
            _lark_data(["task", "+get-my-tasks", "--complete=false", f"--due-end={due_s}"])
        )
    )
    return {"agenda": agenda, "tasks": tasks}


def load_today_snapshot(*, refresh: bool) -> dict:
    """按自然日读缓存；换天或 refresh 才打飞书。"""
    day = today_date()
    cached = _read_today_file()
    if not refresh and cached is not None and cached["date"] == day:
        return cached
    board = fetch_board()
    summary = ""
    summary_at = ""
    doc_url = ""
    if cached is not None and cached["date"] == day:
        summary = cached["summary"]
        summary_at = cached["summary_at"]
        doc_url = cached["doc_url"]
    snap = {
        "date": day,
        "fetched_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "agenda": board["agenda"],
        "tasks": board["tasks"],
        "summary": summary,
        "summary_at": summary_at,
        "doc_url": doc_url,
    }
    _write_today_file(snap)
    return snap


def save_today_fields(**fields) -> dict:
    """在当天快照上改总结或文档链接。没有当天文件就失败。"""
    day = today_date()
    cached = _read_today_file()
    if cached is None:
        raise RuntimeError(
            "还没有今日快照。先打开看板「今日」页或点刷新，再生成本周复盘。"
        )
    if cached["date"] != day:
        raise RuntimeError(
            f"今日快照是 {cached['date']}，今天已是 {day}。先点「刷新」拉今天的日程。"
        )
    allowed = {"summary", "summary_at", "doc_url"}
    unknown = [key for key in fields if key not in allowed]
    if unknown:
        raise RuntimeError(f"今日快照不能改这些键：{', '.join(unknown)}。")
    snap = dict(cached)
    snap.update(fields)
    _write_today_file(snap)
    return snap


def _read_today_file() -> dict | None:
    path = today_path()
    if not path.is_file():
        return None
    with _LOCK:
        text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{path} 不是合法 JSON。删掉该文件后到看板「今日」点刷新。"
        ) from exc
    return _validate_today(raw, path)


def _write_today_file(snap: dict) -> None:
    path = today_path()
    clean = _validate_today(snap, path)
    text = json.dumps(clean, ensure_ascii=False, indent=2) + "\n"
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _validate_today(raw, path: Path) -> dict:
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} 根节点必须是对象。删掉该文件后点刷新。")
    missing = [key for key in TODAY_KEYS if key not in raw]
    if missing:
        raise RuntimeError(
            f"{path} 缺少字段 {', '.join(missing)}。删掉该文件后点刷新。"
        )
    date = raw["date"]
    if type(date) is not str:
        raise RuntimeError(f"{path} 的 date 必须是字符串。删掉该文件后点刷新。")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise RuntimeError(
            f"{path} 的 date={date!r} 必须是 YYYY-MM-DD。删掉该文件后点刷新。"
        ) from exc
    for key in ("fetched_at", "summary", "summary_at", "doc_url"):
        if type(raw[key]) is not str:
            raise RuntimeError(f"{path} 的 {key} 必须是字符串。删掉该文件后点刷新。")
    agenda = _validate_section(raw["agenda"], "agenda", path)
    tasks = _validate_section(raw["tasks"], "tasks", path)
    return {
        "date": date,
        "fetched_at": raw["fetched_at"],
        "agenda": agenda,
        "tasks": tasks,
        "summary": raw["summary"],
        "summary_at": raw["summary_at"],
        "doc_url": raw["doc_url"],
    }


def _validate_section(section, name: str, path: Path) -> dict:
    if not isinstance(section, dict):
        raise RuntimeError(f"{path} 的 {name} 必须是对象。删掉该文件后点刷新。")
    if "ok" not in section:
        raise RuntimeError(f"{path} 的 {name} 缺少 ok。删掉该文件后点刷新。")
    if type(section["ok"]) is not bool:
        raise RuntimeError(f"{path} 的 {name}.ok 必须是 true/false。删掉该文件后点刷新。")
    items = section.get("items", [])
    if not isinstance(items, list):
        raise RuntimeError(f"{path} 的 {name}.items 必须是列表。删掉该文件后点刷新。")
    out = {"ok": section["ok"], "items": items}
    if not section["ok"]:
        error = section.get("error")
        if type(error) is not str or not error.strip():
            raise RuntimeError(
                f"{path} 的 {name} 失败时必须有非空 error。删掉该文件后点刷新。"
            )
        out["error"] = error
    return out


def _lark_data(args: list[str]):
    raw = _run_lark(args)
    try:
        env = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"lark-cli 未返回 JSON。{AUTH_HINT}\n{raw}") from exc
    if not isinstance(env, dict) or env.get("ok") is not True:
        raise RuntimeError(f"lark-cli 返回失败信封。{AUTH_HINT}\n{raw}")
    if "data" not in env:
        raise RuntimeError(f"lark-cli 成功信封缺少 data。\n{raw}")
    return env["data"]


def _section(loader) -> dict:
    try:
        return {"ok": True, "items": loader()}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "items": []}


def parse_agenda(data, *, with_date: bool = False) -> list[dict]:
    items = _as_items(data, "日程")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("日程条目不是对象。")
        summary = item.get("summary") or item.get("title")
        if not summary:
            raise RuntimeError(f"日程缺少标题，字段: {list(item.keys())}")
        start = _event_time(item, "start", with_date=with_date)
        if not start:
            raise RuntimeError(f"日程「{summary}」缺少开始时间，字段: {list(item.keys())}")
        out.append(
            {
                "summary": str(summary),
                "start": start,
                "end": _event_time(item, "end", with_date=with_date),
            }
        )
    return out


def parse_tasks(data) -> list[dict]:
    items = _as_items(data, "待办")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("待办条目不是对象。")
        summary = item.get("summary")
        if not summary:
            raise RuntimeError(f"待办缺少 summary，字段: {list(item.keys())}")
        out.append(
            {
                "summary": str(summary),
                "due_at": item.get("due_at") or "",
                "url": item.get("url") or "",
            }
        )
    return out


def _as_items(data, label: str) -> list:
    if data in (None, [], {}):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        items = data["items"]
        if items in (None, []):
            return []
        if not isinstance(items, list):
            raise RuntimeError(f"{label} data.items 不是列表。")
        return items
    raise RuntimeError(f"无法解析{label}：期望列表或带 items 的对象，实际 {type(data).__name__}。")


def _event_time(item: dict, which: str, *, with_date: bool = False) -> str:
    for key in (which, f"{which}_time"):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, str) and val.strip():
            return _short_time(val, with_date=with_date)
        if isinstance(val, dict):
            if val.get("date"):
                return f"{val['date']} 全天"
            if val.get("timestamp") not in (None, ""):
                ts = int(val["timestamp"])
                fmt = "%Y-%m-%d %H:%M" if with_date else "%H:%M"
                return datetime.fromtimestamp(ts, TZ).strftime(fmt)
            raw = val.get("time") or val.get("datetime")
            if raw:
                return _short_time(str(raw), with_date=with_date)
    return ""


def _short_time(raw: str, *, with_date: bool = False) -> str:
    text = raw.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        fmt = "%Y-%m-%d %H:%M" if with_date else "%H:%M"
        return dt.astimezone(TZ).strftime(fmt)
    except ValueError:
        if "T" in text:
            return text.replace("T", " ")[:16] if with_date else text.split("T")[1][:5]
        return text


def bubble_today(*, refresh: bool) -> dict:
    """气泡「今日」壳：一块重点 + 最多 4 条其余。失败原文，不编造。"""
    snap = load_today_snapshot(refresh=refresh)
    now = datetime.now(TZ)
    errors: list[str] = []
    agenda = snap["agenda"]
    tasks = snap["tasks"]
    events: list[dict] = []
    todos: list[dict] = []
    if agenda["ok"]:
        events = list(agenda.get("items") or [])
    else:
        errors.append(str(agenda.get("error") or "读取日程失败。"))
    if tasks["ok"]:
        todos = list(tasks.get("items") or [])
    else:
        errors.append(str(tasks.get("error") or "读取待办失败。"))

    focus = None
    used = None
    overdue = [item for item in todos if _task_overdue(item.get("due_at") or "", now)]
    if overdue:
        item = overdue[0]
        focus = {"kind": "task", "title": item["summary"], "when": _when_label(item.get("due_at") or "", "已过期")}
        used = ("task", item["summary"], item.get("due_at") or "")
    else:
        nxt = _next_event(events, now)
        if nxt is not None:
            focus = {"kind": "event", "title": nxt["summary"], "when": nxt.get("start") or ""}
            used = ("event", nxt["summary"], nxt.get("start") or "")
        elif events:
            item = events[0]
            focus = {"kind": "event", "title": item["summary"], "when": item.get("start") or ""}
            used = ("event", item["summary"], item.get("start") or "")
        elif todos:
            item = todos[0]
            focus = {"kind": "task", "title": item["summary"], "when": _when_label(item.get("due_at") or "", "")}
            used = ("task", item["summary"], item.get("due_at") or "")
        else:
            if errors:
                focus = {"kind": "empty", "title": "今日安排读不到。", "when": ""}
            else:
                focus = {"kind": "empty", "title": "今天没有必须盯的事", "when": ""}

    rest: list[dict] = []
    for item in events:
        key = ("event", item["summary"], item.get("start") or "")
        if used == key:
            continue
        rest.append({"kind": "event", "title": item["summary"], "when": item.get("start") or ""})
    for item in todos:
        key = ("task", item["summary"], item.get("due_at") or "")
        if used == key:
            continue
        rest.append({"kind": "task", "title": item["summary"], "when": _when_label(item.get("due_at") or "", "")})
    more = max(0, len(rest) - 4)
    return {
        "ok": True,
        "date": snap["date"],
        "error": "\n".join(errors),
        "focus": focus,
        "rest": rest[:4],
        "more": more,
    }


def _when_label(raw: str, fallback: str) -> str:
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(TZ).strftime("%H:%M")
    except ValueError:
        return text


def _task_overdue(raw: str, now: datetime) -> bool:
    text = (raw or "").strip()
    if not text:
        return False
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt <= now
    except ValueError:
        return False


def _next_event(events: list[dict], now: datetime) -> dict | None:
    best = None
    best_delta = None
    for item in events:
        start = str(item.get("start") or "")
        if "全天" in start:
            continue
        if len(start) < 5 or start[2] != ":":
            continue
        try:
            hour = int(start[:2])
            minute = int(start[3:5])
        except ValueError:
            continue
        event_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = (event_at - now).total_seconds()
        if delta < -60:
            continue
        if best is None or delta < best_delta:
            best = item
            best_delta = delta
    return best
