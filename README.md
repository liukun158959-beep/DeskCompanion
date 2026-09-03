# DeskCompanion

Windows 上常驻的个人助手。桌宠是入口，Atlas 是脑子。作者本机自用：问飞书今日安排，托管长时间任务（第一例是明日方舟日常）。

不是安装包，不是多用户产品，不接插件市场。

## 本机跑

需要 Windows、Python 3.11+、本机已 `pip install -e` 的 Atlas 源码、以及本机 `gh` / `lark-cli`（看板对应页才会通）。

```powershell
pip install -e <Atlas目录>
pip install -e .
cd pet-ui
npm install
npm run build
cd ..
python -m desk_companion
```

Live2D Cubism Core 和形象包不在本仓库。Core 放到 `pet-ui/public/Core/live2dcubismcore.js`，皮肤放到 `skins/`。没有这些文件启动会失败并给出路径，不要靠默认形象凑合。

看板「模型」页填写 API Key。不要把 `.env`、账本、对话记录推进 Git。

## 仓库里有什么

- `desk_companion/` Python 壳：宠物窗、看板、飞书、MAA 远控、GitHub 状态
- `pet-ui/` Electron 凯尔希窗
- `docs/prd_desktop_pet.md` 产品拍板
- `skills/` 对话技能（写飞书总结、读日志、总结 GitHub）

## 不会进 Git 的

`.env`、`user_state.json`、`maa.json`、`arknights_account.json`、`memory/`、`skins/` 素材、`_refs/`、Live2D Core。

## GitHub 页

看板 GitHub 读当前 `gh` 登录账号下全部未归档仓库。路线图只认带 milestone 的未关闭 issue；卡片上的总结由这些 issue 拼出来，不编。对话里「总结某仓库最近」走技能 `github-repo-summary`，只在气泡里说。
