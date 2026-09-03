"""Atlas 工具：读已同步的森空岛账号状态。不同步。"""
from __future__ import annotations

from .skland import format_operator_text, format_status_text


def get_arknights_skland(_args: dict) -> str:
    try:
        return format_status_text()
    except RuntimeError as exc:
        return str(exc)


def get_arknights_operator(args: dict) -> str:
    name = args.get("name") if isinstance(args, dict) else None
    try:
        return format_operator_text(name if type(name) is str else "")
    except RuntimeError as exc:
        return str(exc)


STATUS_SPEC = {
    "func": get_arknights_skland,
    "name": "get_arknights_skland",
    "description": (
        "读取本号森空岛账号状态：实时理智、本周剿灭合成玉、保全增补仪/条、月卡、同步时间。"
        "用户问理智、周玉、保全额度、月卡时必须调用。"
        "没有今天的同步时把恢复指引原样告诉用户，不要编数字。"
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
    "isReadOnly": True,
}

OPERATOR_SPEC = {
    "func": get_arknights_operator,
    "name": "get_arknights_operator",
    "description": (
        "按游戏中文名查询单个干员的精英阶段、等级、技能等级、专精和模组。"
        "用户问某干员练到哪、精二了没、专精几时必须调用。"
        "必须用精确中文名。不要一次列出全部干员。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "游戏里的干员中文名，例如 阿米娅、凯尔希。",
            }
        },
        "required": ["name"],
    },
    "isReadOnly": True,
}
