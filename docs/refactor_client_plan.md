# 桌宠重构实现计划：看板变客户端（Tauri + React）

> 状态：待对齐确认。动手前请确认本文的架构决策与分期。
> 决策来源：2026-09-22 grill-me。技术栈 Tauri 2 + React + TS；统一成一个客户端（宠物窗 + 气泡 + 看板都进新前端），Python 退居后端只做脑子和工具；客户端为主界面、宠物为常驻入口和陪伴；视觉参考 Claude / ChatGPT / Cursor / Raycast / Hermes-CN-Desktop。

## 1. 问题

作者在 Windows 上自用桌宠。当前看板是 Python 拼 HTML 塞进 pywebview 的窗，样式和交互靠手写字符串堆，改一处要动 Python，动画和组件谈不上现代客户端质感。宠物窗又是另一个独立 Electron 进程。两套壳、两套渲染，视觉和交互割裂。

- When：作者日常开机常驻，要问今日安排、托管明日方舟日常、看 GitHub / 飞书状态、配模型和自动化任务时。
- I want：一个好看流畅、像现代 agent 客户端的统一界面，会话、对话、看板面板都在里面，宠物是常驻入口和陪伴角色。
- so I can：把「问一句今天干什么 + 托管长任务 + 管配置」这件事在一个顺手的客户端里完成，而不是在拼字符串的看板和独立宠物窗之间跳。

## 2. 非目标（本阶段不做，防范围膨胀）

- 不做安装包分发、不做多用户、不做插件市场（延续 V1 自用定位）。
- 不重写 Python 后端的脑子和工具（Atlas 接入、飞书/MAA/GitHub/森空岛 40+ py 文件保持，只在其上加本地 API 层）。
- 不做跨平台，只 Windows。macOS 以后再说。
- 不引入语音（TTS/ASR），对话仍是打字。
- 不做 Live2D 形象编辑器、不换精灵格式，沿用现有 Live2D 资源加载约定。
<!-- SEC-NONGOAL -->
## 3. 现状与替代方案

现在的三块：

- 宠物窗：独立 Electron App（`pet-ui/`，0.3.0），PixiJS 6 + `pixi-live2d-display` 渲染 Live2D。
- 看板 + 气泡：Python 侧 pywebview（WebView2/edgechromium），HTML 由 `board_workbench.py`（253 行）+ `board_data.py`（416 行）拼，`app.py`（1176 行）总装，前端 JS 在 `pet-ui/src/renderer/src/`（`pet.js` / `bubble.js` / `main.js`）。
- 脑子 + 工具：全在 Python，`bridge.py`（163 行）暴露约 45 个方法给 JS（send_board_chat / load_board / list_automation_jobs / board_maa / sync_skland / save_model 等）。

作者现在怎么凑合：看板样式想改就改 Python 字符串，宠物和看板两个进程各活各的。新客户端必须比这个更好看、改起来更快（前端归前端），且不牺牲现有已跑通的能力。

## 4. 目标架构

一个 Tauri 2 应用，内含两个窗口，共享一套前端设计系统；Python 变成本地无头服务，被 Tauri 壳拉起并托管。

```
+-------------------------------------------------------------+
|  Tauri App (Rust 壳)                                        |
|  - 拉起并托管 Python 后端子进程 (spawn + 健康检查 + 退出清理) |
|  - 窗口管理：主客户端窗 + 宠物透明窗                          |
|  - Rust command 代理 REST/WS 到本地 Python (集中鉴权/CORS)   |
|  +-------------------------+  +---------------------------+  |
|  | 主客户端窗 (React)       |  | 宠物窗 (React, 透明置顶)   |  |
|  | 侧栏会话 + 主对话 + 看板 |  | Live2D + 气泡对话          |  |
|  +-------------------------+  +---------------------------+  |
+----------------------------|--------------------------------+
                             | 本地 HTTP + WebSocket (127.0.0.1)
+----------------------------v--------------------------------+
|  Python 后端 (无头服务，复用现有脑子和工具)                   |
|  - 新增本地 API 层：把 bridge 的 45 个方法暴露为 REST + WS    |
|  - Atlas 接入 / 飞书 / MAA / GitHub / 森空岛 / 自动化任务保持 |
+-------------------------------------------------------------+
```

核心变化：`bridge.py` 的方法从「pywebview JS 桥」改为「本地 HTTP/WS 端点」。前端不再由 Python 拼 HTML，改成 React 组件消费 JSON API。宠物 Live2D 渲染逻辑从 Electron 迁到 Tauri webview（同一套 `pixi-live2d-display`）。
<!-- SEC-TARGET -->
## 5. 通信方式（最关键决策）

**决策：Python 起一个本地 HTTP + WebSocket 服务（127.0.0.1 + 随机端口），Tauri Rust 壳负责 spawn/托管/健康检查，前端经 Rust command 代理调用。**

理由：

- 和 Hermes-CN-Desktop 同构（它就是 Tauri 壳把 agent 内核当 runtime 进程管，前端经 Rust 代理 REST/WS），是被验证过的桌面 agent 客户端骨架。
- Atlas 本身已有 dashboard 的 HTTP(8765)+WebSocket(8766) 服务范式，Python 侧起本地服务不是从零。
- HTTP 管请求/响应类（load_board / save_model / list_automation_jobs 等 40 个），WebSocket 管流式（对话 token 流、MAA 远控状态推送、自动化任务进度）。

约定：

- 端口绑定 `127.0.0.1`，启动时选空闲端口写入本地文件，Rust 读后注入前端，不对外暴露。
- 加一个进程级 token：Rust 生成，启动 Python 时传入，前端每次请求带上，挡掉本机其它进程误连。
- Python 服务无头（不再 pywebview），崩溃由 Rust 检测并按恢复指引提示，不静默重启兜底。

**这一层是本次重构的骨架，也是最大工作量和最大风险（见第 12 节）。**

契约用一个 `protocol` 包收口：TypeScript 侧 Zod schema + Python 侧对应的请求/响应 dataclass，两边共享字段定义，避免手写 JSON 对不齐。
## 6. 前端设计与技术选型

- 框架：React 18 + TypeScript + Vite。
- 服务端状态：TanStack Query（缓存 + 失效 + 轮询看板数据）。UI 局部状态：Zustand（轻量，不上 Redux）。
- 样式：Tailwind CSS + 一套 design token（颜色/间距/圆角/阴影/动效时长），暗色浅色双主题。
- 动画：Framer Motion（面板切换、卡片展开、气泡进出、侧栏滑动）。目标是「好看流畅」，动效走统一 token，不逐个手调。
- 渲染：Markdown/LaTeX/代码高亮复用现有 `marked` + `purify` 思路，升级为 React 组件（react-markdown + KaTeX + Shiki）。

主客户端窗布局（参考 Claude/Cursor 工作台 + Raycast 动效）：

- 左侧栏：会话列表（新建/切换/删除，对应 bridge 的 new_chat_session / switch_chat_session）+ 导航入口（对话 / 看板 / 自动化 / 设置）。
- 中间主区：流式对话（token 逐字、工具调用可折叠卡片、附件），或看板面板（今日日程时间轴 + 未完成待办 + GitHub/飞书/MAA/森空岛状态卡）。
- 设置区：模型服务商配置、人设、飞书登录、MAA 路径与选项、用量统计、运行时诊断与日志（对应 board_model / board_persona / feishu / board_maa / board_usage / board_log_errors）。

组件分层：`packages/shared-ui`（design token + 基础组件：Button/Card/Panel/Timeline/StatusPill/Toast/Modal）供两个窗复用。
## 7. 宠物窗

- 独立 Tauri 窗口：透明背景、置顶、无边框、可拖、点击穿透非角色区域（Tauri 支持 transparent + always-on-top + decorations=false + skip-taskbar）。
- Live2D 渲染：沿用 `pixi-live2d-display` + PixiJS，从 `pet-ui/src/renderer/src/pet.js` 迁移（先 copy 再改），资源加载约定不变（Core 放 `public/Core/`，皮肤放 `skins/`，缺失即失败给路径）。
- 气泡对话：点宠物在角色旁弹输入框，回车发给后端，回答流式回到气泡。从 `bubble.js` 迁移逻辑，重写为 React 组件。
- 宠物窗和主窗共享后端连接和 design token；点气泡里的「打开客户端」唤起主窗。

风险点：当前宠物窗是 Win32 分层窗（逐像素 Alpha），Tauri 用的是 WebView2 透明窗，透明和点击穿透的表现要实测验证（见第 12 节）。
## 8. 迁移原则

按「先 copy 再改写」，不凭记忆重写：

- Live2D 渲染、气泡逻辑：从 `pet-ui/src/renderer/src/` copy 出来，改成 React 组件 + TS。
- 看板数据整形：`board_data.py` / `board_workbench.py` 里「取数 + 整形」的逻辑保留在 Python，只把「拼 HTML」那部分删掉，改成返回 JSON。前端拿 JSON 渲染。
- bridge 45 个方法：逐个映射成 REST/WS 端点，方法名、参数、返回结构尽量不变，降低对不齐风险。
- 现有 Python 工具（飞书/MAA/GitHub/森空岛/自动化）完全不动。

区分两类 bridge 方法：

- 数据类（load_board / board_maa / sync_skland / save_model ...）→ REST 端点。
- 窗口/UI 类（close_bubble / fit_card / close_board / open_url）→ 不再进 Python，改由 Tauri 前端/Rust 直接处理（窗口关闭、尺寸自适应、开链接都是壳的职责）。
## 9. 分期（每期对应一个 GitHub issue，一刀一 issue，直推 main）

工程量按「周」级，不是一次做完。建议顺序：

1. **P1 Python 本地 API 层**：把 bridge 数据类方法暴露为本地 HTTP + WS 服务（无头模式），保留现有 pywebview 入口不删，先让 API 和旧看板并存可验证。契约用 protocol 包收口。
2. **P2 Tauri 壳骨架**：Tauri 2 工程 + Rust spawn/托管 Python + 健康检查 + 端口/token 注入 + REST/WS 代理 command + 主窗和宠物窗两个空窗能起。
3. **P3 设计系统 + 主窗骨架**：Tailwind + design token + shared-ui 基础组件 + 双主题 + 侧栏/主区/设置区布局骨架（Framer Motion 动效基线）。
4. **P4 对话客户端**：流式对话、会话侧栏、工具调用折叠卡、Markdown/LaTeX 渲染。
5. **P5 看板面板**：今日日程时间轴 + 待办 + GitHub/飞书/MAA/森空岛状态卡，接 P1 的 API。
6. **P6 宠物窗**：Live2D 迁移 + 透明置顶点击穿透 + 气泡对话。
7. **P7 设置与自动化**：模型配置/人设/飞书登录/MAA 选项/用量/诊断日志 + 自动化任务管理。
8. **P8 收尾切换**：删除 pywebview 看板和 Electron pet-ui，打包（Tauri build），更新 README。

每期做完可独立验证；P1 完成后新旧并存，不是大爆炸切换。
## 10. 验收（Given / When / Then，能当场判过不过）

- Given 客户端已启动，When 点侧栏新建会话并发一句「今天干什么」，Then 主对话区流式返回，内容基于飞书日程和未完成待办，不是编的。
- Given 主窗看板页，When 点刷新，Then 今日日程时间轴 + 待办 + 各状态卡在 2 秒内更新为真实数据。
- Given 宠物窗常驻桌面，When 点宠物打字回车，Then 角色旁气泡流式出答案，宠物窗透明且非角色区不挡鼠标。
- Given 关闭 Python 后端进程，When 前端发起请求，Then 客户端明确报「后端未运行」并给恢复指引，不静默转圈或编造。
- Given Tauri 应用退出，When 检查进程，Then Python 子进程被一并清理，无残留。

成功标准是作者行为：能在这个客户端里顺手完成「问今日安排 + 托管方舟日常 + 管配置」，且视觉/动效达到现代 agent 客户端质感。
## 11. AI / 运行时失败可见

延续「消除 fallback 触发场景」，失败可见并给恢复指引，不静默兜底：

- Python 后端未起 / 崩溃：前端顶部横幅明确提示 + 恢复指引（怎么看日志、怎么重启），不无限转圈。
- 模型调用失败 / 超时 / 编造工具：对话区标红显示错误，保留可重试入口，不假装成功。
- 飞书 / MAA / 森空岛 未登录或 token 失效：对应状态卡显示未连接 + 去哪配置，不静默跳过或塞默认值。
- 端口 / token 注入失败：Rust 侧启动即失败并弹窗给路径，不带病启动。
## 12. 最危险假设与下一步最小验证

**最危险假设**：Tauri 的 WebView2 透明窗能达到当前 Win32 分层窗（逐像素 Alpha）同等的宠物透明 + 点击穿透效果。若达不到，宠物窗这条路要重新设计（可能宠物窗暂时保留 Electron，主客户端用 Tauri）。

**次危险假设**：把 bridge 45 个方法平移到本地 HTTP/WS 后，流式对话和 MAA 远控状态推送的实时性、时序与现在 pywebview 直连一致。

**下一步最小验证（做 P2/P6 前先做一个 spike）**：

1. 一个最小 Tauri 窗，透明 + 置顶 + 无边框 + 点击穿透，塞进 `pixi-live2d-display` 渲染现有咕嘎皮肤，实测透明边缘和鼠标穿透是否达标。
2. 一个最小本地 FastAPI（或复用 Atlas dashboard 范式）跑通「一条 WS 流式对话」，Rust spawn 它 + 健康检查 + 退出清理，验证进程托管链路。

两个 spike 过了，再按 P1-P8 铺开。若宠物 spike 不达标，回来重议宠物窗技术选型。

## 13. 已确认（2026-09-22）

- 认可「Python 起本地 HTTP/WS 服务 + Tauri 托管」骨架（第 5 节）。
- 先做两个 spike 验证最危险假设，再铺开分期实现。
- 包管理器：**pnpm**（workspace 结构对多包管理更省事，与 Hermes 参考一致）。
- 分期按 P1-P8 顺序。

## 14. Spike 计划（铺开前先做）

- **Spike A（宠物透明窗）**：最小 Tauri 窗，透明 + 置顶 + 无边框 + 点击穿透，塞 `pixi-live2d-display` 渲染现有咕嘎皮肤，实测透明边缘与鼠标穿透是否达 Win32 分层窗水平。
- **Spike B（后端托管 + 流式）**：最小本地服务跑通一条 WS 流式对话，Rust spawn + 健康检查 + 退出清理，验证进程托管与实时性。
- 通过标准：A 透明与穿透达标；B 流式实时、进程随 App 退出清理。任一不达标回来重议对应技术选型。

### Spike 结论（2026-09-22，两个均通过）

- **Spike A 通过（#20）**：Tauri 2 透明置顶无边框窗 + alpha hit-test 点击穿透，达标。宠物窗确定走 Tauri。实现落在 `client/`（前端 Vite+TS，Rust 壳 `set_click_through` 命令按角色像素 alpha 动态切换穿透）。
- **Spike B 通过（#21）**：Python 最小本地服务（`websockets`，同端口 HTTP `/health` + WS 流式），Rust 壳 spawn + 轮询健康检查 + `RunEvent::ExitRequested` 退出清理，前端经 WS 收流式 token 逐字显示。流式实时；优雅关闭 App 后 Python 后端无孤儿。骨架成立。
- 结论：透明宠物窗 + 后端托管 + WS 流式的整套 Tauri 骨架被证明可行，按 P1-P8 正式铺开。
