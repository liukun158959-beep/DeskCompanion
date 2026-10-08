"""培养清单：点名干员和档位，用材料总账减今天的仓库。"""
from __future__ import annotations

from .paths import data_root

import json
import threading
from pathlib import Path

from .maa_depot import describe_depot_sync
from .material_ledger import cost, gap

ROSTER_NAME = "raise_roster.json"
_RANKS = ("精一", "精二")
_LOCK = threading.Lock()
_EMPTY = "没有点名的培养清单，算不了整体缺口。"


def roster_path() -> Path:
    return data_root() / ROSTER_NAME


def snapshot() -> dict:
    """名单始终返回。缺口只在仓是今天、且清单非空时带数字。"""
    items = read_roster()
    if not items:
        return {"ok": False, "error": _EMPTY, "roster": [], "lines": []}
    try:
        data = gap([f"{item['operator']}:{item['rank']}" for item in items])
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "roster": items, "lines": []}
    _sync, day, fresh = describe_depot_sync(data["depot_sync"])
    if not fresh:
        return {
            "ok": False,
            "error": f"仓库日期是 {day}，不是今天。先开一次清日常。",
            "roster": items,
            "lines": [],
        }
    return {
        "ok": True,
        "error": "",
        "roster": items,
        "depot_sync": data["depot_sync"],
        "depot_day": day,
        "lines": [
            {
                "name": row["name"],
                "tier": row["tier"],
                "need": row["need"],
                "have": row["have"],
                "in_depot": row["in_depot"],
                "short": row["short"],
            }
            for row in data["lines"]
        ],
    }


def add_target(operator: str, rank: str) -> dict:
    """先用总账确认干员和档位，通过才写入。"""
    view = cost(operator, rank)
    name = view["operator"]["name"]
    rank_name = view["rank"]
    items = read_roster()
    if any(item["operator"] == name and item["rank"] == rank_name for item in items):
        raise RuntimeError(f"{name} {rank_name} 已经在清单里。")
    items.append({"operator": name, "rank": rank_name})
    _write(items)
    return snapshot()


def remove_target(operator: str, rank: str) -> dict:
    who = operator.strip() if type(operator) is str else ""
    tier = rank.strip() if type(rank) is str else ""
    if not who or tier not in _RANKS:
        raise RuntimeError("删除要给干员名，档位只认 精一 或 精二。")
    items = read_roster()
    kept = [item for item in items if not (item["operator"] == who and item["rank"] == tier)]
    if len(kept) == len(items):
        raise RuntimeError(f"清单里没有 {who} {tier}。")
    _write(kept)
    return snapshot()


def read_roster() -> list[dict]:
    path = roster_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 不是合法 JSON。删掉该文件后重填。") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} 根节点必须是对象。删掉该文件后重填。")
    items = raw.get("items")
    if not isinstance(items, list):
        raise RuntimeError(f"{path} 的 items 必须是数组。删掉该文件后重填。")
    out = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError(f"{path} 的条目必须是对象。删掉该文件后重填。")
        who = item.get("operator")
        tier = item.get("rank")
        if type(who) is not str or not who.strip():
            raise RuntimeError(f"{path} 有空的干员名。删掉该文件后重填。")
        if tier not in _RANKS:
            raise RuntimeError(f"{path} 的档位只认 精一 或 精二。删掉该文件后重填。")
        key = (who.strip(), tier)
        if key in seen:
            raise RuntimeError(f"{path} 里 {key[0]} {tier} 重复。删掉该文件后重填。")
        seen.add(key)
        out.append({"operator": key[0], "rank": tier})
    return out


def _write(items: list[dict]) -> None:
    path = roster_path()
    text = json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n"
    with _LOCK:
        path.write_text(text, encoding="utf-8")
