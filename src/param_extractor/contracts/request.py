"""输入契约（设计 §4.1）。"""
from typing import Optional

from pydantic import BaseModel


class ExtractionRequest(BaseModel):
    transcript_id: str
    content: str
    customer_id_hint: Optional[str] = None
    trace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    idempotency_key: Optional[str] = None
