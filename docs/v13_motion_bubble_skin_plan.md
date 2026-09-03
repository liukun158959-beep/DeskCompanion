# V13 实施计划：悬挂/跑步节奏与咕嘎气泡皮肤

> grill-me 对齐后冻结。2026-08-14。

## 0. 决策

| 项 | 选择 |
|----|------|
| 顶部悬挂 | 12 帧总时长约 2.2 秒，`frameMs=184` |
| 跑步节奏 | 三类跑步均放慢约 40%：向左/向右 `frameMs=87`，通用跑 `frameMs=66` |
| 跑步位移 | 单轮由 160px 调整为 240px |
| 气泡皮肤 | 奶白肚皮、深灰描边、喙黄点缀；CSS 圆角 22px |
| 字体 | 站酷快乐体 ZCOOL KuaiLe，SIL OFL 1.1，本地嵌入 |

## 1. 动作

1. 只改 [`skins/guga/pet.json`](skins/guga/pet.json) 的 `cling-top` 与三类跑步 `frameMs`，不改素材帧。
2. [`desk_companion/pet.py`](desk_companion/pet.py) 的跑步归一化位移改为 240px。
3. 诊断同步校验终点 ±240px。

## 2. 气泡皮肤

1. 将 `ZCOOLKuaiLe-Regular.ttf` 与 `OFL.txt` 放入 `desk_companion/ui/fonts/`。
2. [`tokens.css`](desk_companion/ui/tokens.css) 用 `@font-face` 声明并作为界面字体。
3. [`bubble.html`](desk_companion/ui/bubble.html) 给 `.shell` 加 22px 圆角、奶白底和深灰描边；三角尾巴仍指向咕嘎，不被圆角裁切。
4. 不引入在线字体，缺文件时直接失败。

## 3. 验收

1. `cling-top` 一轮约 2208ms；向右跑一轮约 1740ms，终点 240px。
2. 气泡圆角可见，正文使用快乐体。
3. 编译与离线诊断通过。
