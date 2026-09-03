"""本项目 .env：模型键与森空岛凭证。保存模型时保留已有 SKLAND_*。"""
from __future__ import annotations

from pathlib import Path

LLM_KEYS = ("ATLAS_API_KEY", "ATLAS_BASE_URL", "ATLAS_MODEL")
ENV_KEYS = LLM_KEYS
SKLAND_KEYS = ("SKLAND_TOKEN", "SKLAND_UID")
KNOWN_KEYS = LLM_KEYS + SKLAND_KEYS
SKLAND_TOKEN_HINT = (
    "本项目 .env 没有 SKLAND_TOKEN。"
    "浏览器登录 https://www.skland.com/ ，同一浏览器打开 "
    "https://web-api.skland.com/account/info/hg ，"
    "把 JSON 里 data.content 整串写成 SKLAND_TOKEN=。"
    "不要把这串发到对话里。"
)


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
        if key in KNOWN_KEYS:
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
    missing = [key for key in LLM_KEYS if not data.get(key)]
    if missing:
        raise RuntimeError(
            "本项目 .env 缺少 "
            + ", ".join(missing)
            + "。打开看板「模型」页填写 API 地址、模型名和 Key。"
        )
    return {key: data[key] for key in LLM_KEYS}


def require_skland_token() -> str:
    token = (parse_env_file().get("SKLAND_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(SKLAND_TOKEN_HINT)
    return token


def skland_uid() -> str:
    return (parse_env_file().get("SKLAND_UID") or "").strip()


def has_skland_token() -> bool:
    return bool((parse_env_file().get("SKLAND_TOKEN") or "").strip())


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
    existing = parse_env_file()
    lines = [
        f"ATLAS_API_KEY={api_key}",
        f"ATLAS_BASE_URL={base_url}",
        f"ATLAS_MODEL={model}",
    ]
    token = (existing.get("SKLAND_TOKEN") or "").strip()
    uid = (existing.get("SKLAND_UID") or "").strip()
    if token:
        if any(ch in token for ch in "\n\r"):
            raise RuntimeError("SKLAND_TOKEN 不能包含换行。")
        lines.append(f"SKLAND_TOKEN={token}")
    if uid:
        if any(ch in uid for ch in "\n\r"):
            raise RuntimeError("SKLAND_UID 不能包含换行。")
        lines.append(f"SKLAND_UID={uid}")
    env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
