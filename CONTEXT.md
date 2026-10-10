# desk-companion

Windows 上常驻的个人助手，作者本机自用。凯尔希桌宠是入口，Atlas 是脑子。不做多用户、安装包分发或插件市场。

## 当前架构

- 主入口：client/ 的 Tauri 2 + React + TypeScript 客户端，主窗和透明 Live2D 宠物窗。
- Rust 拉起 desk_companion.local_api.server，绑定本机随机端口；前端通过带进程 token 的 WebSocket 调用白名单 RPC，并接收对话流。
- Python 的 HeadlessApp 复用 App / BoardWorkbench 数据方法，通过 Atlas 组装模型与业务工具。
- python -m desk_companion 的 Electron / pywebview 旧入口仍保留。pet-ui/、Windows 窗口辅助模块、旧看板及资源仍有实际引用，不能当成无用文件删除。

## 已有能力与约束

- 多会话对话、模型清单与切换、思考和 token 统计、技能与临时 MCP 工具、飞书整篇文档注入。
- 当前线程去重后的全部正文参与上下文；超过输入预算才压缩，原文仍留在 memory/chat.jsonl。
- 跨会话事实由工具或用户写入 memory/facts.json。模型写入必须有当前用户原话作依据，工具没有成功回执不能声称记住。
- 飞书文档知识库使用本地向量检索和重排。笔记会话与普通对话分开，带来源引用，可导出 Markdown 或飞书文档。
- 飞书日程和待办、GitHub 状态与路线图、字幕视频学习及飞书知识库归档。
- 本地文件/文件夹读取、按知识库分组、文字工具栏、非阻塞附件窗口与全量 Agent 调试。游戏业务入口与工具已移除。
- 失败要说明原因和恢复方式，不编数据、不悄悄换来源。

## 文件和提交

个人配置、凭据、记忆、模型权重、游戏数据、Live2D 素材与生成产物均按 .gitignore 留在本机。历史文档保留为决策记录，阅读时以当前代码和更新的产品条款核对。

每项改动对应一个 GitHub issue，提交写 Fixes #编号: 中文说明。，直推 main，不开 PR。验证命令见 README。
