"""明日方舟 / MAA 本机配置。独立文件，不进 user_state.json。"""
from __future__ import annotations

import json
import threading
import winreg
from pathlib import Path

from .maa_options import IDS, default_selected, parse_selected

CONFIG_NAME = "maa.json"
REQUIRED = (
    "launcher_exe",
    "game_exe",
    "maa_exe",
    "selected",
    "open_timeout_sec",
    "remote_port",
)
_LOCK = threading.Lock()


def config_path() -> Path:
    return Path(__file__).resolve().parents[1] / CONFIG_NAME


def load_maa() -> dict:
    path = config_path()
    if not path.is_file():
        data = _blank()
        _write(path, data)
        return load_maa()
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
    launcher = _must_str(raw["launcher_exe"], "launcher_exe", path)
    game = _must_str(raw["game_exe"], "game_exe", path)
    maa_exe = _must_str(raw["maa_exe"], "maa_exe", path)
    timeout = raw["open_timeout_sec"]
    if type(timeout) is not int or timeout < 10:
        raise RuntimeError(
            f"{path} 的 open_timeout_sec 必须是大于等于 10 的整数。改正或删掉该文件后重启。"
        )
    remote_port = raw["remote_port"]
    if type(remote_port) is not int or remote_port < 1024 or remote_port > 65535:
        raise RuntimeError(
            f"{path} 的 remote_port 必须是 1024 到 65535 的整数。改正或删掉该文件后重启。"
        )
    selected = parse_selected(raw["selected"])
    return {
        "launcher_exe": launcher,
        "game_exe": game,
        "maa_exe": maa_exe,
        "selected": selected,
        "open_timeout_sec": timeout,
        "remote_port": remote_port,
        "path": str(path),
    }


def save_maa(
    *,
    launcher_exe: str,
    game_exe: str,
    maa_exe: str,
    selected: list[str],
    open_timeout_sec: int,
    remote_port: int,
) -> dict:
    data = {
        "launcher_exe": launcher_exe.strip(),
        "game_exe": game_exe.strip(),
        "maa_exe": maa_exe.strip(),
        "selected": parse_selected(selected),
        "open_timeout_sec": int(open_timeout_sec),
        "remote_port": int(remote_port),
    }
    if data["open_timeout_sec"] < 10:
        raise RuntimeError("打开超时至少 10 秒。")
    if data["remote_port"] < 1024 or data["remote_port"] > 65535:
        raise RuntimeError("远控端口必须是 1024 到 65535。")
    path = config_path()
    _write(path, data)
    return load_maa()


def save_selected(selected: list[str]) -> dict:
    cfg = load_maa()
    return save_maa(
        launcher_exe=cfg["launcher_exe"],
        game_exe=cfg["game_exe"],
        maa_exe=cfg["maa_exe"],
        selected=selected,
        open_timeout_sec=cfg["open_timeout_sec"],
        remote_port=cfg["remote_port"],
    )


def require_pc_paths(cfg: dict) -> tuple[Path, Path]:
    """开游戏前检查启动器和游戏 exe。缺了就失败，不另找别的路径。"""
    path = cfg["path"]
    launcher = Path(cfg["launcher_exe"])
    game = Path(cfg["game_exe"])
    if not cfg["launcher_exe"]:
        raise RuntimeError(
            f"还没填鹰角启动器路径。在看板「明日方舟」页填写 Launcher.exe。"
            f"{_hint()}"
        )
    if not cfg["game_exe"]:
        raise RuntimeError(
            f"还没填明日方舟 PC 客户端路径。填写启动器目录下的 Arknights.exe，不要填模拟器。"
            f"{_hint()}"
        )
    if not launcher.is_file():
        raise RuntimeError(
            f"{path} 的 launcher_exe 不是文件：{launcher}。改正后再打开游戏。{_hint()}"
        )
    if not game.is_file():
        raise RuntimeError(
            f"{path} 的 game_exe 不是文件：{game}。应是鹰角启动器安装的 Arknights.exe。{_hint()}"
        )
    if game.name.lower() != "arknights.exe":
        raise RuntimeError(
            f"game_exe 必须是 Arknights.exe，当前是 {game.name}。"
            "不要填 Endfield.exe，也不要填安卓模拟器。"
        )
    if game.name.lower() == "endfield.exe" or "endfield" in game.as_posix().lower():
        raise RuntimeError("不要用终末地客户端。game_exe 必须是明日方舟 Arknights.exe。")
    return launcher, game


def require_maa_exe(cfg: dict) -> Path:
    path = cfg["path"]
    if not cfg["maa_exe"]:
        raise RuntimeError(
            "还没填官方 MAA.exe。装好后把路径写进看板「明日方舟」页。"
            "不要把 MaaCore 链进桌宠。"
        )
    maa = Path(cfg["maa_exe"])
    if not maa.is_file():
        raise RuntimeError(f"{path} 的 maa_exe 不是文件：{maa}。")
    if maa.name.lower() != "maa.exe":
        raise RuntimeError(f"maa_exe 必须是 MAA.exe，当前是 {maa.name}。")
    return maa


def probe_hint_paths() -> tuple[str, str]:
    """只用于失败文案，不自动改 maa.json。"""
    launcher, game = _probe_install()
    return launcher, game


def _blank() -> dict:
    launcher, game = _probe_install()
    return {
        "launcher_exe": launcher,
        "game_exe": game,
        "maa_exe": "",
        "selected": default_selected(),
        "open_timeout_sec": 90,
        "remote_port": 12701,
    }


def _probe_install() -> tuple[str, str]:
    """首次写 maa.json 时，若本机卸载项指向已存在的文件则写入。不是运行时换路。"""
    root = _uninstall_location()
    if not root:
        return "", ""
    launcher = root / "Launcher.exe"
    game = root / "games" / "Arknights Game" / "Arknights.exe"
    launcher_s = str(launcher) if launcher.is_file() else ""
    game_s = str(game) if game.is_file() else ""
    return launcher_s, game_s


def _uninstall_location() -> Path | None:
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, key_path in roots:
        try:
            with winreg.OpenKey(hive, key_path) as parent:
                count = winreg.QueryInfoKey(parent)[0]
                for i in range(count):
                    name = winreg.EnumKey(parent, i)
                    try:
                        with winreg.OpenKey(parent, name) as sub:
                            loc = _reg_str(sub, "InstallLocation")
                            pub = _reg_str(sub, "Publisher")
                    except OSError:
                        continue
                    if "hypergryph" not in pub.lower():
                        continue
                    if loc:
                        path = Path(loc)
                        if path.is_dir():
                            return path
        except OSError:
            continue
    return None


def _reg_str(key, name: str) -> str:
    try:
        value, _typ = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return ""
    if type(value) is not str:
        return ""
    return value.strip()


def _must_str(value, key: str, path: Path) -> str:
    if type(value) is not str:
        raise RuntimeError(f"{path} 的 {key} 必须是字符串。改正或删掉该文件后重启。")
    return value.strip()


def _write(path: Path, data: dict) -> None:
    payload = {key: data[key] for key in REQUIRED}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with _LOCK:
        path.write_text(text, encoding="utf-8")


def _hint() -> str:
    launcher, game = probe_hint_paths()
    lines = [" 本机探到的路径（仅提示，填进看板才会用）："]
    if launcher:
        lines.append(f"启动器 {launcher}")
    else:
        lines.append("未探到鹰角启动器 InstallLocation。")
    if game:
        lines.append(f"游戏 {game}")
    else:
        lines.append("未探到 games\\Arknights Game\\Arknights.exe。")
    return " ".join(lines)
