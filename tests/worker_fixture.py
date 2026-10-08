"""仅离线测试启动：真实 worker/Atlas 循环，模型脚本在子进程内注入。"""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from atlas.testing import FakeLLM
from desk_companion import assistant, model_catalog
from desk_companion.task_worker import main
from desk_companion.paths import data_root

original = assistant.build_agent

def build(host):
    agent = original(host)
    def query(messages, tools):
        (data_root() / "seen.json").write_text(__import__('json').dumps(messages, ensure_ascii=False), "utf-8")
        return {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function",
                "function": {"name": "channel_write" if "写入测试" in messages[-1].get("content", "") else "channel_lookup", "arguments": "{}"}}]}
    def lookup(args):
        (data_root() / "tool_called").write_text("1", "utf-8")
        return "离线工具结果"
    agent.tools.register(name="channel_lookup", description="离线查询", parameters={"type":"object","properties":{}},
                         func=lookup, isReadOnly=True)
    def write(args):
        path = data_root() / "write_count"
        value = int(path.read_text("utf-8")) if path.exists() else 0
        path.write_text(str(value + 1), "utf-8")
        return "已完成测试写入"
    agent.tools.register(name="channel_write", description="离线写入测试", parameters={"type":"object","properties":{}},
                         func=write, retry_max=0)
    agent.llm = FakeLLM([query, "本地流式回归正常。"])
    agent.llm.client = SimpleNamespace(with_options=lambda **kw: SimpleNamespace())
    return agent

with patch.object(assistant, "require_llm_env", return_value={"ATLAS_API_KEY":"test-only",
        "ATLAS_BASE_URL":"http://example.invalid/v1", "ATLAS_MODEL":"fake"}), \
     patch.object(assistant, "build_agent", build), patch.object(model_catalog, "bind_llm"), \
     patch.object(model_catalog, "require_active", return_value={"model":"fake"}):
    main()
