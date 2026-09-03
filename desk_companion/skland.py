"""从森空岛官方 player/info 建成账号状态，写入 arknights_account.json。"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from .envconf import SKLAND_TOKEN_HINT, has_skland_token, require_skland_token, skland_uid
from .logutil import log
from .maa_depot import (
    account_path,
    merge_skland,
    read_account_file,
    require_skland_today,
    _parse_sync_time,
)

APP_CODE = "4ca99fa6b56cc2ba"
UA = "Skland/1.32.1 (com.hypergryph.skland; build:103201004; Android 33; ) Okhttp/4.11.0"
GRANT_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
CRED_URL = "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code"
BIND_URL = "https://zonai.skland.com/api/v1/game/player/binding"
INFO_URL = "https://zonai.skland.com/api/v1/game/player/info"
ELITE = {0: "未精英", 1: "精一", 2: "精二"}
PROFESSION = {
    "PIONEER": "先锋",
    "WARRIOR": "近卫",
    "TANK": "重装",
    "SNIPER": "狙击",
    "CASTER": "术师",
    "MEDIC": "医疗",
    "SUPPORT": "辅助",
    "SPECIAL": "特种",
}


def sync_from_skland() -> dict:
    """打官方接口，覆盖 skland / skland_sync。不改 inventory。"""
    token = require_skland_token()
    grant_code = _oauth_grant(token)
    cred, sign_token = _cred_by_code(grant_code)
    binding = _signed_get(BIND_URL, cred, sign_token, "绑定角色")
    uid = _pick_official_uid(binding)
    info = _signed_get(f"{INFO_URL}?uid={uid}", cred, sign_token, "玩家数据")
    player = info.get("data")
    if not isinstance(player, dict):
        raise RuntimeError("森空岛 player/info 的 data 必须是对象。")
    model = _parse_player(player, uid)
    sync_raw = datetime.now().astimezone().isoformat(timespec="seconds")
    merge_skland(model, sync_raw)
    log(f"森空岛已同步官服 uid={uid} 干员 {len(model['chars'])} 名")
    return board_snapshot()


def board_snapshot() -> dict:
    """看板用：不含 chars，不含凭证。"""
    out = {
        "ok": True,
        "synced": False,
        "today": False,
        "has_token": has_skland_token(),
        "hint": "",
        "uid": "",
        "level": None,
        "ap": None,
        "ap_max": None,
        "orundum": None,
        "orundum_cap": None,
        "device": None,
        "device_total": None,
        "strip": None,
        "strip_total": None,
        "monthly_card": None,
        "subscription_end": "",
        "sync": "",
        "char_count": 0,
    }
    if not out["has_token"]:
        out["hint"] = SKLAND_TOKEN_HINT
    data = read_account_file()
    skland = data.get("skland")
    sync_raw = data.get("skland_sync")
    if skland is None and sync_raw is None:
        if out["has_token"]:
            out["hint"] = "点「同步森空岛」拉取本号理智、周玉、保全和干员进度。"
        return out
    if not isinstance(skland, dict):
        raise RuntimeError(f"{account_path()} 的 skland 必须是对象。改正或删掉后重新同步。")
    view = _public_view(skland, sync_raw)
    out.update(view)
    out["synced"] = True
    if not out["has_token"]:
        out["hint"] = SKLAND_TOKEN_HINT
    elif not out["today"]:
        out["hint"] = "上次同步不是今天。点「同步森空岛」再拉一次。"
    return out


def format_status_text() -> str:
    skland = require_skland_today()
    view = _public_view(skland, _sync_raw())
    card = "有效" if view["monthly_card"] else "无效"
    end = view["subscription_end"] or "无到期时间"
    return (
        f"官服 uid {view['uid']}，等级 {view['level']}。\n"
        f"实时理智 {view['ap']} / {view['ap_max']}。\n"
        f"本周剿灭合成玉 {view['orundum']} / {view['orundum_cap']}。\n"
        f"保全增补仪 {view['device']} / {view['device_total']}，"
        f"增补条 {view['strip']} / {view['strip_total']}。\n"
        f"月卡{card}（{end}）。\n"
        f"同步时间 {view['sync']}。干员共 {view['char_count']} 名，"
        "查某干员用中文名调 get_arknights_operator。"
    )


def format_operator_text(name: str) -> str:
    if type(name) is not str or not name.strip():
        raise RuntimeError("干员名必须是游戏里的中文名。")
    key = name.strip()
    skland = require_skland_today()
    chars = skland.get("chars")
    if not isinstance(chars, dict):
        raise RuntimeError("账本 skland.chars 必须是对象。打开看板重新同步森空岛。")
    row = chars.get(key)
    if isinstance(row, dict):
        return _one_operator_line(key, row)
    aliases = [stored for stored in chars if stored.startswith(key + "（")]
    if aliases:
        lines = [f"「{key}」有 {len(aliases)} 名，全部如下："]
        for stored in aliases:
            item = chars.get(stored)
            if not isinstance(item, dict):
                raise RuntimeError(
                    f"账本里「{stored}」不是对象。打开看板重新同步森空岛。"
                )
            lines.append(_one_operator_line(stored, item))
        return "\n".join(lines)
    raise RuntimeError(
        f"账本里没有「{key}」。用游戏里的中文名（精确匹配），不要编造。"
    )


def _one_operator_line(key: str, row: dict) -> str:
    elite = ELITE.get(row.get("evolve_phase"))
    if elite is None:
        raise RuntimeError(f"「{key}」的精英阶段无法识别。打开看板重新同步森空岛。")
    specs = row.get("specialize")
    if not isinstance(specs, list):
        raise RuntimeError(f"「{key}」缺少技能专精。打开看板重新同步森空岛。")
    spec_text = "、".join(str(v) for v in specs) if specs else "无"
    modules = row.get("modules")
    if not isinstance(modules, list):
        raise RuntimeError(f"「{key}」缺少模组。打开看板重新同步森空岛。")
    if modules:
        mod_text = "；".join(
            f"{m.get('name') or m.get('id')} 等级 {m.get('level')}" for m in modules
        )
    else:
        mod_text = "无"
    return (
        f"{key}：{elite} {row.get('level')} 级，技能等级 {row.get('main_skill_lvl')}，"
        f"专精 {spec_text}。模组：{mod_text}。"
    )


def live_ap(ap: dict, now_ts: int) -> int:
    """实时理智。禁止直接用 ap.current。"""
    current = _int(ap.get("current"), "ap.current")
    max_ap = _int(ap.get("max"), "ap.max")
    last_add = _int(ap.get("lastApAddTime"), "ap.lastApAddTime")
    complete = _int(ap.get("completeRecoveryTime"), "ap.completeRecoveryTime")
    if type(now_ts) is not int:
        raise RuntimeError("计算理智的当前时间必须是整数时间戳。")
    if complete in (-1, 0):
        return current
    if now_ts >= complete:
        return max_ap
    if now_ts < last_add:
        raise RuntimeError("森空岛 lastApAddTime 晚于当前时间。核对系统时间。")
    recovered = current + (now_ts - last_add) // 360
    if recovered < current:
        raise RuntimeError("算出的实时理智小于快照，核对系统时间后重新同步。")
    return min(max_ap, recovered)


def _oauth_grant(token: str) -> str:
    payload = _http_json(
        "POST",
        GRANT_URL,
        body={"token": token, "appCode": APP_CODE, "type": 0},
        step="oauth grant",
    )
    status = payload.get("status")
    if status != 0:
        msg = payload.get("msg") or payload.get("message") or "失败"
        raise RuntimeError(f"森空岛 oauth grant 失败：{msg}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("森空岛 oauth grant 的 data 必须是对象。")
    code = data.get("code")
    if type(code) is not str or not code.strip():
        raise RuntimeError("森空岛 oauth grant 没有 code。")
    return code.strip()


def _cred_by_code(grant_code: str) -> tuple[str, str]:
    payload = _http_json(
        "POST",
        CRED_URL,
        body={"kind": 1, "code": grant_code},
        step="generate_cred",
    )
    _require_skland_ok(payload, "generate_cred")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("森空岛 generate_cred 的 data 必须是对象。")
    cred = data.get("cred")
    sign_token = data.get("token")
    if type(cred) is not str or not cred.strip():
        raise RuntimeError("森空岛 generate_cred 没有 cred。")
    if type(sign_token) is not str or not sign_token.strip():
        raise RuntimeError("森空岛 generate_cred 没有签名 token。")
    return cred.strip(), sign_token.strip()


def _signed_get(url: str, cred: str, sign_token: str, step: str) -> dict:
    headers = _sign_headers(cred, sign_token, url, "GET", None)
    payload = _http_json("GET", url, headers=headers, step=step)
    _require_skland_ok(payload, step)
    return payload


def _sign_headers(cred: str, cred_token: str, url: str, method: str, body: dict | None) -> dict:
    """copy 自 2026-08-28 已跑通的探测脚本，不改算法。"""
    ts = str(int(time.time()) - 1)
    header_ca = {"platform": "", "timestamp": ts, "dId": "", "vName": ""}
    parsed = urlparse(url)
    query = json.dumps(body, separators=(",", ":")) if method == "POST" else (parsed.query or "")
    secret = f"{parsed.path}{query}{ts}{json.dumps(header_ca, separators=(',', ':'))}"
    hex_secret = hmac.new(cred_token.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()
    sign = hashlib.md5(hex_secret.encode("utf-8")).hexdigest()
    return {
        "cred": cred,
        "sign": sign,
        "platform": "",
        "timestamp": ts,
        "dId": "",
        "vName": "",
        "User-Agent": UA,
    }


def _http_json(
    method: str,
    url: str,
    headers: dict | None = None,
    body: dict | None = None,
    *,
    step: str,
) -> dict:
    data = None
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        parsed = _parse_json_object(text, step)
        msg = parsed.get("msg") or parsed.get("message") or f"HTTP {exc.code}"
        raise RuntimeError(f"森空岛{step}失败：{msg}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"森空岛{step}连不上：{exc.reason}") from None
    return _parse_json_object(text, step)


def _parse_json_object(text: str, step: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"森空岛{step}返回不是 JSON。") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"森空岛{step}返回不是对象。")
    return payload


def _require_skland_ok(payload: dict, step: str) -> None:
    if payload.get("code") != 0:
        msg = payload.get("message") or payload.get("msg") or "失败"
        raise RuntimeError(f"森空岛{step}失败：{msg}")


def _pick_official_uid(payload: dict) -> str:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("森空岛绑定列表的 data 必须是对象。")
    apps = data.get("list")
    if not isinstance(apps, list):
        raise RuntimeError("森空岛绑定列表必须是数组。")
    uids: list[str] = []
    for app in apps:
        if not isinstance(app, dict):
            raise RuntimeError("森空岛绑定项必须是对象。")
        if app.get("appCode") != "arknights":
            continue
        bindings = app.get("bindingList")
        if not isinstance(bindings, list):
            raise RuntimeError("森空岛 bindingList 必须是数组。")
        for row in bindings:
            if not isinstance(row, dict):
                raise RuntimeError("森空岛角色绑定必须是对象。")
            if row.get("isOfficial") is not True:
                continue
            uid = row.get("uid")
            if type(uid) is not str or not uid.strip():
                raise RuntimeError("森空岛官服绑定缺少 uid。")
            uids.append(uid.strip())
    wanted = skland_uid()
    uniq = list(dict.fromkeys(uids))
    if not uniq:
        raise RuntimeError("没有明日方舟官服绑定。不同步终末地或其它鹰角游戏。")
    if wanted:
        if wanted not in uniq:
            raise RuntimeError(
                f".env 的 SKLAND_UID={wanted} 不是明日方舟官服绑定。"
                "官服 uid：" + "、".join(uniq)
            )
        return wanted
    if len(uniq) > 1:
        raise RuntimeError(
            "绑定了多个明日方舟官服角色。在 .env 写 SKLAND_UID=游戏uid 指定其中一个。"
            "官服 uid：" + "、".join(uniq)
        )
    return uniq[0]


def _parse_player(player: dict, uid: str) -> dict:
    status = player.get("status")
    if not isinstance(status, dict):
        raise RuntimeError("森空岛 status 必须是对象。")
    status_uid = status.get("uid")
    if str(status_uid) != uid:
        raise RuntimeError("player/info 的 uid 与绑定官服不一致。")
    ap = status.get("ap")
    if not isinstance(ap, dict):
        raise RuntimeError("森空岛 status.ap 必须是对象。")
    campaign = player.get("campaign")
    if not isinstance(campaign, dict):
        raise RuntimeError("森空岛 campaign 必须是对象。")
    reward = campaign.get("reward")
    if not isinstance(reward, dict):
        raise RuntimeError("森空岛 campaign.reward 必须是对象。")
    tower = player.get("tower")
    if not isinstance(tower, dict):
        raise RuntimeError("森空岛 tower 必须是对象。")
    trew = tower.get("reward")
    if not isinstance(trew, dict):
        raise RuntimeError("森空岛 tower.reward 必须是对象。")
    higher = trew.get("higherItem")
    lower = trew.get("lowerItem")
    if not isinstance(higher, dict) or not isinstance(lower, dict):
        raise RuntimeError("森空岛保全额度 higherItem / lowerItem 必须是对象。")
    sub_end = _int(status.get("subscriptionEnd"), "status.subscriptionEnd")
    now_ts = _int(player.get("currentTs"), "currentTs")
    ap_raw = {
        "current": _int(ap.get("current"), "ap.current"),
        "max": _int(ap.get("max"), "ap.max"),
        "lastApAddTime": _int(ap.get("lastApAddTime"), "ap.lastApAddTime"),
        "completeRecoveryTime": _int(ap.get("completeRecoveryTime"), "ap.completeRecoveryTime"),
    }
    live_ap(ap_raw, now_ts)
    chars = _parse_chars(player)
    return {
        "uid": uid,
        "level": _int(status.get("level"), "status.level"),
        "last_online_ts": _int(status.get("lastOnlineTs"), "status.lastOnlineTs"),
        "main_stage_progress": status.get("mainStageProgress")
        if type(status.get("mainStageProgress")) is str
        else "",
        "subscription_end": sub_end,
        "ap": ap_raw,
        "campaign": {
            "current": _int(reward.get("current"), "campaign.reward.current"),
            "total": _int(reward.get("total"), "campaign.reward.total"),
        },
        "tower": {
            "device_current": _int(higher.get("current"), "tower.higherItem.current"),
            "device_total": _int(higher.get("total"), "tower.higherItem.total"),
            "strip_current": _int(lower.get("current"), "tower.lowerItem.current"),
            "strip_total": _int(lower.get("total"), "tower.lowerItem.total"),
            "term_ts": _int(trew.get("termTs"), "tower.reward.termTs"),
        },
        "chars": chars,
    }


def _parse_chars(player: dict) -> dict:
    raw = player.get("chars")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("森空岛 chars 必须是非空数组。")
    info_map = player.get("charInfoMap")
    if not isinstance(info_map, dict) or not info_map:
        raise RuntimeError("森空岛 charInfoMap 必须是对象。")
    equip_map = player.get("equipmentInfoMap")
    if equip_map is None:
        equip_map = player.get("equipInfoMap")
    if equip_map is not None and not isinstance(equip_map, dict):
        raise RuntimeError("森空岛模组表必须是对象。")
    rows = []
    for index, ch in enumerate(raw):
        if not isinstance(ch, dict):
            raise RuntimeError(f"森空岛 chars[{index}] 必须是对象。")
        char_id = ch.get("charId")
        if type(char_id) is not str or not char_id.strip():
            raise RuntimeError(f"森空岛 chars[{index}] 缺少 charId。")
        info = info_map.get(char_id)
        if not isinstance(info, dict):
            raise RuntimeError(f"森空岛 charInfoMap 没有 {char_id}。")
        name = info.get("name")
        if type(name) is not str or not name.strip():
            raise RuntimeError(f"森空岛 {char_id} 没有中文名。")
        rows.append((name.strip(), char_id.strip(), ch, info))
    counts: dict[str, int] = {}
    for name, _cid, _ch, _info in rows:
        counts[name] = counts.get(name, 0) + 1
    out = {}
    for name, char_id, ch, info in rows:
        key = _char_key(name, info, counts[name])
        if key in out:
            raise RuntimeError(
                f"森空岛干员键重复：{key}（{out[key]['char_id']} 与 {char_id}）。"
            )
        evolve = _int(ch.get("evolvePhase"), f"{key}.evolvePhase")
        if evolve not in ELITE:
            raise RuntimeError(f"{key} 的 evolvePhase 不是 0/1/2。")
        skills = ch.get("skills")
        if skills is None:
            skills = []
        if not isinstance(skills, list):
            raise RuntimeError(f"{key} 的 skills 必须是数组。")
        specialize = []
        for si, skill in enumerate(skills):
            if not isinstance(skill, dict):
                raise RuntimeError(f"{key} 的 skills[{si}] 必须是对象。")
            specialize.append(
                _int(skill.get("specializeLevel"), f"{key}.skills[{si}].specializeLevel")
            )
        modules = []
        equip = ch.get("equip")
        if equip is None:
            equip = []
        if not isinstance(equip, list):
            raise RuntimeError(f"{key} 的 equip 必须是数组。")
        for ei, item in enumerate(equip):
            if not isinstance(item, dict):
                raise RuntimeError(f"{key} 的 equip[{ei}] 必须是对象。")
            eid = item.get("id")
            if type(eid) is not str or not eid.strip():
                raise RuntimeError(f"{key} 的模组缺少 id。")
            label = eid.strip()
            if isinstance(equip_map, dict):
                meta = equip_map.get(label)
                if isinstance(meta, dict) and type(meta.get("name")) is str and meta["name"].strip():
                    label_name = meta["name"].strip()
                else:
                    label_name = label
            else:
                label_name = label
            if item.get("locked") is True:
                continue
            if eid.strip().startswith("uniequip_001_") or label_name.endswith("证章"):
                continue
            modules.append(
                {
                    "id": eid.strip(),
                    "name": label_name,
                    "level": _int(item.get("level"), f"{key}.equip[{ei}].level"),
                }
            )
        out[key] = {
            "char_id": char_id,
            "evolve_phase": evolve,
            "level": _int(ch.get("level"), f"{key}.level"),
            "main_skill_lvl": _int(ch.get("mainSkillLvl"), f"{key}.mainSkillLvl"),
            "specialize": specialize,
            "modules": modules,
        }
    return out


def _char_key(name: str, info: dict, copies: int) -> str:
    if copies == 1:
        return name
    prof = info.get("profession")
    cn = PROFESSION.get(prof) if type(prof) is str else None
    if not cn:
        raise RuntimeError(
            f"{name} 中文名重复，但 profession={prof!r} 无法翻译成职业后缀。"
        )
    return f"{name}（{cn}）"


def _public_view(skland: dict, sync_raw) -> dict:
    ap = skland.get("ap")
    if not isinstance(ap, dict):
        raise RuntimeError("账本 skland.ap 必须是对象。打开看板重新同步森空岛。")
    campaign = skland.get("campaign")
    if not isinstance(campaign, dict):
        raise RuntimeError("账本 skland.campaign 必须是对象。打开看板重新同步森空岛。")
    tower = skland.get("tower")
    if not isinstance(tower, dict):
        raise RuntimeError("账本 skland.tower 必须是对象。打开看板重新同步森空岛。")
    chars = skland.get("chars")
    if not isinstance(chars, dict):
        raise RuntimeError("账本 skland.chars 必须是对象。打开看板重新同步森空岛。")
    now_ts = int(time.time())
    sub_end = _int(skland.get("subscription_end"), "skland.subscription_end")
    today = False
    sync_text = ""
    if type(sync_raw) is str and sync_raw.strip():
        sync_text = sync_raw.strip()
        when = _parse_sync_time(
            sync_raw,
            account_path(),
            field="skland_sync",
            how="打开看板「明日方舟」点「同步森空岛」。",
        )
        today = when.astimezone().date() == datetime.now().astimezone().date()
    end_text = ""
    if sub_end > 0:
        end_text = datetime.fromtimestamp(sub_end).astimezone().strftime("%Y-%m-%d")
    return {
        "uid": str(skland.get("uid") or ""),
        "level": _int(skland.get("level"), "skland.level"),
        "ap": live_ap(ap, now_ts),
        "ap_max": _int(ap.get("max"), "ap.max"),
        "orundum": _int(campaign.get("current"), "campaign.current"),
        "orundum_cap": _int(campaign.get("total"), "campaign.total"),
        "device": _int(tower.get("device_current"), "tower.device_current"),
        "device_total": _int(tower.get("device_total"), "tower.device_total"),
        "strip": _int(tower.get("strip_current"), "tower.strip_current"),
        "strip_total": _int(tower.get("strip_total"), "tower.strip_total"),
        "monthly_card": sub_end > now_ts,
        "subscription_end": end_text,
        "sync": sync_text,
        "today": today,
        "char_count": len(chars),
    }


def _sync_raw() -> str:
    data = read_account_file()
    raw = data.get("skland_sync")
    if type(raw) is not str:
        return ""
    return raw


def _int(value, path: str) -> int:
    if type(value) is not int:
        raise RuntimeError(f"森空岛 {path} 必须是整数，缺了不当 0。")
    return value
