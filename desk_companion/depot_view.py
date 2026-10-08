"""仓库一览：账本里的库存按类排开，图标用本机 MAA 物品图。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .farm_plan import CHIP_ITEMS, EXP_ITEMS
from .maa_config import load_maa, require_maa_exe
from .maa_depot import describe_depot_sync, read_account_file, read_saved_inventory
from .material_ledger import _items, _tier
from .skland import PROFESSION

_ID_RE = re.compile(r"[A-Za-z0-9_]+")
_CHIP_NAMES = {name for name, kind, _zone, _stage in CHIP_ITEMS if kind == "chip"}
_PACK_NAMES = {name for name, kind, _zone, _stage in CHIP_ITEMS if kind == "chip_pack"}
_DUAL_NAMES = {f"{label}双芯片" for label in PROFESSION.values()}
_CURRENCY_TYPES = {"GOLD", "DIAMOND_SHD", "HGG_SHD", "LGG_SHD", "TKT_GACHA"}
_CURRENCY_NAMES = {"采购凭证"}
_GROUPS = (
    ("chip", "芯片"),
    ("chip_pack", "芯片组"),
    ("dual_chip", "双芯片"),
    ("elite", "精英材料"),
    ("skill_book", "技巧概要"),
    ("exp", "作战记录"),
    ("currency", "货币"),
    ("other", "其余"),
    ("unlisted", "对不上材料表"),
)


def depot_snapshot() -> dict:
    """账本里的仓库。不是今天也返回数量，并带上日历日。"""
    inventory = read_saved_inventory()
    account = read_account_file()
    sync, day, fresh = describe_depot_sync(account.get("depot_sync"))
    return assemble(inventory, sync, depot_day=day, today=fresh)


def assemble(inventory: dict, depot_sync: str, *, depot_day: str, today: bool) -> dict:
    items_dir, by_name, _by_id = _maa_index()
    table = _items()
    buckets: dict[str, list] = {key: [] for key, _label in _GROUPS}
    for name, count in inventory.items():
        row = _row(name, count, by_name, table, items_dir)
        buckets[row["group"]].append(row)
    groups = []
    for key, label in _GROUPS:
        rows = buckets[key]
        if not rows:
            continue
        rows.sort(key=lambda item: (-1 if item["tier"] is None else -item["tier"], item["name"]))
        groups.append(
            {
                "id": key,
                "label": label,
                "items": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "tier": item["tier"],
                        "count": item["count"],
                        "icon_id": item["icon_id"],
                    }
                    for item in rows
                ],
            }
        )
    return {
        "depot_sync": depot_sync,
        "depot_day": depot_day,
        "today": today,
        "count": len(inventory),
        "groups": groups,
    }


def read_icon(item_id: str) -> bytes:
    """只读 MAA 物品目录里、索引点名的那张 png。"""
    path = _icon_path(item_id)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"读不到图标 {item_id}。") from exc
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"图标 {item_id} 不是 PNG。")
    return data


def _row(name: str, count: int, by_name: dict, table: dict, items_dir: Path) -> dict:
    matches = by_name.get(name) or []
    # 同名多条时不挑一条，否则阶级和图标会对错。
    known = matches[0] if len(matches) == 1 else None
    item_id = known["id"] if known else ""
    record = table.get(item_id) if item_id else None
    if not isinstance(record, dict):
        group = "unlisted"
        tier = None
    else:
        group = _group(name, record)
        tier = _tier(record)
    icon_id = None
    if known and _icon_ready(items_dir, known["icon"]):
        icon_id = item_id
    return {
        "group": group,
        "id": item_id,
        "name": name,
        "tier": tier,
        "count": count,
        "icon_id": icon_id,
    }


def _group(name: str, record: dict) -> str:
    if name in _CHIP_NAMES:
        return "chip"
    if name in _PACK_NAMES:
        return "chip_pack"
    if name in _DUAL_NAMES:
        return "dual_chip"
    if name.startswith("技巧概要"):
        return "skill_book"
    if name.endswith("作战记录") or name in EXP_ITEMS:
        return "exp"
    item_type = record.get("itemType")
    if item_type in _CURRENCY_TYPES or name in _CURRENCY_NAMES:
        return "currency"
    icon_id = record.get("iconId")
    if type(icon_id) is str and icon_id.startswith("MTL_SL_"):
        return "elite"
    return "other"


def _maa_paths() -> tuple[Path, Path]:
    maa = require_maa_exe(load_maa())
    root = maa.resolve().parent
    index_path = root / "resource" / "item_index.json"
    items_dir = root / "resource" / "template" / "items"
    if not index_path.is_file():
        raise RuntimeError(f"没有 MAA 物品表 {index_path}。确认 maa_exe 指向官服 MAA。")
    if not items_dir.is_dir():
        raise RuntimeError(f"没有 MAA 物品图目录 {items_dir}。确认 maa_exe 指向官服 MAA。")
    return index_path, items_dir


def _maa_index() -> tuple[Path, dict]:
    index_path, items_dir = _maa_paths()
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{index_path} 不是合法 JSON。") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{index_path} 根节点必须是对象。")
    by_name: dict[str, list] = {}
    by_id = {}
    for item_id, entry in raw.items():
        if type(item_id) is not str or not isinstance(entry, dict):
            continue
        name = entry.get("name")
        icon = entry.get("icon")
        if type(name) is not str or not name.strip():
            raise RuntimeError(f"MAA 物品 {item_id} 没有中文名。")
        name = name.strip()
        if type(icon) is not str or not icon.endswith(".png") or "/" in icon or "\\" in icon:
            raise RuntimeError(f"MAA 物品 {name} 的图标文件名无效。")
        row = {"id": item_id, "icon": icon}
        by_id[item_id] = row
        by_name.setdefault(name, []).append(row)
    if not by_id:
        raise RuntimeError(f"{index_path} 里没有可用的物品。")
    return items_dir, by_name, by_id


def _icon_path(item_id: str) -> Path:
    if not _ID_RE.fullmatch(item_id):
        raise RuntimeError(f"没有图标 {item_id}。")
    items_dir, _by_name, by_id = _maa_index()
    known = by_id.get(item_id)
    if not known:
        raise RuntimeError(f"没有图标 {item_id}。")
    path = (items_dir / known["icon"]).resolve()
    if path.parent != items_dir.resolve():
        raise RuntimeError(f"没有图标 {item_id}。")
    if not path.is_file():
        raise RuntimeError(f"没有图标文件 {path.name}。")
    return path


def _icon_ready(items_dir: Path, icon_name: str) -> bool:
    path = (items_dir / icon_name).resolve()
    if path.parent != items_dir.resolve() or not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False
