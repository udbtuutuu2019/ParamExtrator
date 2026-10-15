"""LLM 客户端接口（设计 §3.7；决策 D2：调用方控重试）。"""
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    content: str
    finish_reason: Optional[str] = None


@runtime_checkable
class LLMClient(Protocol):
    def extract(self, messages: list[dict], temperature: float = 0.0) -> LLMResponse:
        ...
