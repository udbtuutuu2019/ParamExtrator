"""Task 4.2 结构化日志单元测试（RED 先行）。"""
import json

from param_extractor.contracts.errors import ErrorSignature, ErrorType
from param_extractor.observability.logger import (
    log_guardrail,
    log_llm_call,
    log_pipeline_result,
    log_validation,
)


def test_log_llm_call_has_latency():
    rec = log_llm_call(trace_id="t", model="deepseek-chat", latency_ms=123, attempt_index=0)
    assert rec["event"] == "llm_call"
    assert rec["latency_ms"] == 123
    assert rec["model"] == "deepseek-chat"


def test_log_validation_carries_error_signature():
    sig = ErrorSignature(error_type=ErrorType.ENUM_MISMATCH, fields=["urgency"], messages=["bad"])
    rec = log_validation(trace_id="t", attempt_index=1, is_valid=False, error_signature=sig)
    assert rec["event"] == "validation"
    assert rec["error_signature"]["error_type"] == "ENUM_MISMATCH"
    assert rec["is_valid"] is False


def test_log_validation_redacts_snippet():
    rec = log_validation(trace_id="t", attempt_index=1, is_valid=False,
                         raw_snippet="我的密码是 SuperSecretPass123")
    assert "SuperSecretPass123" not in json.dumps(rec, ensure_ascii=False)


def test_log_pipeline_result_has_status_and_repairs():
    rec = log_pipeline_result(trace_id="t", status="REPAIRED", attempts=2, repairs=1,
                              needs_human_review=False)
    assert rec["status"] == "REPAIRED"
    assert rec["repairs"] == 1


def test_log_guardrail_has_injection_flag():
    rec = log_guardrail(trace_id="t", injection_suspected=True, matched_rules=["system_override"])
    assert rec["injection_suspected"] is True
    assert rec["matched_rules"] == ["system_override"]
