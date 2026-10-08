# DeskCompanion

Windows 上常驻的个人助手。桌宠是入口，Atlas 是脑子。作者本机自用：问飞书今日安排，托管长时间任务（第一例是明日方舟日常）。

提供 Windows x64 便携版，配置保存在本机。不接插件市场。

## 下载与首次使用

到 [GitHub Releases](https://github.com/liukun158959-beep/DeskCompanion/releases) 下载 `DeskCompanion-0.2.1-windows-x64.zip`，完整解压后双击 `DeskCompanion.exe`。无需自行安装 Python、Atlas、Node 或 Rust；需要 Windows 10/11 x64 和 WebView2 Runtime。首次使用按引导填写模型信息。完整步骤、可选功能、备份与升级见 [使用说明](docs/GETTING_STARTED.md)。

Live2D Core 和凯尔希素材不随公开包分发；未配置形象时桌宠窗口显示入口卡片，对话、记忆和笔记仍可使用。知识库检索运行库与权重、飞书 CLI、GitHub CLI、MAA 需按需另外安装。

## 本机跑（当前 Tauri 客户端）

源码版新增 **飞书 → 在飞书使用桌宠 Agent**，可复用本机 CLI 的应用接入本人私聊，调用模型、工具、技能、知识库和 MCP；长连接设置支持选择应用、更新密钥、自动连接、重连间隔和占用检查。配置与故障恢复见 [飞书 Agent 接入说明](docs/FEISHU_AGENT.md)。此功能尚未包含在 0.2.1 公开包中。

需要 Windows、Python 3.11+、本机已 `pip install -e` 的 Atlas 源码、以及本机 `gh` / `lark-cli`（看板对应页才会通）。

```powershell
pip install -e <Atlas目录>
pip install -e .
cd client
pnpm install
pnpm tauri dev
```

主窗启动时显示动画和当前准备阶段，助手连接、会话读取完成后切入主界面。失败会显示原因和「重新加载」；后端未能启动时按提示检查终端并重启客户端。

没有模型配置时自动打开首次引导，按「了解功能 → 连接模型 → 可选功能」准备。API 地址填服务商的 Base URL（通常含 `/v1`），模型名填控制台的准确模型 ID，API Key 填独立密码框。支持 OpenAI Chat Completions 兼容接口；模型调用工具还需支持 tool calling。保存后点「测试连通」，测试会发一条简短请求并可能计费。已有配置不会强制重新引导；「设置 → 打开使用引导」可随时重新查看配置、数据目录和其他能力的入口。

Live2D Cubism Core 和形象包不在本仓库。源码运行的 Core 放到 `client/public/Core/live2dcubismcore.js`，凯尔希形象放到 `client/public/skins/kaltsit/`（包含 `kaltsit.model3.json` 及其引用的素材）。便携版的素材位置在使用引导里显示，缺少素材时显示主窗入口卡片。

旧入口仍保留：在 `pet-ui` 执行 `npm install`、`npm run build`，回到项目根目录执行 `python -m desk_companion`。旧入口使用 `pet-ui/public/Core/` 和 `skins/`，依然需要 Electron、pywebview 和托盘依赖。

看板侧边栏「模型」填写 API Key。看板「自动化任务 → 明日方舟」同步森空岛前，在本项目 `.env` 写 `SKLAND_TOKEN=`（浏览器登录森空岛后打开 `https://web-api.skland.com/account/info/hg`，复制 `data.content`）。不要把这串发到对话或推进 Git。多个方舟官服时再写 `SKLAND_UID=`。问「今天刷什么」走看板按钮或对话工具，仓必须是今天。

## 每日资讯与定时任务

源码版在「飞书 → 每日资讯与定时任务」配置采集主题、知识库父页面、机器人所在群和资讯多维表格。先保存设置并检查位置，再生成今日预览；可以仅归档文档和表格，或发布图文卡片到群。资讯表需要普通文本字段：资讯ID、日期、标题、类别、摘要、实践价值、来源链接、发布时间、每日文档、状态。

日报读取官方网页正文，从最近 1～14 天的资料中选 3～5 条，区分事实、实践建议与局限。日期无法核实时明确标注，不把旧资料当作今日新闻。网络失败或可核实来源不足时保留缺口，停止发布。图片为本期技术类别统计图。

「定时任务管理」支持每天或每周执行，时间按北京时间。首轮检查完成后再启用每日 09:00 推送；桌宠必须保持运行，重新启动只补跑最新错过的一次。资讯与聊天共用独立任务队列，总执行预算 15 分钟，临时失败最多重试一次；停止任务会停止对应进程，关闭定时只影响后续触发。

发布逐步保存文档、表格记录和消息回执，重试会先查重。写入结果不明确时停止重复创建；群消息采用一小时幂等窗口，超出窗口的未确认发送需要人工核实。设置保存在本机 `news_settings.json`，预览和回执位于 `memory/news/`，均不提交 Git。

## 仓库里有什么

- `desk_companion/` Python 壳：宠物窗、看板、飞书、MAA 远控、GitHub 状态
- `client/` Tauri + React 主客户端与 Live2D 宠物窗，本地 WebSocket 连接 Python 后端
- `pet-ui/` 保留的 Electron 旧入口
- `docs/prd_desktop_pet.md` 产品拍板
- `skills/` 对话技能（写飞书总结、读日志、总结 GitHub）

## 不会进 Git 的

`.env`、`user_state.json`、`maa.json`、`arknights_account.json`、`memory/`、`skins/` 素材、`_refs/`、Live2D Core。

## GitHub 页

看板 GitHub 读当前 `gh` 登录账号下全部未归档仓库。路线图只认带 milestone 的未关闭 issue；卡片上的总结由这些 issue 拼出来，不编。对话里「总结某仓库最近」走技能 `github-repo-summary`，只在气泡里说。

合入：一刀一个 issue，提交说明写 `Fixes #6` 这种，直推 `main`，不开发 PR、不要求 review。GitHub 会关对应 issue。

## 验证

根目录执行 `python -m unittest discover -s tests -v`，测试在临时目录写样本，不修改个人记忆、账号和模型配置，也不发送飞书消息或启动游戏。

主窗口「飞书 → 聊天任务监控台」可查看新任务的聊天记录、工具时间线、排队与耗时，停止执行或继续同一段对话。续聊默认只保留在本地；勾选「将这次回答发送回原飞书私聊」才会回复飞书。普通桌面对话与飞书会话分别保存上下文，同一会话按顺序执行。停止或超时保留部分答案；已经尝试过的相同写入不会在继续任务时自动重做，未知结果应先查询核实。旧版任务没有完整工具时间线。

监控台「执行设置」默认同时执行 2 个任务、单次调用 90 秒、任务总时限 300 秒，可调整并关闭凯尔希的进度反馈。任务在独立进程执行，到时限后会停止对应进程树；共享写入工具互斥。任务记录仅保存在本机 `memory/tasks.sqlite3`，关闭桌宠后未完成任务标为中断，不自动重新执行。

桌面与飞书共用联网搜索接口。TLS 握手超时、连接中断或搜索服务临时错误会自动重试一次，并反馈重试进度；两次请求共用 60 秒请求预算，单次请求等待上限保持 30 秒，任务管理器仍按配置的调用和总时限停止任务。鉴权、证书校验错误及无结果不会重试，最终失败会在工具时间线显示失败。长时间等待提示按当前调用计时，避免刚开始调用工具就提示等待过久。

飞书机器人需开通并发布 `cardkit:card:write` 才能使用流式回复卡片。记忆菜单的推送事件标识填写 `memory_request_from_feishu`，事件订阅添加 `application.bot.menu_v6` 并使用长连接，再发布应用；桌宠只响应绑定用户。点击菜单或私聊发送 `/memory` / `记忆`，直接展示长期事实与当前会话已有摘要，无需模型调用。较长内容自动分卡，完整聊天记录在监控台查看。卡片权限不可用时任务仍执行并降级回复，接入页会显示诊断。

在 `client` 执行 `pnpm test`、`pnpm exec tsc --noEmit` 和 `pnpm build`，在 `client/src-tauri` 执行 `cargo check --locked`。旧入口在 `pet-ui` 执行 `npm run build`。Tauri 的 `gen/` 是自动生成目录，不进 Git。
