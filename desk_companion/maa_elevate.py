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
            "请在看板「自动化任务 → 明日方舟」点「授权一次 MAA」，并在那一次 UAC 点是。"
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


def authorize(maa_exe: Path) -> str:
    """
    若 MAA / Stop 任务已在则直接返回。否则用 runas 弹一次 UAC 注册最高权限任务。
    不再注册或运行 DeskCompanion.ArknightsPC。
    """
    if not maa_exe.is_file():
        raise RuntimeError(f"MAA exe 不存在：{maa_exe}")
    need_maa = not task_exists(MAA_TASK)
    need_stop = not task_exists(MAA_STOP_TASK)
    if not need_maa and not need_stop:
        return "MAA 计划任务已就绪。清日常不再代开游戏；请先自己开到「明日方舟」窗口。"

    script = _write_register_script(maa_exe)
    try:
        _runas_powershell(script)
    finally:
        try:
            script.unlink()
        except OSError:
            pass

    if need_maa and not task_exists(MAA_TASK):
        raise RuntimeError(
            "MAA 计划任务没有注册成功。若刚才 UAC 点了否，请再点一次「授权一次 MAA」。"
            "不能由桌宠代点 UAC（安全桌面点不到）。"
        )
    if need_stop and not task_exists(MAA_STOP_TASK):
        raise RuntimeError("MAA 启动任务已在，但关掉 MAA 的任务没注册上。再授权一次。")
    return "已授权 MAA。之后拉起或关掉 MAA 走计划任务。游戏请自己开到窗口，桌宠不再代开启动器。"


def _write_register_script(maa_exe: Path) -> Path:
    maa = str(maa_exe.resolve())
    mdir = str(maa_exe.resolve().parent)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        _task_ps(MAA_TASK, maa, mdir),
        _maa_stop_ps(MAA_STOP_TASK),
    ]
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
                "授权被取消。注册管理员 MAA 计划任务必须同意那一次 UAC。"
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
