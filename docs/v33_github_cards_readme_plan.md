# V33：GitHub 卡片 + 全库路线图总结 + README

> 2026-09-03。V32 验收通过。页太单调；要读账号下全部仓库；要 README。

## 问题

博士打开看板 GitHub 页时，要一眼看出每个库现在卡在哪条路线图上，而不是读一段灰字。现在凑合是自己点进 GitHub。新产品必须比「再开一遍网页」更快：卡片上有数字、状态和一句根据 issue 写的总结。

## 非目标

看板刷新时喊模型写散文；GitHub MCP；从桌宠开 Issue；github.json 白名单（改为 `gh repo list`）。

## Must

1. GitHub 页改成每库一张卡片：可见性 / CI / 路线图阶段徽章，PR·issue·路线图三条数字，总结区，milestone issue 可点。
2. 读取登录账号下全部未归档仓库（满 100 个视为截断，失败可见）。每张卡片的总结只来自未关闭 issue 和 milestone 标题，不编。
3. 公开库根目录有 README，clone 的人知道这是什么、怎么在本机跑、哪些文件不会进库。

## 验收

Given 已登录 gh，When 打开 GitHub 页，Then 每个未归档仓库一张卡片，有总结；没有 milestone issue 的库写「无法从路线图判断」而不是空白。  
Given 公开页，When 打开 DeskCompanion 仓库，Then 能看到 README。
