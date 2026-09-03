"""与 MAA「一键长草」主界面对齐的任务项。名称、顺序、远控 type 不许自造。"""
from __future__ import annotations

# 显示名与 MAA GUI 一致；type 与远程控制 LinkStart-* 一致。
OPTIONS = (
    {"id": "LinkStart-WakeUp", "label": "开始唤醒", "default": True},
    {"id": "LinkStart-Recruiting", "label": "自动公招", "default": True},
    {"id": "LinkStart-Base", "label": "基建换班", "default": True},
    {"id": "LinkStart-Combat", "label": "理智作战", "default": True},
    {"id": "LinkStart-Mall", "label": "信用购物", "default": True},
    {"id": "LinkStart-Mission", "label": "领取奖励", "default": True},
    {"id": "LinkStart-AutoRoguelike", "label": "自动肉鸽", "default": False},
    {"id": "LinkStart-Reclamation", "label": "生息演算", "default": False},
)

IDS = tuple(item["id"] for item in OPTIONS)
LABEL_TO_ID = {item["label"]: item["id"] for item in OPTIONS}
# 桌宠勾选 → MAA gui.new.json TaskQueue.TaskType。不许自造。
TASK_TYPE = {
    "LinkStart-WakeUp": "StartUp",
    "LinkStart-Recruiting": "Recruit",
    "LinkStart-Base": "Infrast",
    "LinkStart-Combat": "Fight",
    "LinkStart-Mall": "Mall",
    "LinkStart-Mission": "Award",
    "LinkStart-AutoRoguelike": "Roguelike",
    "LinkStart-Reclamation": "Reclamation",
}


def default_selected() -> list[str]:
    return [item["id"] for item in OPTIONS if item["default"]]


def catalog(*, selected: list[str]) -> list[dict]:
    chosen = set(selected)
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "checked": item["id"] in chosen,
        }
        for item in OPTIONS
    ]


def parse_selected(raw) -> list[str]:
    """接受远控 type 或中文显示名。结果按 OPTIONS 顺序去重。"""
    if not isinstance(raw, list):
        raise RuntimeError("勾选必须是字符串列表。")
    wanted = set()
    for item in raw:
        if type(item) is not str or not item.strip():
            raise RuntimeError("勾选项必须是非空字符串（显示名或 LinkStart-*）。")
        text = item.strip()
        if text in IDS:
            wanted.add(text)
            continue
        if text in LABEL_TO_ID:
            wanted.add(LABEL_TO_ID[text])
            continue
        known = "、".join(item["label"] for item in OPTIONS)
        raise RuntimeError(f"未知日常项 {text!r}。只能是：{known}。")
    return [opt_id for opt_id in IDS if opt_id in wanted]
