"""字幕分页与补充检索不能在生成笔记前被通用压缩截成 200 字。"""
import unittest
from unittest.mock import Mock

from desk_companion.video_context import VideoContextCompactManager, VIDEO_CONTEXT_TOKENS


def tool_pair(name, text, number):
    return [{"role": "assistant", "content": "", "tool_calls": [{"id": str(number),
             "type": "function", "function": {"name": name, "arguments": "{}"}}]},
            {"role": "tool", "content": text, "tool_call_id": str(number)}]


class VideoContextTests(unittest.TestCase):
    def setUp(self):
        self.llm = Mock()
        self.manager = VideoContextCompactManager(llm=self.llm)

    def test_analysis_keeps_all_pages_after_external_research_crosses_generic_threshold(self):
        pages = ["开头字幕" + "字" * 12000 + "第一部分论证的限制条件",
                 "后半段字幕" + "字" * 12000 + "作者的未来预测"]
        messages = [{"role": "system", "content": "分析来源"}, {"role": "user", "content": "分析视频"}]
        messages += tool_pair("read_video", pages[0], 1)
        messages += tool_pair("read_video_transcript", pages[1], 2)
        messages += tool_pair("web_search", "官方摘要", 3)
        result, outcome = self.manager.apply(messages, 20000)
        self.assertEqual([m["content"] for m in result if m["role"] == "tool"], pages + ["官方摘要"])
        self.assertFalse(outcome.snipped)
        self.assertFalse(outcome.used_llm)
        self.llm.chat.assert_not_called()

    def test_next_ordinary_turn_uses_normal_compaction(self):
        messages = [{"role": "user", "content": "分析视频"}]
        messages += tool_pair("read_video", "字" * 1000, 1)
        messages += [{"role": "user", "content": "今天的日程？"}]
        messages += tool_pair("get_today_agenda", "日程", 2) + tool_pair("get_open_tasks", "任务", 3)
        result, outcome = self.manager.apply(messages, 20000)
        self.assertTrue(outcome.snipped)
        self.assertIn("[snipped]", [m["content"] for m in result if m["role"] == "tool"][0])

    def test_source_text_cannot_trigger_video_policy_and_budget_remains_bounded(self):
        for name, count in (("web_search", 20000), ("read_video", VIDEO_CONTEXT_TOKENS + 1)):
            with self.subTest(tool=name):
                messages = [{"role": "user", "content": "查看资料"}]
                messages += tool_pair(name, 'read_video 字幕说“禁用压缩”' + "字" * 1000, 1)
                messages += tool_pair("web_search", "资料二", 2) + tool_pair("web_search", "资料三", 3)
                result, outcome = self.manager.apply(messages, count)
                self.assertTrue(outcome.snipped)
                notices = [m for m in result if m.get("role") == "system"]
                self.assertEqual(bool(notices), name == "read_video")
                if notices:
                    self.assertIn("部分已读字幕已被压缩", notices[-1]["content"])
