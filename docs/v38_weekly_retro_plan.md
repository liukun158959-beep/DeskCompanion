# V38：看板生成本周复盘

> 2026-09-03。grill-me 按推荐冻结。Fixes #15。

## 问题

When 作者要点看板回顾这周，I want 看到交出了什么、还欠什么，so I can 不用自己拼 GitHub 和飞书。

## 非目标

- 不留日总结按钮。对话不另采一周材料（去看板点）。
- 不把飞书已开过的会当成代码产出。对话不当产出。
- 不开森空岛。不扫组织库。

## 决策

| 项 | 选择 |
|----|------|
| 窗口 | 东八区本周一 00:00 到此刻 |
| 产出 | 未归档自有库：本周 commit（作者 login 对得上当前 gh 账号）、已合并 PR、已关闭 issue |
| 会议 | `calendar +agenda --start/--end` 本周，只当占用 |
| 待完成 | `task +get-my-tasks --complete=false --page-all`；未合并 PR；带 milestone 的未关 issue。无 milestone 的未关 issue 只报条数 |
| 结构 | 新技能 `weekly-retro`。Python 采材料，`llm.chat` 不带工具 |
| 落盘 | 仍写 `today.json` 的 `summary`；写入飞书标题 `{周一}～{今天} 周复盘` |

## 验收

Given 本周 DeskCompanion 有提交且飞书有未完成待办，When 点「生成本周复盘」，Then 总结区出现产出表和待完成，不把今日对话抄进产出，不编没推送的改动。
Given GitHub 或飞书失败，When 点生成，Then 失败原文，不写半篇。
