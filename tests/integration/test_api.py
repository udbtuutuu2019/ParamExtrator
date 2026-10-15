"""Task 5.1 API 契约测试（RED 先行）。"""
import json

from fastapi.testclient import TestClient

from param_extractor.api.server import app, configure
from param_extractor.config import Settings
from param_extractor.extraction.client import LLMResponse
from tests.fixtures.mock_client import MockLLMClient


def _valid():
    return json.dumps({"customer_id": None, "issue_category": "BILLING", "urgency": "MEDIUM",
                       "summary": "ok", "actionable_steps": [], "detected_pii": False})


def test_extract_ok_returns_200():
    configure(client=MockLLMClient([LLMResponse(_valid())]), settings=Settings())
    resp = TestClient(app).post("/v1/extract", json={"transcript_id": "T", "content": "订单问题"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS"


def test_llm_failure_returns_200_fallback():
    # 决策 D6：失败一律 200
    configure(client=MockLLMClient([LLMResponse("bad")]), settings=Settings())
    resp = TestClient(app).post("/v1/extract", json={"transcript_id": "T", "content": "订单问题"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "FALLBACK"


def test_over_limit_returns_400():
    # Review Focus #5
    configure(client=MockLLMClient([LLMResponse(_valid())]), settings=Settings())
    resp = TestClient(app).post("/v1/extract", json={"transcript_id": "T", "content": "x" * 40000})
    assert resp.status_code == 400


def test_server_configures_logging():
    # I5：服务入口应初始化结构化日志
    import logging

    import param_extractor.api.server  # noqa: F401
    handlers = logging.getLogger("param_extractor").handlers
    assert any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler)
               for h in handlers)
