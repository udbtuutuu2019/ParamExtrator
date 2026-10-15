"""Task 5.4 对抗测试 S5/S5b：PII 检测与卡尾号覆写（挑战 §3 用例 1/2）。"""
import json

from param_extractor.config import Settings
from param_extractor.contracts.request import ExtractionRequest
from param_extractor.pipeline.orchestrator import run_pipeline
from param_extractor.extraction.client import LLMResponse
from tests.fixtures.mock_client import MockLLMClient
from tests.fixtures.transcripts import TRANSCRIPTS

SETTINGS = Settings()


def _json(**over):
    base = dict(customer_id=None, issue_category="TECHNICAL", urgency="HIGH",
                summary="summary", actionable_steps=[], detected_pii=False)
    base.update(over)
    return json.dumps(base)


def test_s5_tx002_pii_true_via_local_scan():
    # 模型漏报（false），本地扫描兜底应为 true
    client = MockLLMClient([LLMResponse(_json(detected_pii=False))])
    r = run_pipeline(ExtractionRequest(transcript_id="TX-002", content=TRANSCRIPTS["TX-002"]),
                     client, SETTINGS)
    assert r.data.detected_pii is True


def test_s5b_card_tail_override_to_false():
    # Review Focus #3 / 决策 D1：模型误判为 true，Harness 应输出 false
    client = MockLLMClient([LLMResponse(_json(detected_pii=True))])
    r = run_pipeline(ExtractionRequest(transcript_id="TX-001", content=TRANSCRIPTS["TX-001"]),
                     client, SETTINGS)
    assert r.data.detected_pii is False
