# V45：不再代开启动器 / 游戏 exe（#8）

> 2026-09-03。GitHub #8。grill-me 已对齐。证伪修正：UAC 来自代开 `Launcher.exe`；`schtasks` 拉 `Arknights.exe` 本机不弹。本刀仍三态都不代开。

## 0. 问题

**When** 作者要点清日常或让定时清日常跑完  
**I want** 桌宠不再自己拉启动器（那一下必弹 UAC，安全桌面点不到）  
**so I can** 游戏窗已经在时零次新 UAC 交给 MAA；没开则失败原文，自己去启动器点开始

现状替代：`open_pc_client` 先 `ShellExecute Launcher.exe`（弹 UAC），再 `schtasks DeskCompanion.ArknightsPC`。定时清日常走同一条，夜里无人值守会被 UAC 卡住。

## 1. 非目标

- 代点 UAC、关安全桌面、漏洞绕过。
- 本阶段改连安卓模拟器 / ADB。
- 再找一种「无 UAC 代开启动器」。
- 删用户机器上已有的 `DeskCompanion.ArknightsPC` 任务（不再注册、不再运行即可）。
- 改 MAA 远控 / 勾选 / 扫仓。

## 2. Must（≤3）

1. **三态认窗。** 有可见 `Arknights.exe`「明日方舟」窗口 → 直接干。启动器在、窗不在 → 立刻失败（去启动器点开始）。两边都不在 → 立刻失败（先自己开启动器）。不等 `open_timeout_sec`。
2. **入口同一套。** 「打开游戏」、手点清日常、定时清日常都走改过的 `open_pc_client`，都不 `ShellExecute` 启动器，都不 `schtasks` 开游戏。
3. **授权只管 MAA。** 「授权一次」只注册/检查 `DeskCompanion.MAA` 与 `Stop`。文案不再写「之后开游戏不弹 UAC」。

## 3. 拍板

| 项 | 选择 |
|----|------|
| 已开 | 沿用 `find_game_hwnd()`：可见窗 + 进程是 `Arknights.exe` |
| 打开游戏按钮 | 留下。有窗说已在；没窗失败原文，不拉 exe |
| 等待秒数 | 界面去掉。`maa.json` 的 `open_timeout_sec` 仍必填，保存路径时原样写回 |
| 计划任务 | 不再写、不再跑 `DeskCompanion.ArknightsPC`。MAA / Stop 照旧 `schtasks /Run` |

## 4. 验收

- Given 已有「明日方舟」窗口，When 点打开游戏或清日常或定时立刻执行，Then 不出现新的 UAC，清日常走现有 MAA 路径。
- Given 启动器在、没有游戏窗，When 点打开游戏或清日常，Then 立刻失败，文案要求在启动器点开始游戏；不拉 `Arknights.exe`、不弹 UAC。
- Given 启动器和游戏都不在，When 点打开游戏或清日常，Then 立刻失败，文案要求自己开启动器（UAC 自己点）；不 `ShellExecute Launcher.exe`。
- Given 打开看板方舟页，When 看按钮，Then 授权文案不再承诺「开游戏不弹 UAC」；没有「等待游戏窗口秒数」。

## 5. 最危险假设

1. 夜里定时在没开游戏时会「失败可见」而不是偷偷代开。验证：日志/任务 `last_error` 是认窗失败，没有新的 UAC。
2. 有窗时 MAA 计划任务仍不弹 UAC（本刀不改 MAA 拉起）。

## 6. 实现落点

- `maa_pc.open_pc_client`：只认窗，立刻失败；禁止 `start_detached(launcher)` 和 `run_task(GAME_TASK)`。
- `maa_elevate.authorize`：只注册 MAA / Stop。
- `maa_job` 快照 `elevate_ready` 改为看 `MAA_TASK`；文案「授权一次 MAA」。
- `board.html` 提示与按钮。
- 提交 `Fixes #8`。
