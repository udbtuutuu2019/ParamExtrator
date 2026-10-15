"""POC-2 / POC-3 共享最小骨架。

只包含验证所需的确定性逻辑，**不含完整业务流程**：
- 校验 + 错误签名归一化
- 针对性修复提示构建
- 注入检测
- 输出复核（urgency 保守化）
"""
import json
import re

from pydantic import ValidationError

from schema import ExtractionOutput

MODEL = "deepseek-chat"


def wrap(text: str) -> str:
    return f"<untrusted_user_data>\n{text}\n</untrusted_user_data>"


# ---------- 校验 + 错误签名 ----------

def _signature(exc: ValidationError):
    fields, msgs, etype = [], [], "SCHEMA_VALIDATION"
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"])
        if loc == "__root__":
            loc = "<root>"
        fields.append(loc)
        msgs.append(f"{loc}: {err['msg']}")
        t = err["type"]
        if "literal" in t:
            etype = "ENUM_MISMATCH"
        elif "too_long" in t or "too_short" in t or "string_too" in t:
            etype = "LENGTH_VIOLATION"
        elif "extra_forbidden" in t:
            etype = "EXTRA_FIELD"
        elif "missing" in t:
            etype = "MISSING_FIELD"
    return {"error_type": etype, "fields": fields, "messages": msgs}


def validate_content(content: str):
    """返回 (ExtractionOutput | None, error_signature | None)。永不抛异常。"""
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        return None, {"error_type": "JSON_DECODE", "fields": [], "messages": [f"invalid JSON: {e}"]}
    try:
        return ExtractionOutput.model_validate(obj), None
    except ValidationError as e:
        return None, _signature(e)


# ---------- 针对性修复提示（POC-2 核心） ----------

def repair_prompt(raw_output: str, sig: dict) -> str:
    lines = [
        "上一步输出未通过校验。请修正以下问题后重新输出 JSON。",
        "",
        "【你的原始输出】",
        raw_output[:500],
        "",
        "【校验错误】",
    ]
    lines += [f"- {m}" for m in sig["messages"]]
    lines += [
        "",
        "【要求】",
        "- 仅修正上述字段，保持其它字段不变",
        "- 只输出 JSON 对象本身，不要 markdown 代码块，不要解释",
    ]
    return "\n".join(lines)


# ---------- 注入检测（POC-3） ----------

_INJECTION_RULES = [
    ("system_override", re.compile(r"system\s*override|ignore\s+(all\s+)?previous|忽略之前|disregard|忽略.*指令", re.I)),
    ("output_manipulation", re.compile(r"不要输出\s*json|do\s+not\s+output\s+json|print\s+[“\"]|设为\s*critical|set\s+.*(urg|crit)|打印\s|sortie", re.I)),
    ("role_hijack", re.compile(r"you\s+are\s+now|act\s+as|你现在是|作为管理员", re.I)),
]


def detect_injection(text: str):
    matched = [name for name, rx in _INJECTION_RULES if rx.search(text)]
    return matched, len(matched) > 0


# ---------- 输出复核（POC-3）：注入命中且 urgency 被抬高 → 保守化 ----------

def review_output(data: ExtractionOutput, injection_suspected: bool) -> ExtractionOutput:
    if injection_suspected and data.urgency == "CRITICAL":
        return data.model_copy(update={"urgency": "MEDIUM"})
    return data
