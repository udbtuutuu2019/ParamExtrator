"""Fallback Handler（设计 §3.6；决策 D1/D6）。

产出**固定常量**保守默认对象；绝不抛异常。卡尾号策略在兜底路径同样生效（由 pii 参数决定）。
"""
from ..contracts.output import ExtractionOutput
from ..contracts.result import ExtractionResult, Status


def build_fallback(trace_id: str, reason: str, pii: bool = False,
                   attempts: int = 0, latency_ms: int = 0) -> ExtractionResult:
    data = ExtractionOutput(
        customer_id=None,
        issue_category="OTHER",
        urgency="MEDIUM",
        summary="自动提取失败，需人工复核",
        actionable_steps=["转交人工客服审核"],
        detected_pii=bool(pii),
    )
    return ExtractionResult(
        status=Status.FALLBACK,
        data=data,
        attempts=attempts,
        repairs=max(attempts - 1, 0),
        needs_human_review=True,
        failure_reason=reason,
        trace_id=trace_id,
        latency_ms=latency_ms,
    )
