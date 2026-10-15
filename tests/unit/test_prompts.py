"""Task 3.2 提示词单元测试（RED 先行）。"""
from param_extractor.contracts.errors import ErrorSignature, ErrorType
from param_extractor.extraction.prompts import SYSTEM_PROMPT, build_repair_prompt

ENUMS = ["BILLING", "TECHNICAL", "ACCOUNT", "OTHER",
         "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_system_prompt_has_security_statement():
    assert "untrusted_user_data" in SYSTEM_PROMPT
    assert "忽略" in SYSTEM_PROMPT


def test_system_prompt_lists_all_enums():
    for v in ENUMS:
        assert v in SYSTEM_PROMPT


def test_repair_prompt_includes_raw_output_and_errors():
    sig = ErrorSignature(error_type=ErrorType.ENUM_MISMATCH, fields=["urgency"],
                         messages=["urgency: 'URGENT' is not valid"])
    out = build_repair_prompt('{"urgency": "URGENT"}', sig)
    assert '{"urgency": "URGENT"}' in out
    assert "urgency: 'URGENT' is not valid" in out


def test_repair_prompt_requires_json_only():
    sig = ErrorSignature(error_type=ErrorType.JSON_DECODE, messages=["invalid JSON"])
    out = build_repair_prompt("bad", sig)
    assert "JSON" in out
    assert "不要" in out


def test_repair_prompt_truncates_long_raw_output():
    sig = ErrorSignature(error_type=ErrorType.LENGTH_VIOLATION, messages=["too long"])
    out = build_repair_prompt("x" * 5000, sig)
    assert len(out) < 5000
