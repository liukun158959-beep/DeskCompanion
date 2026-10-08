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
from desk_companion.feishu_agent import EVENT_KEY, FeishuAgent, Inbox, accepted, chunks, identify
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

    def test_quitting_during_identity_check_does_not_spawn_a_new_listener(self):
        started, release = threading.Event(), threading.Event()
        failures = []
        def identity():
            started.set()
            release.wait(3)
            return BINDING.copy()
        def enable():
            try:
                self.gateway.enable()
            except RuntimeError as exc:
                failures.append(str(exc))
        with patch("desk_companion.feishu_agent.identify", side_effect=identity), \
             patch("desk_companion.feishu_agent._lark_cmd") as spawn:
            opening = threading.Thread(target=enable)
            opening.start()
            self.assertTrue(started.wait(2))
            closing = threading.Thread(target=self.gateway.stop, args=(False,))
            closing.start()
            self.assertTrue(self.gateway._closing.wait(2))
            release.set()
            opening.join(3)
            closing.join(3)
            spawn.assert_not_called()
        self.assertTrue(failures)
        self.assertFalse((self.root / "feishu_agent.json").exists())

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

    def test_settings_persist_without_switching_default_profile_and_rebind_is_explicit(self):
        self.gateway._save(False)
        profiles = {"ok": True, "profiles": [{"name": "dedicated"}, {"name": "test-profile"}]}
        with patch.object(self.gateway, "profiles", return_value=profiles), patch("desk_companion.feishu_agent._run_lark") as cli:
            result = self.gateway.save_settings("dedicated", False, False, 5, 60)
            cli.assert_not_called()
        self.assertEqual(result["binding"], {})
        fresh = FeishuAgent(self.host)
        self.assertEqual(fresh.settings(), {"profile": "dedicated", "auto_start": False,
            "auto_reconnect": False, "retry_min": 5, "retry_max": 60})
        fresh._binding = BINDING.copy()
        fresh._save(True)
        self.assertEqual(fresh.settings()["retry_max"], 60)
        with patch.object(fresh, "enable") as enable:
            fresh.autostart()
            enable.assert_not_called()

    def test_invalid_settings_and_changes_while_listening_are_rejected(self):
        for low, high in ((0, 30), (30, 2), (2, 301), (True, 30), (2.5, 30)):
            with self.assertRaises(RuntimeError):
                self.gateway.save_settings("test-profile", True, True, low, high)
        self.gateway._supervisor = Mock()
        self.gateway._supervisor.is_alive.return_value = True
        with self.assertRaisesRegex(RuntimeError, "先停止"):
            self.gateway.save_settings("test-profile", True, True, 2, 30)
        self.gateway._supervisor = None

    def test_credential_update_uses_stdin_same_named_profile_and_redacts_errors(self):
        profiles = {"profiles": [{"name": "test-profile", "appId": "test-app", "brand": "feishu"}]}
        with patch.object(self.gateway, "profiles", return_value=profiles), \
             patch("desk_companion.feishu_agent._run_lark", return_value="{}") as cli:
            self.assertTrue(self.gateway.update_credentials("test-profile", "test-only-secret")["ok"])
            args, kwargs = cli.call_args
            self.assertNotIn("test-only-secret", args[0])
            self.assertEqual(kwargs["stdin"], "test-only-secret\n")
            self.assertIn("--name", args[0])
            self.assertNotIn("--use", args[0])
        with patch.object(self.gateway, "profiles", return_value=profiles), \
             patch("desk_companion.feishu_agent._run_lark", side_effect=RuntimeError("test-only-secret")):
            with self.assertRaises(RuntimeError) as failure:
                self.gateway.update_credentials("test-profile", "test-only-secret")
            self.assertNotIn("test-only-secret", str(failure.exception))
        self.assertFalse((self.root / "feishu_agent.json").exists())

    def test_hermes_environment_allows_only_existing_profile_secret_update(self):
        profiles = {"profiles": [{"name": "test-profile", "appId": "test-app", "brand": "feishu"}]}
        with patch.dict(os.environ, {"HERMES_HOME": "test-hermes-home"}), \
             patch.object(self.gateway, "profiles", return_value=profiles), \
             patch("desk_companion.feishu_agent._run_lark", return_value="{}") as cli:
            self.gateway.update_credentials("test-profile", "test-only-secret")
            command = cli.call_args.args[0]
            self.assertIn("--force-init", command)
            self.assertEqual(command[:2], ["--profile", "test-profile"])
            self.assertEqual(command[command.index("--name") + 1], "test-profile")
            self.assertEqual(command[command.index("--app-id") + 1], "test-app")
            self.assertNotIn("--new", command)
            self.assertNotIn("--use", command)
            self.assertEqual(os.environ["HERMES_HOME"], "test-hermes-home")
            cli.reset_mock()
            with self.assertRaisesRegex(RuntimeError, "不存在"):
                self.gateway.update_credentials("unknown", "test-only-secret")
            cli.assert_not_called()

    def test_invalid_secret_after_cli_save_has_actionable_redacted_error(self):
        profiles = {"profiles": [{"name": "test-profile", "appId": "test-app", "brand": "feishu"}]}
        with patch.object(self.gateway, "profiles", return_value=profiles), \
             patch("desk_companion.feishu_agent._run_lark", side_effect=["", RuntimeError("invalid_client test-only-secret")]):
            with self.assertRaisesRegex(RuntimeError, "飞书校验未通过") as failure:
                self.gateway.update_credentials("test-profile", "test-only-secret")
            self.assertNotIn("test-only-secret", str(failure.exception))

    def test_connection_check_distinguishes_remote_occupancy_and_invalid_credentials(self):
        for count, running in ((0, False), (1, False), (1, True)):
            replies = [json.dumps({"ok": True, "data": {"online_instance_cnt": count}}),
                       json.dumps({"apps": [{"running": running}]})]
            with patch("desk_companion.feishu_agent._run_lark", side_effect=replies) as cli:
                result = self.gateway.check_connection("test-profile")
                self.assertTrue(result["ok"])
                self.assertEqual(result["count"], count)
                self.assertEqual(result["local_running"], running)
                self.assertEqual(cli.call_args_list[0].args[0][:2], ["--profile", "test-profile"])
        with patch("desk_companion.feishu_agent._run_lark", side_effect=RuntimeError("invalid_client test-only-secret")):
            result = self.gateway.check_connection("test-profile")
            self.assertFalse(result["ok"])
            self.assertIn("App Secret 无效", result["error"])
            self.assertNotIn("test-only-secret", result["error"])

    def test_identity_uses_selected_profile_and_not_the_global_default(self):
        values = [{"profile": "dedicated", "appId": "test-app"}, {"appId": "test-app", "identities": {
            "bot": {"available": True, "verified": True}, "user": {"available": True, "openId": "ou_owner"}}}]
        with patch("desk_companion.feishu_agent._run_lark", side_effect=[json.dumps(row) for row in values]) as cli:
            self.assertEqual(identify("dedicated")["profile"], "dedicated")
            self.assertTrue(all(call.args[0][:2] == ["--profile", "dedicated"] for call in cli.call_args_list))

    def test_network_retry_uses_saved_interval_and_can_be_disabled(self):
        stub = self.root / "network_exit.py"
        stub.write_text("import sys\nsys.exit(4)\n", encoding="utf-8")
        for reconnect in (True, False):
            with self.subTest(reconnect=reconnect):
                gateway = FeishuAgent(self.host)
                (self.root / "feishu_agent.json").write_text(json.dumps({"profile": "test-profile",
                    "auto_reconnect": reconnect, "retry_min": 7, "retry_max": 60}), encoding="utf-8")
                with patch("desk_companion.feishu_agent.identify", return_value=BINDING.copy()), \
                     patch("desk_companion.feishu_agent._lark_cmd", return_value=[sys.executable, str(stub)]), \
                     patch.object(gateway._stop, "wait", return_value=True) as wait:
                    try:
                        gateway.enable()
                        gateway._supervisor.join(3)
                        self.assertFalse(gateway._supervisor.is_alive())
                        if reconnect:
                            wait.assert_called_once_with(7)
                        else:
                            wait.assert_not_called()
                            self.assertIn("自动重连已关闭", gateway.status()["error"])
                    finally:
                        gateway.stop(False)


if __name__ == "__main__":
    unittest.main()
