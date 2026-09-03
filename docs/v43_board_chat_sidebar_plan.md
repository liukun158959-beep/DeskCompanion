# V43：看板改为对话工作台（侧边栏 + 新 session）

> 2026-09-03。GitHub #18。复盘进对话、飞书文档选改/新建已对齐。开工。

## 0. 问题

**When** 作者打开看板要跟凯尔希干活（问今日、带上某份技能、对着某个已连仓库说话、下令开游戏/清日常、写本周复盘并落到一篇飞书文档）  
**I want** 看板本身就是对话工作台：能发消息、能开新线程、输入时能点选已有 skill / CLI / 仓 / 方舟动作；复盘在对话里生成，并选已有飞书文档覆盖或指定标题新建；记忆人设技能不再跟「今日」平级抢顶栏  
**so I can** 不用在十个顶栏 tab 和头顶气泡之间找入口，也不用「清空对话」才能换话题，更不用先生成再去今日页点写入

现状替代：对话页只读 `memory/chat.jsonl`（V12 规定不在看板里发消息）；复盘在今日页两按钮，写入永远新建一篇。

## 1. 非目标

- 不另建工具总表 / 插件市场 / 任意 shell。
- 不新增 MAA 能力；方舟 chips 走现有开游戏 / 清日常 / 同步森空岛 / 今天刷什么。勾选仍是同一份。
- 不把「清空对话」当成新 session。
- 不砍气泡：气泡继续说**当前** session。看板发消息不强制弹出气泡。
- 不做云同步 session、多用户。
- 不开 V25 活动商店 / 企鹅、#8 UAC、#9 会前打断、#10 判断层。
- 不把清日常状态小窗搬进看板。
- 不用 `overwrite` 以外的 block 补丁编辑飞书文档；复盘是整篇替换。不搜知识库 Wiki、不改 sheet/bitable。

## 2. Must（≤3）

1. **看板能对话，且能开新 session。** 新 session = 新线程，旧线程留在历史。气泡与看板共用当前 session。
2. **输入框能为本轮点选上下文 / 动作。** skill、已注册 `lark-cli`/`gh` 工具、GitHub 已列出仓、已有方舟动作。复盘生成与飞书落盘在对话里完成（子界面 + 同一套确定性函数）。
3. **功能进侧边栏；记忆 / 历史 / 人设 / 技能 / 复盘是对话子界面。** 侧边栏：今日、对话、方舟、GitHub、飞书、日志、模型、用量。日志仍隐蔽标红。

## 3. 拍板

| 项 | 选择 |
|----|------|
| 对话从哪发 | 看板输入框发送，走现有 Agent。失败原文与气泡同一套。流式同时写看板和（若已打开的）气泡 |
| session | `chat.jsonl` 每条 `session_id`；`user_state.session_id` 为当前。旧行没有该字段时一次性打上当前 id 后写回，不删文件 |
| 气泡 | 只加载当前 session。切 session 后气泡历史跟着换。看板发送不 `show_bubble` |
| skill chip | 本轮必须 `read_skill(<id>)` |
| CLI chip | 已注册工具：`get_today_agenda`、`get_open_tasks`、`github_status`、`github_recent`、`github_roadmap`。禁止自由输入命令。选了 recent/roadmap 必须同时选仓 |
| GitHub chip | `list_owned_repos()` 同一套未归档仓 |
| 方舟 chip | 点选即走现有实现，不经模型。不可与 skill/CLI 同时选 |
| 复盘 | 对话子界面：生成仍用现有 `generate_week_review`（读 `weekly-retro`，不带工具）。今日页去掉生成/写入按钮，只读已落盘正文 |
| 飞书文档 | 获取：`drive +search --query "" --as user --created-by-me --doc-types docx --sort edit_time --page-size 20`。选中一篇：`docs +update --command overwrite --doc-format markdown`。新建：标题必填，走现有 `docs +create`。没选文档且没填标题 → 失败可见，不默默新建 |
| 侧边栏 | 今日、对话、明日方舟、GitHub、飞书、日志、模型、用量 |
| 对话子界面 | 当前会话、历史、记忆、人设、技能、复盘 |

## 4. 验收

- Given 打开看板对话，When 输入一句并发送，Then 看板出现这轮问答并写入当前 session；气泡若打开则同步。不强制弹出气泡。
- Given 当前 session 已有几句，When 点「新对话」，Then 输入区对着空线程；旧线程出现在历史；`chat.jsonl` 整文件仍在。
- Given 历史里点开旧 session 再发一句，Then 写进该 session。
- Given 选中 `maa-log-analysis` 再问日志，When 对话，Then 本轮用户消息带本轮指定，合同要求 `read_skill`。
- Given 选中某个已列出仓再问最近提交，When 对话，Then 本轮指定该 `owner/name`。
- Given 输入区点「开始清日常」，When 发出，Then 走现有清日常线程，不另起勾选源。
- Given 对话复盘子界面点生成，When 成功，Then 正文出现在复盘子界面和今日只读区。
- Given 已有复盘且选中一篇搜索到的 docx，When 点写入，Then 该文档被 markdown 整篇覆盖，不另建。
- Given 已有复盘且填写新标题、不选已有文档，When 点写入，Then `docs +create` 新建并打开链接。
- Given 没有复盘正文，When 点写入，Then 失败原文，不建空文档。
- Given 打开看板，When 看导航，Then 记忆 / 人设 / 技能 / 复盘不在与「今日」平级处；今日页没有生成/写入飞书按钮。

## 5. AI 失败

- 没接模型 → 去侧边栏「模型」页填。
- 选了 skill / CLI / 仓却要把动作交给模型时，本轮消息写明指定；工具失败原文。
- 飞书未登录或没有 docs 权限 → 搜索/写入失败，去侧边栏「飞书」登录（`calendar,task,docs`）。
- 新 session 写盘失败 → 不静默留在旧线程。

## 6. 最危险假设

1. 「CLI」被做成任意命令框。验收：列表来自已注册工具。
2. 「新对话」被做成清空。验收：旧 session 能打开。
3. 写入飞书在没选文档时偷偷新建。验收：必须选文档或填标题。
4. 方舟 chip 复制出第二份勾选。验收：同一份 `selected`。
