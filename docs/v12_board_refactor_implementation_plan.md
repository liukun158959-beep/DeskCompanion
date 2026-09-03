# V12 实施计划：看板重构（模型 / 人设 / 历史 / 用量 / 飞书）

> grill-me 对齐后冻结。2026-08-14。动作设计和优化不在本轮。

## 0. 决策

| 项 | 选择 |
|----|------|
| 结构 | 仍是一个看板窗。页签：今日 / 对话 / 人设 / 模型 / 用量 / 飞书 |
| 模型配置 | 只读写 `desk-companion/.env`（`ATLAS_API_KEY` / `ATLAS_BASE_URL` / `ATLAS_MODEL`）。**不再读** Atlas 目录 `.env`。缺必填就失败，看板「模型」页给出填写指引 |
| 历史 | 看板可看可清。最近 N 轮写入模型上下文，N 在看板可改 |
| 人设 | 只改性格/说话方式。查日程必须调工具的规则锁在代码里 |
| 用量 | 接口只拿 token（`usage.prompt_tokens` / `completion_tokens`）。金额用看板里用户填的该模型单价算人民币。没填单价就只显示 token，不算钱。不用 Atlas 内置价格表，不调各家账单接口 |
| 飞书 | 独立页：状态、缺什么、一键登录（打开浏览器）、退出、刷新。失败原文展示，不静默跳过 |
| 启动 | 缺 API Key **不杀进程**。宠物和看板照常起来；说话时提示去看板填。保存模型配置后当场重建 Agent，不重启进程 |

## 1. 看板页签

奶油纸面、现有 `tokens.css`。窗大约 1000×680，内容区滚动。托盘「打开看板」不变。

1. **今日**：现有日程 + 未完成待办 +「让咕嘎讲」。飞书失败时给跳转到「飞书」页的按钮。
2. **对话**：读 `memory/chat.jsonl`，按时间列出。可清空（与气泡清空同一文件）。不在看板里发消息（仍走头顶气泡）。
3. **人设**：多行编辑「性格/说话方式」。只读展示锁死的工具协议（问日程必须调 `get_today_agenda` / `get_open_tasks`，失败原样说怎么修）。保存后重建 Agent。另可改：喂给模型的历史轮数 N、`max_steps`、主动搭话开关（与托盘同一字段）。
4. **模型**：提供商下拉（Atlas `PROVIDERS`：qwen / openai / deepseek / moonshot / zhipu）自动填 URL 和默认模型名；URL、模型名、API Key 均可改。Key 用密码框，回写只显示是否已填。当前模型的**输入/输出单价**（元 / 百万 token）写在本页，按模型名分别记。按钮：保存、测试连通（发一条极短 chat，失败原文）。自定义 URL 允许，不在列表里也行。
5. **用量**：今日 / 本月 / 累计的输入 token、输出 token、次数。该次 run 的模型若已填单价，同时记人民币；没填则金额为空，看板写「未填单价」。不展示美元，不用 Atlas `PRICING_TABLE`。
6. **飞书**：是否找到 `lark-cli`、是否已登录、用户名、calendar/task 权限是否够。按钮：刷新、登录、退出。登录走 `lark-cli auth login --domain calendar,task --no-wait --json`，拿到链接用系统浏览器打开。

## 2. 配置落盘

| 数据 | 位置 | 说明 |
|------|------|------|
| API Key / URL / 模型 | `desk-companion/.env` | 密钥不进 `user_state.json`、不进日志、不进对话 |
| 人设正文、N、`max_steps`、主动搭话、各模型单价 | `user_state.json` 必填字段 | `model_prices` 是对象，键为模型名，值 `{input_cny_per_mtok, output_cny_per_mtok}`；可以是 `{}`。缺这个键启动失败 |
| 对话 | `memory/chat.jsonl` | 已有 |
| 用量 | `memory/usage.jsonl` | 每次 Agent run 一行：时间、模型、in/out/total、cost_cny（未填单价则为 null）、run_id |

`load_env` 只加载本项目 `.env`。禁止再 `load_dotenv(Atlas/.env)`。

保存人设或模型时：若正在跑 Agent，拒绝保存并说明等这句说完。否则写盘并 `build_agent(host)` 换新实例。

## 3. Agent

1. `system_prompt = 人设正文 + "\n\n" + 锁死的工具协议`。人设空则失败，不套默认性格。
2. 每次 `run` 前把最近 N 条 `chat.jsonl` 做成 user/assistant 消息注入（N=0 表示不喂）。只注入，不把 jsonl 当 Atlas Memory 持久化。
3. 注册已有 `BubbleStreamPlugin`，再注册 `TokenCostPlugin`（只要它累加的 token，不要它的美元表）。run 结束用 `get_summary(run_id)` 的 token，按当时模型在 `model_prices` 里的单价算 `cost_cny`，追加到 `usage.jsonl`。
4. `LLM(...)` 显式传入 `.env` 里的 `api_key` / `base_url` / `model`，不靠 Atlas 默认值猜。

## 4. Atlas（仅用量能算出来所需）

流式路径补 `stream_options={"include_usage": True}`，否则桌宠一直走 stream，`usage` 经常是空，token 都记不上。不改 Atlas 计价表、不改插件协议。

## 5. 飞书页命令

只封装已有 `lark-cli`，不在看板里做 `config init` 创建应用。若 CLI 未装或未 init，状态里写清要先在本机装好并 `lark-cli config init`。

## 6. 不做

- 动作设计、换帧、Live2D
- 在看板里聊天
- 把整段 system prompt（含工具协议）开放编辑
- 继续读取 Atlas `.env`
- temperature（Atlas `LLM.chat` 没接，本轮不改）
- 为旧 `user_state.json` 做字段兜底；缺键就失败并列出要补的键
- 把 API Key 写进 git / jsonl / 日志
- 用 Atlas 内置价格表或汇率估人民币
- 去各家控制台拉账单 / 余额
