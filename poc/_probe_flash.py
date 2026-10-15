import sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()
import os
from openai import OpenAI

c = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

# 测试1: deepseek-flash + json_object 模式（不走 tool_choice）
try:
    r = c.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role": "user", "content": '输出JSON: {"a":1}'}],
        response_format={"type": "json_object"},
        max_tokens=200,
    )
    print("flash+json_object OK ->", r.choices[0].message.content[:80])
except Exception as e:
    print("flash+json_object FAIL ->", str(e)[:200])

# 测试2: deepseek-flash 关闭思考模式
try:
    r = c.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role": "user", "content": "回复OK"}],
        extra_body={"thinking": {"type": "disabled"}},
        max_tokens=50,
    )
    print("flash+thinking_disabled OK ->", r.choices[0].message.content[:40])
except Exception as e:
    print("flash+thinking_disabled FAIL ->", str(e)[:200])

# 测试3: deepseek-flash 关闭思考 + json_object
try:
    r = c.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role": "user", "content": '输出JSON: {"a":1}'}],
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
        max_tokens=200,
    )
    print("flash+thinking_disabled+json_object OK ->", r.choices[0].message.content[:80])
except Exception as e:
    print("flash+thinking_disabled+json_object FAIL ->", str(e)[:200])
