"""POC 遗留项探针（修正版）：修复收敛性 + V2 实证确认。

结论来源（源码级）：
    instructor 的重试在 v2/core/retry.py 中调用 handlers.reask_handler(...)，
    对 OpenAI tools 模式会追加一条消息：
        "Validation Error found:\\n{exception}\\nRecall the function correctly, fix the errors"
    其中 exception 是完整的 Pydantic ValidationError（含字段名/错误/非法值）。
    => V2 结论：instructor 确实回喂错误，不是简单重发。

本探针的实证目标（设计风险 2/3）：
    R2  温度 0.0 vs 0.3，修复轮是否收敛（修好错误）？
    R3  是否出现"越修越差"（单调性破坏）？
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
from pydantic import BaseModel, Field
from typing import Literal

from prompts import SYSTEM_PROMPT
from transcripts import BASE_CASES

API_KEY = os.environ["DEEPSEEK_API_KEY"]
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


class StrictOutput(BaseModel):
    """summary 上限 20 字符，迫使模型压缩，大概率触发重试。"""
    issue_category: Literal["BILLING", "TECHNICAL", "ACCOUNT", "OTHER"]
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    summary: str = Field(max_length=20)
    actionable_steps: list[str]
    detected_pii: bool


base_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 只 patch 一次，避免叠加
_original_create = base_client.chat.completions.create
_calls = []


def _logging_create(**kwargs):
    _calls.append(kwargs.get("messages", []))
    return _original_create(**kwargs)


base_client.chat.completions.create = _logging_create
client = instructor.from_openai(base_client)


def run_once(text, temperature, max_retries=3):
    """返回 (ok, 调用次数, summary长度或错误, 各轮summary长度列表)。"""
    _calls.clear()
    t0 = time.perf_counter()
    summaries = []
    try:
        result = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"<untrusted_user_data>\n{text}\n</untrusted_user_data>"},
            ],
            response_model=StrictOutput,
            max_retries=max_retries,
            temperature=temperature,
        )
        lat = int((time.perf_counter() - t0) * 1000)
        return True, len(_calls), len(result.summary), lat, result.summary
    except instructor.exceptions.InstructorRetryException as e:
        lat = int((time.perf_counter() - t0) * 1000)
        # 从 failed_attempts 提取每轮 summary 长度
        for fa in getattr(e, "failed_attempts", []):
            try:
                comp = fa.completion.choices[0].message
                content = comp.content or ""
                import json
                d = json.loads(content)
                summaries.append(len(d.get("summary", "")))
            except Exception:
                summaries.append(-1)
        return False, len(_calls), None, lat, str(e)[:80]


def show_reask(attempt_idx):
    """展示第 attempt_idx 次调用的消息，确认是否含错误回喂。"""
    if attempt_idx >= len(_calls):
        return
    print(f"    [第 {attempt_idx + 1} 次调用] 消息数={len(_calls[attempt_idx])}")
    for m in _calls[attempt_idx]:
        role = m.get("role")
        c = m.get("content", "")
        if isinstance(c, list):
            c = str(c)
        c = c.replace("\n", " ")
        if "Validation Error" in c or "Recall" in c:
            print(f"      >> role={role}: {c[:200]}")
        else:
            print(f"        role={role}: {c[:90]}")


def main():
    text = BASE_CASES[0]["text"]  # TX-001

    print("=" * 78)
    print("R2/R3 收敛性实测：summary 上限 20 字符（必然需要压缩），max_retries=3")
    print("=" * 78)

    for temp in (0.0, 0.3):
        print(f"\n--- 温度 = {temp} ---")
        ok_cnt = fail_cnt = tot_attempts = 0
        for i in range(3):
            ok, attempts, slen, lat, extra = run_once(text, temperature=temp)
            tot_attempts += attempts
            if ok:
                ok_cnt += 1
                print(f"  第{i+1}次: 成功, 调用 {attempts} 次, summary_len={slen}, {lat}ms")
            else:
                fail_cnt += 1
                print(f"  第{i+1}次: 失败, 调用 {attempts} 次, {lat}ms, err={extra}")
        print(f"  -> 温度 {temp}: 成功 {ok_cnt}/3, 平均调用 {tot_attempts/3:.1f} 次")

    print("\n" + "=" * 78)
    print("V2 实证：展示一次触发重试的消息序列（温度 0.0）")
    print("=" * 78)
    run_once(text, temperature=0.0, max_retries=2)
    for i in range(len(_calls)):
        show_reask(i)


if __name__ == "__main__":
    main()
