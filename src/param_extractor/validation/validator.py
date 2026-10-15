"""校验器：三级校验（完整性 → 解码 → schema），输出归一化错误签名。

设计 §3.4；决策 G2（extra=forbid）、G3（分截断）。**永不抛异常**。
"""
import json
from typing import Optional

from pydantic import ValidationError

from ..contracts.errors import ErrorSignature, ErrorType
from ..contracts.output import ExtractionOutput


def _classify(err_type: str) -> ErrorType:
    if "literal" in err_type:
        return ErrorType.ENUM_MISMATCH
    if "string_too" in err_type:
        return ErrorType.LENGTH_VIOLATION
    if "extra_forbidden" in err_type:
        return ErrorType.EXTRA_FIELD
    if err_type == "missing":
        return ErrorType.MISSING_FIELD
    if err_type.endswith("_type") or "parsing" in err_type:
        return ErrorType.TYPE_ERROR
    return ErrorType.SCHEMA_VALIDATION


def _signature(exc: ValidationError) -> ErrorSignature:
    fields: list[str] = []
    messages: list[str] = []
    error_type = ErrorType.SCHEMA_VALIDATION
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        fields.append(loc)
        messages.append(f"{loc}: {err['msg']}")
        classified = _classify(err["type"])
        if error_type == ErrorType.SCHEMA_VALIDATION:
            error_type = classified
    return ErrorSignature(error_type=error_type, fields=fields, messages=messages)


def validate_content(
    content,
    finish_reason: Optional[str] = None,
) -> "tuple[ExtractionOutput | None, ErrorSignature | None]":
    """返回 (ExtractionOutput | None, ErrorSignature | None)。永不抛异常。"""
    # ① 完整性级：max_tokens 截断
    if finish_reason == "length":
        return None, ErrorSignature(
            error_type=ErrorType.INCOMPLETE_RESPONSE, fields=[],
            messages=["响应被 max_tokens 截断（finish_reason=length）"])

    # ② 解码级
    if not isinstance(content, str):
        return None, ErrorSignature(
            error_type=ErrorType.JSON_DECODE, fields=[],
            messages=[f"content 非字符串: {type(content).__name__}"])
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        return None, ErrorSignature(
            error_type=ErrorType.JSON_DECODE, fields=[],
            messages=[f"invalid JSON: {e}"])

    if not isinstance(obj, dict):
        return None, ErrorSignature(
            error_type=ErrorType.SCHEMA_VALIDATION, fields=[],
            messages=["顶层 JSON 不是对象"])

    # ③ Schema 级
    try:
        return ExtractionOutput.model_validate(obj), None
    except ValidationError as e:
        return None, _signature(e)
