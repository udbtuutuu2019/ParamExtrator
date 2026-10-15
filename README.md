# ParamExtrator

> 一个围绕非确定性 LLM 构建的**确定性、弹性、可观测**的数据提取 Harness。
> 把杂乱的客服对话稳定地转换为强类型结构化数据；模型失效时**优雅降级**而非崩溃。

## 快速开始

```bash
pip install -e ".[dev]"          # 安装（含测试依赖）
cp .env.example .env             # 填入 DEEPSEEK_API_KEY
pytest                           # 运行全部测试（全 mock，无需 API Key）
python examples/run_demo.py      # 跑通用例 1~4（需要真实 API Key）
```

启动服务：

```bash
uvicorn param_extractor.api.server:app --port 8000
curl -X POST http://localhost:8000/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"transcript_id":"TX-001","content":"我昨天被重复扣了 150 美元..."}'
```

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

**错误恢复流程**（状态机，§5）：`SUCCESS`（首轮通过）/ `REPAIRED`（修复后通过）/ `FALLBACK`（预算耗尽→固定常量兜底+人工审核）。

| 组件 | 职责 |
|------|------|
| `guardrail/` | 注入检测、语义隔离、PII 本地扫描（卡尾号策略） |
| `validation/` | 三级校验（完整性/解码/schema）→ 错误签名 |
| `repair/` | 针对性修复提示 + 单调性熔断 |
| `fallback/` | 固定常量兜底（绝不抛异常） |
| `pipeline/orchestrator.py` | 状态机编排（**永不崩溃**） |
| `observability/` | JSON 结构化日志（延迟/重试/校验错误/结果）+ 脱敏 |

---

## 权衡取舍（时间限制下的决策）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 结构化输出 | `instructor + Pydantic` | 成熟、胶水少；聚焦 Harness 而非重复造轮子 |
| 重试归属 | instructor `max_retries=0`，全部交自研层 `N=2` | 避免两层重试叠加超预算（决策 D2） |
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
tests/              # unit / integration / adversarial（全 mock）
docs/               # 设计文档 + POC 结果
```

## 文档

- `docs/TECHNICAL_DESIGN.md` —— 系统设计（v1.4，含决策记录）
- `docs/RISK_AND_POC_CHECKLIST.md` —— 高风险假设与 POC 验证结果
- `docs/POC_INSTRUCTOR_DEEPSEEK.md` —— instructor × DeepSeek 兼容性 POC
