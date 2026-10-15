"""本地 PII 扫描 + 卡尾号策略（设计 §7.2；决策 D1）。不依赖 LLM。"""
import re

CARD_FULL = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
NRIC = re.compile(r"\b[STFGM]\d{7}[A-Z]\b")
PASSWORD = re.compile(
    r"(?:密码|password|pwd|passcode)\s*(?:是|为|：|:|=|is)?\s*([^\s，。,.！!？?\n]{3,})", re.I)
PHONE = re.compile(r"\b(?:\+?86)?1[3-9]\d{9}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
CARD_TAIL = re.compile(r"(?:尾号|末四位|ending\s+in|last\s+4)\s*(?:是|为)?\s*(\d{4})", re.I)

# 卡尾号是明确排除项：单独命中不算 PII（决策 D1）
HIGH_CONFIDENCE = {"card_full", "nric", "password", "phone", "email"}


def scan_pii(text) -> "tuple[set[str], bool]":
    """返回 (命中的类别集合, 是否判定为 PII)。"""
    if not isinstance(text, str):
        return set(), False
    cats: set[str] = set()
    if CARD_FULL.search(text):
        cats.add("card_full")
    if NRIC.search(text):
        cats.add("nric")
    if PASSWORD.search(text):
        cats.add("password")
    if PHONE.search(text):
        cats.add("phone")
    if EMAIL.search(text):
        cats.add("email")
    if CARD_TAIL.search(text):
        cats.add("card_tail")
    return cats, bool(cats & HIGH_CONFIDENCE)


def apply_pii_policy(llm_flag: bool, cats) -> bool:
    """合并 LLM 标记与本地扫描（高召回）；卡尾号是明确排除项（决策 D1）。"""
    cats = set(cats)
    if cats & HIGH_CONFIDENCE:
        return True
    if "card_tail" in cats:
        return False  # 仅卡尾号 → 覆写为 false
    return bool(llm_flag)
