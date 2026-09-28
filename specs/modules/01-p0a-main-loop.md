# 01-p0a-main-loop — P0a 主循环末端契约

> 状态：✅ 待实现
> 性质：编码前必读。定义 P0a 核心闭环剩余模块和主循环行为。
> 前序依赖：00-core-interfaces.md、00-error-contract.md、00-adapter-factory.md

---

## 1. P0a 目标

跑通完整核心闭环，不依赖真实 Ollama / 云端 API / 持久化存储。所有外部组件均为 mock / 内存 / noop 实现。

**验收标准**：用户输入一句话，智能体经过"理解 → 决策 → 工具执行 → 回复"全链路，返回可读的中文结果。下一轮能通过 MemoryBackend 检索到本轮对话。

**P0a 范围限制**：

- 单回合至多 1 个工具调用（草案 0 或 1 个，`15-tool-orchestration-hardening.md` §2.1）。多工具编排留到有真实需求证据时立项（`15` §11）
- `requires_user_confirmation = True` 的操作**直接拒绝执行**，不会在下一轮恢复
- 云端咨询不可用
- 自进化不可用

---

## 2. InputNormalizer

```python
class InputNormalizer:
    def __init__(self) -> None: ...
    def normalize(self, raw_text: str, session_id: str, project_id: str | None = None) -> InputEvent: ...
```

**行为**：
- 生成当前 UTC ISO 时间戳
- `text` = `raw_text.strip()`
- 空白输入（`raw_text.strip() == ""`）抛 `LocalMindError(code="INVALID_INPUT", user_message="输入不能为空。", recoverable=True)`
- `source` 固定为 `"cli"`

---

## 3. TaskPlanner

```python
class TaskPlanner:
    def __init__(self) -> None: ...
    def plan(self, candidate: IntentCandidate, context: MinimalContext) -> ExecutionPlan: ...
```

**行为**（2026-09-18 起以 `15-tool-orchestration-hardening.md` §4 为准）：

- 第一道门是 `candidate.tool_call_resolution != "resolved"` → 直接返回空计划（解析层已定性失败形态，本模块不重新解释原始 raw）；`resolved` 时才用 `candidate.tool_call`（结构化草案：工具名 + 参数）。**不再**读 `candidate.suggested_tools`
- `tool_name` = 草案的工具名；须先经 `validate_tool_call(draft, context.tool_defs)` 校验（成员、必填、类型、未知键；**draft 非可选**）
- `action` = 工具名中最后一个 `.` 之后的段（如 `"system.echo"` → `"echo"`）; 无 `.` 时用工具名本身
- `params` = 草案的 `arguments`（唯一参数来源）；`entities` 只作观测字段随 step 传递，**不再是参数来源**
- `risk_level` = `candidate.risk_draft`；`approval_profile` **不由本模块设置**（来源是注册表 + preflight 的只升不降合成，见 `13`）
- 无可用草案（`resolution != "resolved"`）或校验不通过 → 返回 `ExecutionPlan(steps=[])`，把「为什么」交给策略层的 `reason`（App 依上面的空计划分流表决定回复构造器）
- **禁止**：TaskPlanner 不调用模型、不推断参数、不按工具名分支、不出现任何工具名字面量（即插即用）

---

## 4. ResponseBuilder

```python
class ResponseBuilder:
    def __init__(self) -> None: ...
    def build(self, plan: ExecutionPlan, results: dict[int, dict[str, object]]) -> str: ...
```

**P0a 行为**：
- `results` 为空时：返回 `"没有需要执行的操作。"`
- 有结果时：每条一行，格式 `"[{step_index}] {tool_name}：{result_dict_summary}"`
  - `result_dict_summary` = 结果的 key-value 拼接，如 `{"content": "hello"}` → `"content: hello"`
- 不用模板引擎，不调用模型

---

## 5. ReflectionRecorder

```python
class ReflectionRecorder:
    def __init__(self, evolution: EvolutionBackend) -> None: ...
    def record(self, task_context: dict, outcome: str) -> None: ...
```

**P0a 行为**：纯 no-op。`record()` 直接 return，不调用 `evolution.collect_experience()`，不写文件。参数签名保留，为 P8 预留接口。

---

## 6. NoopCloudAdvisoryBackend

```python
class NoopCloudAdvisoryBackend(CloudAdvisoryBackend):
    def advise(self, request: CloudRequestPackage) -> AdvisoryResult: ...
```

**行为**：
```python
def advise(self, request):
    return AdvisoryResult(
        analysis="云端咨询暂未启用。",
        risks=[],
        requires_local_validation=True,
    )
```

> **P4 注记（2026-09-02）**：`enabled=true` + `backend="noop"` 自 P4 起为配置矛盾（bootstrap 抛 `CONFIG_ERROR`，见 `05-p4-cloud-advisory.md` §8），noop 仅存在于 `enabled=false` 默认组合，`advise()` 不应被触达。本节行为保留为兜底定义。

---

## 7. NoopEvolutionBackend

```python
class NoopEvolutionBackend(EvolutionBackend):
    def reflect(self, task_context: dict) -> list[Experience]: ...
    def get_skills(self, intent: str) -> list[Skill]: ...
    def collect_experience(self, task: dict, outcome: str) -> None: ...
```

**行为**：
- `reflect()` → 返回 `[]`
- `get_skills()` → 返回 `[]`
- `collect_experience()` → no-op，直接 return

---

## 8. GuardedToolExecutor 审计

GuardedToolExecutor 在 `execute()` 中为每个 step 记录 AuditEvent 到内存列表。

### 执行签名变更

```python
class GuardedToolExecutor:
    def __init__(
        self,
        tool_backend: ToolBackend,
        safety_policy: SafetyPolicy,
        audit_log: list[AuditEvent] | None = None,
    ) -> None: ...

    def execute(
        self,
        plan: ExecutionPlan,
        task_id: str = "",
        intent_id: str = "",
    ) -> dict[int, dict[str, object]]:
        """逐 step 执行。task_id 和 intent_id 由 App.handle() 传入，写入 AuditEvent。"""
```

### AuditEvent 字段来源

| 字段 | 来源 |
|------|------|
| `audit_id` | `uuid4().hex[:12]` |
| `task_id` | 参数 `task_id`（App.handle() 传入） |
| `intent_id` | 参数 `intent_id`（App.handle() 传入） |
| `tool_name` | `step.tool_name` |
| `params_redacted` | `_redact(step.params)`（见下） |
| `risk_level` | `_effective_risk(step, tool_def)`（模型可升不可降，见下） |
| `verdict` | `"allowed"` / `"denied"` / `"error"` |
| `reason` | 安全拒绝：`verdict.reason`<br>执行失败：`ToolError.message`<br>成功：`"ok"` |
| `timestamp` | UTC ISO 时间戳 |

### 脱敏规则

```python
import re
from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_PARAM_KEYS = {"password", "passwd", "token", "secret", "api_key", "passphrase", "key"}
# 复用 RuleOnlySafetyBackend 的敏感信息正则，对字符串值二次扫描
_SENSITIVE_VALUE_RE = re.compile(
    r"\b(password|passwd|secret|token|api_key)\s*=\s*\S+", re.IGNORECASE
)

def _redact(value: Any) -> Any:
    """递归脱敏：敏感键 → '***'，敏感值模式 → '***'，嵌套容器递归处理。"""
    if isinstance(value, Mapping):
        return {
            key: "***" if _is_sensitive_key(key) else _redact(val)
            for key, val in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_redact(item) for item in value]
    if isinstance(value, str) and _SENSITIVE_VALUE_RE.search(value):
        return "***"
    return value

def _is_sensitive_key(key: str) -> bool:
    return key.lower() in _SENSITIVE_PARAM_KEYS
```

**额外降级规则**：当 verdict = `"denied"` 且风险等级为 `sensitive` 或 `dangerous` 时，`params_redacted` 只保留键名（值全部替换为 `"***"`），防止被拒绝的高风险操作参数细节进入日志。

### 风险等级：模型只能升不能降

工具在注册表中的风险等级（ToolDef.risk_level）是不可绕过的底线。模型的 `risk_draft` 只能将其向上调整。

```python
_RISK_ORDER = {"normal": 0, "sensitive": 1, "dangerous": 2}

def _effective_risk(step: ExecutionStep, tool_def: ToolDef | None) -> str:
    """模型 risk_draft 只能升不能降。未注册工具按模型值。"""
    model_level = _RISK_ORDER.get(step.risk_level, _RISK_ORDER["sensitive"])
    if tool_def is None:
        return step.risk_level
    tool_level = _RISK_ORDER.get(tool_def.risk_level, _RISK_ORDER["sensitive"])
    effective = max(model_level, tool_level)
    for level, idx in _RISK_ORDER.items():
        if idx == effective:
            return level
    return "sensitive"
```

> **兜底档位不得是 `normal`（2026-09-16）**：`_RISK_ORDER.get(..., 0)` 是 fail-open 兜底——闭集外的值会被当成 `normal`（无需确认）。`risk_draft` 在解析层已归一化为闭集（`12-risk-draft-closed-set.md` §2），本分支按构造不可达，但仍须把兜底钉在**保守档 `sensitive`**，并由「直接构造闭集外 `risk_level` → 按 `sensitive` 处理」的用例锁定（12 §4.3）。返回 `"normal"` 的末行兜底同理。

**P0a 硬限制**：`_effective_risk` 不为 `"normal"` 时，GuardedToolExecutor **直接拒绝执行**，不进入安全检查，不调用 ToolBackend：

```python
# 在 execute() 中，白名单校验通过后、安全策略检查之前：
effective_risk = _effective_risk(step, tool_def)
if effective_risk != "normal":
    audit_log.append(AuditEvent(
        # ... verdict="denied", reason="P0a 暂不支持敏感/危险操作"
    ))
    raise ToolError(
        code="CAPABILITY_MISMATCH",
        message=f"Tool {step.tool_name} requires risk level {effective_risk}, P0a only supports normal",
        user_message="当前版本暂不支持此操作。",
        recoverable=False,
        details={"tool_name": step.tool_name, "risk_level": effective_risk},
    )
```

- `system.echo`、`system.get_time`、`file.list_dir` → normal → 放行
- `file.read` → sensitive → P0a 直接拒绝。P3 有确认状态机后再放开
- 模型把 `file.read` 标为 normal 不影响此判断——以注册表为准

### 审计时机

- 安全拒绝：在抛 SafetyDenied 之前记录 AuditEvent（verdict="denied"）
- 执行失败：在抛 ToolError 之前记录 AuditEvent（verdict="error"）
- 执行成功：在 `results[step_index] = ...` 之后记录 AuditEvent（verdict="allowed"）

---

## 9. App.handle() 主循环

```python
class App:
    def handle(self, raw_text: str, session_id: str, project_id: str | None = None) -> str:
        """执行一次完整的核心闭环。失败时返回 user_message，不抛异常。"""
```

### 正常流程

```
1. InputNormalizer.normalize(raw_text, session_id, project_id) → InputEvent
2. ContextAssembler.assemble(input_event) → MinimalContext
3. IntentResolver.resolve(minimal_context) → IntentCandidate
4. ControlPolicy.decide(candidate, cloud_state, resolution_exhausted=resolver.last_resolution_exhausted, no_progress=resolver.last_no_progress, tool_defs=context.tool_defs) → NextAction
5. 根据 NextAction 走分支 → 回复文本 reply
6. 本轮对话写入 MemoryBackend.store_episode()
7. ReflectionRecorder.record(...)（旁路，独立 try/except，失败不改变回复）
8. return reply
```

### 审计上下文生成（步骤 5 执行前）

`App.handle()` 在执行 PLAN_LOCAL 前生成 `task_id` 和 `intent_id`，传入 `executor.execute()`：

```python
task_id = f"task_{session_id}_{int(time.time())}"
intent_id = f"intent_{session_id}_{int(time.time())}"
```

### 本轮对话记录（步骤 6）

```python
self.memory.store_episode(
    content=f"User: {raw_text}\nAssistant: {reply}",
    metadata={"topic": candidate.intent_type, "session_id": session_id},
)
```

- store_episode 失败时捕获异常，reply 仍正常返回

### 安全模型：双层拦截（P0a 明确立场）

| 层级 | 负责模块 | 检查对象 | P0a 实现 |
|------|------|------|:---:|
| 意图级 | ControlPolicy | IntentCandidate.risk_draft | REFUSE 拒绝 dangerous 意图（闭集 `normal`/`sensitive`/`dangerous`，解析层归一化，见 `12-risk-draft-closed-set.md`） |
| 执行级 | SafetyPolicy → RuleOnlySafetyBackend | ExecutionStep 操作文本 | L1 规则拒绝 forbidden commands/paths/patterns |

**P3 已知缺口**：SafetyBackend.check_dangerous() 的 operation 契约（00-core-interfaces.md）要求包含 `intent_type` 和 `entities`，但当前 SafetyPolicy.check() 仅从 ExecutionStep 提取 `tool_name`/`action`/`params`/`risk_level`。P3 实现 L2 语义检测时需二选一：扩展 ExecutionStep 增加 `intent_type`/`entities` 字段，或让 GuardedToolExecutor 在执行时额外传入 intent 上下文。此项不阻塞 P0a。

### 异常兜底

`handle()` 内部 try/except 包裹整个流程，任何异常都转为 `user_message` 返回：

| 异常类型 | 行为 |
|------|------|
| `LocalMindError`（含子类） | return `exc.user_message` |
| 其他 Exception | return `"系统内部错误，请重试。"` |

### 分支处理表

| NextAction | P0a 行为 |
|------|------|
| `PLAN_LOCAL` + confirmation=False | 1. 生成 task_id、intent_id<br>2. `TaskPlanner.plan(candidate, context)` → ExecutionPlan<br>3. `GuardedToolExecutor.execute(plan, task_id, intent_id)` → results dict<br>4. `ResponseBuilder.build(plan, results)` → 回复文本 |
| `PLAN_LOCAL` + confirmation=True | **不执行**。返回 `"此操作需要确认后才能执行，当前版本暂不支持。请尝试更简单明确的请求。"`<br>P0a 无确认状态机，不会在下一轮恢复 |
| `ASK_USER` | 基于 `candidate.missing_info` 拼接反问文本：`["target", "project"]` → `"请补充以下信息：target, project"`<br>无 missing_info 时 → `"请更具体地描述你的需求。"` |
| `RETRIEVE_MORE` | P0a 已无更多检索能力，等同于 ASK_USER<br>**P6d 起**：检索已证明无增量（连续两轮语义签名不变且本轮零新增）的候选**不再返回本动作**（空转），改为 `ASK_USER` 或条件化本地回答（`PLAN_LOCAL`，只读、无需确认——`tool_intent == "none"` ⇒ 无草案 ⇒ 空计划 ⇒ 按构造零副作用；2026-09-18 前读 `suggested_tools`，见 `15-tool-orchestration-hardening.md` §2.5）——`10-p6d-autonomous-escalation.md` §3.3；本动作在仍可能有检索增量时继续存在 |
| `REQUEST_CLOUD` | P0a：返回 `"云端咨询暂未启用。"`<br>**P4 起改**：进入 `05-p4-cloud-advisory.md` §1.4 授权状态机（PREPARING → AWAITING_AUTHORIZATION → …），不再返回固定文案 |
| `REFUSE` | 返回 `"此操作已被安全策略拒绝。"` |

> 本表为 **P0a 行为快照**。P3 起的确认恢复/身份验证分支以 `04-p3-safety-hardening.md` 为准；P4 起的云端分支（含 force_cloud/deny_cloud 指令、授权交互）以 `05-p4-cloud-advisory.md` §1.4 为准，两者覆盖本表对应行。

### `PLAN_LOCAL` 的空计划分流（2026-09-18，`15-tool-orchestration-hardening.md` §5）

空计划有**两种截然不同的含义**，App 必须在分派回复前区分。**顺序权威定义在 `15` §5.2**：计划非空才进 preflight/确认链；空计划按 `reason` 分流，**不进入确认链**（确认语义是 step-scoped——没有 step 就没有可确认的操作；**2026-09-18 改正**：初稿曾写「必须先判 `requires_user_confirmation`」，那会产出「确认一个空计划」+ 空 pending 状态）。

历史缺陷的真实内容是：`main.py:792-800` 的早返回**不区分两种空计划**，把「本该有工具、没能建立」也送进 `_build_local_reply` 的自由文本——这才是 S14「文件不存在 / 已创建 / 已覆盖」的产生位置。

| `NextAction.reason` | 含义 | 回复构造器 | `reply_provenance` |
|---|---|---|:---:|
| `tool_call_missing` / `unknown_tool` / `param_invalid` / `tool_call_invalid_shape` / `multiple_proposed` / `tool_catalog_absent` | 本该有工具、没能建立 | **能力错误常量模板**（不调模型） | `unfulfilled` |
| `param_missing` | 缺必填参数（策略已返回 ASK_USER） | 确定性追问（不调模型） | `unfulfilled` |
| 纯分析 / 条件化回答 / 云端回流 | 本回合确实不需要工具 | `_build_local_reply` / `_build_local_advisory_reply` | `answered` |
| 计划非空且存在 `verdict="allowed"` 的执行记录 | 真的执行了 | `ResponseBuilder.build()` | `executed` |
| 计划非空但无成功记录（拒绝/失败） | 执行未成功 | 既有拒绝/失败路径 | `unfulfilled` |

判定的第一个输入是 `IntentCandidate.tool_call_resolution`（解析层归一化结论，随候选携带，`15` §2.1）：`!= "resolved"` 时**不再调用** `validate_tool_call`，直接按上表取 reason；只有 `resolved` 才把草案交给校验函数（`15` §2.3 末条）。

**硬断言**：空计划轮次不得出现 `awaiting_confirmation` 文案、待执行 step 或 `_pending_plan` 残留（`15` §9 A11）。

三条不变式（`15` §5.1）：

- **模型声明了本地动作（`tool_intent="local_action"`）的回合，可见回复一律由确定性构造器产出**——该轮不存在模型调用点，故「未执行却声称完成」在结构上不可达；
- `answered` 轮在 `requires_user_confirmation=True` 或 `risk_draft ∈ {sensitive, dangerous}` 时，必须追加**常量**来源声明（明示本轮未执行本地操作）；
- 每轮的 `reply_provenance` 按上表确定性判定，落 `turn_completed.data.reply_provenance`，不得由模型或提示词决定。

### 关键约束

- `handle()` **只返回字符串**，不抛异常
- `ControlPolicy.decide()` 使用 App 组装的 `CloudControlState` 与 Resolver 的确定性事实（`last_no_progress` / `last_resolution_exhausted`）——**轮次不再进策略**：`round_count` 位置参数与云端准入的轮次判据已于 2026-09-17 删除（`14-resolution-exhausted.md` §3），避免「传了却不用」的死输入与「超轮次不走云端」的越权拦截
- `ReflectionRecorder.record()` **单独 try/except**
- P0a 不调用 `CloudBoundary`、`IdentityVerifier`

---

## 10. Mock 模型 READY 注入——验收路径

P0a 的 MockModelBackend 默认 `structured_response = {}`，解析为 VAGUE。演示时需注入 READY 候选。

### 方式：bootstrap() 接受可选的模型后端覆盖

```python
def bootstrap(
    config_path: str,
    model_backend_override: ModelBackend | None = None,
) -> App:
```

- 若 `model_backend_override` 不为 None，跳过 `create_model_backend(config)`，直接使用该实例
- 其他后端仍按配置创建

**演示脚本示例**：

```python
# scripts/run_p0a.py
from src.main import bootstrap
from src.models.mock_backend import MockModelBackend

model = MockModelBackend(
    structured_response={
        "state": "READY",
        "intent_type": "echo_message",
        "entities": {"message": "Hello LocalMind!"},
        "missing_info": [],
        "suggested_tools": ["system.echo"],
        "risk_draft": "normal",
        "model_confidence": 0.85,
        "reasoning": "User wants to test the echo tool.",
    }
)
model.load()
app = bootstrap("config/default.toml", model_backend_override=model)
reply = app.handle("echo hello", session_id="demo")
print(reply)
```

### 约束

- Mock 模型不从配置文件自动解析 structured_response
- 演示脚本负责构造和注入
- 生产配置（Ollama）不使用此覆盖参数

---

## 11. bootstrap() 完整更新

```python
def bootstrap(
    config_path: str,
    model_backend_override: ModelBackend | None = None,
) -> App:
    config = load_config(config_path)

    # 1. 创建所有 Adapter
    if model_backend_override is not None:
        model_backend = model_backend_override
    else:
        model_backend = create_model_backend(config)

    model_backend.load()
    if not model_backend.health_check():
        raise LocalMindError(
            code="MODEL_UNAVAILABLE",
            message="Model health check failed after load",
            user_message="本地模型启动失败，请检查 Ollama 是否运行",
            recoverable=False,
        )

    memory_backend   = create_memory_backend(config)
    tool_backend     = create_tool_backend(config)
    safety_backend   = create_safety_backend(config)
    cloud_backend    = create_cloud_advisory_backend(config)
    evolution_backend = create_evolution_backend(config)

    # 2. 组装 Core 模块
    audit_log: list[AuditEvent] = []
    max_rounds = config.get("execution", {}).get("intent_max_rounds", 4)
    if not isinstance(max_rounds, int) or max_rounds < 1 or max_rounds > 4:
        raise LocalMindError(
            code="CONFIG_ERROR",
            message=f"intent_max_rounds must be 1..4, got {max_rounds}",
            user_message="系统配置有误，请检查 execution.intent_max_rounds。",
            recoverable=False,
        )

    normalizer  = InputNormalizer()
    assembler   = ContextAssembler(memory=memory_backend, tools=tool_backend)
    resolver    = IntentResolver(model=model_backend, memory=memory_backend, max_rounds=max_rounds)
    policy      = ControlPolicy()
    planner     = TaskPlanner()
    safety      = SafetyPolicy(backend=safety_backend)
    executor    = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=safety,
        audit_log=audit_log,
    )

    # 2b. 安全层与云端模块（PrivacyPolicy / AuthorizationManager / CloudBoundary /
    #     SideEffectGateway / CloudAdvisoryService）的构造，及 3. App(...) 完整参数：
    #     以 00-adapter-factory.md §bootstrap 为唯一权威，本节不再内联副本。
    #     （P4 前此处曾内联 CloudBoundary(backend=...) 与 cloud_boundary= App 参数，
    #       均为已废弃签名，已删除以免双源漂移。）
    return App(...)   # 完整参数清单见 00-adapter-factory.md §bootstrap
```

### 注入变化汇总

| 注入点 | 值 | 来源 |
|------|------|------|
| `IntentResolver.max_rounds` | 默认 4 | `config.execution.intent_max_rounds` |
| `GuardedToolExecutor.audit_log` | 空列表 | bootstrap() 创建 |
| `App.memory` | MemoryBackend 实例 | bootstrap() 传入 |
| `model_backend` | Mock（带 structured_response）或 Ollama | 覆盖参数或配置 |

---

## 实现清单

| 模块 | 位置 | P0a 程度 |
|------|------|:---:|
| InputNormalizer | `src/core/input_normalizer.py` | 完整 |
| TaskPlanner | `src/core/task_planner.py` | 基础（至多 1 工具，不含参数推断） |
| ResponseBuilder | `src/core/response_builder.py` | 基础（纯文本拼接） |
| ReflectionRecorder | `src/core/reflection_recorder.py` | No-op stub |
| NoopCloudAdvisoryBackend | `src/tools/cloud_advisory.py`（与 00-adapter-factory 工厂 import 一致） | 完整 |
| NoopEvolutionBackend | `src/evolution/noop_backend.py` | 完整 |
| App + bootstrap() | `src/main.py` | 完整（含 `model_backend_override`） |
| GuardedToolExecutor 审计 + 脱敏 | `src/safety/guarded_executor.py` | 修改：audit_log、execute(task_id, intent_id)、_redact() |
