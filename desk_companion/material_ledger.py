"""材料总账：官方表算晋升消耗，再减今天的仓库。数字不交给模型。"""
from __future__ import annotations

from .paths import data_root

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .farm_plan import CHIP_ITEMS
from .maa_depot import read_account_file, require_today_inventory
from .skland import PROFESSION

SOURCE = "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel"
FILES = (
    "item_table.json",
    "character_table.json",
    "building_data.json",
)
RANKS = {"精一": 1, "精二": 2}
STATIONS = {
    "WORKSHOP": ("加工站", "workshopFormulas"),
    "MANUFACTURE": ("制造站", "manufactFormulas"),
}
CATALOG_LIMIT = 40
_CHIP_NAMES = {name for name, kind, _zone, _stage in CHIP_ITEMS if kind == "chip"}
_CACHE: dict[str, dict] = {}


def gamedata_dir() -> Path:
    return data_root() / "gamedata"


def fetch() -> dict:
    """下载三张官方表。任一失败则不替换已有文件。"""
    _CACHE.clear()
    root = gamedata_dir()
    root.mkdir(parents=True, exist_ok=True)
    saved = []
    for name in FILES:
        dest = root / name
        url = f"{SOURCE}/{name}"
        part = dest.with_suffix(dest.suffix + ".part")
        _download(url, part)
        try:
            raw = json.loads(part.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"{name} 不是合法 JSON。重新 fetch。") from exc
        try:
            _expect_table(name, raw)
        except RuntimeError:
            part.unlink(missing_ok=True)
            raise
        part.replace(dest)
        saved.append({"file": name, "bytes": dest.stat().st_size, "url": url})
    return {"dir": str(root), "files": saved}


def catalog(keyword: str) -> dict:
    word = keyword.strip()
    if not word:
        raise RuntimeError("材料目录要给名字或关键词。")
    items = _items()
    hit = []
    for item_id, item in items.items():
        name = _item_name(item_id, item)
        if word == item_id or word in name:
            hit.append(item)
    if not hit:
        raise RuntimeError(f"材料目录里没有「{word}」。")
    if len(hit) > CATALOG_LIMIT:
        raise RuntimeError(f"「{word}」命中 {len(hit)} 条，把名字写具体些。")
    hit.sort(key=lambda item: (_tier(item), _item_name(item["itemId"], item), item["itemId"]))
    rows = [_catalog_row(item) for item in hit]
    return {"keyword": word, "items": rows}


def cost(who: str, rank: str) -> dict:
    """只算升到这一档的晋升消耗。"""
    operator = _find_operator(who)
    rank_name = _rank_name(rank)
    costs = _evolve_costs(operator, rank_name)
    chip = _profession_chip(operator["profession"])
    chip_count = sum(row["count"] for row in costs if row["name"] == chip)
    return {
        "operator": _operator_view(operator),
        "rank": rank_name,
        "scope": "evolve",
        "costs": costs,
        "profession_chip": {"name": chip, "count": chip_count},
    }


def gap(specs: list[str]) -> dict:
    """点名清单加总后减去今天的仓库。没有清单就没有边界。"""
    if not specs:
        raise RuntimeError(
            "没有点名的培养清单，算不了整体缺口。"
            "写法：python -m desk_companion.material_ledger gap 银灰:精一"
        )
    targets = [cost(*_split_spec(spec)) for spec in specs]
    inventory = require_today_inventory()
    account = read_account_file()
    sync = account.get("depot_sync")
    if type(sync) is not str or not sync.strip():
        raise RuntimeError("账本没有 depot_sync。先开一次清日常。")
    need: dict[str, dict] = {}
    order: list[str] = []
    for target in targets:
        for row in target["costs"]:
            item_id = row["id"]
            if item_id not in need:
                need[item_id] = {
                    "id": item_id,
                    "name": row["name"],
                    "tier": row["tier"],
                    "need": 0,
                }
                order.append(item_id)
            elif need[item_id]["name"] != row["name"]:
                raise RuntimeError(
                    f"材料 {item_id} 出现了两个中文名，表不一致。重新 fetch。"
                )
            need[item_id]["need"] += row["count"]
    names = [need[item_id]["name"] for item_id in order]
    if len(names) != len(set(names)):
        raise RuntimeError("清单里有两件材料中文名相同，仓库按名字记账，没法相减。")
    lines = []
    for item_id in order:
        row = need[item_id]
        recorded = row["name"] in inventory
        have = inventory[row["name"]] if recorded else 0
        short = row["need"] - have
        if short < 0:
            short = 0
        lines.append({**row, "have": have, "in_depot": recorded, "short": short})
    return {
        "depot_sync": sync.strip(),
        "absent_is_zero": True,
        "targets": targets,
        "lines": lines,
    }


def format_catalog(data: dict) -> str:
    lines = [f"材料目录「{data['keyword']}」 {len(data['items'])} 条"]
    for item in data["items"]:
        lines.append(f"{item['name']}  id {item['id']}  阶级 {item['tier']}")
        if not item["recipes"]:
            lines.append("  无合成")
            continue
        for recipe in item["recipes"]:
            left = " + ".join(
                f"{part['name']}×{part['count']}" for part in recipe["inputs"]
            )
            if not left:
                left = "无原料"
            extra = ""
            if recipe["extra"]:
                names = "、".join(part["name"] for part in recipe["extra"]["outputs"])
                extra = f"；额外 {recipe['extra']['rate_text']} 随机 1 个（{names}）"
            lines.append(
                f"  {recipe['station']} 配方{recipe['formula_id']}："
                f"{left} → {item['name']}×{recipe['output_count']}{extra}"
            )
    return "\n".join(lines)


def format_cost(data: dict) -> str:
    op = data["operator"]
    lines = [
        f"{op['name']}  {op['id']}  {op['stars_text']}{op['profession']}  {data['rank']}",
        "只算升到这一档的晋升消耗，不含技能升级、专精、模组。",
    ]
    for row in data["costs"]:
        lines.append(
            f"{row['name']}  id {row['id']}  阶级 {row['tier']}  需要 {row['count']}"
        )
    chip = data["profession_chip"]
    lines.append(f"本职业芯片 {chip['name']} {chip['count']}")
    return "\n".join(lines)


def format_gap(data: dict) -> str:
    lines = ["清单"]
    for target in data["targets"]:
        op = target["operator"]
        chip = target["profession_chip"]
        lines.append(
            f"- {op['name']} {op['id']} {op['stars_text']}{op['profession']} {target['rank']}"
            f"  本职业芯片 {chip['name']} {chip['count']}"
        )
    lines.append(f"仓库日期 {data['depot_sync']}")
    lines.append("仓库没写出的材料按 0，并标明未记录。")
    for row in data["lines"]:
        if row["in_depot"]:
            owned = f"仓库 {row['have']}"
        else:
            owned = "仓库 未记录，按 0"
        lines.append(
            f"{row['name']}  需要 {row['need']}  {owned}  缺口 {row['short']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(prog="python -m desk_companion.material_ledger")
    parser.add_argument("--json", action="store_true", help="只打印结构")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    catalog_cmd = sub.add_parser("catalog")
    catalog_cmd.add_argument("keyword")
    cost_cmd = sub.add_parser("cost")
    cost_cmd.add_argument("operator")
    cost_cmd.add_argument("rank")
    gap_cmd = sub.add_parser("gap")
    gap_cmd.add_argument("targets", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "fetch":
            data = fetch()
            text = "\n".join(
                f"{row['file']}  {row['bytes']} 字节" for row in data["files"]
            )
            text = f"{data['dir']}\n{text}"
        elif args.cmd == "catalog":
            data = catalog(args.keyword)
            text = format_catalog(data)
        elif args.cmd == "cost":
            data = cost(args.operator, args.rank)
            text = format_cost(data)
        else:
            data = gap(args.targets)
            text = format_gap(data)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "desk-companion"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with dest.open("wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"下载失败 {url}。检查网络后重新执行 fetch，不要换别的数据源。"
        ) from exc


def _expect_table(name: str, raw: object) -> None:
    if not isinstance(raw, dict):
        raise RuntimeError(f"{name} 根节点必须是对象。重新 fetch。")
    if name == "item_table.json":
        items = raw.get("items")
        chip = items.get("3221") if isinstance(items, dict) else None
        if not isinstance(chip, dict) or chip.get("name") != "近卫芯片":
            raise RuntimeError("item_table 里没有近卫芯片（3221）。重新 fetch。")
        return
    if name == "character_table.json":
        operator = raw.get("char_172_svrash")
        if not isinstance(operator, dict) or operator.get("name") != "银灰":
            raise RuntimeError("character_table 里没有银灰（char_172_svrash）。重新 fetch。")
        return
    if name == "building_data.json":
        for key in ("workshopFormulas", "manufactFormulas"):
            if not isinstance(raw.get(key), dict):
                raise RuntimeError(f"building_data 缺少 {key}。重新 fetch。")
        return
    raise RuntimeError(f"不认识的表 {name}。")


def _load(name: str) -> dict:
    if name in _CACHE:
        return _CACHE[name]
    path = gamedata_dir() / name
    if not path.is_file():
        raise RuntimeError(
            f"缺少 {path}。在 desk-companion 目录执行："
            "python -m desk_companion.material_ledger fetch"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 不是合法 JSON。删掉 gamedata 后重新 fetch。") from exc
    _expect_table(name, raw)
    _CACHE[name] = raw
    return raw


def _items() -> dict:
    items = _load("item_table.json").get("items")
    if not isinstance(items, dict):
        raise RuntimeError("item_table 缺少 items。重新 fetch。")
    return items


def _item_name(item_id: str, item: dict) -> str:
    name = item.get("name")
    if type(name) is not str or not name.strip():
        raise RuntimeError(f"材料 {item_id} 没有中文名。重新 fetch。")
    return name.strip()


def _tier(item: dict) -> int:
    rarity = item.get("rarity")
    if type(rarity) is not str or not rarity.startswith("TIER_"):
        raise RuntimeError(f"材料 {item.get('itemId')} 的阶级不是 TIER_。重新 fetch。")
    number = rarity.removeprefix("TIER_")
    if not number.isdigit():
        raise RuntimeError(f"材料 {item.get('itemId')} 的阶级无法读取。重新 fetch。")
    return int(number)


def _catalog_row(item: dict) -> dict:
    item_id = item.get("itemId")
    if type(item_id) is not str or not item_id:
        raise RuntimeError("材料没有 itemId。重新 fetch。")
    products = item.get("buildingProductList")
    if not isinstance(products, list):
        raise RuntimeError(f"材料 {item_id} 的合成列表不是数组。重新 fetch。")
    return {
        "id": item_id,
        "name": _item_name(item_id, item),
        "tier": _tier(item),
        "recipes": [_recipe(item_id, entry) for entry in products],
    }


def _recipe(item_id: str, entry: object) -> dict:
    if not isinstance(entry, dict):
        raise RuntimeError(f"材料 {item_id} 的合成条目不是对象。重新 fetch。")
    room = entry.get("roomType")
    formula_id = entry.get("formulaId")
    if type(room) is not str or room not in STATIONS:
        raise RuntimeError(f"材料 {item_id} 的合成房间无法识别：{room}。")
    if type(formula_id) is not str or not formula_id:
        raise RuntimeError(f"材料 {item_id} 的配方编号是空的。重新 fetch。")
    station, table_key = STATIONS[room]
    tables = _load("building_data.json")
    formulas = tables.get(table_key)
    if not isinstance(formulas, dict) or formula_id not in formulas:
        raise RuntimeError(
            f"{station}没有配方 {formula_id}。重新 fetch，不要换数据源。"
        )
    formula = formulas[formula_id]
    if not isinstance(formula, dict):
        raise RuntimeError(f"配方 {formula_id} 不是对象。重新 fetch。")
    output_count = _positive_int(formula.get("count"), f"配方 {formula_id} 的产出数量")
    if formula.get("itemId") != item_id:
        raise RuntimeError(
            f"配方 {formula_id} 的产物不是 {item_id}。重新 fetch。"
        )
    inputs = []
    # 加工站配方带 goldCost；制造站配方没有这个字段。
    if room == "WORKSHOP":
        gold = formula.get("goldCost")
        if type(gold) is not int or gold < 0:
            raise RuntimeError(f"配方 {formula_id} 的龙门币消耗无法读取。重新 fetch。")
        if gold:
            inputs.append({"id": "4001", "name": "龙门币", "count": gold})
    costs = formula.get("costs")
    if not isinstance(costs, list):
        raise RuntimeError(f"配方 {formula_id} 的原料不是数组。重新 fetch。")
    items = _items()
    for part in costs:
        if not isinstance(part, dict):
            raise RuntimeError(f"配方 {formula_id} 的原料条目不是对象。重新 fetch。")
        part_id = part.get("id")
        if type(part_id) is not str or part_id not in items:
            raise RuntimeError(f"配方 {formula_id} 的原料 {part_id} 不在材料表。重新 fetch。")
        inputs.append(
            {
                "id": part_id,
                "name": _item_name(part_id, items[part_id]),
                "count": _positive_int(part.get("count"), f"配方 {formula_id} 的原料数量"),
            }
        )
    return {
        "station": station,
        "formula_id": formula_id,
        "inputs": inputs,
        "output_count": output_count,
        "extra": _extra_outcome(formula, formula_id, items, room),
    }


def _extra_outcome(formula: dict, formula_id: str, items: dict, room: str) -> dict | None:
    # 加工站配方带额外产出概率；制造站配方没有这个字段。
    if room == "WORKSHOP" and "extraOutcomeRate" not in formula:
        raise RuntimeError(f"配方 {formula_id} 没有额外产出概率。重新 fetch。")
    rate = formula.get("extraOutcomeRate", 0)
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate < 0:
        raise RuntimeError(f"配方 {formula_id} 的额外产出概率无法读取。重新 fetch。")
    if rate == 0:
        return None
    group = formula.get("extraOutcomeGroup")
    if not isinstance(group, list) or not group:
        raise RuntimeError(f"配方 {formula_id} 写了额外产出，但没有条目。重新 fetch。")
    outputs = []
    for entry in group:
        if not isinstance(entry, dict):
            raise RuntimeError(f"配方 {formula_id} 的额外产出不是对象。重新 fetch。")
        part_id = entry.get("itemId")
        if type(part_id) is not str or part_id not in items:
            raise RuntimeError(f"配方 {formula_id} 的额外产物 {part_id} 不在材料表。重新 fetch。")
        count = entry.get("itemCount")
        if type(count) is not int or count <= 0:
            raise RuntimeError(f"配方 {formula_id} 的额外产出数量无法读取。重新 fetch。")
        outputs.append(
            {"id": part_id, "name": _item_name(part_id, items[part_id]), "count": count}
        )
    percent = float(rate) * 100
    if abs(percent - round(percent)) < 1e-6:
        rate_text = f"{round(percent)}%"
    else:
        rate_text = f"{percent:.1f}%"
    return {"rate": rate, "rate_text": rate_text, "outputs": outputs}


def _characters() -> dict:
    return _load("character_table.json")


def _find_operator(who: str) -> dict:
    token = who.strip()
    if not token:
        raise RuntimeError("要给干员名或编号。")
    table = _characters()
    if token in table and isinstance(table[token], dict):
        operator = table[token]
        _require_operator(token, operator)
        return operator
    found = []
    for char_id, operator in table.items():
        if not isinstance(operator, dict):
            continue
        if operator.get("name") != token:
            continue
        if operator.get("profession") not in PROFESSION:
            continue
        _require_operator(char_id, operator)
        found.append(operator)
    if not found:
        raise RuntimeError(f"没有叫「{token}」的干员。")
    if len(found) > 1:
        lines = [
            f"有多名干员都叫「{token}」。改用编号：",
            *(
                f"  {op['id']}  {op['stars_text']}{PROFESSION[op['profession']]}"
                for op in found
            ),
        ]
        raise RuntimeError("\n".join(lines))
    return found[0]


def _require_operator(char_id: str, operator: dict) -> None:
    if type(char_id) is not str or not char_id:
        raise RuntimeError("干员编号是空的。重新 fetch。")
    name = operator.get("name")
    profession = operator.get("profession")
    if type(name) is not str or not name.strip():
        raise RuntimeError(f"{char_id} 没有中文名。重新 fetch。")
    if profession not in PROFESSION:
        raise RuntimeError(f"{name} 的职业不在八职业里，不算养成干员。")
    if not isinstance(operator.get("phases"), list):
        raise RuntimeError(f"{name} 没有晋升阶段。重新 fetch。")
    operator["id"] = char_id
    operator["stars"] = _stars(operator.get("rarity"), name)
    operator["stars_text"] = "一二三四五六"[operator["stars"] - 1] + "星"


def _stars(rarity: object, name: str) -> int:
    if type(rarity) is not str or not rarity.startswith("TIER_"):
        raise RuntimeError(f"{name} 的星级无法读取。重新 fetch。")
    number = rarity.removeprefix("TIER_")
    if number not in {"1", "2", "3", "4", "5", "6"}:
        raise RuntimeError(f"{name} 的星级无法读取。重新 fetch。")
    return int(number)


def _operator_view(operator: dict) -> dict:
    return {
        "id": operator["id"],
        "name": operator["name"].strip(),
        "stars": operator["stars"],
        "stars_text": operator["stars_text"],
        "profession": PROFESSION[operator["profession"]],
        "chip": _profession_chip(operator["profession"]),
    }


def _profession_chip(profession: str) -> str:
    if profession not in PROFESSION:
        raise RuntimeError(f"职业 {profession} 对不上芯片。")
    name = f"{PROFESSION[profession]}芯片"
    if name not in _CHIP_NAMES:
        raise RuntimeError(f"{name} 不在刷图芯片表里。")
    return name


def _rank_name(rank: str) -> str:
    text = rank.strip()
    if text not in RANKS:
        raise RuntimeError("档位只认 精一 或 精二。")
    return text


def _evolve_costs(operator: dict, rank: str) -> list[dict]:
    phases = operator["phases"]
    index = RANKS[rank]
    name = operator["name"].strip()
    if index >= len(phases):
        raise RuntimeError(f"{name} 没有{rank}。")
    phase = phases[index]
    if not isinstance(phase, dict):
        raise RuntimeError(f"{name} 的{rank}阶段不是对象。重新 fetch。")
    raw = phase.get("evolveCost")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"{name} 的{rank}没有晋升消耗。")
    items = _items()
    totals: dict[str, int] = {}
    order: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise RuntimeError(f"{name} 的{rank}消耗条目不是对象。重新 fetch。")
        item_id = entry.get("id")
        if type(item_id) is not str or item_id not in items:
            raise RuntimeError(
                f"{name} 的{rank}材料 {item_id} 不在材料表。重新 fetch。"
            )
        count = _positive_int(entry.get("count"), f"{name} 的{rank}材料数量")
        if item_id not in totals:
            totals[item_id] = 0
            order.append(item_id)
        totals[item_id] += count
    rows = []
    for item_id in order:
        item = items[item_id]
        rows.append(
            {
                "id": item_id,
                "name": _item_name(item_id, item),
                "tier": _tier(item),
                "count": totals[item_id],
            }
        )
    return rows


def _split_spec(spec: str) -> tuple[str, str]:
    text = spec.strip()
    for mark in (":", "："):
        if mark in text:
            who, rank = text.split(mark, 1)
            if who.strip() and rank.strip():
                return who.strip(), rank.strip()
    raise RuntimeError(
        f"「{spec}」不是 干员:档位。例子：银灰:精一"
    )


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise RuntimeError(f"{label}必须是正整数。重新 fetch。")
    return value


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
