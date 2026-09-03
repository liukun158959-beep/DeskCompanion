# V34：lark-cli 找不到 node

> 2026-09-03。对话里飞书工具失败，原文是 `'"node"' 不是内部或外部命令`，却提示去看板登录。

## 根因

npm 全局 `lark-cli.cmd` 最终执行 `"node"`。Cursor 拉起的 Python 进程 PATH 经常没有 Node。exit 1 一律附上登录提示，把 PATH 问题说成没登录。

## 修复

合并用户/系统 PATH 之后用 `shutil.which("node")` 直接跑 `@larksuite/cli/scripts/run.js`。找不到 node 或 run.js 就失败原文，不要说去登录。

## 验收

Given 用户 PATH 里有 node 和 lark-cli，When 桌宠调今日日程，Then 不再出现「不是内部或外部命令」，也不再因此要求重新登录。
