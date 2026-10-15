# SDD ledger — plan: docs/superpowers/plans/2026-10-15-param-extractor-harness.md

**Executor:** inline (Native) ｜ **Branch:** feat/harness ｜ **Base:** a366b3f (main)
**Spec:** docs/TECHNICAL_DESIGN.md v1.4 ｜ **Risk/POC:** docs/RISK_AND_POC_CHECKLIST.md

## Pre-flight scan（跨任务接口冲突）

| 生产者 | 消费者 | 接口 | 结论 |
|--------|--------|------|------|
| Task 1.2 contracts (ExtractionOutput/Request/Result/Status/ErrorType/ErrorSignature) | 2.1,2.4,3.3,4.1,4.3,5.1 | 名称与签名 | ✅ 一致 |
| Task 2.1 `validate_content(content, finish_reason)` | 4.3 | 签名含 finish_reason | ✅ 一致 |
| Task 2.2 `detect_injection` | 4.3 | 返回 (rules, bool) | ✅ 一致 |
| Task 2.3 `wrap_untrusted` | 4.3 | 返回 str | ✅ 一致 |
| Task 2.4 `scan_pii` / `apply_pii_policy` | 4.3 | 返回 (set, bool) / bool | ✅ 一致 |
| Task 2.5 `redact` | 4.2 | 返回 str | ✅ 一致 |
| Task 3.1 `LLMClient.extract` / `LLMResponse` | 4.3, 5.2 | 签名 + finish_reason 字段 | ✅ 一致 |
| Task 3.2 `SYSTEM_PROMPT` / `build_repair_prompt` | 3.3, 4.3 | 名称与签名 | ✅ 一致 |
| Task 3.3 `RepairEngine` | 4.3 | next_message/should_halt | ✅ 一致 |
| Task 4.1 `build_fallback` | 4.3 | 签名 | ✅ 一致 |
| Task 4.3 `run_pipeline` | 5.1, 5.3 | 签名 | ✅ 一致 |

**结论：无跨任务接口冲突。** 共享接口以 contracts/ 为准。

## Progress

### Task 1.1: complete (commits a366b3f..ad0e3cd, tests: `python -c "import param_extractor"` → OK)
- Ruling: 接受 `pip install -e .` 将 starlette 1.0.0 降为 0.48.0（fastapi 依赖约束所致；环境既有 sse-starlette 冲突与本项目无关）—— 因本 Harness 不依赖 starlette 版本特性，接受该降级 —— 若下游工具需 starlette≥1.0 会受影响（本项目不受影响）

### Task 1.2: complete (commits ad0e3cd..9799e8e, tests: `pytest -q` → 10/10 pass)

### Task 1.3: complete (commits 9799e8e..ea7dd1b, tests: `pytest -q` → 13/13 pass)
- **Phase 1 阶段验收**：`test_contracts.py` 全绿 ✅；`import param_extractor` OK ✅；契约约束（extra/枚举/min_length）被测试证明 ✅

### Phase 1: DONE

### Task 2.1: complete (commits ea7dd1b..a4f9d5b, tests: `pytest -q` → 22/22 pass)

### Task 2.2: complete (commits a4f9d5b..a9511dd, tests: `pytest -q` → 27/27 pass)
- Ruling: 将 `tests/fixtures/transcripts.py`（原计划 Task 5.2 的一部分）提前到 Task 2.2 创建 —— Task 2.2 测试需要基准用例文本，fixtures 属共享测试数据，提前避免内联重复 —— 若 Task 5.2 重复创建会冲突（5.2 将只补 MockLLMClient）

### Task 2.3: complete (commits a9511dd..db8b3f3, tests: `pytest -q` → 30/30 pass)

### Task 2.4: complete (commits db8b3f3..f6d4695, tests: `pytest -q` → 40/40 pass)

### Task 2.5: complete (commits f6d4695..8acd0c3, tests: `pytest -q` → 46/46 pass)
- **Phase 2 阶段验收**：`pytest tests/unit` 全绿 ✅；6 类错误签名可归一化 ✅；注入不误杀 ✅；PII 召回 5/5、误报 0 ✅；脱敏正确 ✅

### Phase 2: DONE

### Task 3.1: complete (commits 8acd0c3..e9c4aa6, tests: `pytest -q` → 50/50 pass)

### Task 3.2: complete (commits e9c4aa6..36e57db, tests: `pytest -q` → 55/55 pass)

### Task 3.3: complete (commits 36e57db..f1e73b0, tests: `pytest -q` → 58/58 pass)
- **Phase 3 阶段验收**：`pytest` 全绿 ✅；修复提示/单调性熔断单元被测 ✅（端到端"≤2 次收敛"由 Phase 5 的 S2 覆盖）

### Phase 3: DONE

### Task 4.1: complete (commits f1e73b0..99e370d, tests: `pytest -q` → 62/62 pass)

### Task 4.2: complete (commits 99e370d..6fc2023, tests: `pytest -q` → 67/67 pass)

### Task 4.3: complete (commits 6fc2023..e2e1ef9, tests: `pytest -q` → 77/77 pass)- Ruling: `apply_pii_policy` 扩展为"卡尾号覆写"完整策略（LLM 说 true 但仅有卡尾号 → false），并补测试 —— 因决策 D1 要求覆写须生效于编排输出复核层 —— 若实现遗漏则该策略在端到端失效（已补 S5b 覆盖）
- Ruling: 将 `tests/fixtures/mock_client.py`（原计划 Task 5.2）提前到 Task 4.3 —— Task 4.3 的 7 故障场景需要脚本化 mock —— 若重复创建会冲突（5.2 将只补 conftest 引用）

### Task 4.4: complete (commits e2e1ef9..a8cc1ca, tests: `pytest -q` → 83/83 pass)
- **Phase 4 阶段验收**：7 故障场景全收敛定义终态 ✅；0 未捕获异常 ✅；日志四要素 ✅

### Phase 4: DONE

### Task 5.1: complete (commits a8cc1ca..e4709dd, tests: `pytest -q` → 86/86 pass)

### Task 5.2 + 5.3: complete (commits e4709dd..3c99362, tests: `pytest -q` → 89/89 pass)- Ruling: Task 5.2（MockLLMClient/fixtures）已在 Task 2.2/4.3 提前完成，此处仅补 `tests/conftest.py` —— 避免重复创建 —— 无成本
- 说明：S1/S2/S3 为集成验证套件，行为已于 Task 4.3 TDD；S2 新增日志断言（首次错误签名）

### Task 5.4: complete (commits 3c99362..f2c8eec, tests: `pytest -q` → 95/95 pass)
- **Phase 5 阶段验收**：`pytest` 全绿（S1/S2/S3/S4/S5/S5b）✅；API 契约测试通过 ✅；全 mock、无需 API Key ✅

### Phase 5: DONE

### Task 6.1 + 6.2: complete (commits f2c8eec..dd5a911, tests: `pytest -q` → 96/96 pass; `python examples/run_demo.py` → 4/4 SUCCESS)
- **Finding + Fix（E2E 抓到）**：真实 API 端到端暴露 provider bug —— function-calling 模式下 `message.content` 为空，结构化数据在 `tool_calls[0].function.arguments`，导致全部 JSON_DECODE。已 TDD 修复：`_from_raw` 回退读 tool_calls 参数。**这正是 mock 测试覆盖不到、必须真实 E2E 才能发现的缺陷。**
- 决策记录：E2E 结果完全符合设计附录 A（TX-001 pii=False 卡尾号覆写生效；TX-003 urgency 未被抬升）

### Task 6.3: complete (验证：`git status` 干净；`.env` 未跟踪；`.env.example` 无真实密钥；`pytest -q` → 96/96 pass)
- **Phase 6 阶段验收**：`pytest` 全绿 ✅；README 三部分齐全 ✅；demo 跑通用例 1~4 ✅；无硬编码密钥 ✅

### Phase 6: DONE —— 全部 18 个任务完成

### Final review（fresh reviewer subagent, branch a366b3f..dd5a911）
评审结论：**With fixes**。重新分级（按"使用者实际得到什么"）后进入修复：
- Critical：C1（所有 FALLBACK 出口不写 `pipeline_result` 日志，空输入零日志）、C2（`redact` 未掩码邮箱/手机号，违反 §8.4 必做）
- Important：I1（provider 未传 timeout/max_tokens）、I2（传输错误无退避）、I3（净化器未转义分隔符，可逃逸）、I4（超长仅 HTTP 层拒绝，`run_pipeline` 绕过）、I5（服务入口未初始化日志）、I6（`_classify_transport` 返回契约外值）
- Minor（deferred）：见最终消息

Final: fixed C1 — test_fallback_emits_pipeline_result_log + test_empty_input_emits_pipeline_result_log RED→GREEN，suite 105/105
Final: fixed C2 — test_email_masked + test_phone_masked RED→GREEN，suite 105/105
Final: fixed I1 — test_extract_passes_timeout_and_max_tokens RED→GREEN，suite 105/105
Final: fixed I2 — test_backoff_delay_grows_exponentially RED→GREEN，suite 105/105
Final: fixed I3 — test_nested_markers_are_escaped RED→GREEN，suite 105/105
Final: fixed I4 — test_over_limit_rejected_at_orchestrator RED→GREEN，suite 105/105
Final: fixed I5 — test_server_configures_logging RED→GREEN，suite 105/105
Final: fixed I6 — ErrorType 新增 TRANSPORT_ERROR（契约补齐），suite 105/105
Final: E2E 复验 `python examples/run_demo.py` → exit 0，4/4 SUCCESS，pipeline_result 已记录
Ruling: 保留 SDD 账本为交付文档（复制到 `docs/BUILD_LOG.md`）而非直接删除 —— 该账本记录了全部裁定与 POC/评审轨迹，是有价值的交付物 —— 无成本



