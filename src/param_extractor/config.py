"""集中式配置（设计 §9；决策记录见附录 C）。

优先级：环境变量 > config/default.yaml > 代码默认值。
"""
import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

_CONFIG_CANDIDATES = [
    Path("config/default.yaml"),
    Path(__file__).resolve().parents[2] / "config" / "default.yaml",
]


class Settings(BaseModel):
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: Optional[str] = None
    llm_temperature: float = 0.0
    llm_timeout_s: int = 30
    max_retries: int = 2
    retry_budget_policy: str = "shared"
    backoff_base_ms: int = 500
    injection_threshold: int = 1
    max_input_bytes: int = 32768
    fallback_urgency: str = "MEDIUM"
    log_level: str = "INFO"
    log_format: str = "json"


def _load_yaml() -> dict:
    for p in _CONFIG_CANDIDATES:
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def load_settings() -> Settings:
    load_dotenv(override=False)
    data = _load_yaml()

    # 环境变量覆盖（字段名大写）
    for field in Settings.model_fields:
        if field == "llm_api_key":
            continue
        env_val = os.environ.get(field.upper())
        if env_val is not None:
            data[field] = env_val

    # API Key：LLM_API_KEY 优先，回退 DEEPSEEK_API_KEY
    key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if key:
        data["llm_api_key"] = key

    return Settings.model_validate(data)
