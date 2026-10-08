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
import hmac

from websockets.asyncio.server import serve

from ..sampling import parse_sampling
from .host import HeadlessApp

# 白名单：bridge 上可无头调用的数据方法。窗口/UI 类（close_bubble/fit_card/
# open_url/ask_today/ask_logs/close_board/send_chat）与流式（send_board_chat）不在此。
RPC_METHODS = frozenset({
    "load_onboarding", "complete_onboarding", "report_pet_status",
    "load_board", "delete_agenda", "delete_task", "create_agenda", "load_log_errors", "load_skills",
    "load_persona", "save_persona",
    "load_model", "save_model", "test_model",
    "load_models", "save_model_entry", "delete_model_entry", "use_model",
    "load_usage", "load_chat_log", "load_memory", "compress_context",
    "add_fact", "update_fact", "delete_fact", "delete_memory_turn",
    "load_feishu", "feishu_login", "feishu_logout",
    "load_feishu_agent", "start_feishu_agent", "stop_feishu_agent",
    "list_feishu_agent_profiles", "save_feishu_agent_settings",
    "update_feishu_agent_credentials", "check_feishu_agent_connection",
    "load_maa", "load_depot", "load_raise", "add_raise", "remove_raise",
    "load_github", "load_skland", "sync_skland",
    "save_maa_paths", "save_maa_option",
    "maa_open_game", "maa_start_daily", "maa_stop", "maa_authorize",
    "compute_farm_plan", "generate_week_review",
    "write_today_summary_doc", "write_week_review_doc",
    "list_feishu_docs", "list_mcp_tools", "load_composer_options",
    "load_knowledge", "save_knowledge", "download_knowledge", "delete_model",
    "add_knowledge", "delete_knowledge", "rebuild_knowledge", "ask_knowledge",
    "load_notebook", "new_notebook", "save_notebook_note", "delete_notebook_note",
    "export_notebook_markdown", "export_notebook_feishu", "summarize_notebook",
    "open_notebook_file", "reveal_notebook_file", "delete_notebook_file",
    "new_chat_session", "switch_chat_session", "clear_chat",
    "list_automation_jobs", "save_automation_job",
    "delete_automation_job", "run_automation_job",
})

TOKEN = ""
HOST: HeadlessApp | None = None
SHUTDOWN: asyncio.Event | None = None


def _health(connection, request):
    if request.path == "/shutdown":
        authorization = request.headers.get("Authorization", "")
        if not TOKEN or not hmac.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
            return connection.respond(401, "bad token\n")
        if SHUTDOWN is None:
            return connection.respond(503, "shutdown unavailable\n")
        SHUTDOWN.set()
        response = connection.respond(200, "shutting down\n")
        response.headers["Cache-Control"] = "no-store"
        return response
    # 非 WS 的普通 HTTP：/health 返回 200，物品图走 /depot-icon/，其余交给 WS 握手或 404
    if request.path == "/health":
        return connection.respond(200, "ok\n")
    if request.path.startswith("/depot-icon/"):
        return _depot_icon(connection, request.path)
    if request.path.startswith("/pet-assets/"):
        return _pet_asset(connection, request.path)
    if request.path.startswith("/ws"):
        return None
    return connection.respond(404, "not found\n")


def read_pet_asset(request_path: str):
    from urllib.parse import unquote, urlsplit
    from ..paths import asset_root
    path = urlsplit(request_path).path.removeprefix("/pet-assets/")
    token, _, relative = path.partition("/")
    if not TOKEN or token != TOKEN:
        raise PermissionError("素材请求的 token 不对。")
    root = asset_root().resolve()
    target = (root / unquote(relative)).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix.lower() not in {
        ".js", ".json", ".png", ".jpg", ".jpeg", ".webp", ".moc3", ".wasm", ".wav", ".mp3", ".ogg"
    }:
        raise FileNotFoundError("找不到形象素材。")
    return target


def _pet_asset(connection, request_path: str):
    from websockets.asyncio.server import Response
    from websockets.datastructures import Headers
    try:
        path = read_pet_asset(request_path)
    except PermissionError as exc:
        return connection.respond(401, str(exc))
    except (FileNotFoundError, ValueError, OSError):
        return connection.respond(404, "asset not found\n")
    body = path.read_bytes()
    headers = Headers()
    # Windows 注册表可能将 .js 标记成 text/plain；跨源脚本会被浏览器拒绝。
    # 素材类型固定，不能使用受注册表影响的 mimetypes.guess_type。
    headers["Content-Type"] = {
        ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".wasm": "application/wasm", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp", ".wav": "audio/wav",
        ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
    }.get(path.suffix.lower(), "application/octet-stream")
    headers["Content-Length"] = str(len(body))
    headers["Access-Control-Allow-Origin"] = "*"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Cache-Control"] = "no-store"
    return Response(200, "OK", headers, body)


def _depot_icon(connection, path: str):
    from urllib.parse import parse_qs, urlsplit

    from websockets.asyncio.server import Response
    from websockets.datastructures import Headers

    from ..depot_view import read_icon

    parts = urlsplit(path)
    if TOKEN:
        token = parse_qs(parts.query).get("token", [""])[0]
        if token != TOKEN:
            return connection.respond(401, "图标请求的 token 不对。\n")
    item_id = parts.path.removeprefix("/depot-icon/").strip("/")
    try:
        body = read_icon(item_id)
    except RuntimeError as exc:
        return connection.respond(404, f"{exc}\n")
    headers = Headers()
    headers["Content-Type"] = "image/png"
    headers["Content-Length"] = str(len(body))
    headers["Cache-Control"] = "no-store"
    return Response(200, "OK", headers, body)


def _dispatch(method: str, args: dict) -> dict:
    # 按白名单派发到 Bridge。不在白名单直接失败，不静默兜底。
    if method not in RPC_METHODS:
        return {"ok": False, "error": f"方法不允许或不存在：{method}"}
    fn = getattr(HOST.bridge, method, None)
    if fn is None:
        return {"ok": False, "error": f"Bridge 无此方法：{method}"}
    try:
        if method in {"load_feishu_agent", "start_feishu_agent", "stop_feishu_agent",
                      "list_feishu_agent_profiles", "save_feishu_agent_settings",
                      "update_feishu_agent_credentials", "check_feishu_agent_connection"}:
            result = fn(**args) if args else fn()
        else:
            # 飞书与桌面共享 Agent；数据方法不能读到临时切换中的飞书线程。
            with HOST.turn_lock:
                result = fn(**args) if args else fn()
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def _handler(ws):
    from urllib.parse import parse_qs, urlsplit
    req_path = ws.request.path if ws.request else ""
    parts = urlsplit(req_path)
    if parts.path != "/ws" or (TOKEN and parse_qs(parts.query).get("token", [""])[0] != TOKEN):
        await ws.close(code=4401, reason="bad token")
        return
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "data": "非法 JSON"}))
            continue
        mtype = msg.get("type")
        if mtype == "rpc":
            method = str(msg.get("method", ""))
            args = msg.get("args") or {}
            # 数据方法可能有阻塞 IO（飞书/MAA/GitHub），丢线程池不堵事件循环
            res = await asyncio.to_thread(_dispatch, method, args)
            await ws.send(json.dumps({"type": "rpc_result", "id": msg.get("id"), "result": res}))
        elif mtype == "chat":
            await _handle_chat(ws, msg)
        elif mtype == "notebook":
            await _handle_notebook(ws, msg)
        else:
            await ws.send(json.dumps({"type": "error", "data": f"未知消息类型：{mtype}"}))


async def _handle_chat(ws, msg: dict) -> None:
    # 流式对话：agent.run 阻塞跑在线程池，deltas 经线程安全队列回推 WS。
    try:
        sampling = parse_sampling(msg.get("sampling"))
    except RuntimeError as exc:
        await ws.send(json.dumps({"type": "error", "data": str(exc)}))
        return
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def delta_sink(piece: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("token", piece))

    def think_sink(piece: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("think", piece))

    def status_sink(text: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("status", text))

    def run() -> None:
        try:
            def knowledge_sink(payload: dict) -> None:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    ("knowledge", json.dumps(payload, ensure_ascii=False)),
                )

            with HOST.turn_lock:
                answer = HOST.run_chat(
                    str(msg.get("text", "")),
                    msg.get("chips"),
                    delta_sink,
                    status_sink,
                    sampling,
                    think_sink,
                    str(msg.get("model_id") or ""),
                    bool(msg.get("knowledge")),
                    knowledge_sink,
                )
            loop.call_soon_threadsafe(queue.put_nowait, ("done", answer))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", f"{type(exc).__name__}: {exc}"))

    asyncio.get_running_loop().run_in_executor(None, run)
    while True:
        kind, data = await queue.get()
        await ws.send(json.dumps({"type": kind, "data": data}))
        if kind in ("done", "error"):
            break


async def _handle_notebook(ws, msg: dict) -> None:
    try:
        sampling = parse_sampling(msg.get("sampling"))
    except RuntimeError as exc:
        await ws.send(json.dumps({"type": "error", "data": str(exc)}))
        return
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def delta_sink(piece: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("token", piece))

    def status_sink(text: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("status", text))

    def run() -> None:
        try:
            with HOST.turn_lock:
                found = HOST.run_notebook(
                    str(msg.get("session_id") or ""),
                    str(msg.get("text") or ""),
                    msg.get("doc_ids") if isinstance(msg.get("doc_ids"), list) else [],
                    sampling,
                    delta_sink,
                    status_sink,
                )
            loop.call_soon_threadsafe(
                queue.put_nowait,
                ("done", json.dumps(found, ensure_ascii=False)),
            )
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", f"{type(exc).__name__}: {exc}"))

    asyncio.get_running_loop().run_in_executor(None, run)
    while True:
        kind, data = await queue.get()
        await ws.send(json.dumps({"type": kind, "data": data}, ensure_ascii=False))
        if kind in ("done", "error"):
            break


async def main() -> None:
    global TOKEN, HOST, SHUTDOWN
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, default="")
    args = parser.parse_args()
    TOKEN = args.token
    HOST = HeadlessApp()
    SHUTDOWN = asyncio.Event()
    asyncio.create_task(asyncio.to_thread(HOST.feishu_agent.autostart))
    try:
        async with serve(_handler, "127.0.0.1", args.port, process_request=_health):
            print(f"local_api ready on 127.0.0.1:{args.port}", flush=True)
            await SHUTDOWN.wait()
    finally:
        await asyncio.to_thread(HOST.feishu_agent.stop, False)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
