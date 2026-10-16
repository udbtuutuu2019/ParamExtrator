"""演示：一个会**触发修复重试**的用例（纯 mock，无需 API Key）。

场景：模型首轮输出非法枚举（urgency="UNAVAILABLE"）
  → Harness 捕获错误签名 → 生成针对性修复提示 → 第 2 轮模型改对 → status=REPAIRED。

用法：python examples/run_retry_demo.py
"""
import json
import logging
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from param_extractor.config import Settings
from param_extractor.contracts.request import ExtractionRequest
from param_extractor.extraction.client import LLMResponse
from param_extractor.pipeline.orchestrator import run_pipeline

# ---- 捕获结构化日志事件 ----
_events = []


class _Capture(logging.Handler):
    def emit(self, record):
        _events.append(record.getMessage())


_logger = logging.getLogger("param_extractor")
_logger.addHandler(_Capture())
_logger.setLevel(logging.INFO)


# ---- 脚本化 mock：源数据在 tests/fixtures/mock_client.py，这里内联以免依赖 tests ----
class _MockClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self._last = None

    def extract(self, messages, temperature: float = 0.0):
        self.calls += 1
        if self.script:
            self._last = self.script.pop(0)
        step = self._last
        if isinstance(step, BaseException):
            raise step
        return step


# 首轮：urgency 非法（"UNAVAILABLE" 不在枚举内）
BAD = json.dumps({"customer_id": "CUST-98234", "issue_category": "BILLING",
                  "urgency": "UNAVAILABLE", "summary": "重复扣款",
                  "actionable_steps": [], "detected_pii": False}, ensure_ascii=False)
# 第 2 轮：改对
GOOD = json.dumps({"customer_id": "CUST-98234", "issue_category": "BILLING",
                   "urgency": "MEDIUM", "summary": "重复扣款",
                   "actionable_steps": [], "detected_pii": False}, ensure_ascii=False)


def main() -> int:
    client = _MockClient([LLMResponse(BAD), LLMResponse(GOOD)])
    req = ExtractionRequest(transcript_id="TX-RETRY",
                            content="[Transcript ID: TX-RETRY] 我昨天被重复扣了 150 美元。")
    result = run_pipeline(req, client, Settings(backoff_base_ms=0))

    print("=" * 70)
    print("事件序列（每秒一条 JSON）")
    print("=" * 70)
    for e in _events:
        print(" ", e)
    print("=" * 70)
    print(f"结果: status={result.status}  attempts={result.attempts}  "
          f"repairs={result.repairs}  urgency={result.data.urgency}")
    print(f"LLM 实际被调用次数: {client.calls}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
