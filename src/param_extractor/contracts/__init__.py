"""数据契约包：系统的唯一通信语言。"""
from .errors import ErrorSignature, ErrorType
from .output import ExtractionOutput
from .request import ExtractionRequest
from .result import ExtractionResult, Status

__all__ = [
    "ErrorSignature",
    "ErrorType",
    "ExtractionOutput",
    "ExtractionRequest",
    "ExtractionResult",
    "Status",
]
