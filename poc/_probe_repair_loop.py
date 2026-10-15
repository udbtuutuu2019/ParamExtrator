"""确定性验证修复循环：mock 第 1 次返回非法响应，观察 instructor 回喂 + 第 2 次收敛。

对应设计文档 S2 场景（schema 校验失败时，自我纠正循环的执行与恢复，使用 mock）。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()
import os

import instructor
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from pydantic import BaseModel, Field
from typing import Literal

from prompts import SYSTEM_PROMPT
from transcripts import BASE_CASES

API_KEY = os.environ["DEEPSEEK_API_KEY"]
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


class Out(BaseModel):
    issue_category: Literal["BILLING", "TECHNICAL", "ACCOUNT", "OTHER"]
    urgency: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    summary: str = Field(max_length=200)
    actionable_steps: list[str]
    detected_pii: bool


base_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
real_create = base_client.chat.completions.create
call_count = {"n": 0}
captured_msgs = []


def mock_create(**kwargs):
    call_count["n"] += 1
    captured_msgs.append(kwargs.get("messages", []))
    if call_count["n"] == 1:
        # 第 1 次：返回"非法 JSON"（模拟模型输出格式漂移）
        return ChatCompletion(
            id="mock-1", object="chat.completion", created=0, model=MODEL, choices=[
                Choice(index=0, finish_reason="stop",
                       message=ChatCompletionMessage(
                           role="assistant", content="这不是JSON，是一段散文"))
            ], usage=None)
    # 第 2 次起：走真实 API
    return real_create(**kwargs)


base_client.chat.completions.create = mock_create
client = instructor.from_openai(base_client)


def main():
    text = BASE_CASES[0]["text"]
    print("=" * 78)
    print("mock 第 1 次返回非法文本，观察 instructor 修复循环（max_retries=2）")
    print("=" * 78)
    try:
        result = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"<untrusted_user_data>\n{text}\n</untrusted_user_data>"},
            ],
            response_model=Out,
            max_retries=2,
            temperature=0.0,
        )
        print(f"最终成功: category={result.issue_category} urgency={result.urgency} "
              f"summary_len={len(result.summary)}")
    except instructor.exceptions.InstructorRetryException as e:
        print(f"最终失败: {type(e).__name__}: {str(e)[:120]}")
    print(f"总调用次数: {call_count['n']}")

    print("\n--- 各次调用的消息序列 ---")
    for i, msgs in enumerate(captured_msgs):
        print(f"[第 {i+1} 次] 消息数={len(msgs)}")
        for m in msgs:
            role = m.get("role")
            c = m.get("content", "")
            if isinstance(c, list):
                c = str(c)
            c = c.replace("\n", " ")
            tag = ">>" if ("Validation Error" in c or "Recall" in c) else "  "
            print(f"  {tag} role={role}: {c[:130]}")


if __name__ == "__main__":
    main()
