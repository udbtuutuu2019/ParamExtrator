"""POC 用 Schema —— 与生产契约一致（见 docs/TECHNICAL_DESIGN.md §4.2）。

包含设计 v1.3 的关键约束：
- extra="forbid"（拒绝幻觉字段，回应 G2）
- summary min_length=1, max_length=200（回应 I3 / 空值策略）
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: Optional[str] = None
    issue_category: Literal["BILLING", "TECHNICAL", "ACCOUNT", "OTHER"]
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    summary: str = Field(min_length=1, max_length=200)
    actionable_steps: list[str]
    detected_pii: bool
