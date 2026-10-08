"""源码运行沿用仓库目录；发布版由客户端指定独立用户目录。"""
import os
from pathlib import Path


def data_root() -> Path:
    value = os.environ.get("DESK_COMPANION_DATA_DIR")
    root = Path(value).expanduser().resolve() if value else Path(__file__).resolve().parents[1]
    root.mkdir(parents=True, exist_ok=True)
    return root


def asset_root() -> Path:
    value = os.environ.get("DESK_COMPANION_ASSET_DIR")
    return Path(value).resolve() if value else Path(__file__).resolve().parents[1] / "client/public"
