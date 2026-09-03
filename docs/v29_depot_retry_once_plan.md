# V29 实施计划：扫仓同趟再试一次

> 2026-09-02。产品已写进主 PRD §5「再其后：扫仓同趟再试一次」。不是日志页、不是对话、不是模型下发。

## 0. 问题

**When** 这一趟长草跑完，仓库 `data` 是空的（主题点空 / 没进仓）
**I want** 同一趟清日常里再扫一次仓，不要我整段再点、也不要模型决定试不试
**so I can** 从偶发空仓里恢复；仍空则失败可见，账本日期不动

## 1. 非目标

整段重跑唤醒/作战；第三次；改 MAA 模板；Agent 调远控；日志页触发；方舟壳只读文案（下一刀）。

## 2. Must

1. `ingest_depot` 因空仓 / 没写完 / 没文件拒绝写入时，清日常线程里再跑 **1 次** 仅更新数据。
2. 再试：关掉当前 MAA → 队列只开 `UserDataUpdate`、`TriggerInterval=EveryTime` → 计划任务拉起 → 一条 `LinkStart` → 再读仓。
3. 无论成败：MAA 停掉后把间隔写回 `Daily`、8 项勾选写回桌宠当前勾选。禁止留下 EveryTime。

## 3. 工程要点

- 正在跑的管理员 MAA **不会**重读刚写的 `gui.new.json`。必须先停进程再拉起。用户级 `TerminateProcess` 杀不掉管理员窗，因此授权时加计划任务 `DeskCompanion.MAA.Stop`（`taskkill /F /IM MAA.exe`）。没有该任务则再试失败可见：再点一次授权。
- `selected=[]` 写入队列 = 八项全关、更新数据仍开。再试走这条，**不要**走到「一项都没勾不下发」。
- 非空仓失败（译名、不是今天但有货）不重试。
- 再试等待上限 20 分钟，不是 3 小时。
- 拉起前要 `reset_poll`，否则会沿用上一趟的已轮询标记。

## 4. 验收

- Given 第一趟 `DepotData.json` 今天但 `data` 为空，When 清日常收尾，Then 自动再跑一次仅更新数据；仍空则气泡说已再试仍失败，账本日期不是这一趟。
- Given 再试扫到件，When 结束，Then inventory 有货，`TriggerInterval` 为 Daily，八项勾选与桌宠一致。
- Given 只打开看板日志或问「看看日志」，When 对话结束，Then 没有新的 `LinkStart`。
