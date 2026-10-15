"""POC-1：instructor × DeepSeek 结构化输出稳定性 + extra="forbid" 兼容 + 模型可用性。

对应 docs/RISK_AND_POC_CHECKLIST.md 的 POC-1（风险 R1）。

验收标准：
  1. 首轮 schema 通过率 ≥ 95%
  2. extra="forbid" 不误伤（0 次因多余字段误判）
  3. 至少 1 个模型名可用，记录延迟
  4. 产出模型选型结论

运行：python poc/poc1_forbid.py
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()
import os
import time

import instructor
from openai import OpenAI
from pydantic import ValidationError

from schema import ExtractionOutput
from prompts import SYSTEM_PROMPT
from transcripts import BASE_CASES

API_KEY = os.environ["DEEPSEEK_API_KEY"]
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")

base_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
client = instructor.from_openai(base_client)

# 待测模型配置（flash 需禁思考模式才能配合 function-calling，见 POC §7.2）
MODELS = [
    ("deepseek-chat", None),
    ("deepseek-flash", {"thinking": {"type": "disabled"}}),
]


def wrap(text):
    return f"<untrusted_user_data>\n{text}\n</untrusted_user_data>"


def extract(text, model, extra_body=None):
    t0 = time.perf_counter()
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": wrap(text)},
        ],
        response_model=ExtractionOutput,
        max_retries=0,
        temperature=0.0,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body
    try:
        r = client.chat.completions.create(**kwargs)
        return True, int((time.perf_counter() - t0) * 1000), r, None
    except Exception as e:  # noqa: BLE001
        return False, int((time.perf_counter() - t0) * 1000), None, f"{type(e).__name__}: {str(e)[:110]}"


def test_forbid_schema():
    """直接单测 schema 行为（确定性，不依赖模型）。"""
    normal = {"customer_id": None, "issue_category": "BILLING", "urgency": "MEDIUM",
              "summary": "x", "actionable_steps": [], "detected_pii": False}

    def passes(d):
        try:
            ExtractionOutput.model_validate(d)
            return True
        except ValidationError:
            return False

    normal_ok = passes(normal)
    extra_caught = not passes({**normal, "hallucinated_field": "boom"})
    empty_caught = not passes({**normal, "summary": ""})  # min_length=1
    enum_caught = not passes({**normal, "urgency": "URGENT"})
    return normal_ok, extra_caught, empty_caught, enum_caught


def main():
    print("=" * 74)
    print("POC-1 第 1 步：extra='forbid' / min_length / 枚举 的 schema 行为（确定性）")
    print("=" * 74)
    normal_ok, extra_caught, empty_caught, enum_caught = test_forbid_schema()
    print(f"  正常对象通过              : {normal_ok}   （应 True）")
    print(f"  幻觉字段被拒绝(extra=forbid): {extra_caught}   （应 True）")
    print(f"  空摘要被拒绝(min_length=1) : {empty_caught}   （应 True）")
    print(f"  非法枚举被拒绝            : {enum_caught}   （应 True）")
    forbid_ok = all([normal_ok, extra_caught, empty_caught, enum_caught])
    print(f"  -> schema 约束自检: {'PASS' if forbid_ok else 'FAIL'}")

    print()
    print("=" * 74)
    print("POC-1 第 2 步：模型可用性 + 首轮通过率（4 用例 × 3 次，max_retries=0）")
    print("=" * 74)

    summary = []
    for model, extra_body in MODELS:
        tag = model + ("（禁思考）" if extra_body else "")
        print(f"\n--- 模型：{tag} ---")
        total = passed = 0
        latencies = []
        errors = []
        for case in BASE_CASES:
            for i in range(3):
                total += 1
                ok, lat, res, err = extract(case["text"], model, extra_body)
                latencies.append(lat)
                if ok:
                    passed += 1
                    print(f"  {case['id']:<8} #{i} [{lat:>4}ms] OK")
                else:
                    errors.append(err)
                    print(f"  {case['id']:<8} #{i} [{lat:>4}ms] FAIL  {err}")
        rate = passed / total * 100 if total else 0
        p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0
        p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0
        summary.append((tag, passed, total, rate, p50, p95))
        print(f"  -> 首轮通过 {passed}/{total} ({rate:.0f}%) | P50 {p50}ms | P95 {p95}ms")

    print()
    print("=" * 74)
    print("POC-1 结论")
    print("=" * 74)
    print(f"  schema 约束自检           : {'PASS' if forbid_ok else 'FAIL'}")
    for tag, passed, total, rate, p50, p95 in summary:
        verdict = "达标(≥95%)" if rate >= 95 else "未达标(<95%)"
        print(f"  {tag:<26}: {passed}/{total} ({rate:.0f}%) {verdict} | P50 {p50}ms P95 {p95}ms")
    usable = [s for s in summary if s[3] > 0]
    if usable:
        best = max(usable, key=lambda s: s[3])
        print(f"  -> 模型可用性: 至少 1 个可用；首轮通过率最高 = {best[0]} ({best[3]:.0f}%)")
    else:
        print("  -> 模型可用性: 全部不可用（需检查模型名/网络/Key）")


if __name__ == "__main__":
    main()
