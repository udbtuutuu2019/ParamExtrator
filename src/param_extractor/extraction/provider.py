"""instructor 实现（设计 §3.7；决策 D2：`max_retries=0`）。

只负责调用与返回**原始 content**；校验由 `validation.validate_content` 负责（单一真相）。
"""
from typing import Any, Optional

from ..contracts.output import ExtractionOutput
from .client import LLMResponse


class InstructorClient:
    def __init__(self, instructor_client: Any, model: str):
        self._client = instructor_client
        self._model = model

    def extract(self, messages: list[dict], temperature: float = 0.0) -> LLMResponse:
        try:
            _parsed, raw = self._client.chat.completions.create_with_completion(
                model=self._model,
                messages=messages,
                response_model=ExtractionOutput,
                max_retries=0,          # 决策 D2：重试全交自研层
                temperature=temperature,
            )
            return self._from_raw(raw)
        except Exception as e:  # noqa: BLE001
            raw = getattr(e, "last_completion", None)
            if getattr(raw, "choices", None):
                return self._from_raw(raw)
            raise

    @staticmethod
    def _from_raw(raw) -> LLMResponse:
        choice = raw.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            finish_reason=getattr(choice, "finish_reason", None),
        )
