"""飞书通道离线回归：真实 Agent 工具循环与 CLI 子进程协议，全部临时数据。"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from atlas.testing import FakeLLM
from desk_companion import assistant, memory, logutil
from desk_companion.feishu_agent import EVENT_KEY, FeishuAgent, Inbox, accepted, chunks
from desk_companion.local_api.host import HeadlessApp
from desk_companion.local_api import server

BINDING = {"profile": "test-profile", "app_id": "test-app", "app_name": "测试机器人",
           "owner_id": "ou_owner", "owner_name": "测试用户"}


def event(message="om_1", text="打个招呼", **changes):
    result = {"type": EVENT_KEY, "sender_type": "user", "sender_id": "ou_owner", "chat_type": "p2p",
              "message_id": message, "chat_id": "oc_private", "content": text, "message_type": "text",
              "create_time": str(int(time.time() * 1000))}
    return {**result, **changes}


class FeishuAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"DESK_COMPANION_DATA_DIR": str(self.root)}).start()
        patch.object(logutil, "LOG_PATH", self.root / "desk_companion.log").start()
        self.host = Mock()
        self.host.run_channel_chat.return_value = "你好。"
        self.gateway = FeishuAgent(self.host)
        self.gateway._binding = BINDING.copy()
        self.gateway._inbox = Inbox(self.root / "inbox.sqlite3")
        self.addCleanup(self.gateway.stop, False)

    def queue(self, payload=None):
        self.gateway._inbox.add("test-app", payload or event())
        return self.gateway._inbox.take("test-app")

    def test_only_fresh_owner_private_messages_are_accepted(self):
        self.assertTrue(accepted(event(), "ou_owner"))
        for changes in ({"sender_id": "ou_intruder"}, {"sender_type": "bot"}, {"chat_type": "group"},
                        {"message_id": ""}, {"chat_id": ""}, {"create_time": "garbage"},
                        {"create_time": "1"}, {"type": "other.event"}):
            self.assertFalse(accepted(event(**changes), "ou_owner"), changes)
        self.assertFalse(accepted({"schema": "2.0", "event": event()}, "ou_owner"))

    def test_message_id_deduplicates_across_restart_and_event_ids(self):
        inbox = self.gateway._inbox
        self.assertTrue(inbox.add("test-app", event(event_id="delivery1")))
        restarted = Inbox(inbox.path)
        self.assertFalse(restarted.add("test-app", event(event_id="delivery2")))
        self.assertTrue(restarted.add("other-app", event()))
        sid = inbox.session("test-app", "oc_private", "ou_owner")
        self.assertEqual(restarted.session("test-app", "oc_private", "ou_owner"), sid)
        self.assertNotEqual(restarted.session("other-app", "oc_private", "ou_owner"), sid)

    def test_interrupted_tools_are_not_reexecuted_and_old_pending_messages_expire(self):
        self.queue()
        inbox = self.gateway._inbox
        inbox.recover("test-app")
        row = inbox.take("test-app")
        self.assertEqual(row["state"], "answered")
        self.assertIn("避免重复执行", row["answer"])
        inbox.update("test-app", row["id"], state="sent")
        inbox.add("test-app", event("om_old"))
        with inbox.connect() as db:
            db.execute("UPDATE messages SET updated=? WHERE id='om_old'", (time.time() - 700,))
        self.assertIsNone(inbox.take("test-app"))

    def test_partial_reply_retries_only_unsent_chunks_without_rerunning_agent(self):
        self.host.run_channel_chat.return_value = "字" * 7200
        row = self.queue()
        calls = []
        def send(args):
            calls.append(args)
            if len(calls) == 2:
                raise RuntimeError("network")
            return '{"ok":true,"identity":"bot","data":{}}'
        with patch("desk_companion.feishu_agent._run_lark", side_effect=send):
            with self.assertRaises(RuntimeError):
                self.gateway.process_message(row)
            retry = self.gateway._inbox.take("test-app")
            self.assertEqual(retry["state"], "answered")
            self.assertEqual(retry["sent"], 1)
            self.gateway.process_message(retry)
        self.host.run_channel_chat.assert_called_once()
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[1][-1], calls[2][-1])
        self.assertNotEqual(calls[0][-1], calls[1][-1])
        self.assertTrue(all("--as" in args and args[args.index("--as") + 1] == "bot" for args in calls))
        self.assertIsNone(self.gateway._inbox.take("test-app"))
        self.assertEqual("".join(chunks("😀" * 9000)), "😀" * 9000)

    def test_new_skill_knowledge_and_mcp_commands_reach_expected_capabilities(self):
        original = self.gateway._inbox.session("test-app", "oc_private", "ou_owner")
        def command(text):
            return self.gateway._answer({"app": "test-app", "chat": "oc_private", "sender": "ou_owner", "kind": "text", "content": text})
        self.assertIn("旧历史", command("/new"))
        self.assertNotEqual(original, self.gateway._inbox.session("test-app", "oc_private", "ou_owner"))
        command("/skill weekly-retro 整理本周工作")
        self.assertEqual(self.host.run_channel_chat.call_args.args[2], {"skills": ["weekly-retro"]})
        command("/kb\n有哪些准备事项")
        self.assertTrue(self.host.run_channel_chat.call_args.args[3])
        command("/mcp weather/get_weather 北京天气")
        self.assertEqual(self.host.run_channel_chat.call_args.args[2], {"mcp": [{"server": "weather", "tool": "get_weather"}]})
        calls = self.host.run_channel_chat.call_count
        self.assertIn("用法", command("/skill"))
        self.assertEqual(self.host.run_channel_chat.call_count, calls)

    def test_cli_ready_ndjson_duplicate_filter_and_graceful_stdin_close(self):
        stub = self.root / "cli_stub.py"
        events = [event(sender_id="ou_intruder"), event(chat_type="group"), event(sender_type="bot"), event(), event(event_id="duplicate")]
        stub.write_text("import sys, json\nprint('[event] ready event_key=im.message.receive_v1', file=sys.stderr, flush=True)\n"
                        + f"events=json.loads({json.dumps(json.dumps(events, ensure_ascii=False), ensure_ascii=False)})\n"
                        + "for value in events: print(json.dumps(value), flush=True)\nsys.stdin.read()\n", encoding="utf-8")
        replied = threading.Event()
        def reply(_args):
            replied.set()
            return '{"ok":true,"data":{}}'
        with patch("desk_companion.feishu_agent.identify", return_value=BINDING.copy()), \
             patch("desk_companion.feishu_agent._lark_cmd", return_value=[sys.executable, str(stub)]), \
             patch("desk_companion.feishu_agent._run_lark", side_effect=reply):
            self.gateway.enable()
            self.assertTrue(replied.wait(5))
            self.assertTrue(self.gateway.status()["connected"])
            process = self.gateway._process
            self.gateway.stop()
            self.assertEqual(process.poll(), 0)
        self.host.run_channel_chat.assert_called_once()
        saved = json.loads((self.root / "feishu_agent.json").read_text(encoding="utf-8"))
        self.assertFalse(saved["enabled"])
        self.assertNotIn("secret", saved)

    def test_remote_connection_failure_is_visible_and_does_not_run_agent(self):
        done = threading.Event()
        process = SimpleNamespace(stderr=io.StringIO(json.dumps({"ok": False, "error": {
            "type": "validation", "subtype": "failed_precondition", "message": "remote exists"}}, indent=2)))
        self.gateway._stderr(process, done)
        self.assertTrue(done.is_set())
        self.assertFalse(self.gateway.status()["connected"])
        self.assertIn("本机 CLI 无法远程停止", self.gateway.status()["error"])
        self.host.run_channel_chat.assert_not_called()

    def test_real_agent_tool_loop_and_history_do_not_expose_desktop_context(self):
        host = HeadlessApp()
        desktop = host.state.session_id
        memory.append_chat("user", "仅在桌面保存的内容", desktop)
        with patch.object(assistant, "require_llm_env", return_value={"ATLAS_API_KEY": "test-only",
                "ATLAS_BASE_URL": "http://example.invalid/v1", "ATLAS_MODEL": "fake"}):
            host.agent = assistant.build_agent(host)
        tool = Mock(return_value="离线工具结果")
        host.agent.tools.register(name="channel_lookup", description="离线查询", parameters={"type": "object", "properties": {}}, func=tool, isReadOnly=True)
        seen = []
        def tool_turn(messages, tools):
            seen.append(json.dumps(messages, ensure_ascii=False))
            return {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function",
                     "function": {"name": "channel_lookup", "arguments": "{}"}}]}
        host.agent.llm = FakeLLM([tool_turn, "工具查询已完成。"])
        self.gateway.host = host
        with patch.object(host, "engage_model"), patch("desk_companion.feishu_agent._run_lark", return_value='{"ok":true,"data":{}}'):
            self.gateway.process_message(self.queue())
        tool.assert_called_once()
        self.assertNotIn("仅在桌面保存的内容", seen[0])
        self.assertEqual(host.state.session_id, desktop)
        self.assertEqual(json.loads((self.root / "user_state.json").read_text(encoding="utf-8"))["session_id"], desktop)
        remote = self.gateway._inbox.session("test-app", "oc_private", "ou_owner")
        self.assertEqual(memory.list_chat(remote)[-1]["react_loops"], 2)
        self.assertEqual(len(memory.list_chat(desktop)), 1)
        self.assertFalse(host._agent_running)

    def test_rpc_waits_until_remote_turn_restores_desktop_session(self):
        host = HeadlessApp()
        desktop = host.state.session_id
        started, release, read_done = threading.Event(), threading.Event(), threading.Event()
        result = {}
        def run(*_args, **_kwargs):
            started.set()
            self.assertTrue(release.wait(3))
            return "远程回答"
        def read():
            result.update(server._dispatch("load_chat_log", {}))
            read_done.set()
        with patch.object(host, "run_chat", side_effect=run), patch.object(server, "HOST", host):
            remote = threading.Thread(target=host.run_channel_chat, args=("远程问题", "feishu-test", {}))
            remote.start()
            self.assertTrue(started.wait(2))
            reader = threading.Thread(target=read)
            reader.start()
            try:
                self.assertFalse(read_done.wait(.1))
            finally:
                release.set()
                remote.join(3)
                reader.join(3)
        self.assertTrue(read_done.is_set())
        self.assertEqual(result["result"]["session_id"], desktop)


if __name__ == "__main__":
    unittest.main()
