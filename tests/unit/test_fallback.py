"""Task 4.1 Fallback Handler 单元测试（RED 先行）。"""
from param_extractor.contracts.result import Status
from param_extractor.fallback.fallback_handler import build_fallback


def test_fallback_status_and_review_flag():
    r = build_fallback(trace_id="trc_1", reason="budget_exhausted")
    assert r.status == Status.FALLBACK
    assert r.needs_human_review is True


def test_fallback_fixed_constants():
    r = build_fallback(trace_id="trc_1", reason="x")
    assert r.data.customer_id is None
    assert r.data.issue_category == "OTHER"
    assert r.data.urgency == "MEDIUM"
    assert r.data.summary != ""
    assert r.data.actionable_steps == ["转交人工客服审核"]
    assert r.data.detected_pii is False


def test_fallback_pii_flag_propagates():
    assert build_fallback(trace_id="t", reason="x", pii=True).data.detected_pii is True


def test_fallback_carries_reason_and_counts():
    r = build_fallback(trace_id="t", reason="convergence_halt", attempts=3, latency_ms=42)
    assert r.failure_reason == "convergence_halt"
    assert r.attempts == 3
    assert r.repairs == 2
    assert r.latency_ms == 42
