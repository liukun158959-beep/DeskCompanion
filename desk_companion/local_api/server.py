"""P1：本地 API 服务。HTTP /health + WebSocket RPC。

- HTTP GET /health：Rust 壳轮询就绪用。
- WS /ws?token=：收 {"type":"rpc","id","method","args"}，按白名单派发到 Bridge，
  回 {"type":"rpc_result","id","result"}。窗口/UI 类方法不在白名单，消除误用。

用法：python -m desk_companion.local_api.server --port 8770 --token <token>
本轮先做 RPC 数据方法；流式对话在下一刀接入。
"""
from __future__ import annotations

import argparse
import asyncio
import json

from websockets.asyncio.server import serve

from .host import HeadlessApp

# 白名单：bridge 上可无头调用的数据方法。窗口/UI 类（close_bubble/fit_card/
# open_url/ask_today/ask_logs/close_board/send_chat）与流式（send_board_chat）不在此。
RPC_METHODS = frozenset({
    "load_board", "load_log_errors", "load_skills",
    "load_persona", "save_persona",
    "load_model", "save_model", "test_model",
    "load_usage", "load_chat_log", "load_memory",
    "load_feishu", "feishu_login", "feishu_logout",
    "load_maa", "load_github", "load_skland", "sync_skland",
    "save_maa_paths", "save_maa_option",
    "maa_open_game", "maa_start_daily", "maa_stop", "maa_authorize",
    "compute_farm_plan", "generate_week_review",
    "write_today_summary_doc", "write_week_review_doc",
    "list_feishu_docs", "load_composer_options",
    "new_chat_session", "switch_chat_session", "clear_chat",
    "list_automation_jobs", "save_automation_job",
    "delete_automation_job", "run_automation_job",
})

TOKEN = ""
HOST: HeadlessApp | None = None


def _health(connection, request):
    # 非 WS 的普通 HTTP：/health 返回 200，其余交给 WS 握手或 404
    if request.path == "/health":
        return connection.respond(200, "ok\n")
    if request.path.startswith("/ws"):
        return None
    return connection.respond(404, "not found\n")


def _dispatch(method: str, args: dict) -> dict:
    # 按白名单派发到 Bridge。不在白名单直接失败，不静默兜底。
    if method not in RPC_METHODS:
        return {"ok": False, "error": f"方法不允许或不存在：{method}"}
    fn = getattr(HOST.bridge, method, None)
    if fn is None:
        return {"ok": False, "error": f"Bridge 无此方法：{method}"}
    try:
        result = fn(**args) if args else fn()
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def _handler(ws):
    req_path = ws.request.path if ws.request else ""
    if TOKEN and f"token={TOKEN}" not in req_path:
        await ws.close(code=4401, reason="bad token")
        return
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "data": "非法 JSON"}))
            continue
        if msg.get("type") != "rpc":
            await ws.send(json.dumps({"type": "error", "data": "暂只支持 type=rpc"}))
            continue
        method = str(msg.get("method", ""))
        args = msg.get("args") or {}
        # 数据方法可能有阻塞 IO（飞书/MAA/GitHub），丢线程池不堵事件循环
        res = await asyncio.to_thread(_dispatch, method, args)
        await ws.send(json.dumps({"type": "rpc_result", "id": msg.get("id"), "result": res}))


async def main() -> None:
    global TOKEN, HOST
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, default="")
    args = parser.parse_args()
    TOKEN = args.token
    HOST = HeadlessApp()

    async with serve(_handler, "127.0.0.1", args.port, process_request=_health):
        print(f"local_api ready on 127.0.0.1:{args.port}", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
