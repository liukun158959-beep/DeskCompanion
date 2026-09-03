"""明日方舟长任务：先启动器，再 PC 客户端，再让 MAA 按勾选远控执行。"""
from __future__ import annotations

import time
import threading
from pathlib import Path

from .logutil import log
from .maa_config import load_maa, require_maa_exe, require_pc_paths, save_maa, save_selected
from .maa_depot import RetryableDepotError, ingest_depot
from .maa_elevate import GAME_TASK, MAA_STOP_TASK, MAA_TASK, authorize, run_task, task_exists
from .maa_maa_cfg import patch_maa_config
from .maa_options import catalog, parse_selected
from .maa_pc import exe_is_elevated, exe_running, open_pc_client, stop_exe
from .maa_remote import RemoteHub


class MaaController:
    def __init__(self, host) -> None:
        self._host = host
        self._lock = threading.Lock()
        self._running = False
        self._cancel = threading.Event()
        self.status = "idle"
        self.message = "还没开始。"
        self.remote = RemoteHub()

    def start_remote(self) -> None:
        cfg = load_maa()
        self.remote.start(cfg["remote_port"])

    def snapshot(self) -> dict:
        cfg = load_maa()
        reports = self.remote.last_reports()
        return {
            "ok": True,
            "launcher_exe": cfg["launcher_exe"],
            "game_exe": cfg["game_exe"],
            "maa_exe": cfg["maa_exe"],
            "open_timeout_sec": cfg["open_timeout_sec"],
            "remote_port": cfg["remote_port"],
            "options": catalog(selected=cfg["selected"]),
            "selected": list(cfg["selected"]),
            "status": self.status,
            "message": self.message,
            "running": self._running,
            "remote_polled": self.remote.polled(),
            "last_report": reports[-1] if reports else None,
            "queued": [str(item.get("type") or "") for item in self.remote.snapshot_tasks()],
            "elevate_ready": task_exists(GAME_TASK),
            "path": cfg["path"],
        }

    def save_paths(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise RuntimeError("保存参数必须是对象。")
        cfg = load_maa()
        save_maa(
            launcher_exe=str(payload.get("launcher_exe") or ""),
            game_exe=str(payload.get("game_exe") or ""),
            maa_exe=str(payload.get("maa_exe") or ""),
            selected=cfg["selected"],
            open_timeout_sec=int(payload.get("open_timeout_sec") or cfg["open_timeout_sec"]),
            remote_port=int(payload.get("remote_port") or cfg["remote_port"]),
        )
        return self.snapshot()

    def set_option(self, option_id: str, checked: bool) -> dict:
        if type(checked) is not bool:
            raise RuntimeError("勾选必须是 true/false。")
        cfg = load_maa()
        current = set(cfg["selected"])
        parsed = parse_selected([option_id])
        if not parsed:
            raise RuntimeError(f"未知日常项 {option_id!r}。")
        item_id = parsed[0]
        if checked:
            current.add(item_id)
        else:
            current.discard(item_id)
        save_selected(list(current))
        return self.snapshot()

    def set_selected(self, selected: list[str]) -> dict:
        save_selected(parse_selected(selected))
        return self.snapshot()

    def authorize_elevate(self) -> dict:
        cfg = load_maa()
        launcher, game = require_pc_paths(cfg)
        del launcher
        maa = Path(cfg["maa_exe"]) if cfg["maa_exe"] else None
        if maa is not None and not maa.is_file():
            maa = None
        text = authorize(game, maa)
        self.message = text
        self._host.ui(lambda: self._notice(text, panel="maa"))
        snap = self.snapshot()
        snap["message"] = text
        return snap

    def start_open_game(self) -> dict:
        return self._kick("open", "正在打开明日方舟 PC 客户端…")

    def start_daily(self) -> dict:
        return self._kick("daily", "正在打开游戏并让 MAA 清日常…")

    def stop(self) -> dict:
        self._cancel.set()
        try:
            self.remote.enqueue_stop()
        except Exception as exc:
            log(f"maa stop enqueue: {exc}")
        self.message = "已请求停止。"
        return {"ok": True, "message": self.message}

    def _kick(self, kind: str, notice: str) -> dict:
        with self._lock:
            if self._running:
                raise RuntimeError("明日方舟动作还在跑。先停止，或等这次结束。")
            self._running = True
            self._cancel.clear()
            self.status = kind
            self.message = notice
        if kind == "daily":
            self._host.ui(self._host.begin_daily_overlay)
        self._host.ui(lambda: self._notice(notice, panel="maa"))
        threading.Thread(target=self._run, args=(kind,), daemon=True).start()
        return {"ok": True, "message": notice}

    def _run(self, kind: str) -> None:
        failed = False
        try:
            cfg = load_maa()
            launcher, game = require_pc_paths(cfg)
            text = open_pc_client(
                launcher_exe=launcher,
                game_exe=game,
                timeout_sec=cfg["open_timeout_sec"],
                cancel=self._cancel,
            )
            if kind == "daily":
                text = self._dispatch_maa(cfg, text)
            self.message = text
            self.status = "idle"
        except Exception as exc:
            failed = True
            self.message = str(exc)
            self.status = "error"
            log(f"maa_job {kind}: {exc}")
        finally:
            with self._lock:
                self._running = False
            if kind == "daily":
                self._host.ui(self._host.end_daily_overlay)
        msg = self.message
        self._host.ui(lambda: self._done(msg, failed))

    def _dispatch_maa(self, cfg: dict, opened: str) -> str:
        maa = require_maa_exe(cfg)
        get_url, report_url = self.remote.urls()
        if not task_exists(MAA_TASK):
            raise RuntimeError(
                "MAA 还没做成最高权限计划任务。游戏因反作弊已提升，未提升的 MAA 点不到窗口。"
                "请再点「授权一次开游戏」，把 MAA 也注册进去。"
            )
        if exe_running(maa):
            if exe_is_elevated(maa):
                raise RuntimeError(
                    "MAA 已经在跑。本机日志显示它能找到「明日方舟」窗口，但 SendMessage 点「开始游戏」没反应。"
                    "正在跑的窗口不会读刚写进配置的真实鼠标（Seize）。请先关掉 MAA，再点开始清日常。"
                    "桌宠会用管理员计划任务重新拉起。不要自己双击开 MAA。"
                )
            stop_exe(maa)
        selected = list(cfg["selected"])
        # 必须先写队列再拉起，否则整段 LinkStart 仍用旧勾选，且可能误开肉鸽。
        patch_maa_config(maa, get_url, report_url, selected)
        run_task(MAA_TASK)
        if self._cancel.is_set():
            raise RuntimeError("已停止：清日常被取消。")
        if not self.remote.wait_polled(90):
            raise RuntimeError(
                "游戏已打开，但 90 秒内 MAA 没有来拉任务。"
                "请确认 MAA 已用计划任务拉起、连接选 PC。"
                f"获取任务：{get_url}。"
            )
        dispatched = self.remote.replace_linkstart(["LinkStart"])
        if selected:
            handed = opened + " 已把整段长草交给 MAA，等结束后再读仓库。细参数仍用齿轮里已保存的。"
        else:
            handed = opened + " 这项没勾日常项，只跑更新数据（扫仓库）。"
        self.message = handed
        self._host.ui(lambda: self._notice(handed, panel="maa"))
        report = self.remote.wait_report(dispatched[0]["id"], 3 * 3600, self._cancel)
        status = report["status"]
        if status == "FAILED":
            raise RuntimeError(
                "MAA 回报长草失败，仓库未更新。游戏窗不要最小化，再开一次清日常。"
            )
        if status != "SUCCESS":
            raise RuntimeError(
                f"MAA 回报状态是 {status}，仓库未更新。再开一次清日常。"
            )
        try:
            depot = ingest_depot(maa)
        except RetryableDepotError as first:
            depot = self._retry_depot_once(maa, selected, get_url, report_url, first)
        text = opened + f" 长草结束。仓库已写入 {depot['count']} 件（{depot['sync']}）。"
        if depot.get("retried"):
            text = (
                opened
                + f" 长草结束。第一次扫仓是空的，同趟再试后仓库已写入 {depot['count']} 件（{depot['sync']}）。"
            )
        elif not selected:
            text = (
                opened
                + f" 没勾日常项，只跑了更新数据。仓库已写入 {depot['count']} 件（{depot['sync']}）。"
            )
        warning = depot.get("restore_warning")
        if warning:
            text += " " + warning
        return text

    def _retry_depot_once(
        self,
        maa: Path,
        selected: list[str],
        get_url: str,
        report_url: str,
        first: RetryableDepotError,
    ) -> dict:
        if self._cancel.is_set():
            raise RuntimeError("已停止，仓库未更新，再开一次清日常。")
        notice = "第一次扫仓没扫到件，同趟再试一次只更新数据。"
        log(f"maa_job daily retry depot: {first}")
        self.message = notice
        self._host.ui(lambda: self._notice(notice, panel="maa"))
        retry_error: Exception | None = None
        depot = None
        try:
            self._stop_maa(maa)
            if self._cancel.is_set():
                raise RuntimeError("已停止，仓库未更新，再开一次清日常。")
            patch_maa_config(
                maa, get_url, report_url, [], depot_interval="EveryTime"
            )
            self.remote.reset_poll()
            run_task(MAA_TASK)
            if not self.remote.wait_polled(90):
                raise RuntimeError(
                    "再试扫仓时 90 秒内 MAA 没有来拉任务。"
                    "请确认 MAA 已用计划任务拉起。"
                    f"获取任务：{get_url}。"
                )
            dispatched = self.remote.replace_linkstart(["LinkStart"])
            report = self.remote.wait_report(
                dispatched[0]["id"], 20 * 60, self._cancel
            )
            status = report["status"]
            if status == "FAILED":
                raise RuntimeError(
                    "再试只更新数据时 MAA 回报失败，仓库未更新。"
                    "游戏窗不要最小化。"
                )
            if status != "SUCCESS":
                raise RuntimeError(
                    f"再试只更新数据时 MAA 回报状态是 {status}，仓库未更新。"
                )
            depot = ingest_depot(maa)
        except Exception as exc:
            retry_error = exc
        restore_error = None
        try:
            self._restore_daily_queue(maa, get_url, report_url, selected)
        except Exception as exc:
            restore_error = exc
        if depot is not None:
            out = dict(depot)
            out["retried"] = True
            if restore_error is not None:
                out["restore_warning"] = str(restore_error)
            return out
        extra = ""
        if restore_error is not None:
            extra = f" 另外，队列写回每天一次失败：{restore_error}"
        if self._cancel.is_set():
            raise RuntimeError(f"已停止，仓库未更新。{extra}".strip())
        detail = retry_error or first
        raise RuntimeError(
            f"{detail} 已自动再试一次只更新数据，仍未写入仓库。{extra}".strip()
        )

    def _restore_daily_queue(
        self, maa: Path, get_url: str, report_url: str, selected: list[str]
    ) -> None:
        stop_error = None
        try:
            self._stop_maa(maa)
        except Exception as exc:
            stop_error = exc
        patch_maa_config(maa, get_url, report_url, selected, depot_interval="Daily")
        if stop_error is not None:
            raise RuntimeError(
                f"间隔已写回每天一次、勾选已写回，但 MAA 还在跑：{stop_error} "
                "请先手动退出 MAA，避免它把间隔存成每次。"
            )

    def _stop_maa(self, maa: Path) -> None:
        if not exe_running(maa):
            return
        try:
            self.remote.enqueue_stop()
        except Exception as exc:
            log(f"maa stop enqueue: {exc}")
        time.sleep(1)
        if not exe_running(maa):
            return
        if not exe_is_elevated(maa):
            stop_exe(maa)
            return
        if not task_exists(MAA_STOP_TASK):
            raise RuntimeError(
                "空仓后再试扫仓需要先关掉管理员 MAA，但还没有关闭用的计划任务。"
                "请在看板点「授权一次开游戏」，关掉 MAA 后再清日常。"
            )
        run_task(MAA_STOP_TASK)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not exe_running(maa):
                return
            time.sleep(0.2)
        raise RuntimeError(
            "空仓后再试扫仓前关不掉 MAA。请先手动退出 MAA。"
        )

    def _notice(self, text: str, panel: str = "maa") -> None:
        try:
            self._host.show_notice(text, panel=panel)
        except Exception as exc:
            log(f"maa 气泡: {exc}")

    def _done(self, text: str, failed: bool) -> None:
        try:
            if failed and self._host.pet:
                self._host.pet.fail()
            elif self._host.pet:
                self._host.pet.review()
            self._host.show_notice(text, panel="maa")
        except Exception as exc:
            log(f"maa 完成气泡: {exc}")
