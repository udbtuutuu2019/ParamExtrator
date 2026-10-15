"""POC-2：自研"针对性修复"收敛性（N=2）+ 温度策略。

对应 docs/RISK_AND_POC_CHECKLIST.md 的 POC-2（风险 R2，本设计最薄的假设）。

方法：mock 首轮注入 4 类可修复错误；其后走**真实模型**；
      观察是否在 ≤2 次修复内收敛；并比较 temp=0 vs 0.25。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()
import json
import os

from openai import OpenAI

from prompts import SYSTEM_PROMPT
from transcripts import BASE_CASES
from skeleton import MODEL, wrap, validate_content, repair_prompt

base_client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                     base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"))

MAX_REPAIRS = 2


def call_model(messages, temperature):
    resp = base_client.chat.completions.create(
        model=MODEL, messages=messages,
        response_format={"type": "json_object"}, temperature=temperature)
    return resp.choices[0].message.content


def repair_loop(user_text, temperature=0.0, bad_first=None, always_bad=None):
    """返回 (status, attempts, trace)。status ∈ SUCCESS/REPAIRED/FALLBACK/CONVERGENCE_HALT。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": wrap(user_text)},
    ]
    prev_key = None
    trace = []
    for attempt in range(MAX_REPAIRS + 1):
        if attempt == 0 and bad_first is not None:
            content = bad_first
        elif always_bad is not None:
            content = always_bad
        else:
            content = call_model(messages, temperature)

        data, sig = validate_content(content)
        if data is not None:
            return ("SUCCESS" if attempt == 0 else "REPAIRED"), attempt, trace

        key = (sig["error_type"], tuple(sorted(sig["messages"])))
        trace.append((attempt, sig["error_type"], sig["messages"][0] if sig["messages"] else ""))
        if prev_key == key:                       # 单调性熔断：连续同错
            return "CONVERGENCE_HALT", attempt, trace
        prev_key = key
        if attempt == MAX_REPAIRS:
            break
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": repair_prompt(content, sig)})
    return "FALLBACK", MAX_REPAIRS, trace


# ---- 4 类可修复错误（mock 首轮输出）----
BASE = {"customer_id": "CUST-98234", "issue_category": "BILLING", "urgency": "MEDIUM",
        "summary": "客户在发票上被重复扣款并已获退款。", "actionable_steps": ["确认退款到账"],
        "detected_pii": False}


def _dump(d):
    return json.dumps(d, ensure_ascii=False)


def bad_enum():
    return _dump({**BASE, "urgency": "URGENT"})


def bad_long():
    return _dump({**BASE, "summary": "重复扣款需要尽快处理。" * 30})  # >200 字符


def bad_missing():
    d = dict(BASE); d.pop("detected_pii"); return _dump(d)


def bad_extra():
    return _dump({**BASE, "notes": "模型多加的一个字段"})


ERROR_CASES = [("枚举错(ENUM)", bad_enum()), ("超长(LENGTH)", bad_long()),
               ("缺字段(MISSING)", bad_missing()), ("幻觉字段(EXTRA)", bad_extra())]


def main():
    text = BASE_CASES[0]["text"]  # TX-001

    print("=" * 74)
    print("POC-2：自研针对性修复收敛性（mock 首轮错误 → 真实模型修复，N=2）")
    print("=" * 74)

    results = {}
    for temp in (0.0, 0.25):
        print(f"\n--- 温度 = {temp} ---")
        ok = 0
        for name, bad in ERROR_CASES:
            status, attempts, trace = repair_loop(text, temperature=temp, bad_first=bad)
            converged = status in ("SUCCESS", "REPAIRED")
            ok += converged
            mark = "✓收敛" if converged else "✗未收敛"
            print(f"  {name:<18} {status:<16} 修复次数={attempts}  {mark}")
            if not converged:
                for a, et, m in trace:
                    print(f"       attempt{a}: [{et}] {m[:70]}")
        results[temp] = ok
        print(f"  -> 收敛率: {ok}/{len(ERROR_CASES)} ({ok*100//len(ERROR_CASES)}%)")

    print("\n" + "=" * 74)
    print("单调性熔断测试（mock 每次都返回同一错误）")
    print("=" * 74)
    status, attempts, trace = repair_loop(text, temperature=0.0, always_bad=bad_enum())
    print(f"  status={status} | 修复次数={attempts}（应 < {MAX_REPAIRS} 即提前终止）")
    halt_ok = status == "CONVERGENCE_HALT" and attempts < MAX_REPAIRS
    print(f"  -> 单调性熔断: {'PASS' if halt_ok else 'FAIL'}")

    print("\n" + "=" * 74)
    print("POC-2 结论")
    print("=" * 74)
    best = max(results.values())
    rate_best = best * 100 // len(ERROR_CASES)
    print(f"  收敛率: temp=0 -> {results[0.0]}/{len(ERROR_CASES)} | temp=0.25 -> {results[0.25]}/{len(ERROR_CASES)}")
    print(f"  验收(≤2次收敛率 ≥80%): {'PASS' if rate_best >= 80 else 'FAIL'}")
    print(f"  验收(单调性熔断)      : {'PASS' if halt_ok else 'FAIL'}")
    if results[0.25] > results[0.0]:
        print("  温度建议: 修复轮用 0.25 更优")
    elif results[0.25] < results[0.0]:
        print("  温度建议: 保持 0.0 更优")
    else:
        print("  温度建议: 无显著差异")


if __name__ == "__main__":
    main()
