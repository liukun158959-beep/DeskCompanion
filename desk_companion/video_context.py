"""视频阅读期间保留字幕证据，避免通用任务摘要提前抹掉原文。"""
from atlas.context.compact import CompactManager, CompactOutcome

VIDEO_CONTEXT_TOKENS = 64000
VIDEO_READ_TOOLS = {"read_video", "read_video_transcript"}


class VideoContextCompactManager(CompactManager):
    def apply(self, runtime_messages, token_count):
        # 只看本轮实际工具调用，不用链接文本或字幕中的“指令”触发。
        start = next((i for i in range(len(runtime_messages) - 1, -1, -1)
                      if runtime_messages[i].get("role") == "user"), len(runtime_messages))
        reading_video = any(
            call.get("function", {}).get("name") in VIDEO_READ_TOOLS
            for message in runtime_messages[start:] if message.get("role") == "assistant"
            for call in message.get("tool_calls", [])
        )
        if reading_video and token_count <= VIDEO_CONTEXT_TOKENS:
            return runtime_messages, CompactOutcome()
        messages, outcome = super().apply(runtime_messages, token_count)
        if reading_video and (outcome.snipped or outcome.used_llm):
            notice = ("视频证据超出本轮保留预算，部分已读字幕已被压缩，不能再声称完整保留或全面分析全片。"
                      "请明确说明分析覆盖的局限，并针对关键论点重新读取原文核实；超长视频建议按章节分次分析。")
            if outcome.summary:
                outcome.summary += "\n" + notice
            else:
                messages = [*messages, {"role": "system", "content": notice}]
        return messages, outcome
