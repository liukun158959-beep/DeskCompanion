# V15 实施计划：气泡首次漂移、缩小时白底、点击外部关闭

> 基于已复现现象与代码定位冻结。2026-08-15。

## 0. 决策

| 项 | 选择 |
|----|------|
| 首次漂移 | 隐藏时先算好物理像素位置和尺寸，在同一次 GUI 调用里写入 `Location/Size` 再 `Show`；打开时同步测量，禁止 80ms `requestFit` 二次跳 |
| 缩小时白底 | 逻辑 CSS 像素按窗口 DPI 换成物理像素再 `SetWindowPos`；窗体 `BackColor`/`WebView2` 保持全透明；禁止每次 `Show` 改 `EXSTYLE` |
| 点击外部关闭 | 宠物定时器里侦测左键按下：点在气泡或宠物上不关（宠物仍走原 toggle），其余区域关闭聊天和纸条 |

## 1. 首次显示不再漂移

1. `show_form` 不再每次 `apply_tool_window`（改 `EXSTYLE` 会打掉分层透明，并可能把窗弹回 WinForms 记住的旧坐标）。
2. 打开气泡：`showChat` 不触发 `requestFit` → 同步 `measureCard` → `_place_card` 算出物理坐标 → `Show` 前写入位置尺寸。
3. `_load_history` 在隐藏窗上不再 `requestFit`（`clientHeight` 不准）。

## 2. 缩小后不再露白底

1. `_place_card` 把 JS 逻辑宽高乘 `GetDpiForWindow/96`，与 `work_area`/头锚点同一套物理像素。
2. `_prepare_form` 对气泡：`AllowTransparency`、`BackColor` 全透明、`WebView2.DefaultBackgroundColor` 全透明、`DwmExtendFrameIntoClientArea(-1)`。
3. `apply_tool_window` 保留 `WS_EX_LAYERED`；改完样式后 `SWP_FRAMECHANGED`。
4. CSS `html,body` 明确 `rgba(0,0,0,0)`。

## 3. 点击气泡外关闭

宠物 `_tick` 已有的 `on_pet_tick` 里读 `GetAsyncKeyState(VK_LBUTTON)` 边沿。点在气泡矩形内或点在宠物身上不关（宠物仍走原 toggle），否则 `hide_bubble`。打开气泡时吞掉当前这次按下，避免看板按钮把刚打开的气泡立刻关掉。

## 4. 回归（启动白框 / 点击打不开）

日志：`GetDpiForWindow 返回 0`。改 `ShowInTaskbar` 会重建 HWND，旧句柄被拿去读 DPI，打开气泡全部失败。pywebview 透明窗导航时还会 `Show`，启动后留下白框。

处理：DPI 改读宠物 HWND；样式改完再缓存句柄；启动后强制隐藏且 Opacity=0，就位后再亮。
