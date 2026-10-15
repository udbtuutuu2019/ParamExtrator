"""结果信封契约（设计 §4.3；决策 D6）。"""
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel

from .output import ExtractionOutput


class Status(StrEnum):
    SUCCESS = "SUCCESS"
    REPAIRED = "REPAIRED"
    FALLBACK = "FALLBACK"


class ExtractionResult(BaseModel):
    status: Status
    data: ExtractionOutput
    attempts: int
    repairs: int
    needs_human_review: bool
    failure_reason: Optional[str] = None
    trace_id: str
    latency_ms: int
