"""测试用 MockLLMClient（计划 Task 5.2 的一部分，提前到 Task 4.3）。

脚本化：`script` 为 `LLMResponse` 或异常序列；用尽后重复最后一步（模拟持续故障）。
"""
from param_extractor.extraction.client import LLMResponse


class MockLLMClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self._last = LLMResponse(content="{}")

    def extract(self, messages, temperature: float = 0.0) -> LLMResponse:
        self.calls += 1
        if self.script:
            self._last = self.script.pop(0)
        step = self._last
        if isinstance(step, BaseException):
            raise step
        return step
