"""脱敏（设计 §8.4；决策 D3）。日志/错误签名中的敏感文本脱敏。"""
import re

_PASSWORD = re.compile(r"((?:密码|password|pwd|passcode)\s*(?:是|为|：|:|=|is)\s*)(\S+)", re.I)
_CARD = re.compile(r"\b(\d{4})[ -]?(\d{4})[ -]?(\d{4})[ -]?(\d{4})\b")
_NRIC = re.compile(r"\b([STFGM])(\d{4})(\d{3})([A-Z])\b")
_EMAIL = re.compile(r"\b([\w.+-])([\w.+-]*)(@[\w-]+\.[\w.-]+)\b")
_PHONE = re.compile(r"\b(\d{3})\d{4}(\d{4})\b")


def redact(text, max_len: int = 256) -> str:
    if not isinstance(text, str):
        return ""
    out = _PASSWORD.sub(lambda m: m.group(1) + "***", text)
    out = _CARD.sub(lambda m: f"**** **** **** {m.group(4)}", out)
    out = _NRIC.sub(lambda m: f"{m.group(1)}****{m.group(4)}", out)
    out = _EMAIL.sub(lambda m: f"{m.group(1)}***{m.group(3)}", out)
    out = _PHONE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", out)
    if len(out) > max_len:
        out = out[:max_len]
    return out
