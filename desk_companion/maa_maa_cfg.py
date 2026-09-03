"""写入 MAA 6.16 的 gui.new.json：PC 连接 + 远控地址 + 任务队列勾选。URI 用当前用户 DPAPI。"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import win32crypt

from .maa_options import TASK_TYPE


def patch_maa_config(
    maa_exe: Path,
    get_url: str,
    report_url: str,
    selected: list[str],
    *,
    depot_interval: str = "Daily",
) -> Path:
    if not maa_exe.is_file():
        raise RuntimeError(f"MAA.exe 不存在：{maa_exe}")
    root = maa_exe.resolve().parent
    cfg_dir = root / "config"
    cfg_dir.mkdir(exist_ok=True)
    path = cfg_dir / "gui.new.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{path} 不是合法 JSON。关掉 MAA 后删掉该文件，再让桌宠写配置。"
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"{path} 根节点必须是对象。")
    else:
        data = {"Current": "Default", "Configurations": {"Default": {}}}

    current = data.get("Current") or "Default"
    if type(current) is not str or not current:
        current = "Default"
        data["Current"] = current
    configs = data.setdefault("Configurations", {})
    if not isinstance(configs, dict):
        raise RuntimeError(f"{path} 的 Configurations 必须是对象。")
    cfg = configs.setdefault(current, {})
    if not isinstance(cfg, dict):
        raise RuntimeError(f"{path} 的当前配置必须是对象。")
    gui = cfg.setdefault("Gui", {})
    if not isinstance(gui, dict):
        raise RuntimeError(f"{path} 的 Gui 必须是对象。")

    connect = gui.setdefault("ConnectSettings", {})
    if not isinstance(connect, dict):
        raise RuntimeError(f"{path} 的 ConnectSettings 必须是对象。")
    connect["Config"] = "PC"
    connect["AutoDetect"] = False
    extras = connect.setdefault("Extras", {})
    if not isinstance(extras, dict):
        raise RuntimeError(f"{path} 的 Extras 必须是对象。")
    win32 = extras.setdefault("Win32Extra", {})
    if not isinstance(win32, dict):
        raise RuntimeError(f"{path} 的 Win32Extra 必须是对象。")
    # FramePool 截图可用。SendMessage(32) 点得到坐标但 Unity/ACE 不走；Seize(1) 才是真实鼠标。
    win32["ScreencapMethod"] = 2
    win32["MouseMethod"] = 1
    win32["KeyboardMethod"] = 1

    remote = gui.setdefault("RemoteControl", {})
    if not isinstance(remote, dict):
        raise RuntimeError(f"{path} 的 RemoteControl 必须是对象。")
    remote["RemoteControlGetTaskEndpointUri"] = _protect(get_url)
    remote["RemoteControlReportStatusUri"] = _protect(report_url)
    remote["RemoteControlUserIdentity"] = _protect("desk-companion")
    remote["RemoteControlDeviceIdentity"] = _protect("desk-companion-pc")
    remote["RemoteControlPollIntervalMs"] = 1000

    _apply_task_queue(cfg, selected, path, depot_interval=depot_interval)

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def _apply_task_queue(
    cfg: dict, selected: list[str], path: Path, *, depot_interval: str
) -> None:
    if depot_interval not in ("Daily", "EveryTime"):
        raise RuntimeError(
            f"更新数据间隔必须是 Daily 或 EveryTime，不能是 {depot_interval!r}。"
        )
    if not isinstance(selected, list):
        raise RuntimeError("勾选必须是字符串列表。")
    unknown = [item for item in selected if item not in TASK_TYPE]
    if unknown:
        raise RuntimeError(f"未知日常项 {unknown[0]!r}，不能写入任务队列。")
    queue = cfg.get("TaskQueue")
    if not isinstance(queue, list) or not queue:
        raise RuntimeError(
            f"{path} 没有任务队列。关掉 MAA，在主界面保存一次后再点清日常。"
        )
    enable_by_type = {TASK_TYPE[opt_id]: opt_id in set(selected) for opt_id in TASK_TYPE}
    seen: dict[str, int] = {}
    update = None
    for item in queue:
        if not isinstance(item, dict):
            raise RuntimeError(
                f"{path} 的 TaskQueue 有非法项。关掉 MAA，在主界面保存一次。"
            )
        task_type = item.get("TaskType")
        if type(task_type) is not str or not task_type:
            raise RuntimeError(
                f"{path} 的 TaskQueue 有项缺少 TaskType。关掉 MAA，在主界面保存一次。"
            )
        seen[task_type] = seen.get(task_type, 0) + 1
        if seen[task_type] > 1:
            raise RuntimeError(
                f"{path} 的任务队列里 {task_type} 出现两次。不要猜用哪条，先在 MAA 里整理队列。"
            )
        if task_type in enable_by_type:
            item["IsEnable"] = enable_by_type[task_type]
        elif task_type == "UserDataUpdate":
            update = item
    missing = [name for name in enable_by_type if name not in seen]
    if missing:
        raise RuntimeError(
            f"{path} 的任务队列缺少：{'、'.join(missing)}。"
            "关掉 MAA，在主界面补全并保存后再点清日常。"
        )
    if update is None:
        raise RuntimeError(
            f"{path} 没有「更新数据」。在 MAA 主界面勾上更新数据并保存，关掉 MAA，再点清日常。"
        )
    update["IsEnable"] = True
    update["UpdateDepot"] = True
    update["TriggerInterval"] = depot_interval
    update["IsTriggered"] = True


def _protect(plain: str) -> str:
    blob = win32crypt.CryptProtectData(plain.encode("utf-8"), None, None, None, None, 0)
    return base64.b64encode(blob).decode("ascii")
