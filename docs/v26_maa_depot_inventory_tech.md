# V26 技术方案（已拍板，主 PRD 已对齐，未开工）

> 产品决策见 `v26_maa_depot_inventory_plan.md`；整体顺序与数据三层见主 PRD。本文只写怎么改现有清日常链路。
> 2026-08-30。对照本机 MAA 6.16.8 `gui.new.json`、`DepotData.json`、远控协议。
> §8 四条已拍板，按推荐做。

## 0. 要解决的工程缺口

现在 `_dispatch_maa` 只做两件事：写远控 URI，再 `replace_linkstart(selected)` 下发若干 `LinkStart-*`。远控**没有**「更新数据」type。本机 GUI 勾了更新数据也不会跑。

本刀补三段，都挂在已有清日常线程上，不新开入口：

1. 拉起 MAA **之前**改 `TaskQueue` 的 `IsEnable`，并保证 `UserDataUpdate` 开着、间隔 Daily。
2. 下发 **一条** `LinkStart`（走主界面队列，才会进更新数据）。
3. `LinkStart` 汇报结束后读 `{MAA}/data/DepotData.json`，译名写入 `arknights_account.json` 的 `inventory`。

不链 DLL、不 OCR、不点小工具、不读 `OperBoxData.json`。

## 1. 现状锚点（代码已如此）

| 事实 | 位置 |
|------|------|
| 清日常后台线程开游戏后立刻 `_dispatch_maa`，下发完就返回，`_running` 变 false | `maa_job.py` |
| 写 `gui.new.json` 只改 PC 连接 + 远控 URI，**不动 TaskQueue** | `maa_maa_cfg.patch_maa_config` |
| 已在跑的管理员 MAA 会直接失败，要求先关再计划任务拉起 | `_dispatch_maa` |
| 本机队列最后一项已是 `UserDataUpdate`：`UpdateDepot=true`，`TriggerInterval=EveryTime`，`IsTriggered=true` | `config/gui.new.json` |
| 本机队列里肉鸽、生息 **`IsEnable` 都是 true**。今天靠 `LinkStart-*` 无视勾选才没误开 | 同上 |
| `DepotData.json`：`done` + `data`（itemId→整数）+ `syncTime`（ISO，含时区） | 今晚小工具已写出 |
| 译名表：`{MAA}/resource/item_index.json`，键=itemId，`name`=中文 | 官服 CN，不用 YoStar* |
| `arknights_account.json` **还不存在**；`.gitignore` 还没加这文件 | desk-companion 根 |

官方远控：`LinkStart` = 点主界面一键长草，等整段队列 idle 再 `reportStatus`（`SUCCESS`/`FAILED`）。`LinkStart-*` = 无视主界面勾选。更新数据只能跟 `LinkStart` 走。

官方「更新数据」和「小工具仓库识别」写的是**同一份** `DepotData.json`。间隔 Daily 看的是工具箱里的上次同步时间：今天已经手点扫过，第一次桌宠清日常可能 **OCR 跳过**，文件日期仍是今天——读仓应当成功。

## 2. 数据流

```
开始清日常
  → 开游戏（已有）
  → 写 gui.new.json：远控 URI（已有）+ TaskQueue.IsEnable + UserDataUpdate
  → 计划任务拉起 MAA（已有；管理员窗必须先关）
  → 等第一次 getTask 轮询（已有，90s）
  → replace_linkstart(["LinkStart"])     // 不再下发 8 条 LinkStart-*
  → 气泡：已交给 MAA，等长草结束再读仓
  → 等该 task id 的 reportStatus（可取消；超时失败）
  → 读 DepotData.json → 译名 → 合并 inventory
  → 气泡：清日常结束 + 扫仓结果（或失败原文）
```

问「今天刷什么」本刀**不实现**。只提供只读函数，给 V25 以后调用：文件没有 / `done!=true` / `syncTime` 不是本机今天 → `RuntimeError`，文案写先开一次清日常。

## 3. 写队列（`maa_maa_cfg`）

在现有 `patch_maa_config` 同一次写文件里做，不另存一份配置。MAA 必须未在跑（已有约束），否则刚写的队列不会被读到。

**只改这些字段，不重写关卡/基建/公招参数：**

| TaskType | IsEnable |
|----------|----------|
| StartUp | 勾了「开始唤醒」 |
| Recruit | 勾了「自动公招」 |
| Infrast | 勾了「基建换班」 |
| Fight | 勾了「理智作战」 |
| Mall | 勾了「信用购物」 |
| Award | 勾了「领取奖励」 |
| Roguelike | 勾了「自动肉鸽」 |
| Reclamation | 勾了「生息演算」 |
| UserDataUpdate | **恒 true**（不是第 9 个勾选） |

`UserDataUpdate` 另外强制：`UpdateDepot=true`，`TriggerInterval="Daily"`，`IsTriggered=true`。`UpdateOperBox` **不改**（结果不读）。

映射表放 `maa_options.py`，与 8 项 OPTIONS 一一对应，不许自造 TaskType。

**缺项怎么处理（无兜底）：**

- 没有 `TaskQueue` 或不是数组 → 失败：关掉 MAA，在主界面至少保存过一次任务队列。
- 8 项里某一 `TaskType` 找不到 → 失败：写明缺哪个。
- 没有 `UserDataUpdate` → 失败：在 MAA 主界面勾上「更新数据」并保存一次。不在桌宠里凭空拼一个任务对象。
- 同一 TaskType 出现两次 → 失败，不猜用哪条。

写完后的 JSON 仍 UTF-8、`ensure_ascii=False`。远控 URI 继续 DPAPI，与现在相同。

## 4. 下发与等待（`maa_remote` + `maa_job`）

`replace_linkstart` 可复用：传入 `["LinkStart"]`。

新增 `wait_report(task_id, timeout, cancel)`：轮询已有 `record_report`，匹配 `task==id`。

- 状态 `SUCCESS` → 进入读仓。协议写明一般成功失败都报 SUCCESS，因此 **SUCCESS 不等于扫仓成功**，只表示整段队列跑完。扫仓成不成功只看 `DepotData.json`。
- 状态 `FAILED` → 清日常失败原文；**不写** inventory（禁止沿用昨天当今天）。
- 用户点停止：已有 `enqueue_stop` + `_cancel`。等到取消或心跳确认后，读仓失败：「已停止，仓库未更新，再开一次清日常。」
- 超时：建议 **3 小时**（理智作战可能很长）。超时失败可见，不写仓。

行为变化（需要你确认）：今天下发完 `_running` 立刻变 false，可以再点一次清日常。本方案让 `_running` **保持到 LinkStart 汇报**，期间再点会走已有「动作还在跑」。这更接近「长任务」，也避免两趟抢同一份 `gui.new.json`。

对话仍立刻结束（`start_daily` 只 kick 线程）。进度仍走方舟气泡，不占对话轮。

一项都没勾：保持现状，不下发、不读仓。

## 5. 读仓与写入（新模块 `maa_depot.py`）

路径：`maa_exe.parent / "data" / "DepotData.json"`。译名：`maa_exe.parent / "resource" / "item_index.json"`（官服）。

**读仓失败（整次不写 inventory，不改 `depot_sync`）：**

- 文件不存在
- 不是对象，或 `done` 不是 true，或 `data` 不是对象
- **`data` 一个键都没有**（MAA 扫失败也会写 `done=true` + 空对象 + 今天的 `syncTime`；不当成功）
- `syncTime` 缺失 / 解析不出日期 / 转成本机日后不是今天
- `data` 里某值不是整数 ≥0
- 某个 itemId 在 `item_index.json` 没有 `name` 字符串

不把缺的件当 0。不猜中文名。

**写入 `desk-companion/arknights_account.json`（gitignore）：**

- 没有文件：写成 `{ "inventory": { 中文名: 数量, ... } }`。不编 `standing` / `potions` / 代理卡。
- 已有文件：根必须是对象；`inventory` 没有则建对象；有则必须是对象。用扫到的中文名**覆盖**对应键，**不删**其它键。
- 另写 `depot_sync` = 原始 `syncTime` 字符串，方便排错。不进飞书、不进 `user_state`。

V25 要用的 `常态事务代理卡`、药：扫不到就不出现。规划缺键失败，本刀不管。

抽检（实现后用人眼对游戏）：`3301` 技巧概要·卷1、`30135` D32钢、`4001` 龙门币。

只读函数（给 V25）：`require_today_inventory()` → 读账号 json 的 inventory，并用 `depot_sync` 判今天；过期/没有 → 失败原文。本刀可以先写成，桌宠对话还不挂工具。

## 6. 文件清单

| 文件 | 动作 |
|------|------|
| `maa_options.py` | 增加 `TASK_TYPE`：LinkStart-* → TaskType |
| `maa_maa_cfg.py` | `patch_maa_config` 增加 `selected`，写 TaskQueue |
| `maa_remote.py` | `wait_report` |
| `maa_depot.py` | 新建。读 Depot + 译名 + 合并 json |
| `maa_job._dispatch_maa` | 写队列、下发 `LinkStart`、等待、读仓、拼气泡 |
| `.gitignore` | `arknights_account.json` |
| 产品文档 | 已改过，本刀不再改策略表 |

不改看板勾选 UI（仍 8 项）。不改 `maa.json` 字段。不加测试脚本。

## 7. 失败可见（用户能看到的句子）

- 队列缺「更新数据」：先在 MAA 勾上并保存，关掉 MAA，再点清日常。
- MAA 已在跑（管理员）：先关 MAA，不要双击开。
- `LinkStart` 超时 / FAILED / 已停止：这次仓库没写入。
- `DepotData.json` 不是今天：更新数据被 Daily 跳过且没有今天的缓存，或扫仓任务出错。再开一次清日常；游戏窗不要最小化。
- `data` 为空：仓库识别没扫到件（常见于没进仓库界面）。这次仓库没写入；不要把空结果当成今天已同步。
- itemId 无中文名：写出缺的 id，检查 MAA `resource/item_index.json` 是否与游戏版本一致。

## 8. 已拍板（2026-08-30）

1. **`_running` 拉长到整段长草结束。** 下发完不当闲，避免两趟抢配置。对话仍立刻结束，进度走气泡。
2. **间隔 Daily。** 当天已手点过则可能不 OCR，读今天的文件算过。
3. **`UpdateOperBox` 保持 GUI 原值**，结果不进账本。
4. **译名失败整份不写仓。**
5. **`data` 为空对象整份不写仓、不改 `depot_sync`。** `LinkStart` SUCCESS 不够。
5. **`data` 为空对象整份不写仓、不改 `depot_sync`。** `LinkStart` SUCCESS 不够。

更大愿景（多号定制养成 / 日常 / 抽卡）不改变本刀：先把**这一号的仓**拿到、存对、能按今天查找。游戏百科、强度、抽卡另开刀，不先建知识库。

## 9. 验收（实现后当场做）

1. 桌宠只勾基建+信用+唤醒，关 MAA 后点清日常。`gui.new.json` 里 Roguelike/Reclamation 为 false，UserDataUpdate 为 true、Daily。日志有整段 `LinkStart`，没有误开肉鸽。
2. 队列跑完后 `DepotData.json` 的 `syncTime` 是今天且 `data` 非空（或今日已手点过则日期仍是今天、有货），`arknights_account.json` 有龙门币、没有代理卡键。空 `data` 不得改 `depot_sync`。
3. 清日常进行中再点开始：提示还在跑。
4. 中途停止：账号 json 的 `depot_sync` 不变成这一趟的失败时间，文案说仓未更新。
5. 把 `DepotData.json` 改成昨天的日期再调只读函数：失败，出现「先开一次清日常」。
