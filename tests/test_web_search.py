"""搜索临时故障恢复与真实工具失败记录，全部离线。"""
import io
import json
import ssl
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from atlas.testing import FakeLLM
from desk_companion import assistant, web_search

CFG = {"ATLAS_API_KEY": "test-secret", "ATLAS_BASE_URL": "https://example.invalid/v1", "ATLAS_MODEL": "fake"}
GOOD = {"results": [{"title": "天气来源", "link": "https://example.invalid/weather", "snippet": "晴"}]}


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("desk_companion.envconf.require_llm_env", return_value=CFG).start()
        self.sleep = patch.object(web_search.time, "sleep").start()
        self.urlopen = patch.object(web_search.urllib.request, "urlopen").start()

    def test_tls_timeout_retries_and_returns_real_sources(self):
        self.urlopen.side_effect = [urllib.error.URLError(TimeoutError("TLS handshake timed out")), response(GOOD)]
        statuses = []
        result = web_search.web_search({"query": "苏州天气"}, on_status=statuses.append)
        self.assertIn("天气来源", result)
        self.assertEqual(self.urlopen.call_count, 2)
        self.assertEqual(len(statuses), 1)
        self.assertIn("重试", statuses[0])
        self.assertTrue(all(call.kwargs["timeout"] <= 30 for call in self.urlopen.call_args_list))

    def test_upstream_timeout_inside_http_success_retries_once(self):
        self.urlopen.side_effect = [response({"error": "upstream TLS handshake timeout"}), response(GOOD)]
        self.assertIn("天气来源", web_search.web_search({"query": "苏州天气"}))
        self.assertEqual(self.urlopen.call_count, 2)

    def test_permissions_certificate_and_empty_results_do_not_retry(self):
        failures = [urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO(b'{}')),
                    urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")),
                    response({"results": []}),
                    response({"error": "invalid_client request timeout"})]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                self.urlopen.reset_mock(side_effect=True)
                if isinstance(failure, Exception):
                    self.urlopen.side_effect = failure
                else:
                    self.urlopen.return_value = failure
                with self.assertRaises(RuntimeError):
                    web_search.web_search({"query": "苏州天气"})
                self.assertEqual(self.urlopen.call_count, 1)

    def test_retry_uses_remaining_budget_and_stops_when_exhausted(self):
        self.urlopen.side_effect = [urllib.error.URLError(TimeoutError("timeout")), response(GOOD)]
        with patch.object(web_search.time, "monotonic", side_effect=[0, 0, 29, 59]):
            self.assertEqual(web_search._post(CFG["ATLAS_BASE_URL"], "test", "weather"), GOOD)
        self.assertEqual([c.kwargs["timeout"] for c in self.urlopen.call_args_list], [30, 1])
        self.urlopen.reset_mock()
        self.urlopen.side_effect = urllib.error.URLError(TimeoutError("timeout"))
        with patch.object(web_search.time, "monotonic", side_effect=[0, 0, 60]):
            with self.assertRaises(RuntimeError):
                web_search._post(CFG["ATLAS_BASE_URL"], "test", "weather")
        self.assertEqual(self.urlopen.call_count, 1)

    def test_exhausted_search_is_failed_in_atlas_tool_record(self):
        self.urlopen.side_effect = urllib.error.URLError(TimeoutError("TLS handshake timed out test-secret"))
        statuses = []
        host = SimpleNamespace(state=SimpleNamespace(persona="你是凯尔希。", max_steps=8),
                               ui=lambda fn: fn(), on_llm_delta=lambda _: None, on_stream_status=statuses.append)
        with patch.object(assistant, "require_llm_env", return_value=CFG):
            agent = assistant.build_agent(host)
        agent.llm = FakeLLM([{"role": "assistant", "content": "", "tool_calls": [{"id": "s1", "type": "function",
            "function": {"name": "web_search", "arguments": '{"query":"苏州天气"}'}}]}, "搜索失败，请稍后再试。"])
        agent.run("苏州天气", run_id="search-failure")
        events = agent.journal.get_events("search-failure")
        tool = [e for e in events if e.event_type == "tool_after_call"][-1]
        self.assertEqual(tool.payload["status"], "failed")
        self.assertNotIn("test-secret", tool.payload["result"]["output"])
        self.assertEqual(self.urlopen.call_count, 2)
        self.assertTrue(any("重试" in text for text in statuses))


if __name__ == "__main__":
    unittest.main()
