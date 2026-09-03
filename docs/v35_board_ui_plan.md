# V35：看板技能 Markdown、动效、浅色边框

> 2026-09-03。用户三点已明确，剩余对齐已有实现。Fixes #12。

## 问题

作者打开看板看技能或切页时：技能正文是纯文本且默认全展开；页面没有过渡；Windows 深色主题把系统标题栏染成黑条，压在奶油纸面上。

## 非目标

- 不开森空岛 #6、不做 V25。
- 技能页不做插件市场。
- 不改气泡 Markdown 白名单。
- 不拆系统标题栏（V13：最小化/最大化/改大小还要）。

## 决策

| 项 | 选择 |
|----|------|
| Markdown | copy 气泡：`marked.min.js` + `purify.min.js` 同一套 PURIFY |
| 技能默认 | 全部折叠；一次只开一张（手风琴） |
| 卡片 | 标题 = id，副标题 = description，点开才渲染正文 |
| 动效 | 切 tab 短 fade+上移；卡片 hover 轻抬；技能三角旋转。`prefers-reduced-motion` 关掉 |
| 黑边 | 看板窗 `DWMWA_USE_IMMERSIVE_DARK_MODE=0`，标题栏/边框/文字染纸色与墨色；WebView 底刷 `PAPER`。仍 `frameless=False` |

## 改哪些文件

1. `ui/board.html`：引入 vendor、技能卡片、动效 CSS、手风琴。
2. `app.py`：`_prepare_form(tool=False)` 刷纸色与 DWM 标题栏。

## 验收

Given 打开看板技能页，When 不点任何技能，Then 只看到标题和描述，正文折叠，点开一张另一张关上，正文是标题/列表/代码而不是一整块 pre。
Given 切「今日 / GitHub」，When 切页，Then 新页有短过渡，卡片 hover 轻抬。
Given Windows 深色主题，When 打开看板，Then 顶栏和窗口描边是奶油/腮红，不是黑条。
