"""Task 1.3 配置单元测试（RED 先行）。"""
from param_extractor.config import Settings, load_settings


def test_defaults_match_global_constraints():
    s = load_settings()
    assert s.max_retries == 2
    assert s.llm_temperature == 0.0
    assert s.llm_model == "deepseek-chat"
    assert s.llm_base_url == "https://api.deepseek.com"
    assert s.max_input_bytes == 32768
    assert s.fallback_urgency == "MEDIUM"


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    monkeypatch.setenv("MAX_RETRIES", "3")
    s = load_settings()
    assert s.llm_model == "deepseek-flash"
    assert s.max_retries == 3


def test_settings_constructible_with_defaults():
    assert Settings().max_retries == 2
    assert Settings().llm_api_key is None
