"""Task 5.3 必测场景 S1/S2/S3（挑战 §4；集成）。

行为在 Task 4.3 已 TDD；此处按挑战框架固化并覆盖日志断言。
"""
import json
import logging

from param_extractor.config import Settings
from param_extractor.contracts.request import ExtractionRequest
from param_extractor.contracts.result import Status
from param_extractor.extraction.client import LLMResponse
from param_extractor.pipeline.orchestrator import run_pipeline
from tests.fixtures.mock_client import MockLLMClient
from tests.fixtures.transcripts import TRANSCRIPTS

SETTINGS = Settings()


def _json(**over):
    base = dict(customer_id="CUST-98234", issue_category="BILLING", urgency="MEDIUM",
                summary="重复扣款已退款", actionable_steps=["确认到账"], detected_pii=False)
    base.update(over)
    return json.dumps(base)


def _req(tid="TX-001"):
    return ExtractionRequest(transcript_id=tid, content=TRANSCRIPTS[tid])


def test_s1_standard_success():
    client = MockLLMClient([LLMResponse(_json())])
    r = run_pipeline(_req("TX-001"), client, SETTINGS)
    assert r.status == Status.SUCCESS
    assert r.attempts == 1
    assert r.repairs == 0
    assert r.data.issue_category == "BILLING"


def test_s2_repair_recovery_logs_first_error(caplog):
    with caplog.at_level(logging.INFO, logger="param_extractor"):
        client = MockLLMClient([LLMResponse(_json(urgency="URGENT")), LLMResponse(_json())])
        r = run_pipeline(_req("TX-001"), client, SETTINGS)
    assert r.status == Status.REPAIRED
    assert r.repairs == 1
    assert any("ENUM_MISMATCH" in rec.getMessage() for rec in caplog.records)


def test_s3_budget_exhausted_fallback_no_exception():
    client = MockLLMClient([LLMResponse("这不是 JSON")])
    r = run_pipeline(_req("TX-004"), client, SETTINGS)
    assert r.status == Status.FALLBACK
    assert r.needs_human_review is True
