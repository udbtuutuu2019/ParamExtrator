"""instructor 实现（设计 §3.7；决策 D2：`max_retries=0`）。

只负责调用与返回**原始 content**；校验由 `validation.validate_content` 负责（单一真相）。
"""
from typing import Any, Optional

from ..contracts.output import ExtractionOutput
from .client import LLMResponse


class InstructorClient:
    def __init__(self, instructor_client: Any, model: str,
                 timeout: Optional[float] = None, max_tokens: Optional[int] = None):
        self._client = instructor_client
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens

    def extract(self, messages: list[dict], temperature: float = 0.0) -> LLMResponse:
        kwargs: dict = dict(
            model=self._model,
            messages=messages,
            response_model=ExtractionOutput,
            max_retries=0,          # 决策 D2：重试全交自研层
            temperature=temperature,
        )
        if self._timeout is not None:
            kwargs["timeout"] = self._timeout
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        try:
            _parsed, raw = self._client.chat.completions.create_with_completion(**kwargs)
            return self._from_raw(raw)
        except Exception as e:  # noqa: BLE001
            raw = getattr(e, "last_completion", None)
            if getattr(raw, "choices", None):
                return self._from_raw(raw)
            raise

    @staticmethod
    def _from_raw(raw) -> LLMResponse:
        choice = raw.choices[0]
        msg = choice.message
        content = msg.content
        # function-calling 模式下 content 为空，结构化数据在 tool_calls.arguments
        if not content:
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                content = tool_calls[0].function.arguments
        return LLMResponse(
            content=content or "",
            finish_reason=getattr(choice, "finish_reason", None),
        )
