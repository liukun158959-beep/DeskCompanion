# V11 实施计划：崩溃防御、头顶说话气泡、Atlas 同步流式

> grill-me 对齐后冻结。2026-08-14。

## 0. 决策

| 项 | 选择 |
|----|------|
| 防御 | 点宠物 / WebView 失败只记日志，不 `os._exit`。on_ready 失败也 `mark_ready`，让宠物留着 |
| 气泡 | 头顶漫画泡，三角指向帽子；跟着头走。历史在泡内滚，底栏输入 |
| 流式 | Atlas 保持同步。`LLM.chat(..., on_delta=)` 走 `stream=True`。循环 `emit("llm_delta")`。`Agent.run()` 不变。工具轮不把 JSON 当字；`on_tool_before_call` 显示「在查…」 |

对照：OpenPets 是头上短气泡；OpenAI Agents SDK 是 `run_streamed` 事件流。Atlas 已有同步循环 + 插件，接 `on_llm_delta`，不改成 asyncio。

## 1. Atlas

1. `LLM.chat` 增加可选 `on_delta`。有则 `stream=True`，拼完整 message 再返回；content 增量调 `on_delta`；tool_calls 只拼不回调。
2. `AgentLoop` 每次 `chat` 传入 `on_delta` → `plugin_manager.emit("llm_delta")`，**不写 Journal**（避免每字一条）。
3. `BasePlugin.on_llm_delta` 空实现。不改 Protocol，以免旧插件 `isinstance` 失败。
4. `FakeLLM` / `LoopingFakeLLM` 接受 `on_delta`，有正文则回调一次。

## 2. desk-companion

1. `on_pet_click` / `_eval_bubble` 捕获 WebView 异常，不 crash。
2. `on_ready` 失败：弹窗 + 日志 + `mark_ready`，不杀进程。
3. `pet.head_anchor()`：身体不透明区顶边中点。
4. `_place_card`：优先头上方，`data-tail=down`；上方不够再左右，三角仍朝头。
5. 插件 `BubbleStreamPlugin`：delta 推气泡；工具前写「在查…」。流式中纯文本，结束再 Markdown。

## 3. 不做

不把 Atlas 改成 async。不把每字写入 Journal。不新画过渡帧。
