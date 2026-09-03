"""飞书只读工具：日程与未完成待办。失败把恢复指引写进返回字符串。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import winreg
from datetime import datetime, timedelta, timezone
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
AUTH_HINT = "请在看板「飞书」页登录。需要日历、待办和云文档权限：lark-cli auth login --domain calendar,task,docs"
_PATH_MERGED = False


def _merge_user_path() -> None:
    """Cursor 等宿主启动时 PATH 可能不含用户目录里的 lark-cli。"""
    global _PATH_MERGED
    if _PATH_MERGED:
        return
    extra: list[str] = []
    hives = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    for root, sub in hives:
        try:
            with winreg.OpenKey(root, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        extra.extend(part.strip() for part in str(value).split(os.pathsep) if part.strip())
    expanded = [os.path.expandvars(part) for part in extra]
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*expanded, current])
    _PATH_MERGED = True


def _lark_bin() -> str:
    _merge_user_path()
    found = shutil.which("lark-cli")
    if found:
        return found
    raise RuntimeError(
        "找不到 lark-cli。当前进程 PATH 和用户/系统 PATH 里都没有。"
        "请安装 lark-cli，并在本机终端执行 "
        "lark-cli auth login --domain calendar,task,docs"
    )


def _run_lark(args: list[str], timeout: int = 60, stdin: str | None = None) -> str:
    creationflags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    bin_path = _lark_bin()
    if bin_path.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c", bin_path, *args]
    else:
        cmd = [bin_path, *args]
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
            env=env,
            cwd=str(root),
        )
    except FileNotFoundError:
        raise RuntimeError(
            "找不到 lark-cli。请确认已安装并在 PATH 中，然后执行 "
            "lark-cli auth login --domain calendar,task,docs"
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"lark-cli 超时（{timeout}s）。") from None
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"lark-cli 失败（exit {completed.returncode}）。{AUTH_HINT}\n{err}")
    return completed.stdout


def get_today_agenda(_args: dict) -> str:
    """今天的飞书日程。"""
    try:
        return _run_lark(["calendar", "+agenda"])
    except RuntimeError as exc:
        return str(exc)


def get_open_tasks(_args: dict) -> str:
    """我的未完成飞书任务。"""
    due_end = datetime.now(timezone(timedelta(hours=8))).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    due = due_end.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    try:
        return _run_lark(
            ["task", "+get-my-tasks", "--complete=false", f"--due-end={due}"]
        )
    except RuntimeError as exc:
        return str(exc)


AGENDA_SPEC = {
    "func": get_today_agenda,
    "name": "get_today_agenda",
    "description": "查询登录用户今天的飞书日历日程。问今天安排、今天有什么会时必须调用。",
    "parameters": {"type": "object", "properties": {}, "required": []},
    "isReadOnly": True,
}

TASKS_SPEC = {
    "func": get_open_tasks,
    "name": "get_open_tasks",
    "description": "查询登录用户未完成的飞书待办（含今天及更早到期）。问今天待办、今日安排时必须调用。",
    "parameters": {"type": "object", "properties": {}, "required": []},
    "isReadOnly": True,
}
