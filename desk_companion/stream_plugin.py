"""把 Atlas 流式字推到头顶气泡。"""
from __future__ import annotations

from dataclasses import dataclass

from atlas.core.plugin import BasePlugin

TOOL_STATUS = {
    "get_today_agenda": "在看今天的日程…",
    "get_open_tasks": "在看未完成的待办…",
}


@dataclass
class BubbleStreamPlugin(BasePlugin):
    host: object
    name: str = "desk_bubble_stream"
    priority: int = 40

    def on_llm_delta(self, *, run_id: str, turn_idx: int, delta: str) -> None:
        piece = delta
        self.host.ui(lambda: self.host.on_llm_delta(piece))

    def on_tool_before_call(
        self,
        *,
        run_id: str,
        turn_idx: int,
        step_id: str,
        tool_name: str,
        input: dict,
    ) -> None:
        text = TOOL_STATUS.get(tool_name, f"在用 {tool_name}…")
        self.host.ui(lambda: self.host.on_stream_status(text))
