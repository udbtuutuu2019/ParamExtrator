"""Task 4.4 Ingestion 单元测试（RED 先行）。"""
from param_extractor.contracts.request import ExtractionRequest
from param_extractor.ingestion.ingest import (
    compute_idempotency_key,
    is_over_limit,
    normalize,
)


def _req(content="hello", **over):
    return ExtractionRequest(transcript_id="T", content=content, **over)


def test_normalize_strips_whitespace():
    assert normalize(_req("  hello \n")).content == "hello"


def test_normalize_removes_control_chars():
    r = normalize(_req("a\x00b\x07c"))
    assert "\x00" not in r.content
    assert "\x07" not in r.content


def test_normalize_unifies_newlines():
    assert normalize(_req("a\r\nb\rc")).content == "a\nb\nc"


def test_idempotency_key_stable_for_same_input():
    assert compute_idempotency_key(_req("x")) == compute_idempotency_key(_req("x"))


def test_idempotency_key_differs_for_different_content():
    assert compute_idempotency_key(_req("x")) != compute_idempotency_key(_req("y"))


def test_is_over_limit():
    assert is_over_limit(_req("x" * 40000)) is True
    assert is_over_limit(_req("small")) is False
