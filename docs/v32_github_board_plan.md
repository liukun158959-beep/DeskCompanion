# V32：看板 GitHub + 仓库总结

> 2026-09-03。grill-me 已对齐。全屏视频让路先不做（隐藏可替代）。

## 问题

当博士坐在桌前写代码时，要知道 Atlas / DeskCompanion 连没连上、最近推了什么、下一步是哪条，好把注意力放回该写的那一刀。现在凑合是打开 github.com 或终端敲 `gh`。新产品必须比「再切一次浏览器」更快。

## 非目标

全屏让路；GitHub MCP（本机插件坏了）；看板里 `gh auth login`；从桌宠开 Issue / PR / 改 CI；总结写成飞书或 GitHub；扫账号下全部仓库；插件市场。

## Must

1. 看板新页「GitHub」：`gh` 登录态 + `github.json` 里两个库的状态（可见性、上次推送、未关 PR / issue、最近一次 CI）。对话问同一份数据必须调工具。
2. 同一页按仓库展示 roadmap：**未关闭且带 milestone 的 issue**，按 milestone 分组。没有就写恢复指引，不编。
3. 对话「总结某仓库最近」必须先拉近期 commit / PR / issue，再读技能 `github-repo-summary`，只在气泡里说，不写文件。

## 通道与名单

走本机 `gh`（已登录 `liukun158959-beep`）。缺 `gh` 或未登录 → 失败原文。  
`github.json` 必填 `repos`：`liukun158959-beep/Atlas`、`liukun158959-beep/DeskCompanion`。文件 gitignore，缺键失败。

## 验收

Given `gh` 已登录且有 `github.json`，When 打开看板 GitHub 页，Then 看见两个库的状态；roadmap 空则提示去 GitHub 建 milestone 并挂 issue。  
Given 问「GitHub 怎么样」或「Atlas 下一步」，When 对话，Then 先调工具再答，不编。  
Given 说「总结 DeskCompanion 最近」，When 对话，Then 先 `github_recent` 再 `read_skill(github-repo-summary)`，气泡里按技能结构说，不写飞书。
