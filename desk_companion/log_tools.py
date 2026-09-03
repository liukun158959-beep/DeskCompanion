"""Atlas 工具：只读今日出错日志段。"""
from __future__ import annotations

from .log_inspect import inspect_today_errors


def read_recent_errors(_args: dict) -> str:
    snap = inspect_today_errors()
    return snap["text"]


ERROR_LOG_SPEC = {
    "func": read_recent_errors,
    "name": "read_recent_errors",
    "description": (
        "读取今日桌宠与 MAA 出错段，带【重点】【桌宠】【MAA GUI】【MAA Depot】分节。"
        "用户问日志、为什么挂了、仓库怎么识别错了时必须先调用，然后再 read_skill(maa-log-analysis)。"
        "没有出错会返回没有记录。不要编原因。"
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
    "isReadOnly": True,
}
