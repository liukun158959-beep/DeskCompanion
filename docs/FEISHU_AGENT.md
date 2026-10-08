# 将桌宠 Agent 接入飞书应用

飞书 CLI 提供机器人事件监听、消息回复、API schema 和嵌入的开发技能；应用配置、权限、事件订阅及发布流程见飞书官方开发文档。桌宠使用 CLI 管理凭证与长连接，不复制 App Secret 或用户 Token。

## 官方文档

- [飞书开放平台文档总索引](https://open.feishu.cn/llms.txt)
- [企业自建应用开发流程](https://open.feishu.cn/document/develop-process/self-built-application-development-process)
- [机器人概述](https://open.feishu.cn/document/client-docs/bot-v3/bot-overview)
- [使用长连接接收事件](https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case)
- [接收消息事件](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive)
- [回复消息 API](https://open.feishu.cn/document/server-docs/im-v1/message/reply)

长连接适用于企业自建应用。机器需要能够访问飞书公网服务，接收事件不需要公网 IP、域名或内网穿透；桌宠关闭或电脑离线时无法回复。当前接入仅接受绑定用户的私聊，不处理群聊或其他用户的消息。

## 配置应用

1. 复用 `lark-cli whoami` 显示的应用，在飞书开发者后台开启机器人能力。
2. **权限管理**：添加 `im:message.p2p_msg:readonly`（读取发给机器人的单聊消息）；回复开通 `im:message:send_as_bot`。官方回复接口也允许 `im:message` 或历史权限 `im:message:send`，开通一项即可。
3. **事件与回调 → 事件配置**：订阅方式选择「使用长连接接收」，添加 `im.message.receive_v1`（接收消息）。开启权限不等于完成事件订阅。
4. 创建版本、设置应用可用范围并发布；需要管理员审批的权限和版本须审批通过。确认本人能够在飞书搜索并私聊机器人。
5. 本机安装 Node 与 `lark-cli`，配置该应用，登录本人账户。已有配置和登录可直接复用；机器人收发使用应用身份，个人日程、待办等工具继续使用现有用户授权。
6. 桌宠主窗口 **飞书 → 在飞书使用桌宠 Agent → 接入飞书**。界面显示绑定应用、允许私聊的用户和连接状态。等待「已接入」后再发消息。

开启后重启桌宠会尝试恢复连接；「停止接入」关闭当前消费者并取消自动接入。首次绑定保存当前应用 profile、App ID 和登录用户 open_id；应用或用户变化时拒绝自动换绑。

## 在飞书使用

| 输入 | 行为 |
| --- | --- |
| 普通文字或富文本 | 调用桌宠当前模型和 Agent，可使用已配置的日程、待办、GitHub、搜索、记忆、MAA 等工具 |
| `/help` | 查看指令 |
| `/status` | 查看机器人接入状态 |
| `/new` | 新建飞书会话，保留旧历史 |
| `/skills` | 查看技能列表 |
| `/skill 技能名 问题` | 注入该技能正文执行这一轮 |
| `/kb 问题` | 调用桌宠知识库；需要已准备的知识库和模型 |
| `/mcps` | 查看本机已配置的 MCP 工具 |
| `/mcp 服务器名/工具名 问题` | 挂载并使用指定 MCP 工具 |

例：`今天有哪些日程和未完成待办？`、`查询 DeskCompanion 仓库最近的变更`。不要把示例技能名或 MCP 名当成已经安装的实际名称。

模型回复完成后以机器人身份回复原消息，长回答分段发送。当前不是流式卡片，不支持图片、文件、音视频问答；这些消息会收到文字提问提示。每个问题最多 16000 字。飞书会话与桌面当前会话分开保存，桌面和飞书共用 Agent 时串行执行；桌面操作会等待当前任务完成。

这相当于从飞书操作本机助手，绑定用户可以调用桌宠原有工具。模型接口、工具、技能及个人服务的权限仍以本机配置为准。当前消息采样固定为 low、temperature 0.5、top_p 1；不会把思考过程或异常堆栈发送到飞书。

## 长连接被占用

同一应用存在多个长连接时，飞书会在连接之间分配事件，不能保证每条消息到达桌宠。CLI 因此会在检测到其他服务连接时拒绝启动；桌宠保留这项检查。

`lark-cli event status --json`、`lark-cli event stop --app-id 应用ID` **只检查和停止本机 CLI bus**。本机没有 bus 而平台仍有在线连接时，须停止原设备/服务的监听进程，等平台连接超时清除，或改用另一个应用。CLI 没有远程踢掉未知连接的功能，见 [官方修复说明](https://github.com/larksuite/cli/pull/1454)。给 bot 执行用户登录无法解决连接占用或 bot 缺少 scope。

## 数据和恢复

`feishu_agent.json` 保存是否启用和绑定身份，不含凭证。`memory/feishu_agent.sqlite3` 保存消息去重、飞书会话映射及待回复内容；聊天仍使用现有聊天历史。两者都属于本机用户数据，不进入仓库或公开包。

事件消费者快速持久化消息，再由工作线程调用 Agent。消息以 App ID + message_id 去重，避免重推触发重复工具调用；event_id 只标识投递，不作为去重键。排队超过十分钟的请求不再执行。已生成的答案发送失败会重试发送，不重新运行 Agent；超过回复去重窗口或重试次数后保留失败记录。处理中断时不重跑可能已执行的工具，会提示本人先核对原任务结果。

CLI 网络异常按退避重连。权限、配置和连接占用错误显示在界面，修复后点击「重新接入」。没有出现 CLI 的 ready 标记时，不显示已接入。

## 验证范围

离线测试覆盖真实桌宠 Agent 的工具调用循环、消息过滤与去重、历史隔离、桌面与飞书并发、分段回复恢复、CLI 子进程 ready/NDJSON/stdin 关闭协议和界面启停。实际应用仍需在解除连接占用、配置好事件与权限后，在飞书私聊发一条消息完成收发验收。
