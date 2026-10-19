"""Task 4.3 Orchestrator 单元测试（RED 先行）。"""
import json
import logging

from param_extractor.config import Settings
from param_extractor.contracts.request import ExtractionRequest
from param_extractor.contracts.result import Status
from param_extractor.extraction.client import LLMResponse
from param_extractor.pipeline.orchestrator import run_pipeline
from tests.fixtures.mock_client import MockLLMClient
from tests.fixtures.transcripts import TRANSCRIPTS

SETTINGS = Settings(backoff_base_ms=0)  # 测试不真实退避


def _json(**over):
    base = dict(customer_id=None, issue_category="BILLING", urgency="MEDIUM",
                summary="ok", actionable_steps=[], detected_pii=False)
    base.update(over)
    return json.dumps(base)


def _req(text="订单有问题"):
    return ExtractionRequest(transcript_id="T-1", content=text)


def test_happy_path_success():
    client = MockLLMClient([LLMResponse(_json())])
    r = run_pipeline(_req(), client, SETTINGS)
    assert r.status == Status.SUCCESS
    assert r.attempts == 1
    assert r.repairs == 0


def test_repair_recovery():
    client = MockLLMClient([LLMResponse(_json(urgency="URGENT")), LLMResponse(_json())])
    r = run_pipeline(_req(), client, SETTINGS)
    assert r.status == Status.REPAIRED
    assert r.repairs == 1
    assert r.repairs == r.attempts - 1


def test_budget_exhausted_or_halt_fallback():
    client = MockLLMClient([LLMResponse("not json")])
    r = run_pipeline(_req(), client, SETTINGS)
    assert r.status == Status.FALLBACK
    assert r.needs_human_review is True


def test_empty_input_skips_llm():
    # Review Focus #1
    client = MockLLMClient([LLMResponse(_json())])
    r = run_pipeline(_req("   "), client, SETTINGS)
    assert r.status == Status.FALLBACK
    assert client.calls == 0


def test_incomplete_response_detected():
    # Review Focus #4
    client = MockLLMClient([LLMResponse("{}", finish_reason="length")])
    r = run_pipeline(_req(), client, SETTINGS)
    assert r.status == Status.FALLBACK
    assert "INCOMPLETE_RESPONSE" in (r.failure_reason or "")


def test_transport_timeout_fallback():
    client = MockLLMClient([TimeoutError("timed out")])
    r = run_pipeline(_req(), client, SETTINGS)
    assert r.status == Status.FALLBACK
    assert "TRANSPORT_TIMEOUT" in (r.failure_reason or "")


def test_malformed_response_unexpected_fallback():
    client = MockLLMClient([None])
    r = run_pipeline(_req(), client, SETTINGS)
    assert r.status == Status.FALLBACK


def test_card_tail_override_s5b():
    # Review Focus #3：模型返回 true，Harness 应输出 false
    client = MockLLMClient([LLMResponse(_json(detected_pii=True))])
    r = run_pipeline(_req(TRANSCRIPTS["TX-001"]), client, SETTINGS)
    assert r.status == Status.SUCCESS
    assert r.data.detected_pii is False


def test_injection_urgency_downgraded():
    client = MockLLMClient([LLMResponse(_json(urgency="CRITICAL"))])
    r = run_pipeline(_req(TRANSCRIPTS["TX-003"]), client, SETTINGS)
    assert r.status == Status.SUCCESS
    assert r.data.urgency != "CRITICAL"


# ---- Final review fixes (C1 / I4) ----

def test_fallback_emits_pipeline_result_log(caplog):
    with caplog.at_level(logging.INFO, logger="param_extractor"):
        client = MockLLMClient([LLMResponse("not json")])
        run_pipeline(_req(), client, SETTINGS)
    msgs = [r.getMessage() for r in caplog.records]
    assert any('"event": "pipeline_result"' in m and "FALLBACK" in m for m in msgs)


def test_fallback_log_carries_failure_reason(caplog):
    """FALLBACK 的 pipeline_result 日志必须带失败原因。

    线上据此按原因维度拆分告警（模型不收敛 vs 传输抖动，处置方式不同）。
    """
    with caplog.at_level(logging.INFO, logger="param_extractor"):
        client = MockLLMClient([LLMResponse("not json")])
        run_pipeline(_req(), client, SETTINGS)
    (line,) = [r.getMessage() for r in caplog.records
               if '"event": "pipeline_result"' in r.getMessage()]
    rec = json.loads(line)
    assert rec["status"] == "FALLBACK"
    assert rec["failure_reason"]
    assert rec["failure_reason"].startswith(("convergence_halt", "budget_exhausted"))


def test_empty_input_emits_pipeline_result_log(caplog):
    with caplog.at_level(logging.INFO, logger="param_extractor"):
        client = MockLLMClient([LLMResponse(_json())])
        run_pipeline(_req("   "), client, SETTINGS)
    msgs = [r.getMessage() for r in caplog.records]
    assert any('"event": "pipeline_result"' in m for m in msgs)


def test_over_limit_rejected_at_orchestrator():
    # I4: run_pipeline 直接调用也应拒绝超长（Review Focus #5）
    client = MockLLMClient([LLMResponse(_json())])
    r = run_pipeline(_req("x" * 40000), client, SETTINGS)
    assert r.status == Status.FALLBACK
    assert client.calls == 0


def test_backoff_delay_grows_exponentially(monkeypatch):
    # I2：传输错误指数退避
    from param_extractor.pipeline import orchestrator
    delays = []
    monkeypatch.setattr(orchestrator.time, "sleep", lambda s: delays.append(s))
    monkeypatch.setattr(orchestrator.random, "random", lambda: 1.0)
    s = Settings(backoff_base_ms=100)
    orchestrator._sleep_backoff(s, 0)
    orchestrator._sleep_backoff(s, 1)
    assert delays == [0.1, 0.2]
