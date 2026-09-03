# V22 实施计划：无反复 UAC、安装 MAA、远控协同

> 2026-08-27。对齐用户五条：先拉启动器；PC 由桌宠开；桌宠与 MAA 协同；去掉每次 UAC；由我安装官方 MAA。

## 0. 决策

| 项 | 选择 |
|----|------|
| 开游戏 | 先 `Launcher.exe`，再启动 `Arknights.exe` |
| UAC | **不做漏洞绕过，也不点安全桌面上的「是」**。一次授权计划任务（最高权限），之后 `schtasks /Run` 不再弹 |
| MAA | winget 官方包 `MaaAssistantArknights.MaaAssistantArknights`（当前 6.16.8） |
| 协同 | 桌宠本机 `127.0.0.1` 提供 `getTask` / `reportStatus`；写入 MAA `gui.new.json`：连接 `PC` + 远控地址 |
| 权限 | 游戏因反作弊提升后，MAA 也必须同级，否则点不到窗口。MAA 走同一套计划任务启动 |

## 1. 为何不能「点确定」

UAC 默认在安全桌面。普通进程（含桌宠、自动化点击）碰不到那个「是」。关掉安全桌面等于降低系统安全，不做。

合法替代：当前用户、交互登录、`RunLevel Highest` 的计划任务。创建任务时弹 **一次** UAC；之后开游戏 / 开 MAA 不再弹。

## 2. 文件

- `maa_elevate.py`：注册/查询/运行计划任务
- `maa_remote.py`：本机 HTTP 远控
- `maa_maa_cfg.py`：改 MAA `gui.new.json`（PC 连接 + 加密远控 URI）
- 改 `maa_pc.py` / `maa_job.py` / `maa_config.py` / 看板

## 3. 验收

- 授权一次后，再点「打开游戏」不弹 UAC，出现 PC「明日方舟」窗口。
- `E:\` 或 WinGet 目录里有 `MAA.exe`；`maa.json` 的 `maa_exe` 已填。
- 点「开始清日常」：开游戏 → 拉起 MAA → 收到轮询 → 按勾选下发 `LinkStart-*`。未轮询到则失败原文，不假装清完。
