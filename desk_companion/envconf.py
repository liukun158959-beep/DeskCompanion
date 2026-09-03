"""本项目 .env：只认 ATLAS_API_KEY / ATLAS_BASE_URL / ATLAS_MODEL。"""
from __future__ import annotations

from pathlib import Path

ENV_KEYS = ("ATLAS_API_KEY", "ATLAS_BASE_URL", "ATLAS_MODEL")


def env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def parse_env_file() -> dict[str, str]:
    path = env_path()
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in ENV_KEYS:
            out[key] = value.strip().strip('"').strip("'")
    return out


def public_llm_env() -> dict:
    data = parse_env_file()
    key = data.get("ATLAS_API_KEY") or ""
    return {
        "base_url": data.get("ATLAS_BASE_URL") or "",
        "model": data.get("ATLAS_MODEL") or "",
        "has_key": bool(key),
    }


def require_llm_env() -> dict[str, str]:
    data = parse_env_file()
    missing = [key for key in ENV_KEYS if not data.get(key)]
    if missing:
        raise RuntimeError(
            "本项目 .env 缺少 "
            + ", ".join(missing)
            + "。打开看板「模型」页填写 API 地址、模型名和 Key。"
        )
    return {key: data[key] for key in ENV_KEYS}


def write_llm_env(*, api_key: str, base_url: str, model: str) -> None:
    api_key = (api_key or "").strip()
    base_url = (base_url or "").strip()
    model = (model or "").strip()
    if not api_key:
        raise RuntimeError("API Key 不能为空。")
    if not base_url:
        raise RuntimeError("API 地址不能为空。")
    if not model:
        raise RuntimeError("模型名不能为空。")
    if any(ch in api_key for ch in "\n\r") or any(ch in base_url for ch in "\n\r") or any(
        ch in model for ch in "\n\r"
    ):
        raise RuntimeError("配置不能包含换行。")
    text = (
        f"ATLAS_API_KEY={api_key}\n"
        f"ATLAS_BASE_URL={base_url}\n"
        f"ATLAS_MODEL={model}\n"
    )
    env_path().write_text(text, encoding="utf-8")
