# desk-companion

Windows 上常驻的个人助手；桌宠是交互面，Agent 是脑子。第一版只给作者自己用。

## 语言

**桌宠（Pet）**:
常驻桌面的角色窗口（置顶、可拖、可点），是人和助手说话的入口。
_避免使用_: 监视器, overlay, companion platform

**助手（Assistant）**:
真正执行任务的 Agent，由桌宠转达输入并返回结果。
_避免使用_: 聊天机器人, Copilot, 编码监视器

**第一版（V1）**:
只在作者本机跑通即成功，不做安装包、不做开源分发、不做多用户。
_避免使用_: 产品化, Marketplace, 跨平台

**像素精灵（Sprite）**:
V1 的桌宠外观：图片或精灵表，不是 Live2D。形象必须可换成用户自己的素材。
_避免使用_: Live2D, Cubism, 口型同步

**今日安排（Daily Brief）**:
V1 要跑通的那一件事：点桌宠说话，用飞书日程和未完成任务回答「今天干什么」。
_避免使用_: IM 客户端, 编码监视器

**形象包（Skin）**:
一个 Codex Pet 文件夹：`pet.json` + `spritesheet.webp`（或 png）。8 列 × 9 行，每格 192×208。丢进 skins 即可换角色。
_避免使用_: 皮肤编辑器, Cubism 模型, 自造精灵格式

**咕嘎（Guga）**:
V1 默认形象。社区 Codex Pet（作者 CIRCUS），企鹅帽衫 Q 版。素材从 [codex-pet.org/pets/guga](https://codex-pet.org/pets/guga/) 获取，不把原图提交进本仓库。
_避免使用_: Wimi 内置角色（仓库里没有图）

**气泡对话（Bubble Chat）**:
点桌宠后在角色旁输入，回车发给 Atlas，回答仍在气泡。只要打字，不要语音。
_避免使用_: 独立大聊天窗, TTS, ASR

**壳（Shell）**:
同一 Python 进程：宠物用 Windows 分层窗（逐像素 Alpha），气泡和看板用 pywebview HTML，脑子是 Atlas。
_避免使用_: Electron sidecar, Tauri, 品红扣图

**今日看板（Daily Board）**:
独立窗：左侧今天日程时间轴，右侧未完成待办。托盘或右键打开。
_避免使用_: 控制中心, 设置页

**托盘（Tray）**:
常驻通知区入口。显示/隐藏宠物、打开看板、退出。关看板不等于退出。
_避免使用_: 后台服务, 开机安装包
