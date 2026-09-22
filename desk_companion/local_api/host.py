"""P1：本地 API 的无头 host。

复用 App 的全部数据方法（board_*/list_* 等），但不加载皮肤、不建窗口。
流式回调（ui/on_llm_delta/on_stream_status）在无头下改为同步执行 + 推给 WS sink，
不再走 pywebview 窗口队列。
"""
from __future__ import annotations

from typing import Callable

from ..app import App


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
