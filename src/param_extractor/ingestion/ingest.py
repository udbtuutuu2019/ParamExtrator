"""Ingestion：规范化 + 幂等键 + 超长校验（设计 §3.1；决策 M5）。"""
import hashlib
import re

from ..contracts.request import ExtractionRequest

DEFAULT_MAX_BYTES = 32768
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize(req: ExtractionRequest) -> ExtractionRequest:
    content = (req.content or "").replace("\r\n", "\n").replace("\r", "\n")
    content = _CONTROL.sub("", content).strip()
    return req.model_copy(update={"content": content})


def compute_idempotency_key(req: ExtractionRequest) -> str:
    payload = f"{req.transcript_id}\x1f{req.content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_over_limit(req: ExtractionRequest, max_bytes: int = DEFAULT_MAX_BYTES) -> bool:
    return len((req.content or "").encode("utf-8")) > max_bytes
