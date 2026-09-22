"""Spike B：最小本地后端服务。

验证目标（不接真实 Atlas，纯骨架）：
- 同一端口上提供 HTTP /health 健康检查 + WebSocket 流式对话。
- 只绑 127.0.0.1，带进程 token 校验，不对外暴露。
- 收到 {"type":"chat","text":...} 后逐字流式回 {"type":"token"...}，末尾 {"type":"done"}。

用法：python server.py --port 8770 --token <token>
"""
from __future__ import annotations

import argparse
import asyncio
import json

from websockets.asyncio.server import serve
from websockets.http11 import Response
from websockets.datastructures import Headers

TOKEN = ""


def _health(connection, request):
    # 非 WS 的普通 HTTP 请求走这里；/health 返回 200，其余 404
    if request.path == "/health":
        return connection.respond(200, "ok\n")
    if request.path.startswith("/ws"):
        return None  # 交给 WS 握手
    return connection.respond(404, "not found\n")


async def _handler(ws):
    # 简单 token 校验：query 里带 token
    if TOKEN and f"token={TOKEN}" not in (ws.request.path if ws.request else ""):
        await ws.close(code=4401, reason="bad token")
        return
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "data": "非法 JSON"}))
            continue
        if msg.get("type") != "chat":
            continue
        text = str(msg.get("text", ""))
        # 逐字流式回，模拟 LLM token 流
        reply = f"收到：{text}。这是 spike 的流式回显，用来验证 WS 实时性。"
        for ch in reply:
            await ws.send(json.dumps({"type": "token", "data": ch}))
            await asyncio.sleep(0.03)
        await ws.send(json.dumps({"type": "done"}))


async def main() -> None:
    global TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, default="")
    args = parser.parse_args()
    TOKEN = args.token

    async with serve(
        _handler, "127.0.0.1", args.port, process_request=_health
    ):
        print(f"spike backend ready on 127.0.0.1:{args.port}", flush=True)
        await asyncio.Future()  # 永久运行，等外部 kill


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
