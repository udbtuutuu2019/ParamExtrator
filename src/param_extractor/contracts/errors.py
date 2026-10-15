"""错误契约（设计 §4.4；决策 G2/G3）。"""
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class ErrorType(StrEnum):
    INCOMPLETE_RESPONSE = "INCOMPLETE_RESPONSE"
    JSON_DECODE = "JSON_DECODE"
    EXTRA_FIELD = "EXTRA_FIELD"
    SCHEMA_VALIDATION = "SCHEMA_VALIDATION"
    TYPE_ERROR = "TYPE_ERROR"
    ENUM_MISMATCH = "ENUM_MISMATCH"
    LENGTH_VIOLATION = "LENGTH_VIOLATION"
    MISSING_FIELD = "MISSING_FIELD"
    TRANSPORT_TIMEOUT = "TRANSPORT_TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UNEXPECTED = "UNEXPECTED"


class ErrorSignature(BaseModel):
    error_type: ErrorType
    fields: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    raw_snippet: Optional[str] = None
