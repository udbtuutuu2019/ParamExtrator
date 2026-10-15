"""Task 2.1 Validator 单元测试（RED 先行）。"""
import json

from param_extractor.contracts.errors import ErrorType
from param_extractor.validation.validator import validate_content


def _valid(**over):
    base = dict(customer_id=None, issue_category="BILLING", urgency="MEDIUM",
                summary="ok", actionable_steps=[], detected_pii=False)
    base.update(over)
    return json.dumps(base)


def test_valid_content_ok():
    data, sig = validate_content(_valid())
    assert sig is None
    assert data is not None and data.issue_category == "BILLING"


def test_json_decode_error():
    data, sig = validate_content("这不是 JSON")
    assert data is None
    assert sig.error_type == ErrorType.JSON_DECODE


def test_enum_mismatch():
    data, sig = validate_content(_valid(urgency="URGENT"))
    assert data is None
    assert sig.error_type == ErrorType.ENUM_MISMATCH
    assert "urgency" in sig.fields


def test_length_violation():
    data, sig = validate_content(_valid(summary="x" * 201))
    assert sig.error_type == ErrorType.LENGTH_VIOLATION
    assert "summary" in sig.fields


def test_missing_field():
    d = json.loads(_valid())
    del d["detected_pii"]
    data, sig = validate_content(json.dumps(d))
    assert sig.error_type == ErrorType.MISSING_FIELD


def test_extra_field():
    # Review Focus #2：幻觉字段 → EXTRA_FIELD
    d = json.loads(_valid())
    d["hallucinated"] = "boom"
    data, sig = validate_content(json.dumps(d))
    assert sig.error_type == ErrorType.EXTRA_FIELD


def test_type_error():
    data, sig = validate_content(_valid(detected_pii={"x": 1}))
    assert sig.error_type == ErrorType.TYPE_ERROR


def test_incomplete_response_by_finish_reason():
    # Review Focus #4：截断
    data, sig = validate_content("{}", finish_reason="length")
    assert data is None
    assert sig.error_type == ErrorType.INCOMPLETE_RESPONSE


def test_never_raises_on_garbage():
    for bad in ["", None, 123, "{broken"]:
        data, sig = validate_content(bad)  # type: ignore[arg-type]
        assert data is None and sig is not None
