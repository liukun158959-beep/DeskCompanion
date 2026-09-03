"""打开鹰角启动器安装的明日方舟 PC 客户端，不是安卓模拟器。"""
from __future__ import annotations

import ctypes
import time
from pathlib import Path

import win32gui
import win32process
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GAME_EXE_NAME = "arknights.exe"
ENDFIELD_EXE_NAME = "endfield.exe"
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


def find_game_hwnd() -> int | None:
    found: list[int] = []

    def cb(hwnd, _ctx):
        if win32gui.IsWindowVisible(hwnd) and _is_pc_arknights(hwnd):
            found.append(int(hwnd))
        return True

    win32gui.EnumWindows(cb, None)
    if not found:
        return None
    titled = [hwnd for hwnd in found if "明日方舟" in win32gui.GetWindowText(hwnd)]
    return (titled or found)[0]


def exe_running(exe: Path) -> bool:
    return bool(pids_of_exe(exe))


def pids_of_exe(exe: Path) -> list[int]:
    target = exe.resolve()
    found: list[int] = []
    for pid in win32process.EnumProcesses():
        image = _process_image(int(pid))
        if not image:
            continue
        try:
            if Path(image).resolve() == target:
                found.append(int(pid))
        except OSError:
            continue
    return found


def exe_is_elevated(exe: Path) -> bool:
    pids = pids_of_exe(exe)
    if not pids:
        return False
    return all(_pid_is_elevated(pid) for pid in pids)


def stop_exe(exe: Path, timeout_sec: float = 12) -> None:
    """结束已在跑的进程，好用计划任务重新以管理员拉起。"""
    pids = pids_of_exe(exe)
    if not pids:
        return
    PROCESS_TERMINATE = 0x0001
    kernel32 = ctypes.windll.kernel32
    for pid in pids:
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not handle:
            continue
        try:
            kernel32.TerminateProcess(handle, 1)
        finally:
            kernel32.CloseHandle(handle)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not exe_running(exe):
            return
        time.sleep(0.2)
    raise RuntimeError(
        f"{exe.name} 还在跑，关不掉。请先手动退出，再点开始清日常。"
        "桌宠要用管理员计划任务拉起 MAA，自己开的窗口点不到游戏。"
    )


def start_detached(exe: Path) -> None:
    """
    用 ShellExecute 启动。Arknights.exe 清单要求提升，CreateProcess 会 WinError 740。
    「open」会按清单弹出 UAC，不要改成静默 CreateProcess。
    """
    if not exe.is_file():
        raise RuntimeError(f"要启动的文件不存在：{exe}")
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "open"
    info.lpFile = str(exe)
    info.lpDirectory = str(exe.parent)
    info.nShow = SW_SHOWNORMAL
    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))
    if info.hProcess:
        ctypes.windll.kernel32.CloseHandle(info.hProcess)
    if ok:
        return
    err = ctypes.GetLastError()
    if err == ERROR_CANCELLED:
        raise RuntimeError(
            f"启动被取消：{exe}。明日方舟 PC 客户端带反作弊，需要管理员权限。"
            "请在 UAC 窗口点是，或把桌宠以管理员运行后再打开游戏。"
        )
    raise RuntimeError(
        f"无法启动 {exe}（WinError {err}）。"
        "若提示需要提升，允许 UAC，或把桌宠以管理员运行。"
    )


def open_pc_client(
    *,
    launcher_exe: Path,
    game_exe: Path,
    timeout_sec: int,
    cancel,
) -> str:
    """
    等到 Arknights.exe 出现可见窗口。
    启动器没有 CLI 一键进游戏，所以启动器拉起来之后仍要启动游戏 exe。
    """
    hwnd = find_game_hwnd()
    if hwnd:
        title = win32gui.GetWindowText(hwnd) or "(无标题)"
        return f"明日方舟 PC 客户端已经在运行（窗口「{title}」）。"

    if not exe_running(launcher_exe):
        start_detached(launcher_exe)

    wait_until = time.monotonic() + 8
    while time.monotonic() < wait_until:
        if cancel.is_set():
            raise RuntimeError("已停止：打开游戏被取消。")
        if exe_running(launcher_exe):
            break
        time.sleep(0.25)
    if not exe_running(launcher_exe):
        raise RuntimeError(
            f"鹰角启动器没起来：{launcher_exe}。"
            "请确认这是官方 Launcher.exe，再从看板重新打开。"
        )

    if not exe_running(game_exe):
        from .maa_elevate import GAME_TASK, run_task, task_exists

        if not task_exists(GAME_TASK):
            raise RuntimeError(
                "还不能无 UAC 打开游戏。请先在看板点「授权一次开游戏（之后不再弹 UAC）」，"
                "并在那一次 UAC 窗口自己点是。桌宠点不到安全桌面上的按钮，也不会用漏洞绕过。"
            )
        run_task(GAME_TASK)

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if cancel.is_set():
            raise RuntimeError("已停止：打开游戏被取消。")
        hwnd = find_game_hwnd()
        if hwnd:
            title = win32gui.GetWindowText(hwnd) or "(无标题)"
            return f"明日方舟 PC 客户端已打开（窗口「{title}」，进程 Arknights.exe）。"
        time.sleep(0.4)

    running = "在跑" if exe_running(game_exe) else "没在跑"
    raise RuntimeError(
        f"{timeout_sec} 秒内没有出现 Arknights.exe 窗口。"
        f"游戏进程当前{running}。"
        "鹰角启动器没有命令行「开始游戏」，桌宠是：先拉启动器，再用已授权的计划任务启动 Arknights.exe。"
        "若还没授权计划任务，会一直等不到窗口。"
        "若启动器要登录或更新，先在启动器里处理完再点打开游戏。"
        "不要把 MAA 连到安卓模拟器来开这套客户端。"
    )


def _is_pc_arknights(hwnd: int) -> bool:
    title = win32gui.GetWindowText(hwnd)
    if "终末地" in title or "Endfield" in title:
        return False
    image = _window_image(hwnd)
    if not image:
        return False
    name = Path(image).name.lower()
    if name == ENDFIELD_EXE_NAME:
        return False
    return name == GAME_EXE_NAME


def _window_image(hwnd: int) -> str:
    _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
    return _process_image(int(pid))


def _iter_process_images():
    for pid in win32process.EnumProcesses():
        image = _process_image(int(pid))
        if image:
            yield image


def _process_image(pid: int) -> str:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(32768)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    finally:
        kernel32.CloseHandle(handle)


def _pid_is_elevated(pid: int) -> bool:
    TOKEN_QUERY = 0x0008
    TokenElevation = 20

    class TOKEN_ELEVATION(ctypes.Structure):
        _fields_ = [("TokenIsElevated", wintypes.DWORD)]

    kernel32 = ctypes.windll.kernel32
    advapi = ctypes.windll.advapi32
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return False
    token = wintypes.HANDLE()
    try:
        if not advapi.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return False
        elev = TOKEN_ELEVATION()
        ret = wintypes.DWORD()
        ok = advapi.GetTokenInformation(
            token, TokenElevation, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(ret)
        )
        if not ok:
            return False
        return bool(elev.TokenIsElevated)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)
