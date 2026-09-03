---
name: github-repo-summary
description: 根据 GitHub 近 14 天的 commit、PR、issue 做克制的仓库回顾。用户要总结某仓库最近、回顾 GitHub、最近改了什么时使用。先拉工具原文，再按本技能结构说，不编，不写飞书。
---

# GitHub 仓库近期总结（只在气泡）

看板 GitHub 页已按仓库给出基于 milestone issue 的状态总结。对话里要回顾**最近提交 / PR** 时，仍必须先调用 `github_recent`，再 `read_skill`，技能名 `github-repo-summary`。不要写飞书文档，不要开 Issue。

## 结论只能来自工具原文

禁止：猜没出现的功能、把计划文档里的「下一刀」当成已经做完、补作者没推上去的本地改动。

工具写「无」的段落，回答里也写「无」，不要用「持续推进」填空。

## 回答结构（按这个顺序）

1. 一句结论：这 14 天有没有可核对的推送。
2. **做了什么**：只列 `github_recent` 里的 commit / 已合并 PR。没有则写「无」。
3. **还开着**：未关 PR；以及 roadmap 里带 milestone 的 issue。roadmap 空就原样复述恢复指引，不要改写成「暂无规划」。
4. **缺口**：工具里能看出的空档（没有 CI、没有 milestone、只有文档提交）。没有就写「无」。

## 红线

- 不要鸡汤，不要 emoji。
- 不要建议再跑一遍清日常或改 MAA。
- 两个仓库都要总结时，每个仓库单独调一次 `github_recent`，不要混成一段。
