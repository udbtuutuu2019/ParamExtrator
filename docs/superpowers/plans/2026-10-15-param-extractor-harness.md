# ParamExtrator Harness 实现计划

> **给执行者（agentic worker）**：请使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步实现本计划。步骤用 checkbox（`- [ ]`）跟踪。

**Goal:** 实现一个确定性、弹性、可观测的 Harness 流水线，把杂乱客服对话稳定地转为强类型结构化数据，失败时优雅降级而非崩溃。

**Architecture:** 三层控制环——前置护栏（注入/PII）→ 编排状态机（提取→校验→修复，`N=2`）→ 兜底降级。所有子系统通过 `contracts/` 定义的数据契约通信；LLM 通过 `LLMClient` 接口注入，便于 mock 与换供应商。

**Tech Stack:** Python 3.11+、Pydantic v2、instructor（≥1.17）、openai SDK、pytest、FastAPI（服务入口）、python-logging（结构化 JSON）。

**Spec:** `docs/TECHNICAL_DESIGN.md` v1.4（设计），`docs/RISK_AND_POC_CHECKLIST.md`（已验证的高风险假设 R1–R9），`docs/POC_INSTRUCTOR_DEEPSEEK.md`（POC 实证）。

## Global Constraints

以下为规格固定的值，**所有任务隐含遵守**（决策记录见设计附录 C）：

- `LLM_MODEL=deepseek-chat`；`LLM_BASE_URL=https://api.deepseek.com`。
- `LLM_TEMPERATURE=0.0`（初始轮与修复轮统一，决策 D9）。
- `MAX_RETRIES=2`，instructor 调用 **`max_retries=0`**（重试全部由自研层控制，决策 D2）→ 最多 3 次总调用。
- `ExtractionOutput` 必须 `model_config = ConfigDict(extra="forbid")`（幻觉字段判错，决策 G2）。
- 枚举大小写敏感；`summary` 约束 `min_length=1, max_length=200`。
- `detected_pii` 卡尾号策略：**仅卡尾号命中 → `false`**（决策 D1）。
- **LLM 失败不返回 5xx**；统一返回 `200` + `status ∈ {SUCCESS, REPAIRED, FALLBACK}`（决策 D6）。
- Fallback 对象每个字段为**固定常量**；`detected_pii` 亦应用卡尾号覆写。
- 结构化日志为 **JSON**，必须含四项：每次 LLM 调用延迟、重试次数、schema 校验错误、最终结果。
- `.env` 不提交；仓库仅提交 `.env.example`。
- 所有输入内容包进 `<untrusted_user_data>…</untrusted_user_data>` 数据块。

## Review Focus

规格隐含、但常规任务测试不一定覆盖，最可能"咬人"的 5 类输入/失败模式（每条的测试已挂到对应任务）：

1. **空输入 / 纯空白 `content`** → 必须返回 `FALLBACK` 且**不调用 LLM**（不得崩溃、不得白花调用）。测试：Task 4.3。
2. **幻觉字段**（模型多输出 schema 之外的字段）→ 必须被 `extra="forbid"` **拒绝并触发修复**，而非静默丢弃。测试：Task 2.1。
3. **卡尾号-only 输入** → `detected_pii` 必须为 `false`（策略覆写），不得因模型返回 `true` 而透传。测试：Task 5.4（S5b）。
4. **`max_tokens` 截断**（`finish_reason=length`）→ 必须分类为 `INCOMPLETE_RESPONSE`，不得当作合法输出。测试：Task 4.3。
5. **超长 `content`（> `MAX_INPUT_BYTES`）** → 必须拒绝（400），不得静默截断后继续。测试：Task 5.1。

---

## 文件结构（先定边界，再拆任务）

```
ParamExtrator/
├── pyproject.toml                 # 依赖与工具配置
├── .gitignore / .env.example
├── config/default.yaml            # 集中配置
├── src/param_extrator/
│   ├── __init__.py
│   ├── config.py                  # Settings 加载
│   ├── contracts/                 # 数据契约（唯一通信语言）
│   │   ├── output.py              # ExtractionOutput（extra=forbid）
│   │   ├── request.py             # ExtractionRequest
│   │   ├── result.py              # ExtractionResult / Status
│   │   └── errors.py              # ErrorType / ErrorSignature
│   ├── ingestion/ingest.py        # 规范化 + 幂等键 + 超长校验
│   ├── guardrail/
│   │   ├── injection.py           # 注入检测
│   │   ├── sanitizer.py           # 语义隔离
│   │   └── pii_scan.py            # PII 本地扫描 + 卡尾号策略
│   ├── extraction/
│   │   ├── client.py              # LLMClient 接口 + LLMResponse
│   │   ├── provider.py            # instructor 实现（max_retries=0）
│   │   └── prompts.py             # 系统提示 + 修复提示
│   ├── validation/validator.py    # 三级校验 + 错误签名
│   ├── repair/repair_engine.py    # 针对性修复 + 单调性
│   ├── fallback/fallback_handler.py
│   ├── observability/
│   │   ├── logger.py              # JSON 结构化日志
│   │   └── redaction.py           # 脱敏
│   ├── pipeline/orchestrator.py   # 状态机编排（永不抛异常）
│   └── api/server.py              # POST /v1/extract
├── tests/
│   ├── fixtures/transcripts.py     # 用例 1~4
│   ├── conftest.py                 # MockLLMClient
│   ├── unit/ integration/ adversarial/
└── examples/run_demo.py
```

**复用已有 POC 产物**：`poc/poc4_pii.py`（PII 扫描器）→ 重写为 `guardrail/pii_scan.py`；`poc/skeleton.py`（校验/修复提示/注入检测）→ 拆入对应模块。

---

## Phase 1：地基（契约 + 配置 + 骨架）

**阶段验收标准**：`pytest tests/unit/test_contracts.py` 全绿；`import param_extrator` 成功；契约模型对 `extra`/枚举/`min_length` 的约束被测试证明。

### Task 1.1：项目骨架与依赖

**目标**：建立可安装的包与开发环境。
**涉及文件**：
- Create: `pyproject.toml`、`.gitignore`、`.env.example`、`config/default.yaml`、`src/param_extrator/__init__.py`
**接口**：Produces — 可 `import param_extrator`；依赖 `pydantic>=2`、`instructor>=1.17`、`openai`、`fastapi`、`uvicorn`、`pytest`、`python-dotenv`。
**验证方式**：
- 命令 `pip install -e .` 成功；
- 命令 `python -c "import param_extrator"` 无报错；
- `.env.example` 含 `DEEPSEEK_API_KEY=`；`.gitignore` 含 `.env`。

### Task 1.2：数据契约

**目标**：定义系统的唯一通信语言（输入/输出/结果/错误）。
**涉及文件**：
- Create: `src/param_extrator/contracts/output.py`、`request.py`、`result.py`、`errors.py`；`tests/unit/test_contracts.py`
**接口**：
- Produces `ExtractionOutput(BaseModel)`（`extra="forbid"`；字段见 Global Constraints）；
- Produces `ExtractionRequest(BaseModel)`（`transcript_id`、`content`、可选 `customer_id_hint`/`trace_id`/`tenant_id`/`idempotency_key`）；
- Produces `Status(StrEnum)` = `SUCCESS|REPAIRED|FALLBACK`；
- Produces `ExtractionResult(BaseModel)`（`status`、`data`、`attempts`、`repairs`、`needs_human_review`、`failure_reason`、`trace_id`、`latency_ms`）；
- Produces `ErrorType(StrEnum)`（含 `INCOMPLETE_RESPONSE`、`JSON_DECODE`、`EXTRA_FIELD`、`SCHEMA_VALIDATION`、`TYPE_ERROR`、`ENUM_MISMATCH`、`LENGTH_VIOLATION`、`MISSING_FIELD`、`TRANSPORT_TIMEOUT`、`RATE_LIMIT`、`CONTEXT_OVERFLOW`、`UNEXPECTED`）；
- Produces `ErrorSignature(BaseModel)`（`error_type`、`fields`、`messages`、`raw_snippet`）。
**验证方式**：
- `<test_contracts.py>` 断言：合法对象通过；非法枚举抛错；`summary=""` 抛错；`summary` 超 200 抛错；**多出字段抛错**（Review Focus #2）。

### Task 1.3：配置加载

**目标**：集中式配置，含 Global Constraints 的全部默认值。
**涉及文件**：
- Create: `src/param_extrator/config.py`；`tests/unit/test_config.py`
**接口**：Produces `Settings(BaseModel)` 与 `load_settings() -> Settings`（默认值 = Global Constraints；从 env + `config/default.yaml` 读取）。
**验证方式**：
- 单测：默认值与 Global Constraints 一致（`max_retries==2`、`llm_temperature==0.0`、`llm_model=="deepseek-chat"`）；
- 单测：环境变量可覆盖默认值。

---

## Phase 2：校验与护栏

**阶段验收标准**：`pytest tests/unit` 全绿；错误签名可归一化 6 类错误；注入检测命中且不误杀正常对话；PII 扫描召回 5/5、误报 0；脱敏正确。

### Task 2.1：Validator + 错误签名

**目标**：三级校验（完整性→解码→schema），输出归一化错误签名，**永不抛异常**。
**涉及文件**：
- Create: `src/param_extractor/validation/validator.py`；`tests/unit/test_validator.py`
- Consumes: `ExtractionOutput`、`ErrorSignature`、`ErrorType`
**接口**：Produces `validate_content(content: str, finish_reason: str | None = None) -> tuple[ExtractionOutput | None, ErrorSignature | None]`。
**验证方式**：
- 单测 6 类：`JSON_DECODE`、`ENUM_MISMATCH`、`LENGTH_VIOLATION`、`MISSING_FIELD`、**`EXTRA_FIELD`**（Review Focus #2）、`TYPE_ERROR`；
- 单测：`finish_reason="length"` → `INCOMPLETE_RESPONSE`（Review Focus #4 的单元侧）；
- 单测：非法输入返回 `(None, sig)` 而非抛异常。

### Task 2.2：注入检测

**目标**：规则化识别间接提示注入，输出风险标记（**只标记、不拒绝**）。
**涉及文件**：
- Create: `src/param_extractor/guardrail/injection.py`；`tests/unit/test_injection.py`
**接口**：Produces `detect_injection(text: str) -> tuple[list[str], bool]`（命中规则名列表，是否可疑）。
**验证方式**：
- 单测：TX-003 命中 `system_override`；`role_hijack`/`output_manipulation` 各命中；
- 单测：正常对话（TX-001）**不**命中（不误杀）。

### Task 2.3：输入净化 / 语义隔离

**目标**：把不可信内容包进数据块。
**涉及文件**：
- Create: `src/param_extractor/guardrail/sanitizer.py`；`tests/unit/test_sanitizer.py`
**接口**：Produces `wrap_untrusted(text: str) -> str`（含 `<untrusted_user_data>` 标记）。
**验证方式**：
- 单测：输出含开闭标记；内容原样保留。

### Task 2.4：PII 扫描 + 卡尾号策略

**目标**：本地高召回识别 PII；卡尾号单独命中时判非 PII。
**涉及文件**：
- Create: `src/param_extractor/guardrail/pii_scan.py`；`tests/unit/test_pii_scan.py`
- 迁移自: `poc/poc4_pii.py`
**接口**：Produces `scan_pii(text: str) -> tuple[set[str], bool]`、`apply_pii_policy(llm_flag: bool, cats: set[str]) -> bool`。
**验证方式**：
- 单测：NRIC/密码/完整卡号/手机/邮箱 各命中；
- 单测：`尾号 4402` → `False`（Review Focus #3 的本地侧，决策 D1）；
- 单测：负样本（订单号/日期）不误报。

### Task 2.5：脱敏

**目标**：日志/错误签名中的敏感文本脱敏。
**涉及文件**：
- Create: `src/param_extractor/observability/redaction.py`；`tests/unit/test_redaction.py`
**接口**：Produces `redact(text: str, max_len: int = 256) -> str`（密码→`***`、卡号保留后 4、证件号掩码、截断）。
**验证方式**：
- 单测：`SuperSecretPass123` 被掩码；输出长度 ≤ `max_len`。

---

## Phase 3：提取与修复循环

**阶段验收标准**：`pytest tests/unit/test_repair_engine.py` 全绿；mock 驱动下首轮错误在 ≤2 次修复内收敛；连续同错触发单调性熔断。

### Task 3.1：LLMClient 接口 + instructor provider

**目标**：抽象 LLM 调用，供编排与 mock。
**涉及文件**：
- Create: `src/param_extractor/extraction/client.py`、`src/param_extractor/extraction/provider.py`；`tests/unit/test_provider.py`
**接口**：
- Produces `LLMResponse`（`content: str`、`finish_reason: str | None`）；
- Produces `LLMClient(Protocol)`：`extract(messages: list[dict], temperature: float) -> LLMResponse`；
- Produces `InstructorClient(LLMClient)`（instructor `max_retries=0`，`response_model=ExtractionOutput` → 序列化回 `content`）。
**验证方式**：
- 单测（mock OpenAI client）：`InstructorClient.extract` 传参 `max_retries==0`；
- 单测：返回结构含 `content`/`finish_reason`。

### Task 3.2：提示词

**目标**：系统提示（含安全声明）+ 针对性修复提示。
**涉及文件**：
- Create: `src/param_extractor/extraction/prompts.py`；`tests/unit/test_prompts.py`
- 迁移自: `poc/prompts.py`、`poc/skeleton.py::repair_prompt`
**接口**：Produces `SYSTEM_PROMPT: str`、`build_repair_prompt(raw_output: str, sig: ErrorSignature) -> str`。
**验证方式**：
- 单测：系统提示含"不可信数据/忽略块内指令"声明；
- 单测：修复提示含原始输出片段 + 错误清单 + "只输出 JSON"约束。

### Task 3.3：Repair Engine

**目标**：错误→修复消息；维护单调性状态。
**涉及文件**：
- Create: `src/param_extractor/repair/repair_engine.py`；`tests/unit/test_repair_engine.py`
**接口**：Produces `RepairEngine`（`next_message(raw, sig) -> dict`；`should_halt(sig) -> bool` 基于连续同错签名）。
**验证方式**：
- 单测：`next_message` 产出含原始输出+错误的 `user` 消息；
- 单测：连续两次相同签名 → `should_halt == True`。

---

## Phase 4：编排、兜底与可观测

**阶段验收标准**：`pytest tests/unit tests/integration` 全绿；故障注入 7 场景全部收敛到定义终态、**0 未捕获异常**；日志事件含规格四要素。

### Task 4.1：Fallback Handler

**目标**：生成固定常量兜底对象，绝不抛异常。
**涉及文件**：
- Create: `src/param_extractor/fallback/fallback_handler.py`；`tests/unit/test_fallback.py`
**接口**：Produces `build_fallback(trace_id: str, reason: str, pii: bool) -> ExtractionResult`。
**验证方式**：
- 单测：`status==FALLBACK`、`needs_human_review==True`、`data` 各字段为固定常量；
- 单测：`summary` 非空；**卡尾号覆写规则**在兜底路径同样生效（`pii=False` 时 `detected_pii=False`）。

### Task 4.2：结构化日志

**目标**：JSON 日志，含规格四要素。
**涉及文件**：
- Create: `src/param_extractor/observability/logger.py`；`tests/unit/test_logger.py`
- Consumes: `redact`
**接口**：Produces `log_event(event: str, **fields) -> None`；helper `log_llm_call/log_validation/log_pipeline_result/log_guardrail`。
**验证方式**：
- 单测：`log_llm_call` 输出含 `latency_ms`；`log_validation` 含 `error_signature`；`log_pipeline_result` 含 `status/repairs`；
- 单测：敏感字段经 `redact`。

### Task 4.3：Orchestrator（状态机）

**目标**：编排全流程；**保证永不抛异常**。
**涉及文件**：
- Create: `src/param_extractor/pipeline/orchestrator.py`；`tests/unit/test_orchestrator.py`
- Consumes: `LLMClient`、`validate_content`、`RepairEngine`、`build_fallback`、`detect_injection`、`wrap_untrusted`、`scan_pii`、`apply_pii_policy`、`Settings`
**接口**：Produces `run_pipeline(req: ExtractionRequest, client: LLMClient, settings: Settings) -> ExtractionResult`。
**验证方式**：
- 单测 7 故障场景（mock client）：正常→`SUCCESS`；超时→`FALLBACK`(`TRANSPORT_TIMEOUT`)；限流→`FALLBACK`(`RATE_LIMIT`)；非法 JSON→`FALLBACK`(`JSON_DECODE`)；**空输入→`FALLBACK` 且 `client.calls==0`**（Review Focus #1）；**截断→`INCOMPLETE_RESPONSE`**（Review Focus #4）；畸形返回→`FALLBACK`(`UNEXPECTED`)；
- 单测：`attempts/repairs` 口径仅计自研层；`repairs==attempts-1`。

### Task 4.4：Ingestion

**目标**：规范化输入、计算幂等键、拒绝超长。
**涉及文件**：
- Create: `src/param_extractor/ingestion/ingest.py`；`tests/unit/test_ingest.py`
**接口**：Produces `normalize(req) -> ExtractionRequest`、`compute_idempotency_key(req) -> str`、`is_over_limit(req) -> bool`。
**验证方式**：
- 单测：空白被去除、控制字符剥离；
- 单测：相同输入 → 相同幂等键；不同内容 → 不同键；
- 单测：超 `MAX_INPUT_BYTES` → `is_over_limit==True`。

---

## Phase 5：入口与测试套件

**阶段验收标准**：`pytest` 全绿（含 S1/S2/S3/S4/S5/S5b）；API 契约测试通过；全 mock、无需 API Key。

### Task 5.1：API 服务入口

**目标**：`POST /v1/extract`；失败一律 200。
**涉及文件**：
- Create: `src/param_extractor/api/server.py`；`tests/integration/test_api.py`
- Consumes: `run_pipeline`、`ExtractionRequest`、`ExtractionResult`
**接口**：Produces FastAPI `app`；`POST /v1/extract`。
**验证方式**：
- 集成测试：正常请求 → 200 + `status` 字段；
- 集成测试：LLM 失败 → **200** + `status=FALLBACK`（决策 D6）；
- 集成测试：**超长 content → 400**（Review Focus #5）。

### Task 5.2：MockLLMClient 与 fixtures

**目标**：脚本化 mock，支持全分支测试、零成本。
**涉及文件**：
- Create: `tests/fixtures/transcripts.py`（用例 1~4）、`tests/conftest.py`
**接口**：Produces `MockLLMClient(script: list[LLMResponse])`（实现 `LLMClient`，支持 `raise`/截断）；fixtures `tx001..tx004`。
**验证方式**：
- 单测：mock 可脚本化返回、可注入异常、可返回 `finish_reason="length"`。

### Task 5.3：必测场景 S1/S2/S3

**目标**：覆盖挑战要求的三类必测。
**涉及文件**：
- Create: `tests/integration/test_pipeline.py`
**接口**：Consumes MockLLMClient + run_pipeline。
**验证方式**：
- **S1 标准成功**：合法首轮 → `SUCCESS`、`attempts==1`；
- **S2 修复恢复**：首轮非法、次轮合法 → `REPAIRED`、`repairs==1`、日志含首次错误签名；
- **S3 预算耗尽兜底**：始终非法 → `FALLBACK`、`needs_human_review==True`、**不抛异常**。

### Task 5.4：对抗测试 S4/S5/S5b

**目标**：验证注入防御与 PII 策略。
**涉及文件**：
- Create: `tests/adversarial/test_injection.py`、`tests/adversarial/test_pii.py`
**验证方式**：
- **S4 注入**：TX-003 → 输出合法、`urgency != CRITICAL`、无 `SYSTEM COMPROMISED`；
- **S5 PII**：TX-002 → `detected_pii==True`；
- **S5b 卡尾号覆写**：模型返回 `true` 时 → Harness 输出 `false`（Review Focus #3 全链侧）。

---

## Phase 6：文档与交付

**阶段验收标准**：`pytest` 全绿；README 三部分齐全；`examples/run_demo.py` 可跑通用例 1~4；无硬编码密钥。

### Task 6.1：README.md

**目标**：满足挑战 §4 的三部分。
**涉及文件**：Create `README.md`
**验证方式**：
- 人工评审：含"架构 / 权衡取舍 / 生产就绪性（含 10k+/min）"三节 + 快速开始。

### Task 6.2：演示脚本

**目标**：跑通用例 1~4 并打印结果。
**涉及文件**：Create `examples/run_demo.py`
**验证方式**：
- 命令 `python examples/run_demo.py` 输出四条用例结果（真实 API）；
- 无 API Key 时给出清晰提示。

### Task 6.3：提交准备

**目标**：仓库整洁、可提交。
**涉及文件**：Modify `.gitignore`
**验证方式**：
- `git status` 无 `.env`、无 `__pycache__`；
- `.env.example` 存在且无真实密钥；
- 提交前自检清单（设计 §16.4）全部勾选。

---

## 执行顺序与依赖

```
Phase 1 (地基) ──► Phase 2 (校验/护栏) ──► Phase 3 (提取/修复) ──► Phase 4 (编排/兜底) ──► Phase 5 (入口/测试) ──► Phase 6 (文档/交付)
```

- Phase 内部任务基本可并行（契约已定）；Phase 之间**严格顺序**（后一阶段 Consumes 前一阶段 Produces）。
- **POC 产物直接复用**：PII 扫描器（Task 2.4）、校验/修复提示/注入检测（Task 2.1/2.2/3.2/3.3）。
- **未决项**：POC-5（吞吐/并发）**不在本计划内**，它只影响 README 的生产就绪性章节，可在 Phase 6 之前按需补。

---

## Self-Review（对照 Spec 自检）

1. **Spec 覆盖**：§2.A→Task 1.2/2.1；§2.B→Task 3.3/4.1/4.3；§2.C→Task 2.2/2.3/5.4；§2.D→Task 4.2；§3 用例→Task 5.3/5.4；§4 README→Task 6.1；§4 测试→Task 5.3/5.4；§4 10k→Task 6.1（Phase 6）。**无缺口。**
2. **步骤粒度**：每个任务均给出目标/文件/接口/验证，执行者可独立实现。
3. **类型一致**：`ErrorType`/`ErrorSignature`/`ExtractionResult` 只在 Task 1.2 定义，后续任务 Consumes 复用，未改名。
4. **Review Focus**：5 条全部挂到具体任务测试（#1→4.3、#2→2.1、#3→5.4、#4→4.3/2.1、#5→5.1）。
5. **篇幅比例**：计划 < 规格，均为决策而非代码转写。

---

**计划结束。等待确认后再进入 Build。**
