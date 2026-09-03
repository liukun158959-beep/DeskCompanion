"""用一次 UAC 授权的计划任务启动需要提升的进程。不点安全桌面，不用漏洞绕过。"""
from __future__ import annotations

import ctypes
import subprocess
import tempfile
from pathlib import Path

from ctypes import wintypes

GAME_TASK = "DeskCompanion.ArknightsPC"
MAA_TASK = "DeskCompanion.MAA"
MAA_STOP_TASK = "DeskCompanion.MAA.Stop"
CREATE_NO_WINDOW = 0x08000000
WAIT_TIMEOUT = 0x00000102
SW_SHOWNORMAL = 1
SEE_MASK_NOCLOSEPROCESS = 0x00000040
ERROR_CANCELLED = 1223


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hKeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def task_exists(name: str) -> bool:
    completed = subprocess.run(
        ["schtasks", "/Query", "/TN", name],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return completed.returncode == 0


def run_task(name: str) -> None:
    if not task_exists(name):
        raise RuntimeError(
            f"还没有计划任务 {name}。"
            "请在看板「自动化任务 → 明日方舟」点「授权一次开游戏（之后不再弹 UAC）」，并在那一次 UAC 点是。"
        )
    completed = subprocess.run(
        ["schtasks", "/Run", "/TN", name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"计划任务 {name} 启动失败。{err}")


def authorize(game_exe: Path, maa_exe: Path | None) -> str:
    """
    若任务已在则直接返回。否则用 runas 弹一次 UAC 注册最高权限任务。
    之后 schtasks /Run 不再弹。
    """
    need_game = not task_exists(GAME_TASK)
    need_maa = bool(maa_exe) and maa_exe.is_file() and not task_exists(MAA_TASK)
    need_stop = bool(maa_exe) and maa_exe.is_file() and not task_exists(MAA_STOP_TASK)
    if not need_game and not need_maa and not need_stop:
        return "计划任务已就绪，打开游戏和 MAA 都不再弹 UAC。"

    if not game_exe.is_file():
        raise RuntimeError(f"游戏 exe 不存在：{game_exe}")

    register_maa = maa_exe if (need_maa or need_stop) else None
    script = _write_register_script(game_exe, register_maa)
    try:
        _runas_powershell(script)
    finally:
        try:
            script.unlink()
        except OSError:
            pass

    if not task_exists(GAME_TASK):
        raise RuntimeError(
            "计划任务没有注册成功。若刚才 UAC 点了否，请再点一次「授权一次开游戏」。"
            "不能由桌宠代点 UAC（安全桌面点不到）。"
        )
    if need_maa and not task_exists(MAA_TASK):
        raise RuntimeError("游戏任务已在，但 MAA 计划任务没注册上。再授权一次。")
    if need_stop and not task_exists(MAA_STOP_TASK):
        raise RuntimeError(
            "游戏和 MAA 的启动任务已在，但关掉 MAA 的任务没注册上。再授权一次。"
        )
    return "已授权。之后打开 PC 客户端和 MAA 都走计划任务，不再弹 UAC。"


def _write_register_script(game_exe: Path, maa_exe: Path | None) -> Path:
    game = str(game_exe.resolve())
    gdir = str(game_exe.resolve().parent)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        _task_ps(GAME_TASK, game, gdir),
    ]
    if maa_exe is not None:
        maa = str(maa_exe.resolve())
        mdir = str(maa_exe.resolve().parent)
        lines.append(_task_ps(MAA_TASK, maa, mdir))
        lines.append(_maa_stop_ps(MAA_STOP_TASK))
    text = "\n".join(lines) + "\n"
    path = Path(tempfile.gettempdir()) / "desk_companion_register_maa_tasks.ps1"
    path.write_text(text, encoding="utf-8-sig")
    return path


def _task_ps(name: str, exe: str, cwd: str) -> str:
    return (
        f"$action = New-ScheduledTaskAction -Execute '{_ps_lit(exe)}' -WorkingDirectory '{_ps_lit(cwd)}'\n"
        "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest\n"
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero)\n"
        f"Register-ScheduledTask -TaskName '{name}' -Action $action -Principal $principal "
        "-Settings $settings -Force | Out-Null"
    )


def _maa_stop_ps(name: str) -> str:
    return (
        "$action = New-ScheduledTaskAction -Execute 'taskkill.exe' -Argument '/F /IM MAA.exe'\n"
        "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest\n"
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::FromMinutes(2))\n"
        f"Register-ScheduledTask -TaskName '{name}' -Action $action -Principal $principal "
        "-Settings $settings -Force | Out-Null"
    )


def _ps_lit(value: str) -> str:
    return value.replace("'", "''")


def _runas_powershell(script: Path) -> None:
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = "powershell.exe"
    info.lpParameters = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
    info.nShow = SW_SHOWNORMAL
    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))
    if not ok:
        err = ctypes.GetLastError()
        if err == ERROR_CANCELLED:
            raise RuntimeError(
                "授权被取消。打开需要提升的 PC 客户端必须同意那一次 UAC。"
                "桌宠点不到安全桌面上的「是」。"
            )
        raise RuntimeError(f"无法发起管理员授权（WinError {err}）。")
    handle = info.hProcess
    if not handle:
        raise RuntimeError("管理员 PowerShell 没有返回进程句柄。")
    try:
        wait = ctypes.windll.kernel32.WaitForSingleObject(handle, 120000)
        if wait == WAIT_TIMEOUT:
            raise RuntimeError("授权脚本超过 120 秒还没结束。")
        code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        if code.value != 0:
            raise RuntimeError(f"注册计划任务失败，退出码 {code.value}。")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
