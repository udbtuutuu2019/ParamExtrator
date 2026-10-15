"""提示注入检测（设计 §3.2；决策 D3）。

只**标记**风险，不直接拒绝（避免误杀正常对话）。
"""
import re

_INJECTION_RULES = [
    ("system_override", re.compile(
        r"system\s*override|ignore\s+(all\s+)?previous|忽略之前|忽略.{0,6}指令|disregard", re.I)),
    ("output_manipulation", re.compile(
        r"不要输出\s*json|do\s+not\s+output\s+json|print\s+[“\"]|设为\s*critical|set\s+.*(urg|crit)|打印\s", re.I)),
    ("role_hijack", re.compile(
        r"you\s+are\s+now|act\s+as|你现在是|作为管理员", re.I)),
]


def detect_injection(text: str) -> "tuple[list[str], bool]":
    """返回 (命中规则名列表, 是否可疑)。"""
    if not isinstance(text, str):
        return [], False
    matched = [name for name, rx in _INJECTION_RULES if rx.search(text)]
    return matched, len(matched) > 0
