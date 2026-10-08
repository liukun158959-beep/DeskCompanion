# DeskCompanion 0.2.0 使用说明

## 启动

1. 下载 `DeskCompanion-0.2.0-windows-x64.zip`，解压到你选择的目录。不要直接从压缩包内运行，也不要只复制 exe。
2. 双击 `DeskCompanion.exe`。`runtime` 文件夹必须保留在旁边。Python 与 Atlas 已随包提供，普通使用不需要开发环境。
3. 主窗显示启动动画，然后进入首次引导。缺少桌宠素材时，桌宠窗显示入口卡片，点击可打开主窗。

支持 Windows 10/11 x64。需安装 Microsoft Edge WebView2 Runtime；若系统缺少，请从 [微软官方下载页](https://developer.microsoft.com/microsoft-edge/webview2/) 安装 Evergreen Runtime。当前包尚未做代码签名；Windows 可能显示未知发布者提示。

## 连接模型

主窗左侧 **设置 → 模型**，或首次引导第二步：

| 字段 | 去哪里取 | 填写示例 / 注意 |
| --- | --- | --- |
| API 地址 | 服务商控制台的 OpenAI 兼容接口 Base URL | 如 `https://api.example.com/v1`；这是示例，不能直接使用。不要填网页聊天链接、`/chat/completions` 或 `/responses` |
| 模型名 | 服务商模型列表中的模型 ID | 准确复制大小写和版本；模型必须支持 Chat Completions，调用工具还需支持 tool calling |
| API Key | 服务商控制台创建的 API 密钥 | 放入密码框；网页账号或订阅不一定包含 API 额度 |

先 **保存模型**，再 **测试连通**。测试会给服务商发一条简短请求，可能计费。保存成功只表示配置已写入，并不代表已连通。

- 401 / 403：确认 Key、权限和额度；不同服务商的 Key 不能混用。
- 404：确认 Base URL 和模型 ID。
- 超时 / 连接失败：确认网络、服务地址和服务商状态。
- 普通聊天成功但工具失败：确认模型支持 tool calling。

Key 保存在本机 `.env` / `models.json` 中，界面不会回显。对话和使用工具产生的上下文会发给配置的模型服务。不要在聊天中粘贴密钥，也不要共享包含密钥的截图或备份。

## 可选功能与填写位置

这些功能不影响普通对话。设置页的 **打开使用引导** 可以再次查看准备状态和实际目录。

| 功能 | 准备内容 | 入口 |
| --- | --- | --- |
| 飞书 | 安装 `lark-cli` 和 Node；运行 `lark-cli config init` 配置应用，然后登录并授权实际使用的范围 | 看板 → 飞书 |
| GitHub | 安装 [GitHub CLI](https://cli.github.com/)，运行 `gh auth login` | 看板上的 GitHub 状态卡；对话 `/` 选择仓库与 GitHub 工具 |
| MAA | 安装游戏和 MAA，填写启动器、游戏、MAA 路径，配置远控端口及权限 | 看板 → 自动化任务 → 明日方舟 |
| 森空岛 | 在用户目录 `.env` 增加 `SKLAND_TOKEN=你的Token`；多账号可增加 `SKLAND_UID=` | 明日方舟页的森空岛同步；不要把 Token 发到聊天 |
| 知识库 | 运行「安装知识库扩展.cmd」，重启；下载向量与重排模型，登录飞书后添加文档 | 左侧知识库；权重不随包提供，首次下载较大 |
| MCP | 在用户目录建立 `mcp.json`，配置 stdio 服务器的 command / args / env，并安装服务器自身的运行环境 | 对话输入框 `/` → MCP 工具 |
| 提示词、主题和背景 | 提示词无需修改即可使用；主题和背景可按喜好调整 | 设置 |
| Live2D 形象 | 自行准备合法取得的 Cubism Core、凯尔希模型及所有引用素材 | 下述素材目录；放好后重启 |

MCP 配置格式（服务器程序只是示例，请替换为已安装的实际程序；当前不支持 URL 类型服务器）：

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "C:/Tools/my-mcp-server.exe",
      "args": [],
      "env": {}
    }
  }
}
```

## 桌宠形象

公开包不包含 Live2D Cubism Core 和凯尔希素材。放置目录：

```text
%LOCALAPPDATA%/DeskCompanion/assets/
  Core/live2dcubismcore.js
  skins/kaltsit/kaltsit.model3.json
  skins/kaltsit/模型引用的 moc3、贴图、动作、表情等素材
```

模型引用的相对路径必须完整保留。配置后重启；形象窗支持拖动、点击、右键菜单和隐藏，主窗的「唤出桌宠」可再次显示。缺少或损坏素材时保留主窗入口并显示错误，不会阻止对话使用。

## 数据、升级和故障恢复

便携版把配置、聊天、记忆、笔记、模型缓存、素材及日志保存在 `%LOCALAPPDATA%/DeskCompanion`。使用引导中显示的路径为准。源码开发版继续沿用仓库目录。

升级时退出客户端，替换程序目录或解压新版本到新目录；保留用户数据目录。备份时先退出，再复制整个用户数据目录。备份包含密钥和账号信息，请妥善保管。删除程序目录不会删除用户数据；若要彻底重置，先备份，再删除用户目录。

启动失败查看用户目录的 `backend.log` / `desk_companion.log`。提示运行环境缺失时重新完整解压发布包；形象加载失败时检查 Core 和模型引用路径。连接失败先核对模型设置，再测试连通。外部服务的账号、网络与授权问题须在对应页处理。

## 构建与验证

见 [发布构建说明](RELEASING.md)。本版本的首发验证包括隔离目录下的模型保存、HTTP 连通测试、真实 WebSocket 流式回复、采样参数、历史记录和引导完成；模型请求由本地模拟服务接收，不使用作者的密钥和个人资料。界面交互有组件级自动测试；原生窗口的视觉效果仍需实际体验验收。
