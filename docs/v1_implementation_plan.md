# V1 实施计划：Windows 桌宠个人助手

> grill-me 对齐后冻结。2026-08-14。
> 独立仓库（`e:\Learn_Project\desk-companion`），不进 Atlas git。后续再开 GitHub。

实施原则：每步立刻能跑一条命令验证；缺必填就失败并给出恢复指引；Windows / UTF-8 / 中文注释。

## 0. 决策速查表

| 决策项 | 最终选择 |
|--------|---------|
| 产品 | 个人助手；桌宠是入口，Atlas 是脑子 |
| 用户 | 只给作者本机用 |
| 壳 | Python 单进程，tkinter 透明置顶窗 + Pillow 画精灵 |
| 形象格式 | Codex Pet：`pet.json` + 精灵表，8×9，每格 192×208 |
| 默认形象 | 咕嘎（[codex-pet.org/pets/guga](https://codex-pet.org/pets/guga/)），素材不进 git |
| 换装 | 丢文件夹到 `skins/<名字>/` |
| V1 任务 | 气泡问今日安排：`lark-cli calendar +agenda` + `task +get-my-tasks --complete=false` |
| 对话 | 角色旁气泡，打字，无语音 |
| 飞书未登录 / 无皮肤 | 失败并写明怎么修，不静默跳过 |
| 与 Atlas 关系 | `pip install -e ..\Atlas` 后 import atlas，不把本项目放进 Atlas 仓库 |

## 1. 依赖顺序

```
Step 1 工程骨架（pyproject / 包 / skins 占位）
Step 2 Codex 形象包加载（缺文件即失败）
Step 3 置顶精灵窗 + idle 动画 + 拖动 + 右键退出/换肤
Step 4 气泡输入/输出
Step 5 飞书两个只读工具（lark-cli）
Step 6 接入 Atlas Agent，点气泡回车跑一轮
```

验证：每步 `python -c "..."` 或 `python -m desk_companion`（Windows）。

## Step 1：工程骨架

独立包 `desk_companion`。依赖：`pillow`、`python-dotenv`。Atlas 用可编辑安装，不写进本包的 git submodule。

## Step 2：形象包

读 `skins/<id>/pet.json`，解析 `spritesheetPath`（相对该文件夹）。精灵表必须能切出 8×9 格。缺 `pet.json`、缺图、idle 行全透明 → `RuntimeError`，文案含咕嘎下载地址。

## Step 3：窗体

`overrideredirect` + `-topmost` + `-transparentcolor` 品红抠透明。循环播 row0 idle。左键拖。右键：退出、列出 skins。

## Step 4：气泡

Toplevel 贴在角色左侧。输入框回车发送，回答区只展示文本。

## Step 5：飞书工具

`subprocess` 调 `lark-cli`（`creationflags=CREATE_NO_WINDOW`，`encoding=utf-8`）。命令不存在或非 0 退出：把 stderr 丢给 Agent 当工具错误字符串，system 里要求展示恢复指引 `lark-cli auth login --domain calendar,task`。

## Step 6：Atlas

`LLM()` + `Toolkit` 注册两个飞书工具 + `Agent(..., journal=InMemoryJournal(save_full_payload=True), max_steps=8)`。`run()` 放后台线程，思考播 waiting，结束回 idle，工具/Agent 异常播 failed。

启动：`python -m desk_companion`（可 `--skin guga`）。需本目录 `.env` 含 `ATLAS_API_KEY`（可从 Atlas 目录复制）。
