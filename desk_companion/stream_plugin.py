"""把 Atlas 流式字推到头顶气泡。"""
from __future__ import annotations

from dataclasses import dataclass

from atlas.core.plugin import BasePlugin

TOOL_STATUS = {
    "get_today_agenda": "在看今天的日程…",
    "get_open_tasks": "在看未完成的待办…",
    "create_calendar_event": "在创建日程…",
    "web_search": "博士，正在搜索网络来源，核实最新信息。",
    "remember_fact": "博士，正在保存你明确要求记住的内容。",
    "forget_fact": "博士，正在删除你指定的记忆。",
    "github_recent": "博士，正在读取仓库最近的提交。",
    "github_status": "博士，正在检查 GitHub 连接和仓库。",
    "github_roadmap": "博士，正在读取仓库的路线图。",
    "read_skill": "博士，正在查阅这项任务的操作规程。",
    "list_skills": "博士，正在检查可用技能。",
    "read_recent_errors": "博士，正在检查最近的错误日志。",
    "get_arknights_skland": "博士，正在读取理智和周玉记录。",
    "get_arknights_operator": "博士，正在查询干员培养进度。",
    "get_arknights_today_plan": "博士，正在核对今天的刷图计划。",
    "start_arknights_daily": "博士，正在向 MAA 下达日常任务。",
    "stop_arknights_daily": "博士，正在停止 MAA 当前动作。",
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
