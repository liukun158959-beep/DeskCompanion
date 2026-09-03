"""收集今日桌宠 / MAA 出错项。看板用分栏结构，对话用带重点的原文。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .logutil import LOG_PATH

MAX_BYTES = 2 * 1024 * 1024
LIVE_BYTES = 256 * 1024
MAX_TEXT = 8000
_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[")
_GUI_TS = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) ([0-9:.]+)\]")
_ASST_KEEP = (
    "failed to match DepotAllTab",
    "TaskChainError",
    "Save image",
    '"what":"DepotInfo"',
)


def inspect_today_errors() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    desk_items, desk_note = _desk_items(today)
    gui_items, depot_hit, maa_note = _gui_items(today)
    depot_items = _asst_items(today) if depot_hit else []
    highlights = _highlights(desk_items, gui_items, depot_items)
    alert = bool(desk_items or gui_items)
    desk_path = str(LOG_PATH)
    maa_gui_path = ""
    maa_asst_path = ""
    root = _maa_debug_dir()
    if root is not None:
        maa_gui_path = str(root / "gui.log")
        maa_asst_path = str(root / "asst.log")
    text = _tool_text(
        alert=alert,
        highlights=highlights,
        desk_items=desk_items,
        gui_items=gui_items,
        depot_items=depot_items,
        desk_note=desk_note,
        maa_note=maa_note,
        desk_path=desk_path,
        maa_gui_path=maa_gui_path,
        maa_asst_path=maa_asst_path,
    )
    return {
        "ok": True,
        "alert": alert,
        "empty": not alert,
        "text": text,
        "highlights": highlights,
        "desk": {"path": desk_path, "note": desk_note, "items": desk_items},
        "maa_gui": {"path": maa_gui_path, "note": maa_note, "items": gui_items},
        "maa_depot": {"path": maa_asst_path, "note": "", "items": depot_items},
    }


def live_gui_progress() -> dict:
    """今日 gui.log 里最新一条开始任务，以及它之后的任务出错。"""
    empty = {
        "current_task": "",
        "current_task_time": "",
        "task_error": "",
        "task_error_time": "",
        "note": "",
    }
    today = datetime.now().strftime("%Y-%m-%d")
    root = _maa_debug_dir()
    if root is None:
        empty["note"] = "未配置可用的 MAA.exe，没有读 gui.log。"
        return empty
    path = root / "gui.log"
    if not path.is_file():
        empty["note"] = f"没有 {path}。"
        return empty
    try:
        raw = _tail_text(path, LIVE_BYTES)
    except OSError as exc:
        empty["note"] = f"读不了 {path}：{exc}"
        return empty
    current = None
    error = None
    for line in raw.splitlines():
        matched = _GUI_TS.match(line)
        if not matched or matched.group(1) != today:
            continue
        stamp = f"{matched.group(1)} {matched.group(2)}"
        if "开始任务:" in line:
            current = {
                "time": stamp,
                "name": line.split("开始任务:", 1)[-1].strip(),
            }
        elif "任务出错:" in line:
            error = {
                "time": stamp,
                "name": line.split("任务出错:", 1)[-1].strip(),
            }
    if current is None:
        return empty
    out = {
        "current_task": current["name"],
        "current_task_time": current["time"],
        "task_error": "",
        "task_error_time": "",
        "note": "",
    }
    if error is not None and error["time"] >= current["time"]:
        out["task_error"] = error["name"]
        out["task_error_time"] = error["time"]
    return out


def _desk_items(today: str) -> tuple[list[dict], str]:
    if not LOG_PATH.is_file():
        return [], f"没有日志文件 {LOG_PATH}。"
    try:
        raw = _tail_text(LOG_PATH)
    except OSError as exc:
        return [], f"读不了 {LOG_PATH}：{exc}"
    lines = raw.splitlines()
    out: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        matched = _TS.match(line)
        if not matched or matched.group(1) != today:
            i += 1
            continue
        kind = ""
        title = ""
        if "CRASH" in line:
            kind, title = "crash", "崩溃"
        elif "WATCHDOG" in line:
            kind, title = "watchdog", "看门狗"
        elif " maa_job " in line:
            kind, title = "daily", "清日常失败"
        if not kind:
            i += 1
            continue
        block = [line]
        i += 1
        while i < len(lines) and not _TS.match(lines[i]):
            block.append(lines[i])
            i += 1
        out.append(
            _entry(
                source="desk",
                kind=kind,
                time=f"{matched.group(1)} {matched.group(2)}",
                title=title,
                text="\n".join(block),
            )
        )
    return out[-12:], ""


def _gui_items(today: str) -> tuple[list[dict], bool, str]:
    root = _maa_debug_dir()
    if root is None:
        return [], False, "未配置可用的 MAA.exe，没有读 gui.log。"
    path = root / "gui.log"
    if not path.is_file():
        return [], False, f"没有 {path}。"
    try:
        raw = _tail_text(path)
    except OSError as exc:
        return [], False, f"读不了 {path}：{exc}"
    out: list[dict] = []
    depot_hit = False
    for line in raw.splitlines():
        matched = _GUI_TS.match(line)
        if not matched or matched.group(1) != today:
            continue
        if "任务出错" not in line:
            continue
        name = line.split("任务出错:", 1)[-1].strip() if "任务出错:" in line else "任务出错"
        if "仓库" in line:
            depot_hit = True
            kind = "depot"
        else:
            kind = "task_error"
        out.append(
            _entry(
                source="maa_gui",
                kind=kind,
                time=f"{matched.group(1)} {matched.group(2)}",
                title=f"任务出错: {name}",
                text=line,
            )
        )
    return out[-20:], depot_hit, ""


def _asst_items(today: str) -> list[dict]:
    root = _maa_debug_dir()
    if root is None:
        return []
    path = root / "asst.log"
    if not path.is_file():
        return [
            _entry("maa_depot", "depot", "", "没有 asst.log", f"没有 {path}。")
        ]
    try:
        raw = _tail_text(path)
    except OSError as exc:
        return [
            _entry("maa_depot", "depot", "", "读不了 asst.log", f"读不了 {path}：{exc}")
        ]
    prefix = f"[{today}"
    out: list[dict] = []
    for line in raw.splitlines():
        if not line.startswith(prefix):
            continue
        if not any(token in line for token in _ASST_KEEP):
            continue
        if "TaskChainError" in line and "Depot" not in line:
            continue
        matched = _GUI_TS.match(line)
        time = f"{matched.group(1)} {matched.group(2)}" if matched else ""
        if "failed to match DepotAllTab" in line:
            kind, title = "depot", "没对上「全部」页签"
        elif "Save image" in line:
            kind, title = "screenshot", "失败截图路径"
        elif "TaskChainError" in line:
            kind, title = "depot", "Depot 任务链失败"
        else:
            kind, title = "depot", "仓库识别中间结果"
        clipped = line if len(line) <= 400 else line[:400] + "…"
        out.append(_entry("maa_depot", kind, time, title, clipped))
    return out[-20:]


def _highlights(desk: list, gui: list, depot: list) -> list[dict]:
    picked: list[dict] = []
    for pool, kinds in (
        (desk, ("crash", "watchdog")),
        (desk, ("daily",)),
        (gui, ("depot",)),
        (gui, ("task_error",)),
    ):
        found = [item for item in pool if item["kind"] in kinds]
        if found:
            picked.append(found[-1])
        if len(picked) >= 3:
            break
    if not picked and depot:
        picked.append(depot[-1])
    return picked[:3]


def _tool_text(
    *,
    alert: bool,
    highlights: list,
    desk_items: list,
    gui_items: list,
    depot_items: list,
    desk_note: str,
    maa_note: str,
    desk_path: str,
    maa_gui_path: str,
    maa_asst_path: str,
) -> str:
    if not alert:
        lines = ["今日没有崩溃、看门狗或清日常/MAA 任务出错记录。"]
        if desk_note:
            lines.append(desk_note)
        if maa_note:
            lines.append(maa_note)
        return "\n".join(lines)
    parts = ["【重点】"]
    if highlights:
        for item in highlights:
            parts.append(f"- [{item['source']}] {item['time']} {item['title']}")
    else:
        parts.append("- （无）")
    parts.append("")
    parts.append(f"【桌宠】 {desk_path}")
    if desk_note:
        parts.append(desk_note)
    if desk_items:
        parts.extend(item["text"] for item in desk_items)
    else:
        parts.append("今日桌宠无出错段。")
    parts.append("")
    parts.append(f"【MAA GUI】 {maa_gui_path}")
    if maa_note:
        parts.append(maa_note)
    if gui_items:
        parts.extend(item["text"] for item in gui_items)
    else:
        parts.append("今日 MAA 无任务出错。")
    if depot_items:
        parts.append("")
        parts.append(f"【MAA Depot】 {maa_asst_path}")
        parts.extend(f"{item['title']}: {item['text']}" for item in depot_items)
    text = "\n".join(parts)
    if len(text) > MAX_TEXT:
        text = "（已截断，只保留最近出错段）\n" + text[-MAX_TEXT:]
    return text


def _entry(source: str, kind: str, time: str, title: str, text: str) -> dict:
    return {
        "source": source,
        "kind": kind,
        "time": time,
        "title": title,
        "text": text,
    }


def _maa_debug_dir() -> Path | None:
    from .maa_config import load_maa

    cfg = load_maa()
    maa = Path(cfg["maa_exe"])
    if not maa.is_file():
        return None
    return maa.resolve().parent / "debug"


def _tail_text(path: Path, max_bytes: int = MAX_BYTES) -> str:
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        start = max(0, size - max_bytes)
        fh.seek(start)
        raw = fh.read()
    if start > 0:
        nl = raw.find(b"\n")
        if nl >= 0:
            raw = raw[nl + 1 :]
    return raw.decode("utf-8", errors="replace")
