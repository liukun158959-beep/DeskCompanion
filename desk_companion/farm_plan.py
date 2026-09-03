"""今天刷什么：代理卡通道 + 日常养成表。数字不交给模型口算。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .maa_depot import read_account_file, require_today_inventory
from .memory import TZ
from .skland import require_skland_today, _public_view, _sync_raw

PROXY_ITEM = "常态事务代理卡"
SPEND_IDS = (
    "event_shop",
    "event_drops",
    "chip",
    "skill_book",
    "red_cert",
    "elite",
    "exp",
    "carbon",
    "lmd",
)
WEEKDAY_CN = "一二三四五六日"
# 周历：0=周一。来源 PRTS 关卡一览/资源收集。
OPEN_DAYS = {
    "LS": {0, 1, 2, 3, 4, 5, 6},
    "CE": {1, 3, 5, 6},
    "AP": {0, 3, 5, 6},
    "SK": {0, 2, 4, 5},
    "CA": {1, 2, 4},
    "PR-A": {0, 3, 4, 6},
    "PR-B": {0, 1, 4, 5},
    "PR-C": {2, 3, 5, 6},
    "PR-D": {1, 2, 5, 6},
}
CHIP_ITEMS = (
    ("重装芯片", "chip", "PR-A", "PR-A-1"),
    ("重装芯片组", "chip_pack", "PR-A", "PR-A-2"),
    ("医疗芯片", "chip", "PR-A", "PR-A-1"),
    ("医疗芯片组", "chip_pack", "PR-A", "PR-A-2"),
    ("术师芯片", "chip", "PR-B", "PR-B-1"),
    ("术师芯片组", "chip_pack", "PR-B", "PR-B-2"),
    ("狙击芯片", "chip", "PR-B", "PR-B-1"),
    ("狙击芯片组", "chip_pack", "PR-B", "PR-B-2"),
    ("先锋芯片", "chip", "PR-C", "PR-C-1"),
    ("先锋芯片组", "chip_pack", "PR-C", "PR-C-2"),
    ("辅助芯片", "chip", "PR-C", "PR-C-1"),
    ("辅助芯片组", "chip_pack", "PR-C", "PR-C-2"),
    ("近卫芯片", "chip", "PR-D", "PR-D-1"),
    ("近卫芯片组", "chip_pack", "PR-D", "PR-D-2"),
    ("特种芯片", "chip", "PR-D", "PR-D-1"),
    ("特种芯片组", "chip_pack", "PR-D", "PR-D-2"),
)
SKILL_ITEMS = ("技巧概要·卷1", "技巧概要·卷2", "技巧概要·卷3")
EXP_ITEMS = ("基础作战记录", "初级作战记录", "中级作战记录", "高级作战记录")
DEFAULT_STRATEGY = {
    "type_stocks": {
        "chip": 5,
        "chip_pack": 8,
        "skill_book": 50,
        "elite": 50,
        "exp": 50,
        "red_cert": 50,
        "carbon": 0,
        "lmd": 2000000,
    },
    "material_caps": {},
    "lmd_stage": "CE-6",
    "spend_order": list(SPEND_IDS),
    "sss": {"mode": "on"},
}


def today_farm_plan() -> dict:
    """读今天的仓和策略，点了才算。"""
    inventory = require_today_inventory()
    strategy = load_strategy()
    skland = None
    skland_error = ""
    try:
        skland = require_skland_today()
    except RuntimeError as exc:
        skland_error = str(exc)
    return build_plan(
        inventory=inventory,
        skland=skland,
        skland_error=skland_error,
        strategy=strategy,
        now=datetime.now(TZ),
    )


def format_farm_text(plan: dict | None = None) -> str:
    data = plan if plan is not None else today_farm_plan()
    return data["text"]


def load_strategy() -> dict:
    raw = read_account_file().get("strategy")
    if raw is None:
        return _copy_default()
    if not isinstance(raw, dict):
        raise RuntimeError("账本 strategy 必须是对象。改正或删掉该键后用缺省表。")
    return _parse_strategy(raw)


def build_plan(
    *,
    inventory: dict,
    skland,
    skland_error: str,
    strategy: dict,
    now: datetime,
) -> dict:
    game = _game_now(now)
    weekday = game.weekday()
    open_keys = [key for key, days in OPEN_DAYS.items() if weekday in days]
    proxy = _proxy_channel(inventory, skland, skland_error, strategy, game)
    try:
        train = _train_channel(inventory, strategy, weekday)
    except RuntimeError as exc:
        train = {"ok": False, "error": str(exc), "picked": None, "skipped": [], "gaps": []}
    text = _render(game, weekday, open_keys, proxy, train, skland)
    return {
        "ok": True,
        "game_day": game.date().isoformat(),
        "weekday": _weekday_cn(weekday),
        "open": open_keys,
        "proxy": proxy,
        "train": train,
        "text": text,
    }


def _copy_default() -> dict:
    stocks = dict(DEFAULT_STRATEGY["type_stocks"])
    return {
        "type_stocks": stocks,
        "material_caps": {},
        "lmd_stage": DEFAULT_STRATEGY["lmd_stage"],
        "spend_order": list(DEFAULT_STRATEGY["spend_order"]),
        "sss": dict(DEFAULT_STRATEGY["sss"]),
    }


def _parse_strategy(raw: dict) -> dict:
    out = _copy_default()
    if "type_stocks" in raw:
        stocks = raw.get("type_stocks")
        if not isinstance(stocks, dict):
            raise RuntimeError("strategy.type_stocks 必须是对象。")
        for key in DEFAULT_STRATEGY["type_stocks"]:
            if key not in stocks:
                raise RuntimeError(f"strategy.type_stocks 缺少 {key}。")
            value = stocks[key]
            if type(value) is not int or value < 0:
                raise RuntimeError(f"strategy.type_stocks.{key} 必须是大于等于 0 的整数。")
            out["type_stocks"][key] = value
    if "material_caps" in raw:
        caps = raw.get("material_caps")
        if not isinstance(caps, dict):
            raise RuntimeError("strategy.material_caps 必须是对象。")
        cleaned = {}
        for name, value in caps.items():
            if type(name) is not str or not name.strip():
                raise RuntimeError("strategy.material_caps 的键必须是非空字符串。")
            if type(value) is not int or value < 0:
                raise RuntimeError(f"strategy.material_caps[{name!r}] 必须是大于等于 0 的整数。")
            cleaned[name.strip()] = value
        out["material_caps"] = cleaned
    if "lmd_stage" in raw:
        stage = raw.get("lmd_stage")
        if type(stage) is not str or not stage.strip():
            raise RuntimeError("strategy.lmd_stage 必须是非空字符串。")
        out["lmd_stage"] = stage.strip()
    if "spend_order" in raw:
        order = raw.get("spend_order")
        if not isinstance(order, list) or sorted(order) != sorted(SPEND_IDS):
            raise RuntimeError(
                "strategy.spend_order 必须恰好是 event_shop、event_drops、chip、"
                "skill_book、red_cert、elite、exp、carbon、lmd 的一个排列。"
            )
        if any(type(item) is not str for item in order):
            raise RuntimeError("strategy.spend_order 每项必须是字符串。")
        out["spend_order"] = list(order)
    if "sss" in raw:
        sss = raw.get("sss")
        if not isinstance(sss, dict):
            raise RuntimeError("strategy.sss 必须是对象。")
        mode = sss.get("mode")
        if mode not in ("on", "off"):
            raise RuntimeError("strategy.sss.mode 必须是 on 或 off。")
        out["sss"] = {"mode": mode}
    return out


def _game_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)
    if now.hour < 4:
        now = now - timedelta(days=1)
    return now


def _weekday_cn(weekday: int) -> str:
    return "周" + WEEKDAY_CN[weekday]


def _proxy_channel(inventory: dict, skland, skland_error: str, strategy: dict, game: datetime) -> dict:
    if skland_error:
        return {
            "ok": False,
            "error": "代理卡通道需要今天的森空岛同步。" + skland_error,
            "actions": [],
        }
    if skland is None:
        return {
            "ok": False,
            "error": "代理卡通道需要今天的森空岛同步。打开看板「明日方舟」点「同步森空岛」。",
            "actions": [],
        }
    view = _public_view(skland, _sync_raw())
    if PROXY_ITEM not in inventory:
        return {
            "ok": False,
            "error": (
                f"仓里没有「{PROXY_ITEM}」，不当 0。MAA 扫不到这键。"
                f"在 arknights_account.json 的 inventory 里手填 \"{PROXY_ITEM}\": 张数。"
            ),
            "actions": [],
        }
    cards = _need_int(inventory, PROXY_ITEM)
    orundum = view["orundum"]
    cap = view["orundum_cap"]
    device = view["device"]
    device_total = view["device_total"]
    strip = view["strip"]
    strip_total = view["strip_total"]
    sss_on = strategy["sss"]["mode"] == "on"
    sss_open = sss_on and (strip < strip_total or device < device_total)
    reset_at = _next_sss_reset(game)
    actions = []
    if orundum < cap:
        if cards < 1:
            return {
                "ok": False,
                "error": (
                    f"本周剿灭合成玉 {orundum}/{cap}，还没打满，但代理卡 0 张。"
                    "去打日常任务领卡。不要用 CA/PR 代替剿灭。"
                ),
                "actions": [],
            }
        actions.append(
            {
                "name": "剿灭作战",
                "detail": (
                    f"本周合成玉 {orundum}/{cap}，先打剿灭。"
                    f"消耗 1 张代理卡和理智。当前代理卡 {cards} 张，实时理智 {view['ap']}/{view['ap_max']}。"
                    "不编打几次。"
                ),
            }
        )
        remain = cards - 1
        if sss_open and remain >= 2:
            actions.append(_sss_action(strip, strip_total, device, device_total, remain, reset_at))
        elif sss_open and remain < 2:
            actions.append(
                {
                    "name": "保全派驻（未附带）",
                    "detail": (
                        f"保全还没满（条 {strip}/{strip_total}，仪 {device}/{device_total}），"
                        f"但扣掉剿灭 1 张后只剩 {remain} 张，保全要 2 张。领日常卡后再去。"
                    ),
                }
            )
        return {"ok": True, "error": "", "actions": actions}
    if sss_open:
        if cards < 2:
            return {
                "ok": False,
                "error": (
                    f"本周剿灭已满 {orundum}/{cap}。保全未满（条 {strip}/{strip_total}，"
                    f"仪 {device}/{device_total}），要 2 张代理卡，现在 {cards} 张。"
                    "去打日常任务领卡。不要用资源本代替。"
                ),
                "actions": [],
            }
        return {
            "ok": True,
            "error": "",
            "actions": [_sss_action(strip, strip_total, device, device_total, cards, reset_at)],
        }
    return {
        "ok": True,
        "error": "",
        "actions": [],
        "idle": f"本周剿灭已满 {orundum}/{cap}，保全本周期也满了或已关闭。代理卡通道没有要做的。",
    }


def _sss_action(strip, strip_total, device, device_total, cards, reset_at) -> dict:
    return {
        "name": "保全派驻",
        "detail": (
            f"不耗理智，消耗 2 张代理卡。条 {strip}/{strip_total}，仪 {device}/{device_total}。"
            f"当前代理卡 {cards} 张。下次奖励周期 {reset_at.strftime('%Y-%m-%d %H:%M')}（每月 16 日 04:00）。"
            "不编打几次。"
        ),
    }


def _next_sss_reset(now: datetime) -> datetime:
    cand = now.replace(day=16, hour=4, minute=0, second=0, microsecond=0)
    if now >= cand:
        month = 1 if now.month == 12 else now.month + 1
        year = now.year + 1 if now.month == 12 else now.year
        cand = cand.replace(year=year, month=month)
    return cand


def _train_channel(inventory: dict, strategy: dict, weekday: int) -> dict:
    skipped = []
    picked = None
    for bucket in strategy["spend_order"]:
        if bucket in ("event_shop", "event_drops"):
            skipped.append(f"{bucket} 本刀关闭（不接活动商店和活动关掉落）。")
            continue
        if bucket == "elite":
            skipped.append("elite 本刀不接主题曲掉落（没有企鹅不点关）。")
            continue
        if bucket == "chip":
            picked = _pick_chip(inventory, strategy, weekday)
            if picked:
                return {"ok": True, "picked": picked, "skipped": skipped, "gaps": []}
            continue
        if bucket == "skill_book":
            if weekday not in OPEN_DAYS["CA"]:
                continue
            picked = _pick_typed(
                inventory, strategy, SKILL_ITEMS, "skill_book", "CA-5", "空中威胁"
            )
            if picked:
                return {"ok": True, "picked": picked, "skipped": skipped, "gaps": []}
            continue
        if bucket == "red_cert":
            if weekday not in OPEN_DAYS["AP"]:
                continue
            picked = _pick_typed(
                inventory, strategy, ("采购凭证",), "red_cert", "AP-5", "粉碎防御"
            )
            if picked:
                return {"ok": True, "picked": picked, "skipped": skipped, "gaps": []}
            continue
        if bucket == "exp":
            picked = _pick_typed(
                inventory, strategy, EXP_ITEMS, "exp", "LS-6", "战术演习"
            )
            if picked:
                return {"ok": True, "picked": picked, "skipped": skipped, "gaps": []}
            continue
        if bucket == "carbon":
            if strategy["type_stocks"]["carbon"] <= 0:
                skipped.append("carbon=0，不刷 SK。")
                continue
            if weekday not in OPEN_DAYS["SK"]:
                continue
            picked = _pick_typed(
                inventory,
                strategy,
                ("碳", "碳素", "碳素组", "家具零件"),
                "carbon",
                "SK-5",
                "资源保障",
            )
            if picked:
                return {"ok": True, "picked": picked, "skipped": skipped, "gaps": []}
            continue
        if bucket == "lmd":
            if weekday not in OPEN_DAYS["CE"]:
                continue
            picked = _pick_typed(
                inventory,
                strategy,
                ("龙门币",),
                "lmd",
                strategy["lmd_stage"],
                "货物运送",
            )
            if picked:
                return {"ok": True, "picked": picked, "skipped": skipped, "gaps": []}
            continue
        raise RuntimeError(f"未知 spend_order 项 {bucket}。")
    gaps = _remaining_gaps(inventory, strategy, weekday)
    return {"ok": True, "picked": None, "skipped": skipped, "gaps": gaps}


def _pick_chip(inventory: dict, strategy: dict, weekday: int) -> dict | None:
    missing = [name for name, _kind, _pr, _stage in CHIP_ITEMS if name not in inventory]
    if missing:
        raise RuntimeError(
            "仓里没有「"
            + "、".join(missing)
            + "」，不当 0。再扫一次仓或手填这些键后再问今天刷什么。"
        )
    short = []
    for name, kind, pr, stage in CHIP_ITEMS:
        cap = _cap(strategy, name, kind)
        have = _need_int(inventory, name)
        if have < cap and weekday in OPEN_DAYS[pr]:
            short.append((have, name, cap, stage, pr))
    if not short:
        return None
    short.sort(key=lambda row: (row[0], row[1]))
    have, name, cap, stage, pr = short[0]
    return {
        "id": "chip",
        "item": name,
        "have": have,
        "cap": cap,
        "gap": cap - have,
        "stage": stage,
        "family": pr,
        "label": "芯片搜索",
    }


def _pick_typed(inventory: dict, strategy: dict, names: tuple, kind: str, stage: str, label: str) -> dict | None:
    missing = [name for name in names if name not in inventory]
    if missing:
        raise RuntimeError(
            "仓里没有「"
            + "、".join(missing)
            + "」，不当 0。再扫一次仓或手填这些键后再问今天刷什么。"
        )
    short = []
    for name in names:
        cap = _cap(strategy, name, kind)
        have = _need_int(inventory, name)
        if have < cap:
            short.append((have, name, cap))
    if not short:
        return None
    short.sort(key=lambda row: (row[0], row[1]))
    have, name, cap = short[0]
    return {
        "id": kind,
        "item": name,
        "have": have,
        "cap": cap,
        "gap": cap - have,
        "stage": stage,
        "family": kind,
        "label": label,
    }


def _remaining_gaps(inventory: dict, strategy: dict, weekday: int) -> list:
    rows = []
    for name, kind, pr, stage in CHIP_ITEMS:
        if name not in inventory:
            continue
        cap = _cap(strategy, name, kind)
        have = _need_int(inventory, name)
        if have < cap:
            rows.append(
                f"{name} {have}/{cap}，下次 {stage} 开放{_next_open_cn(pr, weekday)}"
            )
    for name in SKILL_ITEMS:
        if name not in inventory:
            continue
        cap = _cap(strategy, name, "skill_book")
        have = _need_int(inventory, name)
        if have < cap:
            rows.append(
                f"{name} {have}/{cap}，下次 CA-5 开放{_next_open_cn('CA', weekday)}"
            )
    if "采购凭证" in inventory:
        cap = _cap(strategy, "采购凭证", "red_cert")
        have = _need_int(inventory, "采购凭证")
        if have < cap:
            rows.append(
                f"采购凭证 {have}/{cap}，下次 AP-5 开放{_next_open_cn('AP', weekday)}"
            )
    if "龙门币" in inventory:
        cap = _cap(strategy, "龙门币", "lmd")
        have = _need_int(inventory, "龙门币")
        if have < cap:
            rows.append(
                f"龙门币 {have}/{cap}，下次 {strategy['lmd_stage']} 开放{_next_open_cn('CE', weekday)}"
            )
    return rows


def _next_open_cn(family: str, weekday: int) -> str:
    days = OPEN_DAYS[family]
    if weekday in days:
        return "今天"
    for step in range(1, 8):
        later = (weekday + step) % 7
        if later in days:
            return _weekday_cn(later)
    raise RuntimeError(f"{family} 的周历是空的。")


def _cap(strategy: dict, name: str, kind: str) -> int:
    caps = strategy["material_caps"]
    if name in caps:
        return caps[name]
    return strategy["type_stocks"][kind]


def _need_int(inventory: dict, name: str) -> int:
    value = inventory[name]
    if type(value) is not int or value < 0:
        raise RuntimeError(f"inventory[{name!r}] 必须是大于等于 0 的整数。")
    return value


def _render(game, weekday, open_keys, proxy, train, skland) -> str:
    lines = [
        f"游戏日 {game.strftime('%Y-%m-%d')} {_weekday_cn(weekday)}（东八区 4:00 切日）。",
        "今日资源本开放：" + "、".join(open_keys) + "。",
        "活动关和企鹅次数本刀不做。不改 MAA 关卡。",
    ]
    if skland is not None:
        view = _public_view(skland, _sync_raw())
        lines.append(f"实时理智 {view['ap']}/{view['ap_max']}。")
    lines.append("")
    lines.append("代理卡通道")
    if not proxy["ok"]:
        lines.append(proxy["error"])
    elif proxy.get("actions"):
        for index, action in enumerate(proxy["actions"], start=1):
            lines.append(f"{index}. {action['name']}：{action['detail']}")
    else:
        lines.append(proxy.get("idle") or "没有要做的。")
    lines.append("")
    lines.append("理智养成通道")
    if not train.get("ok", True):
        lines.append(train.get("error") or "养成通道失败。")
    else:
        picked = train.get("picked")
        if picked:
            lines.append(
                f"今天先刷 {picked['stage']}（{picked['label']}）。"
                f"{picked['item']} {picked['have']}/{picked['cap']}，还差 {picked['gap']}。"
                "不编打几次。"
            )
        else:
            lines.append("今天养成可以不刷（今日开放且未达目标的日常项没有了）。")
            for gap in train.get("gaps") or []:
                lines.append("- " + gap)
        for note in train.get("skipped") or []:
            lines.append("（跳过）" + note)
    return "\n".join(lines)
