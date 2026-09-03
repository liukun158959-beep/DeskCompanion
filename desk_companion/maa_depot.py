"""把 MAA DepotData.json 译成中文库存，写入 arknights_account.json。"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

ACCOUNT_NAME = "arknights_account.json"
_LOCK = threading.Lock()
_SYNC_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:\d{2}|Z)"
)


def account_path() -> Path:
    return Path(__file__).resolve().parents[1] / ACCOUNT_NAME


class RetryableDepotError(RuntimeError):
    """空仓、没写完或没有缓存文件。清日常线程可以再试一次只更新数据。"""


def ingest_depot(maa_exe: Path) -> dict:
    """读今天的仓库缓存，覆盖 inventory 里扫到的键。失败整份不写。"""
    if not isinstance(maa_exe, Path) or not maa_exe.is_file():
        raise RuntimeError("MAA.exe 路径无效，无法读仓库缓存。")
    root = maa_exe.resolve().parent
    depot_path = root / "data" / "DepotData.json"
    index_path = root / "resource" / "item_index.json"
    depot = _read_today_depot(depot_path)
    names = _load_item_names(index_path)
    mapped = _translate(depot["data"], names)
    path = account_path()
    _merge_account(path, mapped, depot["sync_raw"])
    return {
        "path": str(path),
        "sync": depot["sync_raw"],
        "count": len(mapped),
        "inventory": mapped,
    }


def require_today_inventory() -> dict:
    """只读账本。depot_sync 必须是本机今天。"""
    path = account_path()
    data = _read_account(path)
    sync_raw = data.get("depot_sync")
    _require_local_today(sync_raw, path)
    inventory = data.get("inventory")
    if not isinstance(inventory, dict):
        raise RuntimeError(
            f"{path} 的 inventory 必须是对象。先开一次清日常，或删掉该文件后重扫。"
        )
    out = {}
    for key, value in inventory.items():
        if type(key) is not str or not key.strip():
            raise RuntimeError(
                f"{path} 的 inventory 有非法键。先开一次清日常，或删掉该文件后重扫。"
            )
        if type(value) is not int or value < 0:
            raise RuntimeError(
                f"{path} 的 inventory[{key!r}] 必须是大于等于 0 的整数。"
                "先开一次清日常，或删掉该文件后重扫。"
            )
        out[key] = value
    return out


def _read_today_depot(path: Path) -> dict:
    if not path.is_file():
        raise RetryableDepotError(
            f"没有仓库缓存 {path}。先开一次清日常，让 MAA 更新数据。"
        )
    raw = _read_json_object(path)
    if raw.get("done") is not True:
        raise RetryableDepotError(
            f"{path} 的 done 不是 true，仓库识别没完成。先开一次清日常。"
        )
    data = raw.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} 的 data 必须是对象。先开一次清日常。")
    if not data:
        raise RetryableDepotError(
            f"{path} 的 data 是空的，仓库识别没扫到件（常见于没进仓库界面）。"
            "这次仓库没写入。游戏窗不要最小化。"
        )
    counts = {}
    for item_id, value in data.items():
        if type(item_id) is not str or not item_id.strip():
            raise RuntimeError(f"{path} 的 data 有非法 itemId。先开一次清日常。")
        if type(value) is not int or value < 0:
            raise RuntimeError(
                f"{path} 里 {item_id!r} 的数量必须是大于等于 0 的整数。先开一次清日常。"
            )
        counts[item_id] = value
    sync_raw = raw.get("syncTime")
    _require_local_today(sync_raw, path)
    return {"data": counts, "sync_raw": str(sync_raw).strip()}


def _load_item_names(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(
            f"没有物品表 {path}。确认 maa_exe 指向官方官服 MAA 目录。"
        )
    raw = _read_json_object(path)
    names = {}
    for item_id, entry in raw.items():
        if type(item_id) is not str or not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if type(name) is str and name.strip():
            names[item_id] = name.strip()
    if not names:
        raise RuntimeError(f"{path} 里没有可用的 name。检查 MAA 资源是否完整。")
    return names


def _translate(data: dict, names: dict) -> dict:
    missing = [item_id for item_id in data if item_id not in names]
    if missing:
        shown = "、".join(missing[:8])
        extra = f" 等 {len(missing)} 个" if len(missing) > 8 else ""
        raise RuntimeError(
            f"这些 itemId 在 MAA item_index.json 里没有中文名：{shown}{extra}。"
            "检查 MAA 资源是否与游戏版本一致。整份仓库未写入。"
        )
    mapped = {}
    owners = {}
    for item_id, count in data.items():
        name = names[item_id]
        if name in owners and owners[name] != item_id:
            raise RuntimeError(
                f"物品表里 {owners[name]!r} 与 {item_id!r} 都叫 {name}。"
                "整份仓库未写入。"
            )
        owners[name] = item_id
        mapped[name] = count
    return mapped


def merge_skland(skland: dict, sync_raw: str) -> None:
    """写入森空岛块。不改 inventory / depot_sync。"""
    if not isinstance(skland, dict):
        raise RuntimeError("森空岛模型必须是对象。")
    if type(sync_raw) is not str or not sync_raw.strip():
        raise RuntimeError("skland_sync 必须是非空字符串。")
    path = account_path()
    if path.is_file():
        data = _read_json_object(path)
    else:
        data = {}
    data["skland"] = skland
    data["skland_sync"] = sync_raw.strip()
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with _LOCK:
        path.write_text(text, encoding="utf-8")


def read_account_file() -> dict:
    """账本存在则读出；没有文件返回空对象。"""
    path = account_path()
    if not path.is_file():
        return {}
    return _read_json_object(path)


def require_skland_today() -> dict:
    """只读森空岛块。skland_sync 必须是本机今天。"""
    path = account_path()
    if not path.is_file():
        raise RuntimeError(
            f"没有账号快照 {path}。打开看板「明日方舟」点「同步森空岛」。"
        )
    data = _read_json_object(path)
    _require_local_today(
        data.get("skland_sync"),
        path,
        kind="森空岛同步",
        field="skland_sync",
        how="打开看板「明日方舟」点「同步森空岛」。",
    )
    skland = data.get("skland")
    if not isinstance(skland, dict):
        raise RuntimeError(
            f"{path} 的 skland 必须是对象。打开看板「明日方舟」点「同步森空岛」。"
        )
    return skland


def _merge_account(path: Path, inventory: dict, sync_raw: str) -> None:
    if path.is_file():
        data = _read_account(path)
    else:
        data = {}
    current = data.get("inventory")
    if current is None:
        current = {}
    elif not isinstance(current, dict):
        raise RuntimeError(
            f"{path} 的 inventory 必须是对象。改正或删掉该文件后再扫仓。"
        )
    merged = dict(current)
    merged.update(inventory)
    data["inventory"] = merged
    data["depot_sync"] = sync_raw
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with _LOCK:
        path.write_text(text, encoding="utf-8")


def _read_account(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(
            f"没有账号快照 {path}。先开一次清日常，写入仓库缓存。"
        )
    return _read_json_object(path)


def _read_json_object(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 不是合法 JSON。") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path} 根节点必须是对象。")
    return raw


def _require_local_today(
    sync_raw,
    source: Path,
    *,
    kind: str = "仓库",
    field: str = "syncTime",
    how: str = "先开一次清日常。",
) -> None:
    when = _parse_sync_time(sync_raw, source, field=field, how=how)
    local_day = when.astimezone().date()
    today = datetime.now().astimezone().date()
    if local_day != today:
        raise RuntimeError(
            f"{source} 的{kind}日期是 {local_day.isoformat()}，不是今天 {today.isoformat()}。"
            + how
        )


def _parse_sync_time(
    sync_raw,
    source: Path,
    *,
    field: str = "syncTime",
    how: str = "先开一次清日常。",
) -> datetime:
    if type(sync_raw) is not str or not sync_raw.strip():
        raise RuntimeError(f"{source} 缺少 {field}。{how}")
    text = sync_raw.strip()
    matched = _SYNC_RE.fullmatch(text)
    if not matched:
        raise RuntimeError(f"{source} 的 {field} 无法解析：{text!r}。{how}")
    head, frac, tz = matched.group(1), matched.group(2) or "", matched.group(3)
    if frac:
        digits = frac[1:]
        frac = "." + digits[:6]
    if tz == "Z":
        tz = "+00:00"
    try:
        return datetime.fromisoformat(head + frac + tz)
    except ValueError as exc:
        raise RuntimeError(
            f"{source} 的 {field} 无法解析：{text!r}。{how}"
        ) from exc
