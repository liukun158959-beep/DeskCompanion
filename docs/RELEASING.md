# Windows 发布构建

当前产物是独立 x64 便携 ZIP。发布前需执行 Python、前端、Rust 和隔离运行时验证；发布脚本拒绝个人配置与日志。不要把整个开发工作目录压缩上传。

## 构建

PowerShell，在仓库根目录运行（output 必须是新的绝对目录）：

```powershell
python scripts/prepare_runtime.py --atlas ../Atlas --output C:/Build/DeskCompanion-runtime
python -m unittest discover -s tests -v
cd client
pnpm install --frozen-lockfile
pnpm test
pnpm exec tsc --noEmit
$env:DESK_RELEASE = '1'
pnpm tauri build --no-bundle
cd ..
python scripts/smoke_release.py C:/Build/DeskCompanion-runtime
python scripts/bundle_release.py --runtime-package C:/Build/DeskCompanion-runtime --output C:/Build/DeskCompanion-release
```

运行时取 [Python 官方 3.13.16 x64 嵌入包](https://www.python.org/downloads/release/python-31316/)，校验官方 SHA256 后解压。依赖版本固定在 `scripts/runtime-lock.txt`，包内记录 `runtime-packages.txt` 和 `runtime-provenance.json`。

Atlas 取源码库的固定提交 `85af8c1`，再应用明确保存的 `scripts/atlas-sampling.patch`，提供桌宠已使用的采样与思考流回调。补丁对应本机既有接口改动，不改变 Atlas 工作区或把其他未提交文件带入发布。后续 Atlas 正式合入该接口后应更新固定提交并移除补丁。

`DESK_RELEASE=1` 禁止 Vite 扫描开发机的 public 目录，只复制公开的启动脚本。Core、形象、个人模型权重、用户配置和历史不会嵌入 exe。公开包仅附入口卡片；用户可把自己的素材放入引导显示的 assets 目录。

`smoke_release.py` 使用发布包 Python，从空白用户目录启动真实后端，以本地模拟的 OpenAI 兼容 HTTP 服务完成模型保存、测试、流式回复、采样参数、历史记录和引导完成验证。不会连接作者的模型服务或读取个人配置。可再把 ZIP 解压到带空格或中文的新目录运行同一验证，检查可移动性。

## 发布

按仓库规则一刀一个 issue，提交 `Fixes #n: 中文说明。` 并直推 main。确认构建与测试后，创建对应版本 tag，将 ZIP 和 `SHA256SUMS.txt` 上传到 GitHub Release。发布说明需明确 Windows / WebView2 要求、配置引导、Live2D 素材和知识库扩展的准备条件，以及实机界面验收的范围。

本包没有安装器、自动更新器或代码签名。更新替换程序目录即可，用户数据仍在 `%LOCALAPPDATA%/DeskCompanion`。
