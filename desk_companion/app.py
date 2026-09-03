"""组装：Electron Live2D 宠物 + 看板 + 托盘。"""
from __future__ import annotations

import ctypes
import os
import queue
import random
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import webview
import win32api
import win32con
import win32gui

from .assistant import TOOL_CONTRACT, build_agent, inject_history, list_providers, token_plugin
from .bridge import Bridge
from .maa_job import MaaController
from .maa_tools import bind_host
from .envconf import parse_env_file, public_llm_env, write_llm_env
from .layered import enable_dpi_aware, work_area
from .logutil import crash, install_crash_hooks, log, mark_ready, start_os_watchdog
from .memory import TZ, append_chat, chat_on_date, clear_chat, history_for_model, list_chat, recent_chat
from .pet_shell import BASE_PET_H, BASE_PET_W, CMD_QUIT, start_pet_thread
from .skin import load_skin
from .state import load_state
from .tray import start_tray
from .usage import append_usage, cost_cny, summarize_usage
from .winforms_host import (
    apply_app_window,
    apply_tool_window,
    as_hwnd,
    cache_hwnd,
    enable_thick_frame,
    enable_webview_context_menu,
    ensure_ready,
    form_of,
    hide_form,
    invoke,
    move_form,
    root_hwnd,
    show_form,
)

BOARD_W = 1000
BOARD_H = 680
TODAY_ASK = "今天干什么？"
LOG_ASK = "看看日志。"
DAILY_ASK = """【今日纸条】请先调用 get_today_agenda 和 get_open_tasks。
用中文 Markdown 写今日重点：
1. 先用引用块标出最该盯的一件事，格式：
> **重点**
> 事项名（截止时间）
2. 再用有序列表列出今天其余值得盯的 2 到 4 项
3. 若有多条日程或待办，再给一张表格，列：事项 / 截止 / 状态
不要鸡汤，不要写成一段话。工具失败就原样说明怎么修。"""
SUMMARY_ASK = """【今日工作总结】不要调用工具。只根据后面的今日材料写中文 Markdown，不要编造材料里没有的事。
结构、红线和能用的语法以【技能规程】为准，不要另起章节，不要把整篇包进代码块。"""
PAPER = "#FFF6EC"
INK = "#2C241E"
BLUSH = "#E8A598"
DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_NONE = 1
DWMWCP_ROUND = 2
DWMWCP_DONOTROUND = 1
MUTEX_NAME = "Local\\DeskCompanion.Kaltsit"
ERROR_ALREADY_EXISTS = 183

_mutex_handle = None


class App:
    def __init__(self, skin_id: str) -> None:
        self.skin = load_skin(skin_id)
        left, top, right, bottom = work_area()
        self.state = load_state(right - BASE_PET_W - 16, bottom - BASE_PET_H - 8)
        self.agent = None
        self._agent_error = ""
        self._agent_running = False
        self.maa = MaaController(self)
        bind_host(self)
        self.bridge = Bridge(self)
        self._queue: queue.Queue = queue.Queue()
        self.pet = None
        self.board = None
        self.icon = None
        self._quitting = False
        self._nudge_busy = False
        self._board_placed = False
        self._card_mode = "chat"
        self._history_loaded = False
        self._outside_btn_down = False
        self._startup_ok = threading.Event()
        self._next_nudge = time.monotonic() + random.uniform(12 * 60, 18 * 60)
        self._ui_dir = Path(__file__).resolve().parent / "ui"

    def ui(self, fn) -> None:
        self._queue.put(fn)

    def drain_queue(self) -> None:
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception as exc:
                log(f"drain_queue: {type(exc).__name__}: {exc}")

    def on_pet_moved(self, *, talk_js: bool = False) -> None:
        return

    def on_ready(self) -> None:
        log("on_ready 开始")
        try:
            log("ensure_ready 看板")
            ensure_ready(self.board, "看板")
            log("setup_forms")
            self._setup_webview_form(self.board, tool=False)
            enable_webview_context_menu(self.board)
            hide_form(self.board)
            log("load_history")
            self._load_history()
            log("start_tray")
            self.icon = start_tray(self, self.skin)
            try:
                self.maa.start_remote()
            except Exception as exc:
                log(f"MAA 远控没起来: {exc}")
            threading.Thread(target=self._run_daily, daemon=True).start()
            mark_ready()
            self._startup_ok.set()
            log("on_ready 完成")
        except Exception as exc:
            log(f"on_ready 失败: {exc}")
            _message_box(f"对话气泡没就绪，宠物仍可用:\n{exc}")
            mark_ready()
            self._startup_ok.set()

    def _setup_webview_form(
        self,
        window,
        *,
        tool: bool,
        round_corners: bool = True,
        transparent: bool = False,
    ) -> None:
        """shown 之后再碰句柄，避免和 WebView2 Focus 死锁。"""
        invoke(
            form_of(window),
            lambda: _prepare_form(
                window,
                tool=tool,
                round_corners=round_corners,
                transparent=transparent,
            ),
        )

    def post_pet(self, cmd: int) -> None:
        if self.pet is None:
            if cmd == CMD_QUIT:
                self.quit()
                return
            raise RuntimeError("宠物窗口不存在，无法响应托盘命令。")
        self.pet.post_cmd(cmd)

    def on_pet_click(self) -> None:
        try:
            if self._chat_visible():
                self.hide_bubble()
            else:
                self.show_bubble("today")
        except RuntimeError as exc:
            log(f"on_pet_click: {exc}")
        except Exception as exc:
            if _is_ui_fault(exc):
                log(f"on_pet_click: {exc}")
            else:
                crash("on_pet_click", exc)

    def on_pet_tick(self) -> None:
        self._poll_outside_click()
        if not self.state.nudge_enabled or self._nudge_busy:
            return
        now = time.monotonic()
        if now < self._next_nudge:
            return
        self._next_nudge = now + random.uniform(12 * 60, 18 * 60)
        self._nudge_busy = True
        threading.Thread(target=self._run_template_nudge, daemon=True).start()

    def on_open_board(self) -> None:
        self.show_board()

    def on_hide_pet(self) -> None:
        self.hide_pet()

    def on_quit(self) -> None:
        self.quit()

    def toggle_nudge(self) -> None:
        self.state.nudge_enabled = not self.state.nudge_enabled
        self.state.save()

    def toggle_click_through(self) -> None:
        self.state.click_through = not self.state.click_through
        self.state.save()

        def apply() -> None:
            if self.pet is None:
                return
            self.pet.emit("set_click_through", enabled=self.state.click_through)

        self.ui(apply)

    def show_pet(self) -> None:
        if self.pet:
            self.pet.show()

    def hide_pet(self) -> None:
        self.hide_bubble()
        if self.pet:
            self.pet.hide()

    def show_bubble(self, panel: str = "chat") -> None:
        if self.pet is None:
            raise RuntimeError("宠物窗口还在启动，请稍后再点。")
        if not self.pet.visible():
            self.pet.show()
        self._card_mode = "chat" if panel == "chat" else panel
        self.pet.bubble_open = True
        self._eval_bubble("show_panel", panel=panel)

    def hide_bubble(self) -> None:
        if self.pet is None:
            return
        self.pet.bubble_open = False
        self._eval_bubble("hide_bubble")

    def show_notice(self, text: str, panel: str = "chat") -> None:
        text = (text or "").strip()
        if not text:
            raise RuntimeError("纸条内容为空。")
        if self.pet is None:
            raise RuntimeError("宠物窗口还在启动，请稍后再看纸条。")
        if not self.pet.visible():
            self.pet.show()
        self._card_mode = panel
        self.pet.bubble_open = True
        if panel == "maa":
            self._eval_bubble("maa_notice", text=text)
            self._eval_bubble("show_panel", panel="maa")
            return
        if panel == "today":
            self._eval_bubble("today_notice", text=text)
            self._eval_bubble("show_panel", panel="today")
            return
        self._eval_bubble("append_message", role="pet", text=text)
        self._eval_bubble("show_panel", panel="chat")

    def fit_card(self, width: int, height: int) -> None:
        return

    def _load_history(self) -> None:
        if self._history_loaded or self.pet is None:
            return
        rows = recent_chat(40)
        self._eval_bubble("load_history", rows=rows)
        self._history_loaded = True

    def clear_chat_history(self) -> dict:
        if self._agent_running:
            return {"ok": False, "error": "凯尔希正在说话，等这句说完再清空。"}
        if self.pet is None:
            raise RuntimeError("宠物窗口还在启动，无法清空。")
        clear_chat()
        if self.agent is not None:
            self.agent.memory.clear()
        self._eval_bubble("load_history", rows=[])
        self._eval_bubble("show_panel", panel="chat")
        return {"ok": True}

    def try_build_agent(self) -> None:
        try:
            self.agent = build_agent(self)
            self._agent_error = ""
            log("build_agent 完成")
        except Exception as exc:
            self.agent = None
            self._agent_error = str(exc)
            log(f"build_agent 失败: {exc}")

    def _rebuild_agent(self) -> None:
        if self._agent_running:
            raise RuntimeError("凯尔希正在说话，等这句说完再保存。")
        self.try_build_agent()
        if self.agent is None:
            raise RuntimeError(self._agent_error)

    def _record_usage(self, agent, run_id: str) -> None:
        plugin = token_plugin(agent)
        summary = plugin.get_summary(run_id)
        model = getattr(agent.llm, "model", "") or ""
        inn = int(summary.get("input_tokens") or 0)
        out = int(summary.get("output_tokens") or 0)
        append_usage(
            {
                "ts": datetime.now(TZ).isoformat(timespec="seconds"),
                "model": model,
                "input_tokens": inn,
                "output_tokens": out,
                "total_tokens": inn + out,
                "cost_cny": cost_cny(model, inn, out, self.state.model_prices),
                "run_id": run_id,
            }
        )

    def board_chat(self) -> dict:
        try:
            return {"ok": True, "items": list_chat()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_memory(self) -> dict:
        try:
            items = list_chat()
            n = self.state.history_n
            window = history_for_model(n) if n else []
            return {
                "ok": True,
                "history_n": n,
                "total": len(items),
                "items": window,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def load_today_board(self, refresh: bool = False) -> dict:
        from .board_data import load_today_snapshot

        try:
            return {"ok": True, **load_today_snapshot(refresh=bool(refresh))}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_log_errors(self) -> dict:
        from .log_inspect import inspect_today_errors

        try:
            return inspect_today_errors()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_skills(self) -> dict:
        from .skill_catalog import list_skills

        try:
            return {"ok": True, "items": list_skills()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_persona(self) -> dict:
        try:
            return {
                "ok": True,
                "persona": self.state.persona,
                "history_n": self.state.history_n,
                "max_steps": self.state.max_steps,
                "nudge_enabled": self.state.nudge_enabled,
                "tool_contract": TOOL_CONTRACT,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_persona(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "人设保存参数必须是对象。"}
        try:
            if self._agent_running:
                raise RuntimeError("凯尔希正在说话，等这句说完再保存。")
            persona = str(payload.get("persona") or "").strip()
            if not persona:
                raise RuntimeError("人设不能为空。")
            history_n = int(payload.get("history_n"))
            max_steps = int(payload.get("max_steps"))
            if history_n < 0:
                raise RuntimeError("历史条数不能为负。")
            if max_steps < 1:
                raise RuntimeError("max_steps 至少为 1。")
            nudge = payload.get("nudge_enabled")
            if type(nudge) is not bool:
                raise RuntimeError("主动搭话必须是 true/false。")
            self.state.persona = persona
            self.state.history_n = history_n
            self.state.max_steps = max_steps
            self.state.nudge_enabled = nudge
            self.state.save()
            self._rebuild_agent()
            return {"ok": True, "message": "人设已保存。"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_model(self) -> dict:
        try:
            pub = public_llm_env()
            model = pub["model"]
            price = self.state.model_prices.get(model) or {}
            return {
                "ok": True,
                "providers": list_providers(),
                "base_url": pub["base_url"],
                "model": model,
                "has_key": pub["has_key"],
                "agent_ok": self.agent is not None,
                "agent_error": self._agent_error,
                "input_cny_per_mtok": price.get("input_cny_per_mtok"),
                "output_cny_per_mtok": price.get("output_cny_per_mtok"),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_model(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "模型保存参数必须是对象。"}
        try:
            if self._agent_running:
                raise RuntimeError("凯尔希正在说话，等这句说完再保存。")
            base_url = str(payload.get("base_url") or "").strip()
            model = str(payload.get("model") or "").strip()
            api_key = str(payload.get("api_key") or "").strip()
            if not api_key:
                api_key = parse_env_file().get("ATLAS_API_KEY") or ""
            write_llm_env(api_key=api_key, base_url=base_url, model=model)
            prices = dict(self.state.model_prices)
            inn_raw = payload.get("input_cny_per_mtok")
            out_raw = payload.get("output_cny_per_mtok")
            blank = inn_raw in (None, "") and out_raw in (None, "")
            if blank:
                prices.pop(model, None)
            else:
                if inn_raw in (None, "") or out_raw in (None, ""):
                    raise RuntimeError("输入、输出单价要一起填，或都留空。")
                inn = float(inn_raw)
                outv = float(out_raw)
                if inn < 0 or outv < 0:
                    raise RuntimeError("单价不能为负。")
                prices[model] = {
                    "input_cny_per_mtok": inn,
                    "output_cny_per_mtok": outv,
                }
            self.state.model_prices = prices
            self.state.save()
            self._rebuild_agent()
            return {"ok": True, "message": "模型配置已保存。"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def test_model(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "测试参数必须是对象。"}
        try:
            from openai import OpenAI

            base_url = str(payload.get("base_url") or "").strip()
            model = str(payload.get("model") or "").strip()
            api_key = str(payload.get("api_key") or "").strip()
            if not api_key:
                api_key = parse_env_file().get("ATLAS_API_KEY") or ""
            if not api_key or not base_url or not model:
                raise RuntimeError("测试前先填 API 地址、模型名和 Key。")
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=8,
            )
            text = (response.choices[0].message.content or "").strip()
            return {"ok": True, "message": "连通正常。" + (f" 回复：{text}" if text else "")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_usage(self) -> dict:
        try:
            data = summarize_usage()
            data["ok"] = True
            return data
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_maa(self) -> dict:
        try:
            return self.maa.board()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def board_github(self) -> dict:
        from .github import board_snapshot

        try:
            return board_snapshot()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_maa_paths(self, payload: dict) -> dict:
        try:
            snap = self.maa.save_paths(payload)
            snap["message"] = "路径已保存。"
            return snap
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_maa_option(self, payload: dict) -> dict:
        try:
            if not isinstance(payload, dict):
                raise RuntimeError("勾选参数必须是对象。")
            checked = payload.get("checked")
            if type(checked) is not bool:
                raise RuntimeError("勾选必须是 true/false。")
            return self.maa.set_option(str(payload.get("id") or ""), checked)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def maa_open_game(self) -> dict:
        try:
            return self.maa.start_open_game()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def maa_start_daily(self) -> dict:
        try:
            return self.maa.start_daily()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def maa_stop(self) -> dict:
        try:
            return self.maa.stop()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def maa_authorize(self) -> dict:
        try:
            snap = self.maa.authorize_elevate()
            snap["ok"] = True
            return snap
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _chat_visible(self) -> bool:
        return bool(self.pet and self.pet.bubble_open)

    def _work_area(self) -> tuple[int, int, int, int]:
        if self.pet and self.pet.hwnd:
            return work_area(self.pet.hwnd)
        return work_area()

    def _poll_outside_click(self) -> None:
        down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
        was_down = self._outside_btn_down
        self._outside_btn_down = down
        if not down or was_down:
            return
        if not self.pet or not self.pet.bubble_open:
            return
        x, y = win32gui.GetCursorPos()
        hit = root_hwnd(int(win32gui.WindowFromPoint((x, y))))
        if self.pet.hwnd and hit == int(self.pet.hwnd):
            return
        self.hide_bubble()

    def show_board(self) -> None:
        if self.board is None:
            raise RuntimeError("看板窗口还没建好。")
        form = form_of(self.board)
        show_form(self.board, activate=True, tool=False, topmost=False)
        invoke(form, lambda: _paint_paper_chrome(self.board, form))
        if not self._board_placed:
            left, top, right, bottom = self._work_area()
            x = left + max(24, (right - left - BOARD_W) // 2)
            y = top + max(24, (bottom - top - BOARD_H) // 2)
            move_form(self.board, x, y, topmost=False)
            self._board_placed = True
        self.board.evaluate_js("window.reloadBoard && window.reloadBoard()")

    def hide_board(self) -> None:
        hide_form(self.board)

    def minimize_board(self) -> None:
        if self.board is None:
            raise RuntimeError("看板窗口还没建好。")
        form = form_of(self.board)
        from System.Windows.Forms import FormWindowState

        invoke(form, lambda: setattr(form, "WindowState", FormWindowState.Minimized))

    def toggle_maximize_board(self) -> None:
        if self.board is None:
            raise RuntimeError("看板窗口还没建好。")
        form = form_of(self.board)
        from System.Windows.Forms import FormWindowState

        def _do() -> None:
            if form.WindowState == FormWindowState.Maximized:
                form.WindowState = FormWindowState.Normal
            else:
                form.WindowState = FormWindowState.Maximized

        invoke(form, _do)

    def ask_today(self) -> None:
        self.show_pet()
        self.send_chat(TODAY_ASK)

    def ask_logs(self) -> None:
        self.show_pet()
        self.send_chat(LOG_ASK)

    def generate_today_summary(self) -> dict:
        if self._agent_running:
            return {"ok": False, "error": "凯尔希正在说话，等这句说完再生成总结。"}
        if self.agent is None:
            return {
                "ok": False,
                "error": self._agent_error or "还没接上模型。打开看板「模型」页填写。",
            }
        from .board_data import load_today_snapshot, save_today_fields

        try:
            snap = load_today_snapshot(refresh=False)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not snap.get("agenda", {}).get("ok"):
            return {
                "ok": False,
                "error": snap.get("agenda", {}).get("error")
                or "日程读取失败，先点「刷新」或去「飞书」页检查登录。",
            }
        if not snap.get("tasks", {}).get("ok"):
            return {
                "ok": False,
                "error": snap.get("tasks", {}).get("error")
                or "待办读取失败，先点「刷新」或去「飞书」页检查登录。",
            }
        from .skill_catalog import read_skill

        try:
            skill = read_skill("feishu-doc-writing")
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        self._agent_running = True
        run_id = str(uuid.uuid4())
        try:
            prompt = (
                SUMMARY_ASK
                + "\n\n【技能规程】\n"
                + skill["body"]
                + "\n\n【今日材料】\n"
                + self._today_summary_materials(snap)
            )
            result = self.agent.llm.chat(
                [
                    {
                        "role": "system",
                        "content": self.state.persona
                        + "\n\n你现在只写今日工作总结，不要调用工具。按用户消息里的技能规程写。",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            self._record_llm_usage(result.get("usage"), run_id)
            message = result.get("message") or {}
            markdown = str(message.get("content") or "").strip()
            if not markdown:
                raise RuntimeError("总结正文为空。")
            summary_at = datetime.now(TZ).isoformat(timespec="seconds")
            snap = save_today_fields(summary=markdown, summary_at=summary_at)
            return {
                "ok": True,
                **snap,
                "message": "总结已写在今日页，并已落盘。",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            self._agent_running = False

    def write_today_summary_doc(self) -> dict:
        from .board_data import load_today_snapshot, save_today_fields
        from .feishu_auth import create_markdown_doc

        try:
            snap = load_today_snapshot(refresh=False)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        markdown = (snap.get("summary") or "").strip()
        if not markdown:
            return {"ok": False, "error": "还没有总结。先点「生成总结」。"}
        try:
            title = f"{snap['date']} 工作总结"
            created = create_markdown_doc(title, markdown)
            snap = save_today_fields(doc_url=created["url"])
            os.startfile(created["url"])
            return {
                "ok": True,
                **snap,
                "url": created["url"],
                "message": "总结已写到飞书文档，并打开了链接。",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _today_summary_materials(self, snap: dict) -> str:
        day = snap["date"]
        parts = [f"日期：{day}", "", "## 日程"]
        agenda_items = snap["agenda"].get("items") or []
        if not agenda_items:
            parts.append("今日无日程。")
        else:
            for item in agenda_items:
                when = item.get("start") or ""
                if item.get("end"):
                    when = f"{when} – {item['end']}"
                parts.append(f"- {when} {item.get('summary') or ''}".strip())
        parts.extend(["", "## 未完成待办"])
        task_items = snap["tasks"].get("items") or []
        if not task_items:
            parts.append("无未完成待办。")
        else:
            for item in task_items:
                due = item.get("due_at") or "无截止"
                parts.append(f"- {item.get('summary') or ''}（截止 {due}）")
        parts.extend(["", "## 今日对话"])
        chats = chat_on_date(day)
        if not chats:
            parts.append("今日无对话。")
        else:
            for rec in chats:
                who = "用户" if rec["role"] == "user" else "凯尔希"
                parts.append(f"{who}: {rec['text']}")
        return "\n".join(parts)

    def _record_llm_usage(self, usage, run_id: str) -> None:
        model = ""
        if self.agent is not None:
            model = getattr(self.agent.llm, "model", "") or ""
        inn = 0
        out = 0
        if isinstance(usage, dict):
            inn = int(usage.get("prompt_tokens") or 0)
            out = int(usage.get("completion_tokens") or 0)
        append_usage(
            {
                "ts": datetime.now(TZ).isoformat(timespec="seconds"),
                "model": model,
                "input_tokens": inn,
                "output_tokens": out,
                "total_tokens": inn + out,
                "cost_cny": cost_cny(model, inn, out, self.state.model_prices),
                "run_id": run_id,
            }
        )

    def send_chat(self, text: str) -> None:
        text = (text or "").strip()
        if not text or not self.pet:
            return
        if self.agent is None:
            msg = self._agent_error or "还没接上模型。打开看板「模型」页填写 API 地址、模型名和 Key。"
            self.show_bubble("chat")
            self._eval_bubble("append_message", role="user", text=text)
            self._eval_bubble("append_message", role="err", text=msg)
            self._eval_bubble("set_busy", busy=False)
            return
        if self.pet.busy:
            return
        self.show_bubble("chat")
        self._eval_bubble("append_message", role="user", text=text)
        self._eval_bubble("begin_stream")
        self.pet.set_busy(True)
        append_chat("user", text)
        threading.Thread(target=self._run_agent, args=(text,), daemon=True).start()

    def _run_agent(self, text: str) -> None:
        if self.agent is None:
            self.ui(lambda: self._on_agent_done("助手还没就绪，请稍后再试。", True))
            return
        self._agent_running = True
        run_id = str(uuid.uuid4())
        failed = False
        try:
            inject_history(self.agent, self.state.history_n, exclude_user=text)
            answer = str(self.agent.run(text, run_id=run_id))
            self._record_usage(self.agent, run_id)
        except Exception as exc:
            answer = str(exc)
            failed = True
            if self.agent is not None:
                try:
                    self._record_usage(self.agent, run_id)
                except Exception as usage_exc:
                    log(f"用量记录失败: {usage_exc}")
        finally:
            self._agent_running = False
        self.ui(lambda: self._on_agent_done(answer, failed))

    def _on_agent_done(self, answer: str, failed: bool) -> None:
        if not self.pet:
            return
        role = "err" if failed else "pet"
        if not failed:
            self.pet.review()
            append_chat("pet", answer)
        else:
            self.pet.fail()
        self._eval_bubble("end_stream", text=answer, role=role)
        self._eval_bubble("set_busy", busy=False)
        self.show_bubble("chat")

    def _run_daily(self) -> None:
        if not self.state.nudge_enabled:
            return
        today = datetime.now(TZ).date().isoformat()
        if self.state.last_daily_date == today:
            log("今日纸条已写过，跳过")
            return
        if self.agent is None:
            self.ui(
                lambda: self.show_notice(
                    self._agent_error or "还没接上模型。打开看板「模型」页填写后再看今日安排。"
                )
            )
            return
        ready = threading.Event()
        self.ui(lambda: self._begin_daily_stream(ready))
        if not ready.wait(8):
            log("今日纸条：气泡未及时开流")
        self._agent_running = True
        run_id = str(uuid.uuid4())
        failed = False
        try:
            inject_history(self.agent, self.state.history_n)
            answer = str(self.agent.run(DAILY_ASK, run_id=run_id)).strip()
            if not answer:
                raise RuntimeError("今日纸条返回空内容。")
            self._record_usage(self.agent, run_id)
        except Exception as exc:
            answer = str(exc)
            failed = True
            if self.agent is not None:
                try:
                    self._record_usage(self.agent, run_id)
                except Exception as usage_exc:
                    log(f"用量记录失败: {usage_exc}")
        finally:
            self._agent_running = False
        self.ui(lambda: self._on_daily_done(answer, failed, today))

    def _begin_daily_stream(self, ready: threading.Event) -> None:
        try:
            if self.pet and not self.pet.visible():
                self.pet.show()
            self._card_mode = "chat"
            self.pet.bubble_open = True
            self._eval_bubble("show_panel", panel="chat")
            self._eval_bubble("begin_stream")
        except Exception as exc:
            log(f"今日纸条开流: {exc}")
        finally:
            ready.set()

    def _on_daily_done(self, answer: str, failed: bool, today: str) -> None:
        if not self.pet or not self.state.nudge_enabled:
            return
        self._card_mode = "chat"
        role = "err" if failed else "pet"
        self._eval_bubble("end_stream", text=answer, role=role)
        self._eval_bubble("show_panel", panel="chat")
        if failed:
            return
        self.pet.wave()
        append_chat("pet", answer)
        self.state.last_daily_date = today
        self.state.save()

    def _run_template_nudge(self) -> None:
        text = None
        err = None
        try:
            from .board_data import fetch_board
            from .nudge import pick_template

            text = pick_template(fetch_board())
        except Exception as exc:
            err = str(exc)
        self.ui(lambda: self._on_template(text, err))

    def _on_template(self, text: str | None, err: str | None) -> None:
        self._nudge_busy = False
        if not self.pet or not self.state.nudge_enabled:
            return
        if err:
            self.show_notice(err, panel="today")
            return
        if text:
            self.show_notice(text, panel="today")

    def on_llm_delta(self, piece: str) -> None:
        if not piece or self.pet is None:
            return
        self._eval_bubble("append_stream", piece=piece)

    def on_stream_status(self, text: str) -> None:
        if not text or self.pet is None:
            return
        self._eval_bubble("set_stream_status", text=text)

    def _eval_bubble(self, event: str, **params) -> None:
        if self.pet is None:
            log(f"跳过 {event}：宠物还不存在")
            return
        try:
            self.pet.emit(event, **params)
        except Exception as exc:
            log(f"emit {event}: {exc}")

    def quit(self) -> None:
        if self._quitting:
            os._exit(0)
        self._quitting = True
        if self.pet is not None:
            self.pet.persist()
            self.pet.close()
        if self.icon is not None:
            self.icon.visible = False
            icon = self.icon
            self.icon = None
            threading.Thread(target=icon.stop, daemon=True).start()
        self.pet = None
        os._exit(0)

    def on_board_shown(self, *_args) -> None:
        log("board shown")
        try:
            hide_form(self.board)
        except Exception as exc:
            log(f"board shown hide: {exc}")

    def on_board_closing(self, *_args):
        if self._quitting:
            return True
        self.hide_board()
        return False


def run_app(skin_id: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("desk-companion 只支持 Windows。")
    install_crash_hooks()
    log("启动 desk-companion")
    _acquire_singleton()
    enable_dpi_aware()
    ui_dir = Path(__file__).resolve().parent / "ui"
    board_path = ui_dir / "board.html"
    if not board_path.is_file():
        raise RuntimeError(f"缺少界面文件。请确认存在 {board_path}。")

    print("正在加载凯尔希…", flush=True)
    log("load_skin")
    app = App(skin_id)
    print("正在显示宠物…", flush=True)
    log("start_pet_thread")
    app.pet = start_pet_thread(app, app.skin)
    print("正在连接助手…", flush=True)
    log("build_agent")
    app.try_build_agent()
    log("webview.create_window 看板")
    app.board = webview.create_window(
        "看板",
        board_path.as_uri(),
        js_api=app.bridge,
        width=BOARD_W,
        height=BOARD_H,
        min_size=(720, 480),
        frameless=True,
        resizable=True,
        hidden=True,
        on_top=False,
        background_color=PAPER,
        text_select=True,
        shadow=True,
        easy_drag=False,
    )
    app.board.events.shown += app.on_board_shown
    app.board.events.closing += app.on_board_closing
    start_os_watchdog(25)
    try:
        log("webview.start")
        webview.start(app.on_ready, gui="edgechromium")
    except Exception as exc:
        raise RuntimeError(
            "无法启动 Edge WebView2。请安装 Microsoft Edge WebView2 Runtime 后重试。\n"
            f"{exc}"
        ) from exc


def _is_ui_fault(exc: BaseException) -> bool:
    name = type(exc).__name__
    msg = str(exc)
    if name in {"WebViewException", "JSException", "RuntimeError"}:
        return True
    if "WebView" in name:
        return True
    if "Main window failed" in msg or "evaluate_js" in msg:
        return True
    return False


def _acquire_singleton() -> None:
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        raise RuntimeError("无法创建单实例锁，拒绝启动第二个桌宠。")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise RuntimeError(
            "桌宠已经在运行。若桌面上还留着窗口但退不出，"
            "打开任务管理器结束所有命令行含 desk_companion 的 python.exe 后再启动。"
        )
    _mutex_handle = handle


def _prepare_form(
    window,
    *,
    tool: bool,
    round_corners: bool = True,
    transparent: bool = False,
) -> None:
    form = form_of(window)
    if tool:
        apply_tool_window(form)
        if round_corners:
            _set_corner_preference(window, DWMWCP_ROUND)
        else:
            _set_corner_preference(window, DWMWCP_DONOTROUND)
    else:
        apply_app_window(form)
        enable_thick_frame(form)
        _paint_paper_chrome(window, form)
        _set_corner_preference(window, DWMWCP_ROUND)
    form.Opacity = 0
    form.Hide()
    form.Visible = False
    cache_hwnd(window)


def _native_hwnd(window) -> int:
    native = window.native
    if native is None:
        raise RuntimeError("pywebview 窗口还没有 native 句柄。")
    handle = native.Handle
    if hasattr(handle, "ToInt64"):
        return as_hwnd(int(handle.ToInt64()))
    return as_hwnd(int(handle))


def _rgb_colorref(hex_color: str) -> int:
    h = hex_color.removeprefix("#")
    if len(h) != 6:
        raise RuntimeError(f"颜色必须是 #RRGGBB，收到 {hex_color!r}。")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def _set_dwm_int(window, attr: int, value: int) -> None:
    hwnd = _native_hwnd(window)
    buf = ctypes.c_int(value)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        attr,
        ctypes.byref(buf),
        ctypes.sizeof(buf),
    )


def _set_dwm_color(window, attr: int, hex_color: str) -> None:
    hwnd = _native_hwnd(window)
    buf = ctypes.c_uint(_rgb_colorref(hex_color))
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        attr,
        ctypes.byref(buf),
        ctypes.sizeof(buf),
    )


def _paint_paper_chrome(window, form) -> None:
    """关掉深色 Mica，刷成奶油纸。不要品红抠图。"""
    from System.Drawing import ColorTranslator

    paper = ColorTranslator.FromHtml(PAPER)
    form.BackColor = paper
    browser = getattr(form, "browser", None)
    control = getattr(browser, "webview", None) if browser is not None else None
    if control is None:
        raise RuntimeError("看板没有 WebView2 控件，无法刷纸色底。")
    control.DefaultBackgroundColor = paper
    _set_dwm_int(window, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1, 0)
    _set_dwm_int(window, DWMWA_USE_IMMERSIVE_DARK_MODE, 0)
    _set_dwm_int(window, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
    _set_dwm_color(window, DWMWA_BORDER_COLOR, BLUSH)
    _set_dwm_color(window, DWMWA_CAPTION_COLOR, PAPER)
    _set_dwm_color(window, DWMWA_TEXT_COLOR, INK)


def _set_corner_preference(window, preference: int) -> None:
    hwnd = _native_hwnd(window)
    value = ctypes.c_int(preference)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(value),
        ctypes.sizeof(value),
    )


def _message_box(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, text, "desk-companion", 0x10)
