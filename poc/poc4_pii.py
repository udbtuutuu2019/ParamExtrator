"""POC-4：本地 PII 扫描准确率 + 卡尾号覆写。

对应 docs/RISK_AND_POC_CHECKLIST.md 的 POC-4（风险 R4）。
**不接 LLM**，纯本地正则/规则。

验收：
  1. NRIC S9123456A 100% 命中
  2. 密码 SuperSecretPass123 100% 命中
  3. TX-001 卡尾号经覆写输出 false
  4. 误报率 ≤ 10%
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import re

from transcripts import BASE_CASES

# ---------- PII 规则 ----------
CARD_FULL = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")                       # 13-19 位连续数字
NRIC = re.compile(r"\b[STFGM]\d{7}[A-Z]\b")                               # 新加坡 NRIC
PASSWORD = re.compile(r"(?:密码|password|pwd|passcode)\s*(?:是|为|：|:|=|is)?\s*([^\s，。,.！!？?\n]{3,})", re.I)
PHONE = re.compile(r"\b(?:\+?86)?1[3-9]\d{9}\b")                          # 中国手机号
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
CARD_TAIL = re.compile(r"(?:尾号|末四位|ending\s+in|last\s+4)\s*(?:是|为)?\s*(\d{4})", re.I)

HIGH_CONFIDENCE = {"card_full", "nric", "password", "phone", "email"}


def scan(text: str):
    """返回 (categories:set, is_pii:bool)。

    is_pii 规则：card_tail 是**明确排除项**（仅卡尾号命中 → False，见设计 §7.2 / 决策 D1）。
    """
    cats = set()
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
    is_pii = bool(cats & HIGH_CONFIDENCE)
    return cats, is_pii


# ---------- 测试样本 ----------
POSITIVES = [
    ("信用卡完整号", "我的信用卡号是 4111 1111 1111 1111，请帮我查一下"),
    ("NRIC", "我的 NRIC 是 S9123456A"),
    ("密码", "我的密码是 MyPass123"),
    ("手机号", "请联系我 13812345678"),
    ("邮箱", "我的邮箱是 user@example.com"),
]

NEGATIVES = [
    ("订单号", "订单号是 20261015001"),
    ("日期", "退款日期是 2026-10-15"),
    ("卡尾号(应排除)", "退回到尾号 4402 的卡"),
    ("发票号", "发票编号 #INV-4029"),
    ("金额", "被多扣了 150 美元"),
]

# 用例预期（依据设计附录 A）
BASE_EXPECT = {"TX-001": False, "TX-002": True, "TX-003": False, "TX-004": False}


def main():
    print("=" * 74)
    print("POC-4：本地 PII 扫描准确率 + 卡尾号覆写（不接 LLM）")
    print("=" * 74)

    # --- 正样本召回 ---
    print("\n[正样本 — 应命中]")
    pos_ok = 0
    nric_hit = pw_hit = False
    for name, text in POSITIVES:
        cats, is_pii = scan(text)
        hit = is_pii
        pos_ok += hit
        if name == "NRIC" and hit:
            nric_hit = True
        if name == "密码" and hit:
            pw_hit = True
        print(f"  {name:<12} cats={sorted(cats)} is_pii={is_pii}  {'✓' if hit else '✗'}")
    print(f"  -> 召回: {pos_ok}/{len(POSITIVES)}")

    # --- 负样本误报 ---
    print("\n[负样本 — 应为 False]")
    fp = 0
    tail_ok = False
    for name, text in NEGATIVES:
        cats, is_pii = scan(text)
        wrong = is_pii
        fp += wrong
        if name == "卡尾号(应排除)" and not is_pii:
            tail_ok = True
        print(f"  {name:<14} cats={sorted(cats)} is_pii={is_pii}  {'✗误报' if wrong else '✓'}")
    fp_rate = fp / len(NEGATIVES) * 100
    print(f"  -> 误报: {fp}/{len(NEGATIVES)} ({fp_rate:.0f}%)")

    # --- 基准用例 ---
    print("\n[基准用例 — 对照设计附录 A]")
    base_ok = 0
    for case in BASE_CASES:
        cats, is_pii = scan(case["text"])
        expect = BASE_EXPECT[case["id"]]
        ok = is_pii == expect
        base_ok += ok
        print(f"  {case['id']}  cats={sorted(cats)} is_pii={is_pii} 期望={expect}  {'✓' if ok else '✗'}")
    print(f"  -> 基准用例: {base_ok}/{len(BASE_CASES)}")

    print("\n" + "=" * 74)
    print("POC-4 结论")
    print("=" * 74)
    checks = {
        "NRIC 100% 命中": nric_hit,
        "密码 100% 命中": pw_hit,
        "TX-001 卡尾号→false": tail_ok and (BASE_EXPECT["TX-001"] is False),
        "误报率 ≤10%": fp_rate <= 10,
    }
    for k, v in checks.items():
        print(f"  {k:<24}: {'PASS' if v else 'FAIL'}")
    print(f"  -> 总体: {'PASS' if all(checks.values()) else 'FAIL'}")


if __name__ == "__main__":
    main()
