"""Task 1.2 契约单元测试（RED 先行）。"""
import pytest
from pydantic import ValidationError

from param_extractor.contracts.errors import ErrorSignature, ErrorType
from param_extractor.contracts.output import ExtractionOutput
from param_extractor.contracts.request import ExtractionRequest
from param_extractor.contracts.result import ExtractionResult, Status


def _valid_output(**over):
    base = dict(customer_id=None, issue_category="BILLING", urgency="MEDIUM",
                summary="ok", actionable_steps=[], detected_pii=False)
    base.update(over)
    return base


def test_valid_output_passes():
    o = ExtractionOutput.model_validate(_valid_output())
    assert o.issue_category == "BILLING"
    assert o.urgency == "MEDIUM"


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(_valid_output(urgency="URGENT"))


def test_empty_summary_rejected():
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(_valid_output(summary=""))


def test_overlong_summary_rejected():
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(_valid_output(summary="x" * 201))


def test_extra_field_rejected():
    # Review Focus #2：幻觉字段必须被拒绝
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(_valid_output(hallucinated="boom"))


def test_request_minimal_and_optional_defaults():
    r = ExtractionRequest(transcript_id="TX-001", content="hi")
    assert r.customer_id_hint is None
    assert r.trace_id is None


def test_status_values():
    assert Status.SUCCESS == "SUCCESS"
    assert set(Status) == {Status.SUCCESS, Status.REPAIRED, Status.FALLBACK}


def test_result_construction():
    r = ExtractionResult(
        status=Status.SUCCESS, data=ExtractionOutput.model_validate(_valid_output()),
        attempts=1, repairs=0, needs_human_review=False, failure_reason=None,
        trace_id="trc_1", latency_ms=10)
    assert r.status == Status.SUCCESS
    assert r.repairs == 0


def test_error_type_members():
    assert ErrorType.INCOMPLETE_RESPONSE.value == "INCOMPLETE_RESPONSE"
    assert ErrorType.EXTRA_FIELD.value == "EXTRA_FIELD"


def test_error_signature_construction():
    s = ErrorSignature(error_type=ErrorType.ENUM_MISMATCH, fields=["urgency"], messages=["bad"])
    assert s.error_type == ErrorType.ENUM_MISMATCH
    assert s.raw_snippet is None
