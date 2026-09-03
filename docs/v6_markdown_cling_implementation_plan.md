# V6 实施计划：Markdown 企鹅卡、按字缩放、扒边动作文件

> grill-me 对齐后冻结。2026-08-14。

## 0. 决策速查表

| 项 | 选择 |
|----|------|
| Markdown | 只渲染咕嘎的话：粗斜体、列表、代码块、标题、https 链接。用户输入纯文本。本地 marked + DOMPurify，不许 img |
| 卡片 | 就一张企鹅卡。提醒时底部「我知道了」，点角色换成输入框。历史一直在，启动读 `memory/chat.jsonl` |
| 尺寸 | 按内容缩放。最小 280×180。最大 360×480，且不超过工作区 42%×55%。左右贴边再收窄，整块留在内侧 |
| 任务栏 | 气泡/看板设为工具窗，不出现 Python 图标 |
| 扒边 | 不画进 8×9 Codex 表。`skins/guga/cling-left.webp` 与 `cling-right.webp`：横条，每格 192×208，4–6 帧。缺文件启动失败并写清规格 |
| 行为 | 左右边 idle = 循环 cling。底/顶仍用原 idle。20–40 秒挥手只在底边 |

## 1. 扒边图怎么做

1. 画布：每帧 192×208，透明底，角色比例与现有咕嘎一致（企鹅连体衣）。
2. 姿态：身体贴着画面**左**缘，鳍在「抓住边」；脸朝右（屏幕内侧）。循环 4–6 帧，轻微拉扯即可。
3. 导出：帧从左到右拼成一张 webp 或 png，高 208，宽 = 192×帧数。
4. 右侧：镜像左侧，另存 `cling-right.webp`（脸朝左）。
5. 放到 `skins/guga/`，与 `spritesheet.webp` 同级。

## 2. 改哪些文件

1. `ui/bubble.html`：一张企鹅卡；历史在 `#log`；notice 底部「我知道了」，chat 底部输入框；咕嘎消息走 marked + DOMPurify。
2. `app.py`：启动灌 `chat.jsonl`；`fit_card` 按最小 280×180、最大 360×480 且工作区 42%×55% 钳制，左右边再收窄。
3. `winforms_host.py`：`ShowInTaskbar=False` + `WS_EX_TOOLWINDOW`；显示时不 `Activate`。
4. `skin.py` / `behavior.py` / `pet.py`：加载 cling 横条；左右 idle 播 cling；底边才挥手。

## 3. 不做

不用 idle 帧冒充扒边。缺 cling 文件启动失败。不把扒边画进 8×9 Codex 表。

