"""本机 MAA 远程控制：getTask / reportStatus。只绑 127.0.0.1。"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .logutil import log

_INSTANT = frozenset({"StopTask", "HeartBeat", "CaptureImageNow"})


class RemoteHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[dict] = []
        self._reports: list[dict] = []
        self._polled = threading.Event()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self, port: int) -> None:
        if self._httpd is not None:
            return
        if type(port) is not int or port < 1024 or port > 65535:
            raise RuntimeError("远控端口必须是 1024 到 65535 的整数。")
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                path = self.path.split("?", 1)[0]
                if path.endswith("/getTask"):
                    hub._polled.set()
                    body = json.dumps({"tasks": hub.snapshot_tasks()}, ensure_ascii=False)
                elif path.endswith("/reportStatus"):
                    try:
                        payload = json.loads(raw.decode("utf-8") or "{}")
                    except json.JSONDecodeError:
                        payload = {}
                    hub.record_report(payload if isinstance(payload, dict) else {})
                    body = "{}"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, fmt, *args):
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._httpd = httpd
        self.port = port
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()
        log(f"MAA 远控监听 http://127.0.0.1:{port}/maa/getTask")

    def urls(self) -> tuple[str, str]:
        if self.port <= 0:
            raise RuntimeError("远控还没监听。")
        base = f"http://127.0.0.1:{self.port}/maa"
        return f"{base}/getTask", f"{base}/reportStatus"

    def snapshot_tasks(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._tasks]

    def replace_linkstart(self, types: list[str]) -> list[dict]:
        tasks = []
        for item in types:
            if type(item) is not str or not item.strip():
                raise RuntimeError("远控任务 type 必须是非空字符串。")
            tasks.append({"id": str(uuid.uuid4()), "type": item.strip()})
        with self._lock:
            self._tasks = tasks
            self._reports = []
            self._polled.clear()
        return [dict(item) for item in tasks]

    def enqueue_stop(self) -> None:
        with self._lock:
            self._tasks = [{"id": str(uuid.uuid4()), "type": "StopTask"}]
            self._polled.clear()

    def record_report(self, payload: dict) -> None:
        with self._lock:
            self._reports.append(
                {
                    "task": str(payload.get("task") or ""),
                    "status": str(payload.get("status") or ""),
                }
            )

    def reset_poll(self) -> None:
        self._polled.clear()

    def polled(self) -> bool:
        return self._polled.is_set()

    def wait_polled(self, timeout_sec: float) -> bool:
        return self._polled.wait(timeout_sec)

    def wait_report(
        self, task_id: str, timeout_sec: float, cancel: threading.Event
    ) -> dict:
        if type(task_id) is not str or not task_id:
            raise RuntimeError("远控任务 id 必须是非空字符串。")
        if type(timeout_sec) is not float and type(timeout_sec) is not int:
            raise RuntimeError("等待汇报超时必须是数字。")
        deadline = time.monotonic() + float(timeout_sec)
        while True:
            if cancel.is_set():
                raise RuntimeError("已停止，仓库未更新，再开一次清日常。")
            for item in self.last_reports():
                if item["task"] == task_id:
                    return item
            if time.monotonic() >= deadline:
                waited = int(float(timeout_sec))
                raise RuntimeError(
                    f"等 MAA 结束超过 {waited} 秒，仓库未更新。再开一次清日常。"
                )
            time.sleep(1)

    def last_reports(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._reports]
