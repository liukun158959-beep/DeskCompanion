# V21 实施计划：MAA 选项对齐 + 打开 PC 客户端

> 2026-08-27。可行性见 `maa_pc_feasibility.md`。本刀只做两件能当场验收的事：选项和 MAA 一键长草对齐；打开鹰角启动器安装的 PC 客户端，不是安卓/模拟器。

## 0. 决策

| 项 | 选择 |
|----|------|
| 选项 | 8 项与 MAA 主界面同名；远控 type 用 `LinkStart-*`；肉鸽/生息默认不勾 |
| 勾选状态 | 独立 `maa.json`，不进 `user_state.json` |
| 开游戏 | 先确保鹰角 `Launcher.exe` 在跑，再启动 `Arknights.exe`，等到进程窗口出现 |
| 不清日常假成功 | 本机尚未装 MAA：开游戏可以；「开始清日常」在窗口起来后明确说缺 MAA，不下发假任务 |
| 入口 | 看板新页、右击菜单、对话工具走同一 `MaaController` |
| 不做 | 链 MaaCore、点启动器「开始游戏」按钮、开终末地、齿轮页、`:8848` |

## 1. 已知限制（实现里写进失败文案，不假装绕过）

1. MAA PC「开始唤醒」不能启动客户端（官方 #15794）。桌宠自己开游戏。
2. 鹰角启动器没有公开 CLI「启动明日方舟」。只开启动器会停在首页。
3. 因此本刀的打开路径是：**启动器进程 + 游戏目录里的 `Arknights.exe`**（该 exe 就是启动器下发的 PC 客户端）。不是 MAA 连模拟器。

## 2. 文件

- `desk_companion/maa_options.py`：8 项目录与默认勾选
- `desk_companion/maa_config.py`：读写 `maa.json`，缺键/缺路径失败并给填写指引
- `desk_companion/maa_pc.py`：按配置启动启动器与游戏，按 `Arknights.exe` 窗口判定打开
- `desk_companion/maa_job.py`：开游戏 / 开始 / 停止，后台线程，气泡汇报
- `desk_companion/maa_tools.py`：Atlas 工具
- 看板「明日方舟」页；Electron 右击「明日方舟」子菜单

## 3. 验收

- 看板上能勾 8 项，名称与上表一致；右击菜单同一份勾选。
- 点「打开游戏」后出现 PC「明日方舟」窗口（进程为 `Arknights.exe`），不是模拟器。
- 未填路径、启动器/游戏 exe 不存在、超时未出窗口：失败原文含怎么填 `maa.json`。
- 未填 `maa_exe` 时点「开始清日常」：会先尝试开游戏，然后说明清日常还不能下发。
