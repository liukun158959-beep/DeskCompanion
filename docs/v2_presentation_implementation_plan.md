# V2 实施计划：分层窗宠物 + HTML 气泡/看板 + 托盘

> grill-me 对齐后冻结。2026-08-14。
> 接在 V1 之后：消红边、让咕嘎自己动、托盘常驻、今日看板。

实施原则：缺必填就失败并给出恢复指引；Windows / UTF-8 / 中文注释；不留 tkinter 旧壳。

## 0. 决策速查表

| 决策项 | 最终选择 |
|--------|---------|
| 壳 | 混合。宠物 = Windows 分层窗（逐像素 Alpha）；气泡 + 看板 = pywebview HTML。Atlas 仍在同一 Python 进程。 |
| 不做什么 | Electron / Live2D / 整屏覆盖层 / 控制中心堆设置 |
| 角色 | 继续咕嘎精灵表。1.5 倍 LANCZOS + 落地投影 + 常驻起伏 |
| 灵动 | 行为机：隔几秒随机挥手/跳；偶尔沿工作区底边走；点击挥手并打开气泡；思考播 waiting |
| 气泡 | 不透明奶油卡片（Win11 圆角 + CSS 小尾巴）。点宠物打开，回车发给 Atlas |
| 看板 | 今日看板：左日程时间轴，右未完成任务。打开时拉飞书 |
| 讲安排 | 看板按钮 = 打开气泡并自动问「今天干什么？」看板自己不聊天 |
| 视觉 | 暖奶油 / 深棕字 / 腮红点缀 / 软投影 |
| 托盘 | 启动就出宠物；托盘常驻。显示/隐藏宠物、打开看板、退出。关看板不退出 |
| 红边 | 禁止品红扣图。分层窗 UpdateLayeredWindow + 预乘 Alpha |

## 1. 依赖顺序

```
Step 1 计划文档（本文件）+ pyproject 依赖 + 删 tkinter 壳
Step 2 分层窗绘制（真透明、投影、1.5x、点空白穿透）
Step 3 行为机（起伏 / 挥手 / 跳 / 走路）
Step 4 HTML 气泡（pywebview 不透明卡片）
Step 5 今日看板 + 飞书 JSON 解析
Step 6 托盘 + 组装启动
```

验证：`python -m desk_companion`（Windows）。缺皮肤 / Key / WebView2 / pywin32 必须打出恢复指引后退出。

## Step 1：工程

新增依赖：`pywin32`、`pywebview`、`pystray`。
删除 `window.py`、`bubble.py`。入口改为 `app.run_app`。
HTML 放 `desk_companion/ui/`，随包分发。

## Step 2：分层窗

`WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW`，`UpdateLayeredWindow` 送 RGBA。
启动时 `Per-Monitor DPI Aware V2`，避免系统再拉伸一层。
精灵 LANCZOS 放大后贴到带椭圆形落地影的画布上；`WM_NCHITTEST` 对低 Alpha 像素返回穿透。
拖动逻辑从原 `window.py` copy 再改：阈值区分拖与点。

## Step 3：行为机

常驻正弦起伏。idle 8–20s 后随机挥手 / 跳 / 沿工作区走动。
点击：播挥手并打开气泡。Agent 运行中只播 waiting，打断自主行为。失败播 failed 一轮再回 idle。
右键：换装 / 打开看板 / 隐藏 / 退出。

## Step 4：气泡

隐藏的 frameless pywebview。奶油底、圆角、右侧小尾巴。
JS `pywebview.api.send_chat` / `close_bubble`。Esc 与「关闭」隐藏，不销毁。
宠物拖动时若气泡可见则跟随。

## Step 5：看板

独立 frameless 窗。打开时 `calendar +agenda` 与 `task +get-my-tasks --complete=false`。
成功信封 `ok==true` 才渲染；否则该栏展示错误原文 + `lark-cli auth login --domain calendar,task`。
空列表是真的没有，文案「今天没有日程 / 没有未完成待办」，不是失败兜底。
「让咕嘎讲」：显示气泡并发送「今天干什么？」。

## Step 6：托盘

`pystray`，图标取 idle 第一帧缩小。菜单三项。隐藏宠物时一并藏气泡。退出才销毁全部窗。
