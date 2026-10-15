"""POC-6：'永不崩溃'契约 + 不完整响应检测。

对应 docs/RISK_AND_POC_CHECKLIST.md 的 POC-6（风险 R6 + R7）。

方法：构造最小 Orchestrator（含顶层兜底），mock 注入各类故障，断言：
  1. 100% 返回 SUCCESS / REPAIRED / FALLBACK 之一
  2. 0 个未捕获异常向上传播
  3. max_tokens 截断被分类为 INCOMPLETE_RESPONSE
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
from dataclasses import dataclass

from skeleton import wrap, validate_content, repair_prompt
from prompts import SYSTEM_PROMPT

MAX_REPAIRS = 2

FALLBACK_DATA = {
    "customer_id": None, "issue_category": "OTHER", "urgency": "MEDIUM",
    "summary": "自动提取失败，需人工复核", "actionable_steps": ["转交人工客服审核"],
    "detected_pii": False,
}


class FakeRateLimit(Exception):
    pass


@dataclass
class Result:
    status: str
    attempts: int
    repairs: int
    needs_human_review: bool
    failure_reason: str | None = None
    last_error_type: str | None = None
    data: dict | None = None


def classify_transport(e):
    n = type(e).__name__.lower()
    s = str(e).lower()
    if "timeout" in n or "timed out" in s:
        return "TRANSPORT_TIMEOUT"
    if "rate" in n or "429" in s:
        return "RATE_LIMIT"
    return "TRANSPORT_ERROR"


def run_pipeline(text, client, max_repairs=MAX_REPAIRS):
    """最小编排器：**保证永不抛异常**，永远返回 Result。"""
    attempts = 0
    last_err = None
    try:
        # ① 空输入边界：不调用 LLM
        if not text or not text.strip():
            return Result("FALLBACK", 0, 0, True, "empty_input", None, FALLBACK_DATA)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": wrap(text)},
        ]
        prev_key = None
        for attempt in range(max_repairs + 1):
            attempts += 1
            # ② 传输层错误（超时/限流）→ 重试，耗尽则兜底
            try:
                out = client.extract(messages)
            except Exception as e:  # noqa: BLE001
                last_err = classify_transport(e)
                if attempt < max_repairs:
                    continue
                return Result("FALLBACK", attempts, attempt, True,
                              f"transport:{type(e).__name__}", last_err, FALLBACK_DATA)

            # ③ 完整性检查：max_tokens 截断
            if isinstance(out, dict) and out.get("finish_reason") == "length":
                last_err = "INCOMPLETE_RESPONSE"
                content = out.get("content", "") or ""
                sig = {"error_type": "INCOMPLETE_RESPONSE", "fields": [],
                       "messages": ["响应被 max_tokens 截断（finish_reason=length）"]}
            else:
                content = out.get("content", "") or ""
                data, sig = validate_content(content)
                if data is not None:
                    status = "SUCCESS" if attempt == 0 else "REPAIRED"
                    return Result(status, attempts, attempt, False, None, None, data.model_dump())
                last_err = sig["error_type"]

            # ④ 单调性熔断
            key = (sig["error_type"], tuple(sorted(sig["messages"])))
            if prev_key == key:
                return Result("FALLBACK", attempts, attempt, True,
                              f"convergence_halt:{last_err}", last_err, FALLBACK_DATA)
            prev_key = key

            if attempt == max_repairs:
                break
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": repair_prompt(content, sig)})

        return Result("FALLBACK", attempts, max_repairs, True,
                      f"budget_exhausted:{last_err}", last_err, FALLBACK_DATA)

    except Exception as e:  # noqa: BLE001 —— 最后一道防线，绝不允许穿透
        return Result("FALLBACK", attempts, 0, True,
                      f"unexpected:{type(e).__name__}", "UNEXPECTED", FALLBACK_DATA)


# ---------- 可脚本化的 mock client ----------
class ScriptedClient:
    """script: list of ("ok", content, finish_reason) | ("raise", exc) | ("raw", value)"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self._last = ("ok", "{}", "stop")

    def extract(self, messages):
        self.calls += 1
        if self.script:
            self._last = self.script.pop(0)
        step = self._last  # 用尽后重复最后一步（模拟持续故障）
        kind = step[0]
        if kind == "raise":
            raise step[1]
        if kind == "raw":
            return step[1]
        return {"content": step[1], "finish_reason": step[2]}


VALID = json.dumps({"customer_id": "CUST-98234", "issue_category": "BILLING", "urgency": "MEDIUM",
                    "summary": "重复扣款已退款", "actionable_steps": ["确认到账"], "detected_pii": False},
                   ensure_ascii=False)

SCENARIOS = [
    ("正常路径", "订单有问题", [("ok", VALID, "stop")], "SUCCESS", None),
    ("超时", "订单有问题", [("raise", TimeoutError("request timed out"))], "FALLBACK", "TRANSPORT_TIMEOUT"),
    ("限流429", "订单有问题", [("raise", FakeRateLimit("429 too many requests"))], "FALLBACK", "RATE_LIMIT"),
    ("非法JSON", "订单有问题", [("ok", "这不是JSON", "stop"), ("ok", "也不是", "stop"), ("ok", "还不是", "stop")],
     "FALLBACK", "JSON_DECODE"),
    ("空输入", "   ", [], "FALLBACK", None),
    ("max_tokens截断", "订单有问题", [("ok", "{}", "length"), ("ok", "{}", "length"), ("ok", "{}", "length")],
     "FALLBACK", "INCOMPLETE_RESPONSE"),
    ("畸形返回(兜底网)", "订单有问题", [("raw", None)], "FALLBACK", "UNEXPECTED"),
]


def main():
    print("=" * 78)
    print("POC-6：'永不崩溃'契约 + 不完整响应检测（mock 故障注入）")
    print("=" * 78)

    uncaught = 0
    all_terminal = True
    trunc_ok = False
    rows = []

    for name, text, script, exp_status, exp_err in SCENARIOS:
        client = ScriptedClient(script)
        try:
            res = run_pipeline(text, client)
        except BaseException as e:  # 若这里被触发，说明契约被破坏
            uncaught += 1
            print(f"  {name:<18} !! 未捕获异常: {type(e).__name__}: {e}")
            continue
        terminal = res.status in ("SUCCESS", "REPAIRED", "FALLBACK")
        all_terminal = all_terminal and terminal
        if name == "max_tokens截断" and res.last_error_type == "INCOMPLETE_RESPONSE":
            trunc_ok = True
        mark = "✓" if terminal else "✗"
        rows.append((name, res.status, res.attempts, res.last_error_type, mark))
        print(f"  {name:<18} status={res.status:<9} attempts={res.attempts} "
              f"last_err={str(res.last_error_type):<20} {mark}")

    print("\n" + "=" * 78)
    print("POC-6 结论")
    print("=" * 78)
    print(f"  全部返回定义终态      : {'PASS' if all_terminal else 'FAIL'}")
    print(f"  未捕获异常数          : {uncaught}  ({'PASS' if uncaught == 0 else 'FAIL'})")
    print(f"  截断分类为 INCOMPLETE_RESPONSE: {'PASS' if trunc_ok else 'FAIL'}")
    overall = all_terminal and uncaught == 0 and trunc_ok
    print(f"  -> 总体: {'PASS' if overall else 'FAIL'}")


if __name__ == "__main__":
    main()
