"""Task 3.3 Repair Engine 单元测试（RED 先行）。"""
from param_extractor.contracts.errors import ErrorSignature, ErrorType
from param_extractor.repair.repair_engine import RepairEngine


def _sig(et=ErrorType.ENUM_MISMATCH, msgs=None):
    return ErrorSignature(error_type=et, messages=msgs if msgs is not None else ["m"])


def test_next_message_is_user_repair_prompt():
    msg = RepairEngine().next_message('{"urgency":"URGENT"}', _sig())
    assert msg["role"] == "user"
    assert '{"urgency":"URGENT"}' in msg["content"]


def test_should_halt_on_repeated_signature():
    eng = RepairEngine()
    s = _sig()
    assert eng.should_halt(s) is False
    assert eng.should_halt(s) is True


def test_should_not_halt_on_different_signatures():
    eng = RepairEngine()
    assert eng.should_halt(_sig(ErrorType.ENUM_MISMATCH, ["a"])) is False
    assert eng.should_halt(_sig(ErrorType.LENGTH_VIOLATION, ["b"])) is False
