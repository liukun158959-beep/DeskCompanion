"""Atlas 工具：改勾选、打开 PC 客户端。长任务在对话外跑。"""
from __future__ import annotations

_HOST = None


def bind_host(host) -> None:
    global _HOST
    _HOST = host


def _ctrl():
    if _HOST is None:
        raise RuntimeError("明日方舟控制器还没挂上 host。")
    return _HOST.maa


def get_arknights_daily_options(_args: dict) -> str:
    snap = _ctrl().snapshot()
    lines = ["当前勾选（与 MAA 一键长草同名）："]
    for item in snap["options"]:
        mark = "开" if item["checked"] else "关"
        lines.append(f"- {item['label']}（{item['id']}）{mark}")
    lines.append(f"状态：{snap['status']}。{snap['message']}")
    return "\n".join(lines)


def set_arknights_daily_options(args: dict) -> str:
    selected = args.get("selected")
    snap = _ctrl().set_selected(selected)
    names = [item["label"] for item in snap["options"] if item["checked"]]
    if not names:
        return "已保存：这次一项都不勾。开始清日常只会尝试打开游戏。"
    return "已保存勾选：" + "、".join(names)


def open_arknights_pc(_args: dict) -> str:
    result = _ctrl().start_open_game()
    return result["message"]


def start_arknights_daily(_args: dict) -> str:
    result = _ctrl().start_daily()
    return result["message"]


def stop_arknights_daily(_args: dict) -> str:
    result = _ctrl().stop()
    return result["message"]


def option_specs() -> list[dict]:
    labels = "开始唤醒、自动公招、基建换班、理智作战、信用购物、领取奖励、自动肉鸽、生息演算"
    return [
        {
            "func": get_arknights_daily_options,
            "name": "get_arknights_daily_options",
            "description": "查看明日方舟日常勾选，名称与 MAA 一键长草一致。问清哪些日常、当前勾了什么时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "isReadOnly": True,
        },
        {
            "func": set_arknights_daily_options,
            "name": "set_arknights_daily_options",
            "description": f"按用户要求改明日方舟日常勾选。selected 用中文名或 LinkStart-*。可选：{labels}。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selected": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要勾上的项，中文显示名或远控 type。",
                    }
                },
                "required": ["selected"],
            },
            "retry_max": 0,
        },
        {
            "func": open_arknights_pc,
            "name": "open_arknights_pc",
            "description": "打开鹰角启动器安装的明日方舟 PC 客户端，不是安卓模拟器。下令后立即返回，游戏在后台打开。",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "retry_max": 0,
        },
        {
            "func": start_arknights_daily,
            "name": "start_arknights_daily",
            "description": "按当前勾选开始清日常：先打开 PC 客户端。未配置 MAA 时会说明缺什么，不假装已经长草。",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "retry_max": 0,
        },
        {
            "func": stop_arknights_daily,
            "name": "stop_arknights_daily",
            "description": "停止正在进行的打开游戏或清日常等待。",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "retry_max": 0,
        },
    ]
