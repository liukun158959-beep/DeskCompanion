# V18 实施计划：凯尔希 Live2D 替换咕嘎（Electron + Pixi 同窗气泡）

> 2026-08-17 对齐：方案 A。桌宠壳改 Electron，气泡和角色同一透明页。看板/Atlas/飞书留 Python。

## 0. 决策

| 项 | 结论 |
|----|------|
| 壳 | 新建 `pet-ui/`：Electron 透明窗 + PixiJS + pixi-live2d-display |
| 气泡 | 与角色同一 HTML 页，窗外透明；配色改冷白/青灰，字体用微软雅黑，去掉快乐体 |
| 看板 | 仍是 Python pywebview 普通窗 |
| 脑子 | Atlas / 飞书 / 记忆 / 人设仍在 Python，TCP 行协议连 Electron |
| 咕嘎逐帧 | 运行时删除。不双轨、不 fallback |
| 跑跳 cling | 不做。半身办公角色：可拖、默认右下、点开聊天、双击看板 |
| 模型 | 拷到 `skins/kaltsit/`，ASCII 文件名，补 Motions / 眨眼 / 口型 |

## 1. 不做

不把整份 `ai-live2d-go` 搬进来。不接 live2d-py。不保留独立 WebView 气泡。不把 `.cmo3` 打进运行时。

## 2. 结构

```
Python desk_companion          Electron pet-ui
  看板 / 托盘 / Agent             透明窗：Live2D + 气泡
  memory / feishu / state         拖动、点击、缩放、右键表情
           \                    /
            127.0.0.1 TCP 行 JSON
```

启动：`python -m desk_companion` 听端口，拉起 `pet-ui` 的 Electron，缺 `npm install && npm run build` 则失败并给出恢复指引。

## 3. 动作映射

| 状态 | 模型 |
|------|------|
| 待机 | Idle：`M3待机` + `待机动耳朵` |
| 忙（说话/办公） | 参数 `Param4` 办公中 |
| 失败 | 动作 `烦躁` |
| 纸条/搭话 | 动作 `疑问` |
| 回复结束 | 动作 `叹气` |
| 右键 | 惊讶 / 冷汗 / 我的愿望 / 分针 |

## 4. 交互

- 单击角色：开/关聊天气泡（尖尾向右，锚在头左侧）
- 双击：打开看板
- 拖角色：移动整窗，不贴边、不落地
- 滚轮：缩放 1 / 1.5 / 2
- 点空白桌面：关气泡（Electron 把 HWND 回传，Python 沿用外部点击判断）
- 透明像素点击穿透

## 5. 验收

启动后右下角是凯尔希半身，周围能看到桌面；开聊天圆角外也是桌面，不是白/品红；看板和对话仍走现有 Agent。
