"""真实本地 WebSocket 与无头对话链路；模型和用户文件全部隔离。"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from atlas.testing import FakeLLM

from desk_companion import assistant, memory, state, usage
from desk_companion.local_api import server
from desk_companion.local_api.host import HeadlessApp


class LocalApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"DESK_COMPANION_DATA_DIR": str(root)}).start()
        patch.object(memory, "memory_path", return_value=root / "memory" / "chat.jsonl").start()
        patch.object(state, "state_path", return_value=root / "state.json").start()
        patch.object(usage, "usage_path", return_value=root / "usage.jsonl").start()
        self.host = HeadlessApp()
        from desk_companion.tasks import TaskManager
        self.host._tasks = TaskManager(self.host, command=[sys.executable, "-u", "-c", "exec(open('tests/worker_fixture.py', encoding='utf-8').read())"])
        self.addCleanup(self.host._tasks.shutdown)
        with patch.object(assistant, "require_llm_env", return_value={
            "ATLAS_API_KEY": "test-only", "ATLAS_BASE_URL": "http://example.invalid/v1", "ATLAS_MODEL": "fake",
        }):
            self.host.agent = assistant.build_agent(self.host)
        self.host.agent.llm = FakeLLM(["本地流式回归正常。"])
        self.host.agent.llm.sampling = None
        patch.object(self.host, "engage_model").start()
        patch.object(server, "HOST", self.host).start()
        patch.object(server, "TOKEN", "test-token").start()
        self.service = await serve(server._handler, "127.0.0.1", 0, process_request=server._health)
        self.addAsyncCleanup(self.stop_service)
        self.port = self.service.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}/ws?token=test-token"

    async def stop_service(self):
        self.service.close()
        await self.service.wait_closed()

    async def test_health_and_readonly_rpc(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
        self.assertIn(b"200 OK", response)
        async with connect(self.url, proxy=None) as ws:
            await ws.send(json.dumps({"type": "rpc", "id": "1", "method": "load_chat_log", "args": {}}))
            message = json.loads(await asyncio.wait_for(ws.recv(), 5))
        self.assertTrue(message["result"]["ok"])
        self.assertTrue(message["result"]["result"]["ok"])

    async def test_feishu_settings_rpc_reports_invalid_secret_without_echoing_it(self):
        with patch("desk_companion.feishu_agent._run_lark", side_effect=RuntimeError("invalid_client test-only-secret")):
            async with connect(self.url, proxy=None) as ws:
                await ws.send(json.dumps({"type": "rpc", "id": "feishu-check",
                    "method": "check_feishu_agent_connection", "args": {"profile": "test-profile"}}))
                raw = await asyncio.wait_for(ws.recv(), 5)
                message = json.loads(raw)
        self.assertTrue(message["result"]["ok"])
        self.assertFalse(message["result"]["result"]["ok"])
        self.assertIn("App Secret 无效", message["result"]["result"]["error"])
        self.assertNotIn("test-only-secret", raw)

    async def test_shutdown_requires_exact_authorization_and_only_signals_the_server(self):
        shutdown = asyncio.Event()
        async def request(auth):
            reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
            writer.write(("GET /shutdown HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n" + auth + "\r\n").encode())
            await writer.drain()
            result = await asyncio.wait_for(reader.read(), 5)
            writer.close()
            await writer.wait_closed()
            return result
        with patch.object(server, "SHUTDOWN", shutdown):
            self.assertIn(b"401", await request(""))
            self.assertIn(b"401", await request("Authorization: Bearer test-token-suffix\r\n"))
            self.assertFalse(shutdown.is_set())
            self.assertIn(b"200", await request("Authorization: Bearer test-token\r\n"))
            self.assertTrue(shutdown.is_set())

    async def test_chat_stream_persists_metadata_and_releases_busy_state(self):
        frames = []
        async with connect(self.url, proxy=None) as ws:
            await ws.send(json.dumps({"type": "chat", "text": "打个招呼", "chips": {},
                                     "sampling": {"reasoning_effort": "low", "temperature": 0.5, "top_p": 1}}))
            while True:
                frame = json.loads(await asyncio.wait_for(ws.recv(), 10))
                frames.append(frame)
                if frame["type"] in ("done", "error"):
                    break
        self.assertEqual(frames[-1], {"type": "done", "data": "本地流式回归正常。"})
        self.assertTrue(any(frame["type"] == "token" for frame in frames))
        rows = memory.list_chat(self.host.state.session_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["react_loops"], 2)
        self.assertGreater(rows[-1]["total_tokens"], 0)
        self.assertFalse(self.host._agent_running)
        self.assertIsNone(self.host.agent.llm.sampling)

    async def test_unknown_rpc_and_missing_sampling_report_errors(self):
        async with connect(self.url, proxy=None) as ws:
            await ws.send(json.dumps({"type": "rpc", "id": "bad", "method": "open_url"}))
            reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
            self.assertFalse(reply["result"]["ok"])
            await ws.send(json.dumps({"type": "chat", "text": "缺参数"}))
            reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
            self.assertEqual(reply["type"], "error")
        self.assertEqual(memory.list_chat(self.host.state.session_id), [])


if __name__ == "__main__":
    unittest.main()
