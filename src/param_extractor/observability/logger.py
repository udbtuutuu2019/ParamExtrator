"""结构化 JSON 日志（设计 §8；决策 D3）。

`log_event` 返回记录 dict（便于测试与断言），同时以 JSON 一行输出。
"""
import json
import logging
import sys
from typing import Optional

from ..contracts.errors import ErrorSignature
from .redaction import redact

_logger = logging.getLogger("param_extractor")
_logger.addHandler(logging.NullHandler())


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.handlers = [handler]
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    _logger.propagate = False


def log_event(event: str, **fields) -> dict:
    record = {"event": event, **fields}
    _logger.info(json.dumps(record, ensure_ascii=False, default=str))
    return record


def log_llm_call(trace_id: str, model: str, latency_ms: int, attempt_index: int = 0,
                 phase: str = "initial", error_type: Optional[str] = None) -> dict:
    return log_event("llm_call", trace_id=trace_id, model=model, latency_ms=latency_ms,
                     attempt_index=attempt_index, phase=phase, status=("error" if error_type else "ok"),
                     error_type=error_type)


def log_validation(trace_id: str, attempt_index: int, is_valid: bool = False,
                   error_signature: Optional[ErrorSignature] = None,
                   raw_snippet: Optional[str] = None) -> dict:
    return log_event(
        "validation",
        trace_id=trace_id,
        attempt_index=attempt_index,
        is_valid=is_valid,
        error_signature=(error_signature.model_dump(mode="json") if error_signature else None),
        raw_snippet=(redact(raw_snippet) if raw_snippet is not None else None),
    )


def log_pipeline_result(trace_id: str, status: str, attempts: int, repairs: int,
                        needs_human_review: bool, latency_ms: int = 0,
                        injection_suspected: bool = False, detected_pii: bool = False) -> dict:
    return log_event("pipeline_result", trace_id=trace_id, status=status, attempts=attempts,
                     repairs=repairs, needs_human_review=needs_human_review, latency_ms=latency_ms,
                     injection_suspected=injection_suspected, detected_pii=detected_pii)


def log_guardrail(trace_id: str, injection_suspected: bool, matched_rules) -> dict:
    return log_event("guardrail", trace_id=trace_id, injection_suspected=injection_suspected,
                     matched_rules=list(matched_rules))
