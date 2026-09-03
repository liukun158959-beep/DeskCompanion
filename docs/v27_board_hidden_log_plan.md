# V27 实施计划：看板隐蔽日志（含 MAA 出错段）

> 2026-08-31。产品已写进主 PRD §5「其后：看板隐蔽日志」。本刀只做看见原文，不做同趟再试、不下发 MAA。
> 同日夜补：分栏、重点、过滤、技能库。仍不做同趟再试。

## 0. 问题

**When** 桌宠崩了或清日常 / 仓库识别挂了
**I want** 看板页脚一个不抢主路径的「日志」，有问题标红；问凯尔希时她读到出错原文
**so I can** 分清是桌宠崩、还是 MAA 没进仓库，而不是猜网络

夜补：**When** 点开日志仍是一块糊在一起的原文
**I want** 重点先看见、桌宠和 MAA 分开、能过滤；分析有可复用规程且技能文件我能打开看
**so I can** 自己扫一眼，或让凯尔希按同一套规程说话

## 1. 非目标

- 同趟再试更新数据（下一刀）
- 出错自动弹 Agent、气泡红点、模型下发远控
- 整文件 / 失败 png 喂模型
- 日志搜索引擎、实时 tail
- 插件市场、运行时注册任意技能、Atlas RSI SkillLibrary（那是代码沙箱进化，不是规程）

技能库 = 仓库里 `skills/*/SKILL.md` 的目录，看板只读列出。不是 Toolkit 之外再搞一套能力平台。

## 2. Must

1. 页脚小字「日志」；今日有 CRASH / WATCHDOG / `maa_job` 失败 / MAA `gui.log`「任务出错」则标红。
2. 点开：重点区 + 桌宠 / MAA 分栏 + 按来源与类型过滤；仓库失败可附 `asst.log` 摘要和截图路径（文字）。没有则写明没有。
3. 「让凯尔希分析」由人点。对话须 `read_recent_errors` 再 `read_skill(maa-log-analysis)`。合同禁止编网络 / 森空岛、禁止根据分析再清日常。
4. 看板「技能」页列出全部 SKILL.md（名、何时用、正文、路径）。缺目录或缺文件失败可见。

## 3. 怎么读

| 来源 | 规则 |
|------|------|
| `desk_companion.log` | 今日行含 `CRASH` / `WATCHDOG` / `maa_job `（失败才写这一行） |
| `{MAA}/debug/gui.log` | 今日行含 `任务出错`。exe 来自 `maa.json` 的 `maa_exe` 同级 `debug` |
| `{MAA}/debug/asst.log` | 仅当今日 gui 有仓库相关任务出错时，截最近 Depot 链：`DepotAllTab` / `TaskChainError` / `Save image` / `DepotInfo`（仍有上限，禁止整文件） |

重点：最多 3 条，按崩溃/看门狗 → 清日常失败 → MAA 仓库出错 → 其它任务出错取最近一条。

## 4. 技能库

路径：`desk-companion/skills/<name>/SKILL.md`，YAML frontmatter 的 `name` 与文件夹一致。

本刀先放 `maa-log-analysis`。工具：`list_skills`（目录）、`read_skill`（正文）。Cursor 侧同一规程放在工作区 `.cursor/skills/maa-log-analysis/`，正文指向上述文件，避免两套说法。

## 5. 验收

- Given 今日无 CRASH/WATCHDOG/清日常失败且 MAA 无任务出错，When 打开看板，Then 页脚「日志」不红。
- Given 有今日 CRASH 或 `任务出错: 仓库识别`，When 点开日志，Then 重点区有对应条；桌宠栏和 MAA 栏不是同一个文本框。
- Given 点「桌宠」过滤，When 列表刷新，Then MAA 栏无条目或标明已过滤。
- Given 点「让凯尔希分析」，When 对话，Then 先 `read_recent_errors` 再 `read_skill`，解释对得上原文，不编网络。
- Given 打开看板「技能」，When 加载成功，Then 能看见 `maa-log-analysis` 的 description 和正文。
- Given `skills/` 目录不存在，When 打开技能页，Then 失败原文指向该路径，不假装没有技能是正常空态。
