# DeskCompanion

Windows 上常驻的个人助手。桌宠是入口，Atlas 是脑子。作者本机自用：问飞书今日安排，托管长时间任务（第一例是明日方舟日常）。

提供 Windows x64 便携版，配置保存在本机。不接插件市场。

## 下载与首次使用

到 [GitHub Releases](https://github.com/liukun158959-beep/DeskCompanion/releases) 下载 `DeskCompanion-0.2.1-windows-x64.zip`，完整解压后双击 `DeskCompanion.exe`。无需自行安装 Python、Atlas、Node 或 Rust；需要 Windows 10/11 x64 和 WebView2 Runtime。首次使用按引导填写模型信息。完整步骤、可选功能、备份与升级见 [使用说明](docs/GETTING_STARTED.md)。

Live2D Core 和凯尔希素材不随公开包分发；未配置形象时桌宠窗口显示入口卡片，对话、记忆和笔记仍可使用。知识库检索运行库与权重、飞书 CLI、GitHub CLI、MAA 需按需另外安装。

## 本机跑（当前 Tauri 客户端）

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

在 `client` 执行 `pnpm test`、`pnpm exec tsc --noEmit` 和 `pnpm build`，在 `client/src-tauri` 执行 `cargo check --locked`。旧入口在 `pet-ui` 执行 `npm run build`。Tauri 的 `gen/` 是自动生成目录，不进 Git。
