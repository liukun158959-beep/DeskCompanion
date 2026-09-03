"""Atlas 工具：今天刷什么。数字由 farm_plan 算，模型不得改目标或顺序。"""
from __future__ import annotations

from .farm_plan import format_farm_text


def get_arknights_today_plan(_args: dict) -> str:
    try:
        return format_farm_text()
    except RuntimeError as exc:
        return str(exc)


PLAN_SPEC = {
    "func": get_arknights_today_plan,
    "name": "get_arknights_today_plan",
    "description": (
        "按本号今天的仓库和森空岛额度计算今天刷什么：先剿灭/保全，再日常养成关。"
        "用户问今天刷什么、刷哪、剿灭还打吗、芯片还刷吗、保全还做吗时必须调用。"
        "只原样转述工具原文，不要改关卡、不要编打几次、不要因活动开着就推荐。"
        "仓不是今天或缺键时把恢复指引原样告诉用户。"
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
    "isReadOnly": True,
}
