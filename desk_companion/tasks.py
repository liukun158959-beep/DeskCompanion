"""持久任务队列：会话内顺序执行，会话间独立进程并行。"""
from __future__ import annotations
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from .paths import data_root
from .task_process import ProcessTree

TERMINAL = {"succeeded", "failed", "cancelled", "timed_out", "interrupted"}
DEFAULTS = {"parallel": 2, "call_timeout": 90, "task_timeout": 300, "pet_progress": True}


class TaskManager:
    def __init__(self, host=None, path=None, command=None):
        self.host = host
        self.path = Path(path or data_root() / "memory" / "tasks.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.command = command or [sys.executable, "-u", "-m", "desk_companion.task_worker"]
        self.cv = threading.Condition(threading.RLock())
        self.active = {}
        self.listeners = {}
        self.stopped = False
        self.settings_path = self.path.parent / "task_settings.json"
        self.settings = {**DEFAULTS, **(json.loads(self.settings_path.read_text("utf-8")) if self.settings_path.exists() else {})}
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, session TEXT, channel TEXT, "
                       "text TEXT, request TEXT, state TEXT, answer TEXT DEFAULT '', error TEXT DEFAULT '', "
                       "created REAL, started REAL DEFAULT 0, ended REAL DEFAULT 0, source TEXT DEFAULT '{}')")
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, kind TEXT, data TEXT, ts REAL)")
            db.execute("UPDATE tasks SET state='interrupted', ended=?, error='桌宠退出时任务中断，已完成的工具不会自动重做。' "
                       "WHERE state IN ('queued','running','cancelling')", (time.time(),))
            db.commit()
        self.scheduler = threading.Thread(target=self._schedule, daemon=True)
        self.scheduler.start()

    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return closing(db)

    def configure(self, parallel, call_timeout, task_timeout, pet_progress):
        if type(parallel) is not int or not 1 <= parallel <= 4:
            raise ValueError("并行数须为 1～4。")
        if type(call_timeout) is not int or not 10 <= call_timeout <= 300:
            raise ValueError("单次调用时限须为 10～300 秒。")
        if type(task_timeout) is not int or not call_timeout <= task_timeout <= 1800:
            raise ValueError("总时限须大于单次调用时限，且不超过 1800 秒。")
        if type(pet_progress) is not bool:
            raise ValueError("桌宠进度反馈须为开关。")
        with self.cv:
            self.settings = dict(parallel=parallel, call_timeout=call_timeout, task_timeout=task_timeout, pet_progress=pet_progress)
            self.settings_path.write_text(json.dumps(self.settings), "utf-8")
            self.cv.notify_all()
        return {"ok": True, "settings": self.settings}

    def submit(self, text, session, channel="desktop", source=None, callback=None, **request):
        if not isinstance(text, str) or not text.strip() or len(text) > 200000:
            raise ValueError("请填写有效问题。")
        if not isinstance(session, str) or not session:
            raise ValueError("缺少会话。")
        task_id = uuid.uuid4().hex
        with self.cv:
            if self.stopped:
                raise RuntimeError("桌宠正在退出。")
            request.update(text=text, session_id=session, limits=dict(self.settings))
            request.setdefault("sampling", {"reasoning_effort": "low", "temperature": .5, "top_p": 1})
            with self.db() as db:
                db.execute("INSERT INTO tasks(id,session,channel,text,request,state,created,source) VALUES(?,?,?,?,?,'queued',?,?)",
                           (task_id, session, channel, text, json.dumps(request), time.time(), json.dumps(source or {})))
                db.commit()
            if callback:
                self.listeners[task_id] = callback
            self.event(task_id, "status", "博士，任务已登记，正在等待执行。")
            self.cv.notify_all()
        return task_id

    def get(self, task_id, events=True):
        with self.db() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValueError("任务不存在。")
            value = dict(row)
            value.pop("request")
            value["source"] = json.loads(value["source"])
            if events:
                value["events"] = [{**dict(e), "data": json.loads(e["data"])} for e in db.execute(
                    "SELECT seq,kind,data,ts FROM events WHERE task=? ORDER BY seq", (task_id,))]
        value["elapsed"] = round((value["ended"] or time.time()) - value["started"], 1) if value["started"] else 0
        return value

    def list(self, channel="", session=""):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM tasks WHERE (?='' OR channel=?) AND (?='' OR session=?) "
                                          "ORDER BY created DESC LIMIT 100", (channel, channel, session, session))]
        return {"ok": True, "settings": dict(self.settings), "items": [self.get(i, False) for i in ids]}

    def update(self, task_id, **values):
        with self.db() as db:
            db.execute("UPDATE tasks SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", (*values.values(), task_id))
            db.commit()

    def event(self, task_id, kind, data):
        # 思考仅流到当前窗口，不保存进监控台，不转发到飞书。
        if kind != "think":
            with self.db() as db:
                db.execute("INSERT INTO events(task,kind,data,ts) VALUES(?,?,?,?)", (task_id, kind, json.dumps(data), time.time()))
                if kind == "token":
                    db.execute("UPDATE tasks SET answer=answer||? WHERE id=?", (str(data), task_id))
                db.commit()
        callback = self.listeners.get(task_id)
        if callback:
            try:
                callback(kind, data)
            except Exception:
                pass  # 窗口关闭不会取消后台任务。
        with self.cv:
            self.cv.notify_all()

    def wait(self, task_id):
        with self.cv:
            while True:
                row = self.get(task_id)
                if row["state"] in TERMINAL:
                    return row
                self.cv.wait(.3)

    def cancel(self, task_id):
        with self.cv:
            row = self.get(task_id)
            if row["state"] in TERMINAL:
                return {"ok": True, "task": row}
            running = self.active.get(task_id)
            if running:
                running["cancel"].set()
                self.update(task_id, state="cancelling")
            else:
                self.finish(task_id, "cancelled", "博士，已从队列移除。")
            self.cv.notify_all()
        return {"ok": True, "task": self.get(task_id)}

    def finish(self, task_id, state, error="", answer=None):
        values = dict(state=state, error=error, ended=time.time())
        if answer is not None:
            values["answer"] = answer
        self.update(task_id, **values)
        row = self.get(task_id, False)
        self.event(task_id, "done" if state == "succeeded" else "error", row["answer"] if state == "succeeded" else error)
        self.listeners.pop(task_id, None)

    def _schedule(self):
        while True:
            with self.cv:
                if self.stopped:
                    return
                with self.db() as db:
                    queue = [dict(r) for r in db.execute("SELECT * FROM tasks WHERE state='queued' ORDER BY created,rowid")]
                busy = {v["session"] for v in self.active.values()}
                for row in queue:
                    if len(self.active) >= self.settings["parallel"]:
                        break
                    if row["session"] in busy:
                        continue
                    control = {"session": row["session"], "cancel": threading.Event()}
                    self.active[row["id"]] = control
                    busy.add(row["session"])
                    self.update(row["id"], state="running", started=time.time())
                    threading.Thread(target=self._execute, args=(row, control), daemon=True).start()
                self.cv.wait(.2)

    def _execute(self, row, control):
        task_id = row["id"]
        request = json.loads(row["request"])
        tree = process = None
        phase = {"deadline": None}
        ended = threading.Event()
        outcome = {}
        try:
            self.event(task_id, "status", "博士，正在整理上下文，准备调用模型。")
            process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       text=True, encoding="utf-8", errors="replace", cwd=str(Path(__file__).resolve().parents[1]),
                                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=0x08000000 if os.name == "nt" else 0)
            tree = ProcessTree(process)
            # worker 初始化前挂入 Job；从此包括工具子进程在内都能及时停止。
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()

            def read():
                try:
                    for line in process.stdout:
                        event = json.loads(line)
                        kind, data = event["kind"], event.get("data")
                        if kind == "maa":
                            from . import maa_tools
                            from .resource_lock import WRITES
                            with WRITES:
                                result = getattr(maa_tools, data["name"])(data["args"])
                            process.stdin.write(json.dumps({"result": result}) + "\n")
                            process.stdin.flush()
                        elif kind == "result":
                            outcome["answer"] = str(data)
                        elif kind == "failure":
                            outcome["error"] = str(data)
                        else:
                            if kind in ("llm_start", "tool_start"):
                                phase["deadline"] = time.monotonic() + request["limits"]["call_timeout"]
                            elif kind in ("llm_end", "tool_end"):
                                phase["deadline"] = None
                            self.event(task_id, kind, data)
                except Exception:
                    outcome["error"] = "任务通信中断，工具可能已经执行，请查看时间线。"
                finally:
                    ended.set()

            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            deadline = time.monotonic() + request["limits"]["task_timeout"]
            waiting_note = time.monotonic() + 30
            reason = ""
            while not ended.wait(.05):
                if control["cancel"].is_set():
                    reason = "cancelled"
                    break
                if time.monotonic() >= deadline or (phase["deadline"] and time.monotonic() >= phase["deadline"]):
                    reason = "timed_out"
                    break
                if time.monotonic() >= waiting_note:
                    self.event(task_id, "status", "博士，当前调用还未返回。我会保留进度，到时限后停止等待。")
                    waiting_note = float("inf")
            if reason:
                tree.close()
                reader.join(2)
                message = "博士，任务已停止。" if reason == "cancelled" else "博士，调用达到时限，已停止等待。"
                self.finish(task_id, reason, message + "已保留部分答案和工具记录；继续前请确认已执行的操作。")
                self._save_partial(row, reason)
            elif "answer" in outcome:
                self.finish(task_id, "succeeded", answer=outcome["answer"])
            else:
                self.finish(task_id, "failed", outcome.get("error", "任务进程意外退出，请检查模型配置。"))
                self._save_partial(row, "failed")
        except Exception:
            self.finish(task_id, "failed", "无法启动独立任务，请检查后端日志或重启桌宠。")
        finally:
            if tree:
                tree.close()
            if process:
                for pipe in (process.stdin, process.stdout):
                    if pipe:
                        pipe.close()
            with self.cv:
                self.active.pop(task_id, None)
                self.cv.notify_all()

    def _save_partial(self, row, reason):
        from .memory import append_chat
        value = self.get(row["id"], False)
        if value["answer"]:
            append_chat("pet", value["answer"] + "\n\n[任务中断：" + reason + "，部分内容]", row["session"])

    def resume(self, task_id, text, callback=None, send_back=False):
        previous = self.get(task_id)
        if previous["state"] not in TERMINAL:
            raise ValueError("请先停止当前任务或等待完成。")
        steps = [e["data"] for e in previous["events"] if e["kind"] in ("tool_start", "tool_end")]
        note = "\n\n【继续任务】前次工具记录（开始但未结束代表结果未知，须查询确认，不可盲目重做）：\n" + json.dumps(steps, ensure_ascii=False)
        note += "\n前次部分答案：\n" + previous["answer"][-10000:] + "\n避免重复执行已完成的写入操作。"
        with self.db() as db:
            request = json.loads(db.execute("SELECT request FROM tasks WHERE id=?", (task_id,)).fetchone()[0])
        for key in ("text", "session_id", "limits"):
            request.pop(key, None)
        completed = {e["data"].get("fingerprint") for e in previous["events"] if e["kind"] == "tool_end"
                     and e["data"].get("status") in {"success", "idempotency_hit"} and not e["data"].get("read_only", True)}
        request["completed_writes"] = list(set(request.get("completed_writes", [])) | (completed - {None}))
        return self.submit(text, previous["session"], previous["channel"], source={**previous["source"], "parent_task": task_id,
                           "send_back": send_back}, callback=callback, resume_note=note, **{k:v for k,v in request.items() if k != "resume_note"})

    def shutdown(self):
        with self.cv:
            self.stopped = True
            for control in self.active.values():
                control["cancel"].set()
            with self.db() as db:
                db.execute("UPDATE tasks SET state='interrupted', ended=? WHERE state='queued'", (time.time(),))
                db.commit()
            self.cv.notify_all()
            deadline = time.monotonic() + 4
            while self.active and time.monotonic() < deadline:
                self.cv.wait(.05)
        self.scheduler.join(1)
