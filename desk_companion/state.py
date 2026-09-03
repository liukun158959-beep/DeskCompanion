"""记住缩放、位置、人设和看板可改参数。"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .layered import SCALES

STATE_NAME = "user_state.json"
REQUIRED = (
    "scale",
    "x",
    "y",
    "nudge_enabled",
    "drop_to_bottom",
    "click_through",
    "last_daily_date",
    "persona",
    "history_n",
    "max_steps",
    "model_prices",
)
_LOCK = threading.Lock()

DEFAULT_PERSONA = (
    "你是凯尔希。罗德岛的医生。用户是博士。"
    "你始终称对方「博士」，不要用「您好」，不要用客服腔。"
    "打招呼只说「博士你好」或「博士。」，然后直接说事。"
    "禁止这类开场：你好。我是罗德岛的凯尔希医生，正在协助处理你的日程、待办和日常事务。"
    "不要主动自我介绍。博士问起你是谁，答：罗德岛的凯尔希。"
    "说话冷静、简短、准确，像病历或作战简报。可以提醒或轻微责备，不卖萌、不鸡汤、不堆感叹号、不开玩笑。"
    "用中文。信息不足就指出缺什么、怎么补，不要编造。"
    "即使用户对话历史里你曾用客服腔自我介绍，从现在起改口，不要沿用。"
)


def state_path() -> Path:
    return Path(__file__).resolve().parents[1] / STATE_NAME


@dataclass
class UserState:
    scale: float
    x: int
    y: int
    nudge_enabled: bool
    drop_to_bottom: bool
    click_through: bool
    last_daily_date: str
    persona: str
    history_n: int
    max_steps: int
    model_prices: dict

    def save(self) -> None:
        data = {
            "scale": self.scale,
            "x": self.x,
            "y": self.y,
            "nudge_enabled": self.nudge_enabled,
            "drop_to_bottom": self.drop_to_bottom,
            "click_through": self.click_through,
            "last_daily_date": self.last_daily_date,
            "persona": self.persona,
            "history_n": self.history_n,
            "max_steps": self.max_steps,
            "model_prices": self.model_prices,
        }
        path = state_path()
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        with _LOCK:
            path.write_text(text, encoding="utf-8")


def load_state(default_x: int, default_y: int) -> UserState:
    path = state_path()
    if not path.is_file():
        state = UserState(
            scale=1.5,
            x=default_x,
            y=default_y,
            nudge_enabled=True,
            drop_to_bottom=False,
            click_through=False,
            last_daily_date="",
            persona=DEFAULT_PERSONA,
            history_n=20,
            max_steps=8,
            model_prices={},
        )
        state.save()
        return state
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 不是合法 JSON。删掉该文件后重启桌宠。") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} 根节点必须是对象。删掉该文件后重启桌宠。")
    missing = [key for key in REQUIRED if key not in raw]
    if missing:
        raise RuntimeError(
            f"{path} 缺少字段 {', '.join(missing)}。补上这些键后重启，或删掉该文件让程序重写。"
        )
    scale = raw["scale"]
    if scale not in SCALES:
        raise RuntimeError(
            f"{path} 的 scale={scale!r} 无效，只能是 {list(SCALES)}。"
            "改正或删掉该文件后重启。"
        )
    for key in ("x", "y"):
        if type(raw[key]) is not int:
            raise RuntimeError(f"{path} 的 {key} 必须是整数。改正或删掉该文件后重启。")
    if type(raw["nudge_enabled"]) is not bool:
        raise RuntimeError(
            f"{path} 的 nudge_enabled 必须是 true/false。改正或删掉该文件后重启。"
        )
    if type(raw["drop_to_bottom"]) is not bool:
        raise RuntimeError(
            f"{path} 的 drop_to_bottom 必须是 true/false。改正或删掉该文件后重启。"
        )
    if type(raw["click_through"]) is not bool:
        raise RuntimeError(
            f"{path} 的 click_through 必须是 true/false。改正或删掉该文件后重启。"
        )
    last_daily_date = raw["last_daily_date"]
    if type(last_daily_date) is not str:
        raise RuntimeError(
            f"{path} 的 last_daily_date 必须是字符串（YYYY-MM-DD 或空）。改正或删掉该文件后重启。"
        )
    if last_daily_date:
        try:
            datetime.strptime(last_daily_date, "%Y-%m-%d")
        except ValueError as exc:
            raise RuntimeError(
                f"{path} 的 last_daily_date={last_daily_date!r} 必须是 YYYY-MM-DD 或空。"
                "改正或删掉该文件后重启。"
            ) from exc
    persona = raw["persona"]
    if type(persona) is not str or not persona.strip():
        raise RuntimeError(f"{path} 的 persona 必须是非空字符串。改正或删掉该文件后重启。")
    history_n = raw["history_n"]
    if type(history_n) is not int or history_n < 0:
        raise RuntimeError(f"{path} 的 history_n 必须是大于等于 0 的整数。改正或删掉该文件后重启。")
    max_steps = raw["max_steps"]
    if type(max_steps) is not int or max_steps < 1:
        raise RuntimeError(f"{path} 的 max_steps 必须是大于等于 1 的整数。改正或删掉该文件后重启。")
    model_prices = _parse_prices(raw["model_prices"], path)
    return UserState(
        scale=float(scale),
        x=int(raw["x"]),
        y=int(raw["y"]),
        nudge_enabled=raw["nudge_enabled"],
        drop_to_bottom=raw["drop_to_bottom"],
        click_through=raw["click_through"],
        last_daily_date=last_daily_date,
        persona=persona.strip(),
        history_n=history_n,
        max_steps=max_steps,
        model_prices=model_prices,
    )


def _parse_prices(raw, path: Path) -> dict:
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} 的 model_prices 必须是对象。改正或删掉该文件后重启。")
    out = {}
    for model, item in raw.items():
        if type(model) is not str or not model.strip():
            raise RuntimeError(f"{path} 的 model_prices 键必须是非空字符串。")
        if not isinstance(item, dict):
            raise RuntimeError(f"{path} 的 model_prices[{model!r}] 必须是对象。")
        if "input_cny_per_mtok" not in item or "output_cny_per_mtok" not in item:
            raise RuntimeError(
                f"{path} 的 model_prices[{model!r}] 必须有 input_cny_per_mtok 和 output_cny_per_mtok。"
            )
        inn = item["input_cny_per_mtok"]
        outv = item["output_cny_per_mtok"]
        if type(inn) not in (int, float) or type(outv) not in (int, float):
            raise RuntimeError(f"{path} 的 model_prices[{model!r}] 单价必须是数字。")
        if inn < 0 or outv < 0:
            raise RuntimeError(f"{path} 的 model_prices[{model!r}] 单价不能为负。")
        out[model] = {
            "input_cny_per_mtok": float(inn),
            "output_cny_per_mtok": float(outv),
        }
    return out
