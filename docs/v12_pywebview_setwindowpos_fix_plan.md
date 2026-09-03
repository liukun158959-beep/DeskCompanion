# V12 实施计划：隔离 SetWindowPos ctypes 签名

> 基于异常堆栈完成 grill-me 原因对齐。2026-08-14。

## 0. 根因

`winforms_host.py` 在共享的 `ctypes.windll.user32.SetWindowPos` 上设置了强类型 `argtypes`。pywebview 的 WinForms 拖动实现使用 `SWP_NOSIZE`，并向宽高参数传入 `None`；共享签名将其强制解释为 `c_int`，因此抛出第 5 个参数类型错误。

## 1. 修复

1. 使用独立的 `ctypes.WinDLL("user32", use_last_error=True)` 实例绑定项目所需 Win32 API。
2. 只在私有函数对象上设置 `argtypes`，不污染 pywebview 使用的 `ctypes.windll.user32`。
3. `move_form` 与 `place_form` 的坐标、宽高在调用前显式转换为整数。
4. 不修改虚拟环境中的 pywebview 源码，不移除看板拖动能力。

## 2. 验收

1. 导入 `winforms_host` 前后，共享 `ctypes.windll.user32.SetWindowPos.argtypes` 保持不变。
2. 项目私有 `SetWindowPos` 仍使用完整的整数签名。
3. 编译和桌宠离线诊断通过。
4. 拖动 `.pywebview-drag` 标题栏时不再出现 `argument 5: wrong type`。
