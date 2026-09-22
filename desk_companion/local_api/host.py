"""P1：本地 API 的无头 host。

复用 App 的全部数据方法（board_*/list_* 等），但不加载皮肤、不建窗口。
流式回调（ui/on_llm_delta/on_stream_status）在无头下改为同步执行 + 推给 WS sink，
不再走 pywebview 窗口队列。
"""
from __future__ import annotations

import uuid
from typing import Callable

from ..app import App
from ..assistant import inject_history
from ..memory import append_chat


class HeadlessApp(App):
    """本地 API 后端用的无头 App：数据方法照用，UI 回调改道。"""

    def __init__(self) -> None:
        super().__init__(skin_id="", headless=True)
        # 当前 WS 流式回调，send_* 期间由 server 设置；None 表示无活跃流
        self._delta_sink: Callable[[str], None] | None = None
        self._status_sink: Callable[[str], None] | None = None

    def ui(self, fn) -> None:
        # 无头：没有窗口队列，直接同步执行
        fn()

    def on_llm_delta(self, piece: str) -> None:
        if self._delta_sink is not None:
            self._delta_sink(piece)

    def on_stream_status(self, text: str) -> None:
        if self._status_sink is not None:
            self._status_sink(text)

    def run_chat(
        self,
        text: str,
        chips: dict | None,
        delta_sink: Callable[[str], None],
        status_sink: Callable[[str], None],
    ) -> str:
        """无头流式对话：复用 _compose_turn + agent.run + 流式 sink，不碰窗口。

        deltas 经 BubbleStreamPlugin -> host.ui -> on_llm_delta -> delta_sink 推给 WS。
        返回最终答案字符串，失败抛异常由 server 转成 error 帧。
        """
        if self._agent_running:
            raise RuntimeError("凯尔希正在说话，等这句说完再发。")
        if self.agent is None:
            self.try_build_agent()
            if self.agent is None:
                raise RuntimeError(
                    self._agent_error or "还没接上模型。在设置里填写 API 地址、模型名和 Key。"
                )
        message = self._compose_turn(text, chips or {})
        self._delta_sink = delta_sink
        self._status_sink = status_sink
        self._agent_running = True
        run_id = str(uuid.uuid4())
        try:
            append_chat("user", message, self.state.session_id)
            inject_history(
                self.agent,
                self.state.history_n,
                self.state.session_id,
                exclude_user=message,
            )
            answer = str(self.agent.run(message, run_id=run_id))
            self._record_usage(self.agent, run_id)
            append_chat("pet", answer, self.state.session_id)
            return answer
        finally:
            self._agent_running = False
            self._delta_sink = None
            self._status_sink = None
