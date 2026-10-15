"""输出契约（设计 §4.2；决策 G2/D1）。"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExtractionOutput(BaseModel):
    # extra="forbid"：拒绝幻觉字段（Review Focus #2，决策 G2）
    model_config = ConfigDict(extra="forbid")

    customer_id: Optional[str] = None
    issue_category: Literal["BILLING", "TECHNICAL", "ACCOUNT", "OTHER"]
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    summary: str = Field(min_length=1, max_length=200)
    actionable_steps: list[str]
    detected_pii: bool
