"""飞书机器人通道：CLI 托管凭证与长连接，桌宠复用同一 Agent。"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .feishu_tools import CREATE_NO_WINDOW, _lark_cmd, _run_lark
from .paths import data_root

EVENT_KEY = "im.message.receive_v1"
HELP = ("我是桌宠 Agent，使用本机配置的模型、技能和工具。\n"
        "直接发送问题即可。\n/help 帮助\n/new 新对话（保留旧历史）\n/status 接入状态\n"
        "/skills 技能列表\n/skill 技能名 问题\n/kb 问题：使用知识库\n"
        "/mcps MCP 工具列表\n/mcp 服务器名/工具名 问题\n"
        "当前只接收绑定用户的私聊文本或富文本；桌宠必须保持运行。")


def config_path() -> Path:
    return data_root() / "feishu_agent.json"


def json_data(raw: str) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("ok") is False:
        raise RuntimeError("飞书 CLI 未成功返回应用身份。")
    return value.get("data", value)


def identify() -> dict:
    current = json_data(_run_lark(["whoami"]))
    profile = current.get("profile")
    if not isinstance(profile, str) or not profile:
        raise RuntimeError("飞书 CLI 没有配置应用，请先执行 lark-cli config init。")
    verified = json_data(_run_lark(["--profile", profile, "auth", "status", "--json", "--verify"]))
    identities = verified.get("identities") or {}
    bot, user = identities.get("bot") or {}, identities.get("user") or {}
    if bot.get("available") is not True or bot.get("verified") is not True:
        raise RuntimeError("飞书应用机器人身份不可用，请检查 CLI 应用配置和机器人能力。")
    if user.get("available") is not True or not str(user.get("openId") or "").startswith("ou_"):
        raise RuntimeError("请先在飞书页登录，用登录用户绑定允许私聊的本人身份。")
    if verified.get("appId") != current.get("appId"):
        raise RuntimeError("飞书应用身份发生变化，请重新检查 CLI 配置。")
    return {"profile": profile, "app_id": verified["appId"], "app_name": bot.get("appName", ""),
            "owner_id": user["openId"], "owner_name": user.get("userName", "")}


class Inbox:
    """消息 ID 去重与回复记录。中断的工具运行不自动重跑。"""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS messages (app TEXT, id TEXT, chat TEXT, sender TEXT, content TEXT, "
                       "kind TEXT, state TEXT, answer TEXT DEFAULT '', sent INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, "
                       "updated REAL, PRIMARY KEY(app,id))")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, id TEXT)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, app: str, event: dict) -> bool:
        with self.connect() as db:
            cursor = db.execute("INSERT OR IGNORE INTO messages(app,id,chat,sender,content,kind,state,updated) "
                                "VALUES(?,?,?,?,?,?,'queued',?)", (app, event["message_id"], event["chat_id"],
                                event["sender_id"], event["content"], event["message_type"], time.time()))
            return cursor.rowcount == 1

    def recover(self, app: str):
        with self.connect() as db:
            # 飞书回复 uuid 的去重窗口只有一小时，超过后不再自动重试不确定的发送。
            db.execute("UPDATE messages SET state='failed' WHERE app=? AND state='answered' AND updated<?",
                       (app, time.time() - 3600))
            db.execute("UPDATE messages SET state='answered', answer=?, sent=0, updated=? "
                       "WHERE app=? AND state='running'", ("上次处理中断。为避免重复执行工具，"
                       "请先确认原任务结果，再重新提问。", time.time(), app))

    def take(self, app: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE messages SET state='expired' WHERE app=? AND state='queued' AND updated<?",
                       (app, time.time() - 600))
            row = db.execute("SELECT * FROM messages WHERE app=? AND state IN ('queued','answered') "
                             "ORDER BY rowid LIMIT 1", (app,)).fetchone()
            if row and row["state"] == "queued":
                db.execute("UPDATE messages SET state='running', updated=? WHERE app=? AND id=?", (time.time(), app, row["id"]))
            return dict(row) if row else None

    def update(self, app: str, message_id: str, **values):
        allowed = {"state", "answer", "sent", "attempts"}
        if set(values) - allowed:
            raise ValueError("非法消息状态字段。")
        values["updated"] = time.time()
        with self.connect() as db:
            db.execute("UPDATE messages SET " + ",".join(f"{key}=?" for key in values) + " WHERE app=? AND id=?",
                       (*values.values(), app, message_id))

    def session(self, app: str, chat: str, sender: str, reset=False) -> str:
        key = hashlib.sha256(f"{app}:{chat}:{sender}".encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM sessions WHERE key=?", (key,)).fetchone()
            if row and not reset:
                return row[0]
            sid = "feishu-" + uuid.uuid4().hex
            db.execute("INSERT OR REPLACE INTO sessions(key,id) VALUES(?,?)", (key, sid))
            return sid


def accepted(event: object, owner: str, now: float | None = None) -> bool:
    if not isinstance(event, dict) or event.get("type") != EVENT_KEY:
        return False
    if event.get("sender_type") != "user" or event.get("sender_id") != owner or event.get("chat_type") != "p2p":
        return False
    if not all(isinstance(event.get(key), str) and event[key] for key in ("message_id", "chat_id", "content", "message_type")):
        return False
    if not event["message_id"].startswith("om_") or not event["chat_id"].startswith("oc_"):
        return False
    try:
        age = (time.time() if now is None else now) - int(event["create_time"]) / 1000
    except (KeyError, ValueError, TypeError, OverflowError):
        return False
    return -60 <= age <= 600 and len(event["content"]) <= 200000


def chunks(text: str) -> list[str]:
    # Windows 子进程命令行有限长；按 Unicode 字符分段，不截断答案。
    return [text[pos:pos + 3500] for pos in range(0, len(text), 3500)] or ["本次没有生成回复，请重新提问。"]


class FeishuAgent:
    def __init__(self, host):
        self.host = host
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._wake = threading.Event()
        self._process = None
        self._supervisor = None
        self._worker = None
        self._binding = {}
        self._state = "stopped"
        self._error = ""
        self._diagnostic = ""
        self._last_reply = ""
        self._inbox = None

    def _config(self) -> dict:
        path = config_path()
        if not path.exists():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("飞书 Agent 配置不是对象，请检查 feishu_agent.json。")
        return value

    def status(self) -> dict:
        with self._lock:
            config = self._config()
            return {"ok": True, "enabled": config.get("enabled") is True, "state": self._state,
                    "connected": self._ready.is_set() and not self._stop.is_set(),
                    "error": self._error, "diagnostic": self._diagnostic, "last_reply": self._last_reply,
                    "binding": self._binding or config.get("binding", {}), "event": EVENT_KEY,
                    "mode": "本人私聊", "config_path": str(config_path())}

    def enable(self) -> dict:
        with self._lock:
            if self._supervisor and self._supervisor.is_alive():
                return self.status()
            if self._worker and self._worker.is_alive():
                raise RuntimeError("上次 Agent 仍在结束当前任务，请稍后再接入。")
            identity = identify()
            previous = self._config().get("binding") or {}
            if previous and any(previous.get(key) != identity[key] for key in ("app_id", "owner_id", "profile")):
                raise RuntimeError("已绑定的应用或用户与当前 CLI 不同。请检查 CLI profile；不要将个人工具连接到另一身份。")
            self._binding = identity
            self._save(True)
            self._start()
            return self.status()

    def _save(self, enabled: bool):
        config_path().write_text(json.dumps({"enabled": enabled, "binding": self._binding}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def autostart(self):
        try:
            config = self._config()
            if config.get("enabled") is True:
                # 再验证绑定身份。后台执行，不阻塞客户端启动动画。
                self.enable()
        except Exception as exc:
            with self._lock:
                self._state = "error"
                self._error = str(exc)

    def _start(self):
        self._stop.clear()
        self._ready.clear()
        self._error = self._diagnostic = ""
        self._state = "connecting"
        self._inbox = Inbox(data_root() / "memory" / "feishu_agent.sqlite3")
        self._inbox.recover(self._binding["app_id"])
        self._supervisor = threading.Thread(target=self._consume, daemon=True, name="feishu-listener")
        self._worker = threading.Thread(target=self._work, daemon=True, name="feishu-agent")
        self._supervisor.start()
        self._worker.start()

    def stop(self, disable=True) -> dict:
        with self._lock:
            self._stop.set()
            self._ready.clear()
            self._wake.set()
            if disable:
                self._binding = self._binding or self._config().get("binding", {})
                self._save(False)
            process = self._process
            if process and process.stdin:
                try:
                    process.stdin.close()  # CLI 的正常停止协议；保留共享 bus。
                except (OSError, ValueError):
                    pass
            self._state = "stopped"
        if process:
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                # 保留诊断；禁止杀共享 bus 或静默留下一个在线 consumer。
                with self._lock:
                    self._state = "error"
                    self._error = "飞书监听尚未退出，请在 CLI 检查当前应用的 event status。"
        if self._supervisor and self._supervisor is not threading.current_thread():
            self._supervisor.join(timeout=1)
        return self.status()

    def _consume(self):
        delay = 2
        try:
            while not self._stop.is_set():
                self._ready.clear()
                with self._lock:
                    self._state = "connecting"
                command = [*_lark_cmd(), "--profile", self._binding["profile"], "event", "consume", EVENT_KEY, "--as", "bot"]
                env = os.environ.copy()
                env["PATH"] = str(Path(command[0]).parent) + os.pathsep + env.get("PATH", "")
                env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
                with self._lock:
                    if self._stop.is_set():
                        return
                    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, encoding="utf-8", errors="replace", cwd=str(data_root()), env=env,
                                               creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
                    self._process = process
                stderr_done = threading.Event()
                stderr_thread = threading.Thread(target=self._stderr, args=(process, stderr_done), daemon=True)
                stderr_thread.start()
                for line in process.stdout:
                    if self._stop.is_set():
                        break
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        with self._lock:
                            self._diagnostic = "飞书监听返回了无法解析的事件，请检查 CLI 版本。"
                        continue
                    if accepted(event, self._binding["owner_id"]):
                        if self._inbox.add(self._binding["app_id"], event):
                            self._wake.set()
                code = process.wait()
                stderr_done.wait(2)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe and not pipe.closed:
                        pipe.close()
                self._ready.clear()
                with self._lock:
                    self._process = None
                if self._stop.is_set():
                    return
                if code in (1, 2, 3):
                    with self._lock:
                        self._state = "error"
                        self._error = self._error or "飞书监听无法启动，请检查机器人权限、事件订阅和长连接占用。"
                    return
                with self._lock:
                    self._state = "reconnecting"
                    self._error = self._error or "飞书连接中断，正在重连。"
                if self._stop.wait(delay):
                    return
                delay = min(delay * 2, 30)
        except Exception as exc:
            self._ready.clear()
            with self._lock:
                self._state = "error"
                self._error = str(exc)
        finally:
            self._ready.clear()

    def _stderr(self, process, done):
        try:
            envelope = ""
            for line in process.stderr:
                text = line.strip()
                if text == f"[event] ready event_key={EVENT_KEY}":
                    with self._lock:
                        if not self._stop.is_set():
                            self._state = "connected"
                            self._error = ""
                            self._ready.set()
                            self._wake.set()
                    continue
                if text.startswith("{") or envelope:
                    envelope += line
                    try:
                        value = json.loads(envelope)
                    except json.JSONDecodeError:
                        if len(envelope) > 20000:
                            envelope = ""
                        continue
                    envelope = ""
                    error = value.get("error") or {}
                    if value.get("ok") is False:
                        with self._lock:
                            if error.get("subtype") == "failed_precondition":
                                self._error = "这个应用已有其他服务的长连接。请停止原服务，等待平台连接数归零后重试；本机 CLI 无法远程停止它。"
                            elif error.get("subtype") == "missing_scope":
                                self._error = "机器人缺少权限：" + "、".join(error.get("missing_scopes") or []) + "。请在应用后台开通并发布，用户登录不能代替机器人授权。"
                            else:
                                self._error = str(error.get("message") or "飞书监听失败。")[:1000]
                elif "WARN" in text or "drop" in text.lower():
                    with self._lock:
                        self._diagnostic = "飞书监听报告了事件丢失或处理警告，请查看 CLI 事件诊断。"
        finally:
            done.set()

    def _work(self):
        while not self._stop.is_set():
            if not self._ready.wait(.2):
                if self._supervisor and not self._supervisor.is_alive():
                    return
                continue
            row = self._inbox.take(self._binding["app_id"])
            if not row:
                self._wake.wait(.5)
                self._wake.clear()
                continue
            try:
                self.process_message(row)
            except Exception as exc:
                from .logutil import log
                log(f"feishu_reply failed: {type(exc).__name__}")
                with self._lock:
                    self._error = "飞书回复未完成，请在本机检查接入状态。"
                attempts = row["attempts"] + 1
                self._inbox.update(row["app"], row["id"], attempts=attempts, state="failed" if attempts >= 5 else "answered")
                if self._stop.wait(min(2 ** attempts, 30)):
                    return

    def process_message(self, row: dict):
        if row["state"] == "queued":
            try:
                answer = self._answer(row)
            except Exception as exc:
                from .logutil import log
                log(f"feishu_agent failed: {type(exc).__name__}")
                # 具体异常留在本机，不向飞书输出路径、凭证或内部堆栈。
                answer = "本次 Agent 处理失败，请在桌宠检查模型配置和日志。工具可能已执行，请确认结果后再试。"
            self._inbox.update(row["app"], row["id"], answer=answer, state="answered")
        else:
            answer = row["answer"]
        parts = chunks(answer)
        for index in range(row["sent"], len(parts)):
            if self._stop.is_set():
                return
            key = "dc-" + hashlib.sha256(f"{row['app']}:{row['id']}:{index}".encode()).hexdigest()[:40]
            raw = _run_lark(["--profile", self._binding["profile"], "im", "+messages-reply", "--as", "bot",
                             "--message-id", row["id"], "--text", parts[index], "--idempotency-key", key])
            result = json.loads(raw)
            if result.get("ok") is not True:
                raise RuntimeError("飞书回复未确认成功。")
            self._inbox.update(row["app"], row["id"], sent=index + 1)
        self._inbox.update(row["app"], row["id"], state="sent")
        with self._lock:
            self._last_reply = time.strftime("%Y-%m-%d %H:%M:%S")

    def _answer(self, row: dict) -> str:
        if row["kind"] not in ("text", "post"):
            return "目前支持文本和富文本，请把问题发成文字。"
        if len(row["content"]) > 16000:
            return "问题过长，请拆分为不超过 16000 字的消息。"
        text = row["content"].strip()
        command = text.split(maxsplit=1)[0] if text else ""
        if command == "/help":
            return HELP
        if command == "/new":
            self._inbox.session(row["app"], row["chat"], row["sender"], reset=True)
            return "已开始新的飞书对话，旧历史仍保留在桌宠。"
        if command == "/status":
            return f"桌宠已连接飞书应用「{self._binding['app_name']}」，仅接受绑定用户私聊。模型与工具使用桌宠当前配置。"
        if command == "/skills":
            from .skill_catalog import list_skills
            return "\n".join(f"{item['id']}：{item['description']}" for item in list_skills()) or "当前没有技能。"
        if command == "/mcps":
            from .mcp_client import list_mcp_menu
            menu = list_mcp_menu()
            if menu.get("ok") is not True:
                return "MCP 尚未准备好，请在桌宠配置并检查 MCP 工具。"
            return "\n".join(item["label"] for item in menu["items"]) or "当前没有 MCP 工具。"
        knowledge = command == "/kb"
        chips = {}
        if knowledge:
            parts = text.split(maxsplit=1)
            text = parts[1] if len(parts) == 2 else ""
            if not text:
                return "用法：/kb 问题"
        elif command == "/skill":
            pieces = text.split(maxsplit=2)
            if len(pieces) != 3:
                return "用法：/skill 技能名 问题。发送 /skills 查看技能名。"
            chips = {"skills": [pieces[1]]}
            text = pieces[2]
        elif command == "/mcp":
            pieces = text.split(maxsplit=2)
            if len(pieces) != 3 or "/" not in pieces[1]:
                return "用法：/mcp 服务器名/工具名 问题。发送 /mcps 查看工具。"
            server, tool = pieces[1].split("/", 1)
            if not server or not tool:
                return "服务器名和工具名不能为空。"
            chips = {"mcp": [{"server": server, "tool": tool}]}
            text = pieces[2]
        elif command.startswith("/"):
            return HELP
        sid = self._inbox.session(row["app"], row["chat"], row["sender"])
        return self.host.run_channel_chat(text, sid, chips, knowledge)
