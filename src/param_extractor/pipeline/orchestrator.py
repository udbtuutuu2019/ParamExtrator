"""Orchestrator：状态机编排（设计 §3.3/§5；决策 D2/D6/D9）。

**保证永不抛异常**，永远返回定义终态（SUCCESS / REPAIRED / FALLBACK）。
"""
import time
import uuid
from typing import Optional

from ..config import Settings
from ..contracts.errors import ErrorType
from ..contracts.output import ExtractionOutput
from ..contracts.request import ExtractionRequest
from ..contracts.result import ExtractionResult, Status
from ..extraction.client import LLMClient
from ..extraction.prompts import SYSTEM_PROMPT
from ..fallback.fallback_handler import build_fallback
from ..guardrail.injection import detect_injection
from ..guardrail.pii_scan import apply_pii_policy, scan_pii
from ..guardrail.sanitizer import wrap_untrusted
from ..observability.logger import (
    log_guardrail,
    log_llm_call,
    log_pipeline_result,
    log_validation,
)
from ..repair.repair_engine import RepairEngine
from ..validation.validator import validate_content


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _classify_transport(e: Exception) -> str:
    n = type(e).__name__.lower()
    s = str(e).lower()
    if "timeout" in n or "timed out" in s:
        return ErrorType.TRANSPORT_TIMEOUT.value
    if "rate" in n or "429" in s:
        return ErrorType.RATE_LIMIT.value
    return "TRANSPORT_ERROR"


def _review_output(data: ExtractionOutput, cats, injection_suspected: bool) -> ExtractionOutput:
    """输出复核层（设计 §7.1 ⑤）：PII 策略 + 注入 urgency 保守化。"""
    updates = {"detected_pii": apply_pii_policy(data.detected_pii, cats)}
    if injection_suspected and data.urgency == "CRITICAL":
        updates["urgency"] = "MEDIUM"
    return data.model_copy(update=updates)


def run_pipeline(req: ExtractionRequest, client: LLMClient, settings: Settings) -> ExtractionResult:
    t0 = time.perf_counter()
    trace_id = req.trace_id or f"trc_{uuid.uuid4().hex[:8]}"
    attempts = 0
    last_err: Optional[str] = None
    fallback_pii = False
    try:
        # ① 空输入边界：不调用 LLM（Review Focus #1）
        if not req.content or not req.content.strip():
            return build_fallback(trace_id, "empty_input", attempts=0, latency_ms=_ms(t0))

        # ② 前置护栏
        matched, suspected = detect_injection(req.content)
        log_guardrail(trace_id, suspected, matched)
        cats, _local = scan_pii(req.content)
        fallback_pii = apply_pii_policy(False, cats)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": wrap_untrusted(req.content)},
        ]
        engine = RepairEngine()

        for attempt in range(settings.max_retries + 1):
            attempts += 1
            try:
                resp = client.extract(messages, temperature=settings.llm_temperature)
            except Exception as e:  # noqa: BLE001
                last_err = _classify_transport(e)
                log_llm_call(trace_id, settings.llm_model, _ms(t0), attempt, error_type=last_err)
                if attempt < settings.max_retries:
                    continue
                return build_fallback(trace_id, f"transport_error:{last_err}",
                                      fallback_pii, attempts, _ms(t0))

            log_llm_call(trace_id, settings.llm_model, _ms(t0), attempt)
            data, sig = validate_content(resp.content, finish_reason=resp.finish_reason)
            log_validation(trace_id, attempt, is_valid=(sig is None),
                           error_signature=sig, raw_snippet=resp.content)

            if data is not None:
                reviewed = _review_output(data, cats, suspected)
                status = Status.SUCCESS if attempt == 0 else Status.REPAIRED
                result = ExtractionResult(
                    status=status, data=reviewed, attempts=attempts,
                    repairs=max(attempts - 1, 0), needs_human_review=False,
                    failure_reason=None, trace_id=trace_id, latency_ms=_ms(t0))
                log_pipeline_result(trace_id, str(status), attempts, result.repairs, False,
                                    _ms(t0), suspected, reviewed.detected_pii)
                return result

            last_err = sig.error_type
            if engine.should_halt(sig):
                return build_fallback(trace_id, f"convergence_halt:{last_err}",
                                      fallback_pii, attempts, _ms(t0))
            if attempt == settings.max_retries:
                break
            messages.append({"role": "assistant", "content": resp.content})
            messages.append(engine.next_message(resp.content, sig))

        return build_fallback(trace_id, f"budget_exhausted:{last_err}",
                              fallback_pii, attempts, _ms(t0))
    except Exception as e:  # noqa: BLE001 —— 最后一道防线
        return build_fallback(trace_id, f"unexpected:{type(e).__name__}",
                              False, attempts, _ms(t0))
