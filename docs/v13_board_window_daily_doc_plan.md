# V13 实施计划：飞书登录态、看板窗口、日报文档

> 2026-08-14。动作设计不在本轮。

## 0. 飞书「找到 CLI 但没登录」

`lark-cli auth status --json --verify` 成功时是扁平 JSON（`identity` / `identities.user`），**没有** `{ok:true,data:{}}` 信封。看板把「没有 ok」当成失败，整段 JSON 当错误，于是显示未登录、无权限。本机 whoami 已是 user「刘坤」，且 scope 里已有 calendar / task / docs。

## 1. 决策

| 项 | 选择 |
|----|------|
| 飞书状态 | 按真实 status JSON 解析；`identities.user.status=ready` 且 `tokenStatus=valid` 即已登录。权限看 scope 里是否有 `calendar:` / `task:` / `docx:` 或 `docs:` |
| 工具协议 | 人设页只读区拉高，占满剩余高度，可滚动看全文 |
| 看板窗口 | 系统标题栏：可改大小、最小化、最大化。关闭仍是隐藏。任务栏可见。不再置顶、不再当工具窗 |
| 日报 | 今日页一键：用今日日程+待办让模型写 Markdown，再 `docs +create --as user --doc-format markdown` 生成飞书文档并打开链接。登录域改为 calendar,task,docs |

## 2. 不做

- 不改宠物分层窗
- 不独占游戏式全屏（最大化即可）
- 不指定日报父文件夹（建在默认云空间）
