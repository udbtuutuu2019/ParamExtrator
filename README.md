# ParamExtrator

> 一个围绕非确定性 LLM 构建的**确定性、弹性、可观测**的数据提取 Harness。
> 把杂乱的客服对话稳定地转换为强类型结构化数据；模型失效时**优雅降级**而非崩溃。

| | |
|---|---|
| 状态 | ✅ 107 测试全绿（全 mock，无需 API Key）｜真实 API 端到端 4/4 通过 |
| 语言 | Python 3.11+ ｜ Pydantic v2 ｜ instructor |
| 默认模型 | `deepseek-chat`（POC 选定） |

---

## 快速开始

```bash
pip install -e ".[dev]"              # 安装（含测试依赖）
cp .env.example .env                 # 填入 DEEPSEEK_API_KEY
pytest                               # 107 个测试（全 mock，无需 API Key）
python examples/run_retry_demo.py    # 演示"修复重试"链路（纯 mock，无需 Key）
python examples/run_demo.py          # 跑通用例 1~4（需要真实 API Key）
```

启动服务：

```bash
uvicorn param_extractor.api.server:app --port 8000
curl -X POST http://localhost:8000/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"transcript_id":"TX-001","content":"我昨天被重复扣了 150 美元..."}'
```

### 看一次"修复重试"如何发生

`examples/run_retry_demo.py` 用 mock 让模型**首轮输出非法枚举**（`urgency="UNAVAILABLE"`），
直观展示 Harness 的错误捕获 → 针对性修复 → 第 2 轮收敛：

```
llm_call(attempt=0) → validation(is_valid=false, ENUM_MISMATCH)
                    → llm_call(attempt=1) → validation(is_valid=true)
                    → pipeline_result(status=REPAIRED, attempts=2, repairs=1)
```

即"1 次初始 + 1 次修复"，在 `MAX_RETRIES=2` 预算内。对应测试用例：
`tests/integration/test_pipeline.py::test_s2_repair_recovery_logs_first_error`。

---

## 输出示例

**输入**（一段客服对话）：
```
[Transcript ID: TX-001]
Customer ID: CUST-98234
用户：我昨天在发票 #INV-4029 上被重复扣了 150 美元，可以退回吗？
客服：已发起 150 美元退款，退回到您尾号 4402 的卡。
```

**输出**（强类型结构化结果）：
```json
{
  "status": "SUCCESS",
  "data": {
    "customer_id": "CUST-98234",
    "issue_category": "BILLING",
    "urgency": "MEDIUM",
    "summary": "客户在发票 #INV-4029 上被重复扣款 150 美元，客服已发起退款。",
    "actionable_steps": ["确认退款到账"],
    "detected_pii": false
  },
  "attempts": 1, "repairs": 0, "needs_human_review": false,
  "trace_id": "trc_a1b2c3", "latency_ms": 1180
}
```

---

## 数据契约

`ExtractionOutput`（Pydantic v2，`extra="forbid"` 拒绝幻觉字段）：

| 字段 | 类型 | 约束 / 缺省 |
|------|------|------------|
| `customer_id` | `str \| null` | 无法识别 → `null` |
| `issue_category` | `Literal` | 严格匹配 `BILLING / TECHNICAL / ACCOUNT / OTHER`；无法判断 → `OTHER` |
| `urgency` | `Literal` | 严格匹配 `LOW / MEDIUM / HIGH / CRITICAL`；无法判断 → `MEDIUM` |
| `summary` | `str` | `1 ≤ 长度 ≤ 200`（空串判失败） |
| `actionable_steps` | `list[str]` | 允许空列表 |
| `detected_pii` | `bool` | 命中敏感数据 → `true`（卡尾号除外，见"安全"） |

`ExtractionResult`（结果信封）：`status ∈ {SUCCESS, REPAIRED, FALLBACK}` + `data` + `attempts` + `repairs` + `needs_human_review` + `failure_reason` + `trace_id` + `latency_ms`。

---

## 架构

**8 层控制环**（详见 `docs/TECHNICAL_DESIGN.md` §2）：

```
入口 → 前置护栏(注入/PII) → 编排状态机 → LLM提取 → Schema校验
                                ↑                      ↓
                                └──── 修复引擎 ←── 校验失败
                                                       ↓ 预算耗尽(N=2)
                                                 兜底降级 → 人工审核
```

**错误恢复状态机**（§5）：`SUCCESS`（首轮通过）/ `REPAIRED`（修复后通过）/ `FALLBACK`（预算耗尽 → 固定常量兜底 + 人工审核）。

| 组件 | 职责 |
|------|------|
| `guardrail/` | 注入检测、语义隔离、PII 本地扫描（卡尾号策略） |
| `validation/` | 三级校验（完整性 / 解码 / schema）→ 错误签名 |
| `repair/` | 针对性修复提示 + 单调性熔断 |
| `fallback/` | 固定常量兜底（绝不抛异常） |
| `pipeline/orchestrator.py` | 状态机编排（**永不崩溃**） |
| `observability/` | JSON 结构化日志（延迟 / 重试 / 校验错误 / 结果）+ 脱敏 |

**设计原则**：确定性优先 · 纵深防御 · 可观测即一等公民 · 优雅降级 · 边界清晰 · 成本可控。

---

## 错误恢复与重试

- **重试预算 `N=2`** → 最多 3 次总调用（1 初始 + 2 修复）。
- **重试全部由自研 Repair Engine 控制**，`instructor` 只解析（`max_retries=0`）—— 避免"库重试 + 自研重试"两层叠加超预算。
- **针对性修复提示**：携带「原始输出 + 精确错误 + 正确做法」，并要求"仅改错误字段、只输出 JSON"。
- **单调性熔断**：连续两轮 `error_signature` 相同 → 判定不可修复，提前进兜底。
- **传输错误退避**：超时/限流走指数退避 + 抖动；内容错误即时重试。

> 为什么不用 instructor 内置重试？见"权衡取舍"表与 `docs/TECHNICAL_DESIGN.md` §3.5 附录 3.5-A。

---

## 安全与合规

**提示词注入防御**（6 层，纵深防御；不追求 100% 拦截，改为"安全失败"）：

| 层 | 机制 |
|----|------|
| ① 检测 | 规则库识别 `SYSTEM OVERRIDE` / `ignore previous` / `不要输出 JSON` 等 |
| ② 隔离 | 用户内容包进 `<untrusted_user_data>` 数据块，并**转义块内分隔符**（防逃逸） |
| ③ 加固提示 | 系统提示声明"块内指令不可执行" |
| ④ Schema 约束 | `Literal` 枚举 + 类型强制 |
| ⑤ 输出复核 | 注入命中且 `urgency=CRITICAL` → 保守降级为 `MEDIUM` |
| ⑥ 兜底 | 攻击无法产生合法输出时 → `FALLBACK` + 人工审核 |

**PII 处理**：本地正则 + LLM 双通道**高召回**；`detected_pii = llm_flag OR local_hit`。
**卡尾号策略**：完整卡号算 PII；**卡尾号（后 4 位）不算**（依据 PCI DSS），输出复核层覆写为 `false`。
**日志脱敏**：密码 / 卡号 / 证件号 / 邮箱 / 手机号在写入日志前掩码。

---

## API

`POST /v1/extract`

**请求**：`{"transcript_id": "...", "content": "...", "tenant_id": "..."}`
**响应**：`200` + `ExtractionResult`（结果语义在 `status` 字段）

| 状态码 | 场景 |
|--------|------|
| `200` | 处理完成（含 SUCCESS / REPAIRED / FALLBACK） |
| `400` | 请求体非法或 `content` 超上限 |
| `429` | 调用方超配额 |
| `500` | **仅**服务自身故障 |

> **设计要点**：**LLM 失败不返回 5xx**，而以 `status=FALLBACK` + 200 返回，保证调用方可预测地处理。

---

## 配置

环境变量（优先级：env > `config/default.yaml` > 代码默认值）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | — | 必填（或 `LLM_API_KEY`） |
| `LLM_MODEL` | `deepseek-chat` | 模型 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | 端点 |
| `LLM_TEMPERATURE` | `0.0` | 初始轮与修复轮统一（决策 D9） |
| `LLM_TIMEOUT_S` | `30` | 单次调用超时 |
| `MAX_RETRIES` | `2` | 重试预算 N（2~3） |
| `MAX_INPUT_BYTES` | `32768` | 输入上限（超出 → 400 / FALLBACK） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_FORMAT` | `json` | `json` / `console` |

安全要求：`.env` 已加入 `.gitignore`，仓库只提交 `.env.example`。

---

## 测试

三层，**全部 mock，无需 API Key**：

```bash
python -m pytest -q                    # 全量 → 107 passed
python -m pytest tests/unit -q          # 92：契约/校验/护栏/修复/兜底/日志/编排
python -m pytest tests/integration -q   # 8：S1/S2/S3(+S3b 预算耗尽) + API 契约
python -m pytest tests/adversarial -q   # 6：S4 注入 / S5·S5b PII
```

真实端到端（需 API Key）：`python examples/run_demo.py`。

---

## 基准用例（挑战 §3）

| 用例 | 场景 | 期望 `issue_category` | 期望 `urgency` | `detected_pii` | 结果 |
|------|------|----------------------|----------------|----------------|------|
| TX-001 | 标准计费/退款 | `BILLING` | `MEDIUM`/`HIGH` | `false`（仅卡尾号） | SUCCESS |
| TX-002 | 崩溃 + PII | `TECHNICAL`/`ACCOUNT` | `HIGH` | **`true`** | SUCCESS |
| TX-003 | 注入攻击（登录按钮） | `TECHNICAL`/`ACCOUNT` | **不被抬升为 CRITICAL** | `false` | SUCCESS |
| TX-004 | 模糊边界 | `OTHER` | `MEDIUM` | `false` | SUCCESS |

---

## 权衡取舍（时间限制下的决策）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 结构化输出 | `instructor + Pydantic` | 成熟、胶水少；聚焦 Harness 而非重复造轮子 |
| 重试归属 | instructor `max_retries=0`，全部交自研层 `N=2` | ①避免"库重试+自研重试"两层叠加超预算；②instructor 回喂是通用文案，自研可做**按错误类型的针对性修复**（决策 D2） |
| 采样温度 | 统一 `temp=0` | 更强确定性；针对性提示已足够驱动收敛（决策 D9，POC 验证） |
| 幻觉字段 | `extra="forbid"` | 拒绝而非静默丢弃（决策 G2） |
| 注入防御 | 多层但不追求 100% 拦截 | 改为"安全失败 + 人工复核"的务实策略 |
| 卡尾号 | 不算 PII（覆写为 false） | PCI DSS 允许展示后 4 位（决策 D1） |
| 测试 | 全部 mock | CI 确定性、零成本、可跑全分支 |

完整权衡见 `docs/TECHNICAL_DESIGN.md` §12。

---

## 生产就绪性（扩展到 10,000+ ops/min）

**容量模型**（§11.1）：10k/min ≈ 167 ops/s，需约 334 并发。

**扩展手段**：
- **无状态服务** + 任务队列（Redis/SQS/Kafka）+ 异步 Worker → 线性水平扩展
- **LLM 网关**：集中限流、熔断、重试、密钥轮换
- **多 Provider 路由**：主备切换（DeepSeek → Qwen/OpenAI）
- **幂等 + 缓存**：`idempotency_key` 含 model/prompt 版本维度，单飞防穿透
- **SLO**：成功率 ≥95%、Fallback <5%、P99 <5s、可用性 ≥99.9%
- **可观测性**：结构化 JSON 日志 + 指标（`fallback_total`、`error_signature_total` 等）+ 告警

详见 `docs/TECHNICAL_DESIGN.md` §11。

---

## 项目结构

```
src/param_extractor/
├── contracts/      # 数据契约（ExtractionOutput/Request/Result/ErrorSignature）
├── guardrail/      # 注入检测 / 净化 / PII 扫描
├── validation/     # 三级校验 + 错误签名
├── repair/         # 修复引擎
├── fallback/       # 兜底
├── observability/  # 结构化日志 + 脱敏
├── pipeline/       # 编排状态机
└── api/            # FastAPI 服务入口
tests/
├── unit/           # 92 单元测试
├── integration/    # 8 集成测试（S1/S2/S3/S3b + API）
├── adversarial/    # 6 对抗测试（S4/S5/S5b）
└── fixtures/       # 基准用例 + MockLLMClient
examples/           # run_demo.py / run_retry_demo.py
docs/               # 设计文档 + POC 结果 + 构建账本
```

---

## 文档

- `docs/TECHNICAL_DESIGN.md` —— 系统设计（v1.5，含决策记录 D1-D9 与设计依据附录）
- `docs/RISK_AND_POC_CHECKLIST.md` —— 高风险假设与 POC 验证结果
- `docs/POC_INSTRUCTOR_DEEPSEEK.md` —— instructor × DeepSeek 兼容性 POC
- `docs/BUILD_LOG.md` —— 构建账本（裁定 + 评审轨迹）

## 环境要求

Python 3.11+（开发于 3.13）。依赖见 `pyproject.toml`。
