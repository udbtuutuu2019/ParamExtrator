"""Repair Engine（设计 §3.5；决策 D2/D9）。

- next_message：错误 → 针对性修复提示（user 消息）。
- should_halt：连续两次相同错误签名 → 单调性熔断。
"""
from ..contracts.errors import ErrorSignature
from ..extraction.prompts import build_repair_prompt


class RepairEngine:
    def __init__(self) -> None:
        self._prev_key = None

    def next_message(self, raw_output: str, sig: ErrorSignature) -> dict:
        return {"role": "user", "content": build_repair_prompt(raw_output, sig)}

    def should_halt(self, sig: ErrorSignature) -> bool:
        key = (str(sig.error_type), tuple(sorted(sig.messages)))
        halt = key == self._prev_key
        self._prev_key = key
        return halt
