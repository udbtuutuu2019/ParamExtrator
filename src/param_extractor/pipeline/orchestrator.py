"""Orchestrator：状态机编排（设计 §3.3/§5；决策 D2/D6/D9）。

**保证永不抛异常**，永远返回定义终态（SUCCESS / REPAIRED / FALLBACK），
且每个出口都记录一条 `pipeline_result` 结构化日志（Final review C1）。
"""
import random
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
from ..ingestion.ingest import is_over_limit
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
    return ErrorType.TRANSPORT_ERROR.value


def _review_output(data: ExtractionOutput, cats, injection_suspected: bool) -> ExtractionOutput:
    """输出复核层（设计 §7.1 ⑤）：PII 策略 + 注入 urgency 保守化。"""
    updates = {"detected_pii": apply_pii_policy(data.detected_pii, cats)}
    if injection_suspected and data.urgency == "CRITICAL":
        updates["urgency"] = "MEDIUM"
    return data.model_copy(update=updates)


def _finish(result: ExtractionResult, injection_suspected: bool) -> ExtractionResult:
    """统一出货：记录 pipeline_result 后返回（杜绝漏日志）。"""
    log_pipeline_result(result.trace_id, str(result.status), result.attempts, result.repairs,
                        result.needs_human_review, result.latency_ms,
                        injection_suspected, result.data.detected_pii)
    return result


def run_pipeline(req: ExtractionRequest, client: LLMClient, settings: Settings) -> ExtractionResult:
    t0 = time.perf_counter()
    trace_id = req.trace_id or f"trc_{uuid.uuid4().hex[:8]}"
    attempts = 0
    last_err: Optional[str] = None
    suspected = False
    try:
        # ① 空输入边界：不调用 LLM（Review Focus #1）
        if not req.content or not req.content.strip():
            return _finish(build_fallback(trace_id, "empty_input",
                                          attempts=0, latency_ms=_ms(t0)), suspected)

        # ② 超长拒绝（Review Focus #5 / I4）：控制层拦截，不静默继续
        if is_over_limit(req, settings.max_input_bytes):
            return _finish(build_fallback(trace_id, "context_overflow:CONTEXT_OVERFLOW",
                                          attempts=0, latency_ms=_ms(t0)), suspected)

        # ③ 前置护栏
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
                    _sleep_backoff(settings, attempt)   # I2 退避
                    continue
                return _finish(build_fallback(trace_id, f"transport_error:{last_err}",
                                              fallback_pii, attempts, _ms(t0)), suspected)

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
                return _finish(result, suspected)

            last_err = sig.error_type
            if engine.should_halt(sig):
                return _finish(build_fallback(trace_id, f"convergence_halt:{last_err}",
                                              fallback_pii, attempts, _ms(t0)), suspected)
            if attempt == settings.max_retries:
                break
            messages.append({"role": "assistant", "content": resp.content})
            messages.append(engine.next_message(resp.content, sig))

        return _finish(build_fallback(trace_id, f"budget_exhausted:{last_err}",
                                      fallback_pii, attempts, _ms(t0)), suspected)
    except Exception as e:  # noqa: BLE001 —— 最后一道防线
        return _finish(build_fallback(trace_id, f"unexpected:{type(e).__name__}",
                                      False, attempts, _ms(t0)), suspected)


def _sleep_backoff(settings: Settings, attempt: int) -> None:
    """传输类错误的指数退避 + 抖动（设计 §6.3 / I2）。"""
    base = max(settings.backoff_base_ms, 0) / 1000.0
    if base <= 0:
        return
    delay = base * (2 ** attempt)
    time.sleep(delay * (0.5 + random.random() / 2))
