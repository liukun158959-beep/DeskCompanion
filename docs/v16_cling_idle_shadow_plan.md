# V16 实施计划：侧边 cling 放缓、消黑蒙、静止不晃、右缘贴边

> grill-me 对齐后冻结。2026-08-15。推荐项全选；cling-right 贴边为补充项。

## 0. 决策

| 项 | 选择 |
|----|------|
| 左右 cling 节奏 | `frameMs=220`，一轮 2.64 秒。不重绘 |
| 黑色蒙层 | 去掉地面影；`clean_rgba` 清掉半透明近黑边 |
| 静止波动 | 待机钉在 idle 第 0 帧，眨眼/笑照常；只在画面变化时 `UpdateLayeredWindow` |
| cling-right 偏左 | 贴边 bbox 忽略脏透明；加载时把右 cling 各帧不透明区齐到格子右缘 |

## 1. 原因（已测量）

1. 左右 `117ms`、顶部 `184ms`。左右每帧摆幅远大于顶部，所以更急。
2. 脚下椭圆影仍在画；半透明描边里近黑 RGB 预乘后发暗。源图 alpha 正常，不是整窗黑底。
3. idle 12 帧是 4 张同姿势不同画，120ms 整身换像素；16ms 无条件刷新分层窗再闪一层。代码正弦 bob 已不存在。
4. cling-right 角色距格右缘约 42px。`getbbox()` 把 alpha=11 的脏角算进并集，右内边变成 0，贴边算完人还悬在屏内。

## 2. 改哪些

1. `skins/guga/pet.json`：`cling-left` / `cling-right` 的 `frameMs` 改为 220。
2. `skin.py`：近黑半透明像素清成全透明；右 cling 加载后齐右缘。
3. `pet.py`：待机不推进帧；`_paint` 画面没变不 blit；贴边用 `opaque_bbox`；不再合成地面影。
4. `diagnose.py`：左右 cling `frameMs` 断言改为 220。

## 3. 不做

不重绘 webp，不冻眨眼/笑，不改跑步/顶部悬挂时序。
