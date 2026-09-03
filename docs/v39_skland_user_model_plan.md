# V39：森空岛用户模型

> 2026-09-03。grill-me 按推荐冻结。Fixes #6。

## 问题

When 要按号看干员进度、实时理智、本周玉、保全额度，I want 从森空岛官方 `player/info` 建成账号状态，so I can 后面才问「今天刷什么」，而不用打开游戏自己对。

现在的凑合：8 月底用本机号打通了 oauth → cred → binding → `player/info`，代码还没写进产品；仓已经走 V26。

## 非目标

- 不做 V25 规划器、判断层、百科、把 OperBox 当仓库。
- 不写材料 / 龙门币 / 代理卡 / 药（接口里没有；仓仍是 V26 `inventory`）。
- 不后台轮询，不清日常顺带打森空岛，对话里不代点同步。
- 不全量把 `chars[]` 塞进 LLM。不同步终末地 / 来自星尘 / 泡姆泡姆。
- 不在对话或日志里打印 token / cred。

## 决策

| 项 | 选择 |
|----|------|
| 触发 | 看板「明日方舟」页「同步森空岛」。对话问理智 / 周玉 / 保全 / 月卡 / 某干员必须调只读工具 |
| 落盘 | `arknights_account.json` 的 `skland` + `skland_sync`。只覆盖这两项，不改 `inventory` |
| 角色 | 绑定里唯一的明日方舟官服。两个及以上方舟官服 uid → 失败，要求 `.env` 写 `SKLAND_UID` |
| 凭证 | 本项目 `.env` 的 `SKLAND_TOKEN`。缺了失败并写：登录森空岛 → `web-api.skland.com/account/info/hg` → `data.content`。看板保存模型配置时必须保留这两键 |
| 新鲜度 | 工具要求 `skland_sync` 是本机今天；过期失败，让人去看板点同步。看板仍可展示上次数字并标明不是今天 |
| 展示 | 方舟页：实时理智、周玉 current/total、保全仪/条、月卡、同步时间。不列出全部干员 |
| 干员 | 工具按游戏中文名精确取一条。同名（阿米娅术师/近卫/医疗）写成「阿米娅（术师）」；只说阿米娅则列出全名，不擅自选一个。读模型时用本机现在重算实时理智，不重打接口 |
| 签名 | copy 2026-08-28 已跑通的探测脚本：grant `type=0` → `generate_cred_by_code` → HMAC 签名 GET。失败原文，不试 type=1、不试无签名旧头 |

实时理智：`completeRecoveryTime` 为 -1/0 用 `current`（可超上限）；`now >= completeRecoveryTime` 用 `max`；否则 `min(max, current + floor((now - lastApAddTime) / 360))`。禁止直接展示裸 `ap.current`。

## 验收

Given `.env` 有有效 `SKLAND_TOKEN` 且只绑一个方舟官服，When 点「同步森空岛」，Then 方舟页出现实时理智（满时对得上游戏，不是裸 current）、周玉、保全仪/条、月卡，`inventory` 键数不变。
Given 没有 `SKLAND_TOKEN`，When 点同步，Then 失败原文含 hg 页复制指引，日志和对话里没有 token。
Given 上次同步不是今天，When 对话问理智，Then 工具失败，说明去看板点同步，不编数字。
Given 同步是今天，When 问某干员练到哪，Then 只返回那一名的精二/等级/技能/模组，不列出其余干员。
Given 绑定了两个方舟官服且未写 `SKLAND_UID`，When 同步，Then 失败并要求写 uid。
