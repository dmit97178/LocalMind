# 07-p6a-observability-cli — 运行事件流与交互式 CLI 模块契约

> 状态：✅ 待实现
> 阶段：P6a（可观测真实 Agent 闭环 · 第一部分：交互式 CLI 与运行状态可见）
> 性质：编码前必读。本契约定义 P6a 全部新增/演进组件的行为边界。
> 前序依赖：`00-core-interfaces.md`、`00-error-contract.md`、`00-adapter-factory.md`、`01-p0a-main-loop.md`（App.handle 现状）、`04-p3-safety-hardening.md`（确认链）、`05-p4-cloud-advisory.md`（云端轮次）、`06-p5-project-memory.md`（TopicTracker / ProjectStore / ExecutionRecord）。

---

## 0. 范围与不变量

**目标**：把 P0-P5 已完成的核心闭环变成可观察、可交互、可文件落地的真实可用 Agent——对应 FR8。三块能力：结构化运行事件流（RuntimeEventSink）、交互式 CLI（斜杠命令 + 简洁/trace 显示）、工作区内 UTF-8 文本写入（file.write）。

**演进声明（不做推倒重来）**：
- `App.handle()` 签名与返回值**不变**（返回字符串，不抛异常）；事件是旁路。
- **回复语义演进（P6a 审查补记）**：`PLAN_LOCAL` 且计划为空（纯对话、无工具步骤）时，App 以 `_build_local_reply()` 让本地模型直接生成回复——prompt 携带 current_input / relevant_history / project_state，明确禁止声称执行过工具；模型空回复回退模板文案。这取代 P0a 以来"空计划 → ResponseBuilder 模板"的占位输出，是交互 CLI（§4）可用性与 P6b G1 对话场景的前提；**有工具步骤的回复路径不变**。
- P3 文本确认通道（`_parse_confirmation`）与 P4 云端文本指令通道（`_parse_cloud_control`）**原样保留**；斜杠命令不接管、不重复这两类交互。
- 现有演示脚本 `scripts/run_p0a.py` ~ `run_p5.py` 保留，不迁移。
- 事件 sink 默认 Noop：**既有全部测试与行为零变化**（`model_backend_override` 注入模式不变）。

**铁律**：
1. **CLI 只做壳**：只负责输入、显示与会话生命周期（斜杠命令、trace 开关、/quit），不参与意图判断、安全裁决或云端决策。
2. **Core 不打印**：`src/core/**` 不得出现 `print` / stdout 写入；运行状态的唯一对外出口是 RuntimeEventSink。stdout 只属于 CLI 层。
3. **事件是旁路**：sink 构造注入；`emit` 及其消费链上任何异常由 App 吞并（与 `_record_turn` 同一失败语义），绝不影响回复主路径。
4. **事件禁入清单**（违反任一即为 P6a 验收失败）：原始密钥/口令原值、确认原文、未授权自由文本（用户输入原文、chunk 原文、工具结果原文、云端 analysis 原文）、完整 prompt、模型隐藏推理（`reasoning` 字段）、fingerprint/grant 等本地边界字段。事件只带**元数据**。
5. **Core 永远发全量事件**；`/trace on|off` 是 CLI 显示侧开关，不进 Core、不改变事件产生。
6. **App 是唯一 emit 者**：子模块（IntentResolver / ContextAssembler / GuardedToolExecutor / 云端服务）不持有 sink，只通过只读快照属性暴露数据；禁入过滤在 App 侧单点执行。

**范围包含**：
- `src/core/interfaces.py` — 新增 `RuntimeEventSink` ABC；`ToolBackend` 增统一 `preflight()` 能力（签名变更，Claude 所有）
- `src/core/schemas.py` — 新增 `RuntimeEvent`、`RoundTrace`、`RetrievalStats`、`PreflightReport`（见 §1/§2/§6.3）
- `src/core/intent_resolver.py` — 新增只读快照 `last_round_trace`
- `src/core/context_assembler.py` — 新增只读快照 `last_retrieval_stats`
- `src/safety/guarded_executor.py` — 新增 `preflight()`（只消费工具后端标准化评估，§6.3）；preflight 拒绝经既有 `record_denial` 留痕
- `src/safety/rule_only_backend.py` — 工作区路径 L1 校验（§6.2）
- `src/main.py` — App emit 插桩（§3）、只读查询接口（§5）、bootstrap sink 组装（§7）、preflight→pending→复检流程（§6.3）
- `src/observability/` — `NoopEventSink` / `JsonlEventSink` / `CompositeEventSink`
- `src/cli/` — `__main__.py`（入口）、`loop.py`、`commands.py`（命令层）、`sink.py`（CliEventSink）
- `src/tools/file_tools.py` / `src/tools/registry.py` / `src/tools/builtin_backend.py` — file.write 注册与实现；`BuiltinToolBackend.preflight` 动态评估（目标存在性/路径预检）
- `src/core/topic_tracker.py` — 新增只读 `topics_history(session_id)`
- `src/memory/project_store.py` — 新增公开 `normalize_project_id`
- `config/default.toml` — `[observability]`、`[tools]` 段
- `tests/test_runtime_events.py`、`tests/test_cli.py`、`tests/test_file_write.py`、`tests/test_p6a_scenarios.py`；扩展 `tests/test_main.py`、`tests/test_guarded_executor.py`、`tests/test_safety_policy.py`

**范围排除**：GUI / HTTP API、流式输出（`ModelBackend.stream` 仍不启用）、Shell/删除/移动/网络工具、MCP、多会话并发 CLI（一次运行一个 session）、事件回放 UI、trace 持久化（trace 只影响显示；JSONL 记录与 trace 开关无关）。

---

## 1. RuntimeEvent 与 RuntimeEventSink

### 1.1 数据结构（core/schemas.py）

```python
@dataclass(frozen=True)
class RuntimeEvent:
    run_id: str                # App 构造时生成（uuid4 短码），一次进程运行
    turn_id: str | None        # App.handle() 每次调用生成（uuid4 短码）；仅 session_ended 为 None
                               #（它发生在 handle() 之外）。确认轮/授权轮也是 handle() 调用，有 turn_id。
    session_id: str
    seq: int                   # App 内单调递增（进程级），事件顺序的唯一依据
    ts: str                    # UTC ISO
    stage: str                 # 受限枚举，见 §2.1
    level: str                 # "status" | "detail"
    data: Mapping[str, object] # 各 stage 固定字段，见 §2.2；App 侧已消毒，实现不得放宽
                               #（只允许按 §2.2 落盘分级进一步收紧——JsonlEventSink 的别名/计数/剔除转换即属此类）
```

`data` 的键集是**封闭的**：每个 stage 只允许出现 §2.2 表中列出的键；未列出的键禁止加入（验收断言逐 stage 校验键集）。

### 1.2 接口（core/interfaces.py，签名归 Claude 所有）

```python
class RuntimeEventSink(ABC):
    @abstractmethod
    def emit(self, event: RuntimeEvent) -> None:
        """消费一个运行事件。实现不得向调用方抛出异常（内部失败自行吞并或记 stderr）。"""
        ...
```

**实现清单**（§3.5 接口实现表同步）：

| 实现 | 位置 | 行为 |
|---|---|---|
| `NoopEventSink` | `src/observability/` | `emit` 直接 return；bootstrap 未配置 sink 时的默认值 |
| `JsonlEventSink` | `src/observability/` | 逐事件一行 JSON envelope（**格式钉死**：`{"v": 1, "type": "runtime_event", "event": {…RuntimeEvent…}}`，ensure_ascii=False, UTF-8）追加写入；目录不存在则创建；写入失败吞并。envelope 是 P6b 场景运行器的解析契约（08 §5.1），字段只增不改 |
| `CompositeEventSink` | `src/observability/` | 按构造顺序逐一 emit，单个成员异常不影响其余成员 |
| `CliEventSink` | `src/cli/sink.py` | 按 §4.4 格式显示；持有 trace 开关（可运行中切换）；只显示本 run 的事件 |

### 1.3 App 快照数据来源（emit 者模式的配套）

| 数据 | 来源 | 新增形态 |
|---|---|---|
| 逐轮理解 | IntentResolver | 只读属性 `last_round_trace: tuple[RoundTrace, ...]`，每轮 append：`RoundTrace{round, state, model_confidence, missing_info, continue_retrieval, retrieval: RetrievalStats | None}` |
| 主检索 | ContextAssembler | 只读属性 `last_retrieval_stats: RetrievalStats | None`：`RetrievalStats{hits: int, kw_enabled: bool, vec_enabled: bool, degraded: bool}` |
| 工具执行 | ExecutionRecord 列表 | 复用 P5 既有结构（App 已收集），事件只取 `tool_name/verdict/risk_level/outcome/error_code` |
| 云端轮次 | App 内部状态 | P4 既有变量（升级原因、grant 状态、外发类别/字节、sub-turn 序号），不改结构 |
| 话题/项目 | TopicDecision | P5 既有 |

`RoundTrace.retrieval` 记录认知轮内的按需检索统计；`missing_info` 每项在进入事件前截断至 ≤60 字符并过消毒（§3.2）——它是模型输出字段，不可信。

---

## 2. 事件 stage 契约

### 2.1 stage 与 level 总表

| stage | level | 产生时机 |
|---|---|---|
| `turn_started` | detail | handle() 进入，normalize 之后 |
| `topic_decision` | **status** | TopicTracker.on_turn 之后 |
| `memory_retrieval` | detail | 每次检索后（主检索 + 认知轮检索，用 query_source 区分） |
| `intent_round` | detail | IntentResolver 每轮结束 |
| `intent_final` | **status** | 理解循环结束（收敛/达上限/被拒） |
| `dispatch_decision` | **status** | ControlPolicy.decide 之后 |
| `cloud_consult` | detail | 云端升级链路各关键点（授权状态变化时多次 emit） |
| `cloud_return` | detail | 云端返回并入站检查后 |
| `tool_execution` | detail | 每个 ExecutionRecord 一条 |
| `degradation` | detail | 检测到降级路径时 |
| `turn_completed` | **status** | 每次 handle() 调用**恰好一条**终结事件：正常返回前，或异常兜底路径（completion="error"）；同时落 last_turn_report（§5.2） |
| `session_ended` | **status** | App.end_session 完成后 |

status = CLI 简洁模式显示集（§4.4）；detail 仅 trace 模式显示。JSONL 两种都记。

### 2.2 data 字段逐 stage 钉死

| stage | data 键（封闭集） | 类型 / 取值 | JSONL 落盘 |
|---|---|---|---|
| `turn_started` | `input_chars` `project_id` `explicit_directives` | int；str\|None；tuple ⊆ {"force_cloud","deny_cloud"} | 原样 / **别名** / 原样 |
| `topic_decision` | `relation` `topic_label` `referenced_topic` `project_id` `project_switched` | P5 TopicDecision 字段 | 原样 / **别名** / **别名** / **别名** / 原样 |
| `memory_retrieval` | `query_source` `hits` `kw_enabled` `vec_enabled` `degraded` | "main"\|"intent_round"；int；bool×3 | 全原样 |
| `intent_round` | `round` `state` `confidence` `missing_info` `continue_retrieval` `new_memories` | int；枚举；float；tuple；bool；int | 原样 / 原样 / 原样 / **计数** / 原样 / 原样 |
| `intent_final` | `rounds_used` `final_state` `confidence` `intent_type` `missing_info` `proposal_present` `should_consult` `expected_benefit` `escalation_reason` `no_progress_detected` `stopped_early` `risk_draft` `risk_draft_resolution` `resolution_exhausted` `tool_intent` `tool_call_resolution` `tool_intent_conflict` `suggested_tools_count` `capability_id` `capability_resolution` `param_instance_rejected` | int；枚举；float；str；tuple；bool；bool；float；受限枚举；bool；bool；受限枚举；受限枚举；bool；受限枚举 ×3；int（≥0 计数）；**受限枚举 ×2（2026-09-20 新增，`16` §8.1）**；**参数名 tuple（2026-09-23 新增，`16` §8.1——元素是 `ToolDef.parameters.properties` 里的参数名，**键名级、非原文**）** | 原样 / 原样 / 原样 / **不落盘** / **计数** / 后 16 键**全原样**（结构化值，无原文） |
| `dispatch_decision` | `action` `reason` `requires_user_confirmation` `proposal_gate_result` `proposal_denied_reason` `reference_guard_result` | NextAction 三字段 + 受限枚举 ×3（**取值域见 10-p6d §4.3 与 11 §5.1**：`proposal_gate_result` 9 值含 `vetoed`/`not_evaluated`，`proposal_denied_reason` 9 值；`reference_guard_result` 3 值 `not_evaluated`/`not_triggered`/`triggered`——**2026-09-16 由 `11-reference-guard.md` §5 新增**；`not_evaluated` 的合法来源是**未进入正常意图调度的回合**（确认恢复流，见 §3.4 else 分支），正常调度回合出现即接线缺陷。**工具相关 `reason` 的取值域 2026-09-18 扩展 7 值**（`tool_call_missing`/`unknown_tool`/`param_missing`/`param_invalid`/`tool_call_invalid_shape`/`multiple_proposed`/`tool_catalog_absent`，见 `15` §3.3/§3.4；`tool_call_invalid_shape` 与 `param_invalid` **不得合并**——前者是「草案整体形状不合法」，后者是「参数类型/键名不合法」，成因与修法不同。**2026-09-19 口径修正**：①这 7 值只约束**工具相关**的分流——`reason` 字段本身还承载既有的**非工具** reason（英文句子、`no_pending_operation`、`dangling_reference`、`local_conditional_answer` 等），不受本闭集约束；②承载分工是**其中 6 个能力错误值只由 `PLAN_LOCAL` 分支的空计划携带，`param_missing` 由 `ASK_USER` 携带**（追问逐条列出 `missing` 键名）；③实现纪律：`ControlPolicy` 在边界把 `validate_tool_call` 除 `param_missing`/`unknown_tool` 之外的失败**统一映射**为 `param_invalid`——校验器自身的命名空间（`param_type`/`param_unknown_key`，`15` §3.1）**不得**直接进事件） | 原样 / **不落盘** / 原样 / 后 3 键**全原样**（受限枚举） |

> **2026-09-20 扩展（P7a，`16-p7-practical-tools-capability-routing.md` §3.5/§6.6/§8.1）**：① `dispatch_decision.reason` 的工具相关闭集 **7 → 10 值**，新增 `capability_unavailable`（无匹配能力：`capability_resolution ∈ {unavailable, unrecognized}`）、`capability_irrelevant`（选了不服务所选能力的工具）、`capability_unrouted`（给了工具但没给可归属的能力）——三值由 `ControlPolicy` 直接产出，**不经校验器命名空间**。**同日再扩一值（本轮复审）**：`param_not_from_input`——**准入级来源校验**（`16` §6.3 第 4 条）拒绝时的 reason，**闭集 7 → 11 值**；它与 `param_invalid` **不得合并**（后者是「值的类型/键名不合法」，本值是「值不在用户原文里」），且**该轮没有 `tool_execution` 事件**（拒绝发生在建计划之前）——这是它与执行级 `location_rejected` 的唯一区分方式。② `proposal_gate_result` 的**值域不变**（9 值），但 `not_evaluated` 的**合法来源由 2 扩为 3**：新增来源③「能力终端性失败早裁」（`16` §3.8 ①，在 `evaluate_cloud_admission()` 内、`force_cloud` 为假时；**与 dangerous 早裁同类同法**）。③ `intent_final` 新增 `capability_id`（受限枚举：active 能力 id 或 `"none"`）与 `capability_resolution`（五值闭集 `routed`/`none`/`unavailable`/`unrecognized`/`absent`），与 `risk_draft`/`risk_draft_resolution` 同 stage 同法。④ `intent_final.tool_call_resolution` **+3 值**：`irrelevant_tool`、`unrouted_tool`、**`param_not_from_input`**（与 `unknown_tool` **不得合并**：前者「工具存在但不服务所选能力」，后者「目录里没有这个名字」，修法不同；`param_not_from_input` 是「草案有、但某个声明为出站的参数值不在用户原文里」⇒ 不建立草案，与 `param_missing`/`param_invalid` 同族但**不产生 `tool_execution`**）。⑤ **两份键白名单必须同时改**（`main.py` 的 `_sanitize_event_data` 与 `sinks.py` 的 `_PERSISTED_KEYS`），漏改 = 新键形同不存在。

> **2026-09-23 扩展（P7a 第三轮修订，`16` §0.5/§6.3.x/§8.1）**：① `intent_final` **+1 键** `param_instance_rejected`（**参数名 tuple**，元素取自 `ToolDef.parameters.properties`；与本表既有 `missing_info` 同为 tuple，**非自由文本**）——**该键是「值逐字来自用户、却不是该参数有效实例」这一失败态在观测面上的唯一痕迹**（真实复现：输入「今天天气怎么样」，模型把**整句**填进地点参数）。② **进出条件与能力键同进同出**：**开态恒出现**（无剔除时为空元组，**不得省略键**）；**关态整键不出现**（`16` §9.1 第 1 条的「键集相等」——关态下天气工具未注册、判据不存在，故**不得**写空元组）。新增观测键时「关态的存在性」与「开态的取值域」是两个独立问题，**必须分别写死**。③ **出站值校验由两级扩为三级**（来源级 → **实例级** → 执行级，`16` §6.3）——**本节的观测面不因此新增任何值**：实例级拒绝**不产生错误码、不产生 `reason` 值、不改变 `capability_resolution`**，它落在**既有**的 `dispatch_decision.reason="param_missing"`（追问）上，仅以新键与「该轮零 `tool_execution`」共同可辨。**2026-09-20 两条「两级」表述以本段为准**（该轮尚未有实例级）。④ **该键是逐回合事实**：补参续接回合重建候选时**必须重新计算**——把上一轮的拒绝名带进续接轮，既误报该轮、又会让 `16` §8.3 的硬性行自我触发（那一轮本应正常执行）。

> **2026-09-27 扩展（P7c，`18-p7c-local-document-and-search-tools.md` §1 / §10.1）**：`tool_execution` **+1 条件键** `result_delivery`（受限枚举 2 值 `model_summary` / `model_summary_failed`）。**为什么它必须存在**：P7c 新增的只读工具结果回流层使「工具执行后由本地模型基于结果生成回复」成为一条真实路径，回流**不计入 `rounds_used`**（那是意图理解轮次的账，`16` §3.4），因此若不加此键，回流**在观测面上不存在**——`18` §1.6 的失败语义与 §1.8 的轮次账都无法验证。①**事件类型零新增**（`16` §8.4 的纪律保持），只扩键；②**「出现条件」先于「取值域」写死**（同 §3 段 2026-09-23 点②的纪律）：**仅当被执行工具声明 `model_summary` 时才发此键**，因此全部既有工具（含 `file.write`）的 `tool_execution` 键集**与引入前逐字段相等**——「关态逐字段相等」与「键集相等」两条锚点原样成立。若改成"恒发此键"，`17`/`16` 的关态锚点会立刻失效，这是**刻意的取舍**；③**两份白名单必须同时改**（`main.py::_sanitize_event_data` 与 `sinks.py::_PERSISTED_KEYS`）——只改一处即 `18` §12.1 N4 变红；④**该键必须在 `_record_tool_events()` 之前算好**：`18` §1.2 要求回流排在 `_record_tool_events()` **之前**，否则本键无法落在**同一条** `tool_execution` 记录上（会错位到下一条或丢失）。**载体是 `ExecutionRecord.result_delivery`（2026-09-27 第二轮补充）**：回流返回按 **step_index** 索引的映射，由 `_execution_records(plan, results, deliveries)` 回填到记录上，`_record_tool_events(records)` 只读该字段、`None` 即不发键。**不得**把映射直接传进 `_record_tool_events()` 再用列表下标取值（记录列表经过过滤，下标与 step_index 不保证相等；`18` §12.2 R14）；⑤`reply_provenance` **语义不变**（回流是**呈现层**，工具确实执行了 ⇒ 仍是 `"executed"`；改成 `"answered"` 会让"工具是否真的执行"这一事实丢失）；⑥**工具执行本身失败**的回合不发此键（没有结果可回流），且**不得**为工具失败或回流失败发 `degradation`（本条 2026-09-20 的边界补充同法适用：回流失败回落确定性显示，不是系统降级）。
| `cloud_consult` | `phase` `escalation_reason` `authorization` `outbound_categories` `outbound_bytes` `sub_turn` `denied_reason` | 枚举 / 受限枚举 / 枚举 / 枚举元组 / int / int / 枚举 | 全原样（escalation_reason 与 denied_reason 均为受限枚举，非自由文本） |
| `cloud_return` | `inbound_ok` `needs_more_info` `followup_flag` `local_reintegrate` | bool ×4 | 全原样 |
| `tool_execution` | `tool_name` `risk_level` `verdict` `outcome` `error_code` + **条件键** `result_delivery` | ExecutionRecord 对应字段 + **条件键**：**仅当**被执行工具的 `ToolDef.result_delivery == "model_summary"` 时出现，受限枚举 2 值 `model_summary` / `model_summary_failed`（**2026-09-27 新增，`18` §1 / §10.1，P7c 只读工具结果回流层**）。**未声明回流的工具（含全部既有工具）不发此键** ⇒ 既有工具与本键引入前的 `tool_execution` 键集**逐字段相等**，`17` 的「关态事件流逐字段相等」与 `16` §9.1 的「键集相等」锚点不受影响 | 全原样 |
| `degradation` | `component` `fallback` | 枚举——`component` ∈ {"embedding","cloud","memory_retrieval"}；`fallback` ∈ {"keyword_only","local_only","none"}，与 component 一一对应（embedding→keyword_only，cloud→local_only，memory_retrieval→none），三对即全集。**`memory_retrieval` 为 P6d 新增（检索层显式失败）；`embedding` 本轮无生产者、保留待恢复**（见 §3.4）。**2026-09-20 边界补充**：工具失败（含外部服务超时/不可达/解析失败）**不是**降级路径，**不得**为它发本事件、**不得**新增 `weather`/`tool` 组件——否则会把「一次工具失败」记成「系统降级」，重演 §3.4 的假信号（`16` §8.1） | 全原样 |
| `turn_completed` | `completion` `final_action` `rounds_used` `duration_ms` `had_confirmation` `had_cloud` `error_code` `reply_provenance` | 枚举 / str\|None（error 时为 None）/ int（**`rounds_used` 的取值范围含 0**——`16` §4.4 的缺参续接回合零模型调用；P6 基线实现下该值恒 ≥ 1，任何「≥ 1」的隐式假设按缺陷处理）/ int / bool / bool / str\|None / 受限枚举 3 值 `executed`/`unfulfilled`/`answered` | 全原样 |
| `session_ended` | `summary_written`（turn_id=None） | bool | 原样 |

**落盘分级语义**：终端显示（CliEventSink、last_turn_report//why）可显示经消毒截断的原文；**JSONL 持久层不落任何用户/模型派生自由文本**——

- 「**别名**」= run 内随机别名：每个**不同取值**在本次进程内首次出现时分配一次随机短码（`p_`/`t_` 前缀 + uuid4 截 6 hex，分别对应 project / topic），同 run 内**同值同别名**（事件间可聚合关联）；映射表只存在于 JsonlEventSink 进程内存，**不落盘、不跨 run 稳定**。不用确定性哈希——项目名/话题名是低熵文本，sha256 可被字典枚举反推，截断哈希不构成「不可逆匿名」；也不本地 HMAC——P6b 聚合按场景实例组织（run_meta 已含 scenario/variant），不需要跨 run 的主题级关联，HMAC 反而新增本地秘密管理面。跨 run 关联是**评估运行器**的职责（它知道预置了什么）。
- 「**计数**」= `missing_info_count: int`；「**不落盘**」= 该键从 JSONL 行中剔除（`intent_type` 是模型自由文本、`reason` 是规则层模板串，均为可枚举低熵文本，原文与哈希都不落）——细节由终端显示与显式转录（消毒、gitignore）承载。

topic_label 由用户输入前 3 词干派生，可能包含路径/用户名等未命中正则的敏感文本——**不能靠消毒保证落盘安全，只能靠不落盘**。JsonlEventSink 按 stage 键白名单转换，白名单外任何键不得落盘。

`turn_completed` 的 data 即 §5.2 last_turn_report 的摘要版；完整报告字段更多，但**同一数据源**，不得两处独立计算。

**`memory_retrieval.degraded` 与 `degradation` 事件语义（2026-09-15 P6d 修订，取代 P6a 审查补记）**：原判定「本次检索向量侧零参与」（返回 hits 中无任何 `vector_score`）是对服务健康的**推断**，已被真实 run 证伪——空库零命中 → `memories=[]` → `any([]) == False` → `degraded=True` → 每轮发出 `degradation(embedding→keyword_only)`；S06/S09 的定向 run 因此被全程记录为「embedding 故障降级为纯关键词」，而 embedding 配置、服务与调用均无故障，**这是把「零向量命中」谎报成「embedding 故障」**。

修订后（详见 `10-p6d-autonomous-escalation.md` §5）：**`degraded=True` 的唯一来源是检索层委派调用显式失败**（`memory.retrieve()` 返回 `Result.is_err`）。零命中**不是**降级；向量通道缺席**不是**降级；`vec_enabled=False` 只是**结果侧证据**、单独出现时无语义，**禁止**用于推断服务健康或聚合为「故障率」。本轮**明确不宣称**能区分「未配置向量」「向量健康但零命中」「embedding 故障回退」——当前实现做不到，所以不说（宁可漏报，不可谎报）。精确信号待 10-p6d §5.4 的 `MemoryBackend` 可用性快照（接口签名变更，需 Claude 审查）落地后恢复。

**`cloud_return.inbound_ok` 归并说明（P6a 审查补记）**：入站检查失败以异常进入 denied 链路（`cloud_consult.phase="denied"`，`denied_reason="unavailable"`），故 `cloud_return` 仅在入站检查通过后的成功路径产生，`inbound_ok` 恒为 True。字段保留是为与 P6b 评估记录对齐，并为未来"不抛异常的入站软拒绝"预留。

**`cloud_consult.denied_reason` 封闭集（2026-09-13 P6c 扩展，modules/09-p6c-cloud-provider.md §6.2；2026-09-18 再增一值）**：本地否决类 `disabled` / `no_safe_context` / `user_cancelled` / `session_mismatch` / `authorization_expired` / **`sensitive_policy_grant_forbidden`（2026-09-18 新增）** 不变；云端调用失败类按错误码细分——`"auth"`（CLOUD_AUTH_INVALID / CLOUD_CREDENTIAL_MISSING）、`"endpoint"`（CLOUD_ENDPOINT_INVALID）、`"rate_limited"`（CLOUD_RATE_LIMITED）、`"unavailable"`（CLOUD_UNAVAILABLE / CLOUD_PARSE_ERROR 及其余 LocalMindError 兜底）。事件仍不含任何 Key、header、响应体或 payload 原文（禁入清单不变）；细分理由是让评估 JSONL 可区分「凭据错配」与「网络故障」（S13 型）而非依赖 `turn_completed.error_code` 单一通道。

> **`sensitive_policy_grant_forbidden` 的语义与边界（2026-09-18 补，来源：`12-risk-draft-closed-set.md` §3.4、`05-p4-cloud-advisory.md` §3.2）**：它是**冗余防线被触发**的标记——`AuthorizationManager.create_policy_grant()` 收到非 `normal` 的有效授权风险而拒绝签发（`CLOUD_AUTHORIZATION_REQUIRED`），App 捕获后发本条事件并**转入授权等待**。它是**接线缺陷**的观测面，正常实现下**计数恒为 0**（08 §2.6 硬性行）。三条边界必须同时成立：① **只在 `phase="denied"` 上出现**，不新增 stage、不新增 data key、不新增错误码；② **不写 `CloudAuditEvent`**、**不计入 `record_denial()`**——后者的四值 `reason` 闭集与「每条任务清理路径恰一条 / 终止语义」不变量均不变（理由：误调用之后任务并不终止，还要进授权等待、还可能走通）；③ 它不同于 `no_safe_context`（那是**准备阶段产不出可发送内容**的正常否决），也不代表用户拒绝——**不得**被报告聚合读成「用户否决率」或「隐私拒绝率」，只能读成「接线缺陷计数」。

---

## 3. App 插桩与消毒

### 3.1 emit 点

`App.handle()` 内按 §2.1 时机插入 `self._emit(stage, level, data)`；`_emit` 负责：补 run_id/turn_id/session_id/seq/ts → 消毒（§3.2）→ try/except 调 sink（任何异常吞并）。`App.end_session` 末尾 emit `session_ended`。

`App` 构造新增参数 `event_sink: RuntimeEventSink | None = None`（None → 内部 `NoopEventSink()`）与 `run_id: str | None = None`（None → 内部生成 uuid4 短码）；`run_id` 为只读属性。P6b 运行器经 `bootstrap(run_id_override=…)` 注入同一值——App 事件与评估产物（目录/JSONL/session）的 run_id 同源（§7.2）。

### 3.2 文本槽位分级：终端显示 vs JSONL 落盘

自由文本槽位（`topic_label`、`referenced_topic`、`project_id`、`intent_type`、`reason`、`missing_info`）是用户/模型派生文本，**正则消毒对任意文本不构成安全保证**。分级处理：

- **终端显示**（CliEventSink、last_turn_report / /why）：可显示原文；进入前过 `memory_hygiene.sanitize_for_memory()` + 截断（missing_info/intent_type 每项 ≤60 字符，reason ≤200 字符）——消毒只是显示层兜底；
- **JSONL 持久落盘**（JsonlEventSink）：不落上述任何原文，按 §2.2 落盘列替换为 run 内随机别名、计数，或整键剔除；
- 两级转换表唯一真源在 sink 实现：CliEventSink 不过滤（只格式化），JsonlEventSink 按白名单转换；`last_turn_report` 仅终端消费，不落盘。

**禁入清单由三道防线执行**：字段封闭集（§2.2 键集）+ JSONL 落盘分级（本节）+ 终端消毒兜底；验收对三道分别断言。

### 3.3 顺序保证

同一 turn 内事件 seq 严格递增且与实际发生顺序一致；topic_decision 先于 intent_*，intent_final 先于 dispatch_decision，tool_execution 在 dispatch 之后、turn_completed 之前。

### 3.4 降级检测点（degradation 事件）

- **`memory_retrieval→none`（2026-09-15 P6d 新增）**：检索层委派调用显式失败（`memory.retrieve()` 返回 `Result.is_err`）→ 既有构造 `RetrievalStats(0, False, False, True)`（`kw_enabled=False` 且 `degraded=True`，是**真的**什么都没拿到）；主检索（`context_assembler`）与认知轮检索（`intent_resolver`）两处都发事件
- 云端不可用/预算耗尽/冷却导致的本地收敛时（P4 既有否决分支 → `cloud→local_only`）
- **`embedding→keyword_only`（P6d：本轮无生产者）**：语义为「向量通道不可用、本次仅关键词」——这是**正确**的信号，但 `MemoryBackend.retrieve()` 的 `Result[list[MemoryChunk]]` 返回类型**无法把它带出检索边界**，故本轮无法诚实生产，保留枚举值待 10-p6d §5.4 恢复；**恢复前不得以任何推断（`bool(vector_scores)`、`vec_enabled`、`dimensions()`）代替**

> 范围澄清：当前实现**没有模型级降级机制**——Ollama 生成失败走既有 `MODEL_ERROR` 错误路径返回（P1 契约），不产生 degradation 事件；`component` 枚举因此仅 `"embedding" | "cloud" | "memory_retrieval"`，`fallback` 仅 `"keyword_only" | "local_only" | "none"`（一一对应，见 §2.2）。未来若引入模型级降级再扩枚举。

### 3.5 口令确认轮的特殊边界

`_handle_confirmation` 分支（P3 提前返回路径）内的事件照常产生，但 data 中任何槽位都不得含口令原值与确认原文——与 P5 写入链同一约束：调用方根本不把它们传入，而非靠消毒兜底。确认失败轮同样产生事件（`dispatch_decision.reason` 反映锁定状态），但不写记忆（P5 既有）。

### 3.6 异常路径的终结事件

事件生命周期按四类定义，不强行伪造不存在的状态：

| 生命周期 | 终结事件 |
|---|---|
| 普通请求轮 | `turn_completed(completion="normal", final_action=…)` |
| 确认轮 / 云端授权轮（handle 内提前返回分支） | 同为一次 handle() 调用，照常产生 `turn_completed`；确认成功轮含本次执行的事件序列 |
| 异常轮（意图完成前抛错，经 handle 异常兜底） | `turn_completed(completion="error", final_action=None, error_code=…)`——兜底路径也 emit，不省略 |
| 会话生命周期（end_session，handle 之外） | `session_ended`，`turn_id=None` |

不变量：**每次 handle() 调用恰好一条终结事件**；`final_state`/`final_action` 仅在真实达成时填值，异常轮置 None——不得用占位状态冒充意图结论。

---

## 4. 交互式 CLI

### 4.1 模块结构与入口

```
src/cli/__main__.py   # python -m src.cli：bootstrap(config) + loop.run()
src/cli/loop.py       # read-eval 薄壳：读行 → 命令层 → handle()；EOF = /quit
src/cli/commands.py   # 斜杠命令层（纯函数，供 loop 与场景运行器复用）
src/cli/sink.py       # CliEventSink
```

- 启动：`bootstrap(config_path, event_sink_override=<Composite(CliEventSink, JsonlEventSink?)>)`（§7.2）；打印欢迎行（含 /status /why /trace /quit 提示）。
- 输入预处理：`sys.stdin` / `stdout` 显式 `reconfigure(encoding="utf-8")`（Windows 中文输入输出硬要求）。
- 空行跳过；**所有行先经命令层解析**：仅命中 §4.3 自有 7 命令时本地处理（handled=True）；其余一切输入——包括 `/` 开头的 P4 云端指令（`/cloud allow`、`/cloud cancel`、`/cloud deny`、`/cloud ask …`、`/cloud off …`）与未知 `/xxx`——handled=False，**原样透传** `app.handle(text, session_id, project_id=绑定值)`。P4 指令由 App 在 handle 内部解析、不进模型输入（P4 既有行为与测试不变）；透传的命令行照常产生事件与 episode（其文本本就是用户显式指令）。
- 一次运行只有一个 session_id（`sess_cli_<run_id>`）；CLI 侧维护 `bound_project: str | None`（初始 None）。

### 4.2 命令层（commands.py）

```python
@dataclass(frozen=True)
class CommandResult:
    handled: bool                 # 是否命中 07 自有命令；False（含未知 /xxx、P4 /cloud 指令）→ loop 必须原样透传 handle()
    output: str                   # 命令回显（空串 = 无回显）
    action: str                   # "none" | "quit" | "switch_project" | "trace_on" | "trace_off"
    project_id: str | None = None # 仅 switch_project 时非空（已归一化）

def handle_command(line: str, app: App, session_id: str,
                   bound_project: str | None, trace_on: bool) -> CommandResult: ...
```

- 命令层**只识别自有 7 命令**；未命中（含一切其他 `/` 开头行）一律 `handled=False` 交还 loop 透传——命令层不做模糊匹配、不猜测用户意图。
- `/switch` 无参数：output 显示当前绑定，不改变状态。
- `/trace` 参数非法：output 提示用法，不改变状态。
- `switch_project` 的 project_id 经 `ProjectStore.normalize_project_id` 归一化；loop 收到后更新绑定，**下一轮** handle 起以显式 project_id 进入 P5 解析路径（`/switch` 本身不触发 handle、不产生事件）。

### 4.3 命令语义表

| 命令 | 数据来源 | 行为 |
|---|---|---|
| `/status` | `App.status_snapshot()` | 显示会话、当前绑定项目、当前话题、模型后端、云端开关、trace 状态（trace 由 CLI 自行附加） |
| `/why` | `App.last_turn_report()` | 显示上轮决策的结构化理由（§5.2 字段，人类可读行）；无上轮 → 提示；**只展示可验证事实**（决策 reason、缺失信息、检索统计、云端否决原因），不展示模型 `reasoning` |
| `/projects` | `App.list_projects()` | 项目 id 列表 + 标注当前绑定 |
| `/topics` | `TopicTracker.topics_history(session_id)` | 本会话已用话题标签序列（当前话题置末）；不跨会话检索。**范围澄清**：P6a 的 /topics 只看本次会话——项目历史话题（P5 ProjectStore 的 topic_tags）不在 CLI 暴露范围，重启后不可经 /topics 追溯；留待后续按需扩展查询命令，P6a 不扩 |
| `/switch <project>` | CLI 状态 | 更新绑定（§4.2），output 确认 |
| `/trace on\|off` | CliEventSink | 切换显示模式 |
| `/quit` | `App.end_session(session_id)` | 触发 P5 会话收尾（tracker 清理 + 会话摘要最终覆盖）+ `session_ended` 事件，显示「会话已结束，摘要已保存」，退出 |

### 4.4 显示格式

简洁模式（trace off），每轮在回复正文前最多三行状态：

```
[项目: <pid|未归属> | 话题: <topic_label>]
[理解: 第 <n>/<max> 轮，<状态>]        ← 一轮收敛时显示 [理解: 1 轮收敛]
[决策: <action 中文描述>（需确认）?]    ← 取自 dispatch_decision
```

trace 模式额外逐行显示 detail 事件（`<stage>: <k>=<v> …` 单行紧凑格式）。事件显示永远不包含 §2.2 封闭集之外的值——CliEventSink 只做格式化，不做数据加工。

### 4.5 与现有文本通道的关系

- **P4 云端指令**（`/cloud allow|cancel|deny|ask|off`）：经命令层**透传**进入 handle()，由 App 内部解析（不进模型输入）——授权交互流原样保留，07 不重复实现、不改写语义；
- **P3 确认词**（确认/是/ok…）：非斜杠行，不经命令层，直接进入 handle()——原样保留；
- 07 自有命令（/status /why /projects /topics /switch /trace /quit）**不承载**确认、授权或云端指令语义；自有命令行永远不会被解析为确认或授权文本。

---

## 5. App 只读查询接口（签名变更，同步 00-adapter-factory）

### 5.1 新增公开方法

```python
class App:
    def status_snapshot(self) -> dict:
        """{"session_topic": str, "project_id": str|None, "model": str, "cloud_enabled": bool}
        model = 模型后端标识（backend 类名 + 模型名，可得时）。"""

    def last_turn_report(self) -> dict | None: ...

    def topics_snapshot(self, session_id: str) -> tuple[str, ...]: ...

    def list_projects(self) -> list[str]: ...
```

全部只读：不写记忆、不产生事件（除既有路径）、不改变任何状态机。`status_snapshot` 的 `project_id` 取 TopicTracker 当前值（P5 语义），CLI 绑定值由 CLI 自行显示。

### 5.2 last_turn_report 字段（封闭集）

```
turn_id, ts, input_chars, project_id, topic_label, relation,
rounds_used, final_state, model_confidence, intent_type, missing_info,
retrieval: {hits, kw_enabled, vec_enabled, degraded} | None,
action, reason, requires_user_confirmation,
cloud: {escalation_reason, authorization, outbound_categories, outbound_bytes, denied_reason} | None,
tool_results: [{tool_name, verdict, outcome, risk_level}],
duration_ms
```

在 `turn_completed` 时由同一份内部数据落成；`/why` 直接读取。字段与事件共享消毒规则（§3.2）。

---

## 6. file.write 工具

### 6.1 注册

```python
ToolDef(
    name="file.write",
    description="在工作区内写入 UTF-8 文本文件（相对路径）",
    parameters={"path": {"type": "string"}, "content": {"type": "string"}},  # 均必填
    risk_level="sensitive",   # 2026-09-20 老板拍板（P7a-0）：一律确认，新建与覆盖都确认
)
```

- 加入 `registry.py` 白名单与 `BuiltinToolBackend`；实现落 `file_tools.py`。
- **⚠️ 2026-09-20 反转（老板拍板，P7a-0，反转 2026-09-10 的旧口径）**：`file.write` 的注册表基线由 `normal` 改为 **`sensitive`**，`preflight` 的 `requires_confirmation` **恒为 `True`**（不再由 `target_exists` 决定），故**新建与覆盖都进确认链**。理由与执行方式（独立前置变更，不并入能力层批次）见 `requirements.md` FR3、`16` §11 第 21 项、`clarifications.md` 拍板登记。**下面 §6.3 的存在性矩阵、本行下方的分工说明、§6.4 的测试清单、§12 的决策行**均已按此反转——旧口径文字保留并就地标注，以免读者按旧基线实现。翻转后**必须重测 P6 基线**（「关态 = 基线」的锚点值随之改变），并同步 `08` §2.6 的 S14 硬性行与 `13` §2/§3.2。
- **与 `risk_draft` 的分工（2026-09-17 补，`12-risk-draft-closed-set.md` §1.2 表注）**：上表的 `risk_level` 与 §6.3 的 preflight 升险是**工具层/执行层**的确定性风险；`IntentCandidate.risk_draft` 是**意图层**风险，**不复制**这一层，**覆盖**与**路径越界**由 preflight 只升不降（越界 → `effective_risk="dangerous"`）。两层都**只升不降**，任一层升险都不需要另一层同意；反过来，意图层的 `normal` **不得**用于压低工具层的确定性升险。**⚠️ 该分工的「只升不降」结构不变，但原文举的例子与结论「工作区内新建在意图层就是 `normal`／S14『新建无需确认』成立」已在 2026-09-20 作废**：工具层基线现在是 `sensitive`，「新建无需确认」不再是本项目的口径。
- **本层不进入云端授权判定（2026-09-18 补，`12-risk-draft-closed-set.md` §3.5 表后注）**：云端签发 policy grant 时的**有效授权风险**只消费两个信号（payload 候选的隐私分类、`task_has_sensitive_execution_chain`），**不消费**上表的 `risk_level`／preflight 升险／`approval_profile`——policy grant 发生在云端续咨询阶段，那时通常既无 `ExecutionPlan` 也未跑 preflight，本层信号在那里**不可求值**。两条链路正交：**外发内容的敏感度**由 `PrivacyPreparation` 决定，**工具执行的危险度**由本层与 `13` 决定；把本层接进云端授权只会让「未求值即 `sensitive`」把自动续咨询重新锁死，而不会多挡住任何一次外发（真实敏感执行链本就是云端准入的硬否决）。
- **只允许相对路径**：绝对路径（含盘符、UNC、`~`）直接拒绝。

### 6.2 工作区约束（双层校验）

配置 `[tools] workspace_root`（默认 `./data/workspace`），bootstrap 时目录不存在则创建并 realpath。

1. **L1 层（RuleOnlySafetyBackend）**：对 `file.write` 的 `params.path` 解析——非法（逃逸/绝对路径/空）→ `SafetyVerdict(allowed=False, reason="workspace_escape")`；
2. **工具层（file_tools.py）**：执行前重复同一路径校验（不信任调用方），再写入。

解析规则（两处一致）：`base = Path(workspace_root).resolve()`；`target = (base / raw_path).resolve()`；`target.is_relative_to(base)` 必须为 True（含分隔符边界，防 `workspace_root_evil` 前缀绕过——`is_relative_to` 语义天然满足）。失败抛 `LocalMindError(code="FILE_ERROR", recoverable=True, user_message="文件操作被拒绝：路径必须位于工作区内。")`。

### 6.2b 三条文件工具的统一边界（2026-09-18 新增，`15` §6）

§6.2 的双层校验原本只覆盖 `file.write`（`file.read` / `file.list_dir` 直接 `Path(raw)`，完全绕过）。加固后**三条路径共用同一套规则**：

- **唯一解析器** `resolve_workspace_target(raw, workspace_root)`（工具层共享函数）：`file.read` / `file.list_dir` / `file.write` 及其 preflight hook **全部**调用它；拒绝集一致——绝对路径 / 盘符 / UNC / `~` / 解析后不在工作区内（含 `..` 逃逸，以 `is_relative_to` 为准）。
- **风险语义一致的扩展**：逃逸时 preflight 的 `effective_risk="dangerous"`（原仅 `file.write` 如此）→ App 硬拒，**不得**返回任何文件内容或目录项。
- **错误统一**：`FILE_ERROR` + `details.reason` 闭集扩展为 `workspace_escape` / `target_exists` / `target_state_changed` / `target_missing` / `not_a_directory` / `path_type` / `content_too_large`（reason 表由 `00-error-contract.md` 镜像）。**禁止原生异常逃逸**：读不存在的文件返回 `target_missing`，不得抛 `FileNotFoundError`；`message` 必须与操作一致（不再出现读操作回 `File write rejected`）。
- **注册表风险值**：`file.read` 仍 `sensitive`（S14 step0 的确认链依赖它），`file.list_dir` 仍 `normal`（无目标语义、无副作用，**不受 P7a-0 影响**），**`file.write` 由 `normal` 改为 `sensitive`（2026-09-20，P7a-0）**——动态升险仍由 preflight 提供且照常记录，只是基线已不可能是 `normal`。**`08` §2.6 中依赖「写操作 `normal`」的硬性行与 S14 期望必须同步反转**（P6 基线重测后取新值作锚点）。
- **提示词侧同步**：工具目录从「名称 + 短描述」升级为完整定义（含参数结构、必填、风险），见 `15` §6.4。

### 6.3 执行前评估与覆盖确认（preflight，唯一新机制）

**裁决（2026-09-20 反转，见下方 ⚠️）**：新建不确认；**覆盖已有文件必须确认**。App 必须在**建立确认状态之前**知道目标是否存在，而该事实要到工具层做路径解析时才可判定——因此新增无副作用的执行前评估。

> **⚠️ 2026-09-20 老板拍板（P7a-0）：本节的确认口径已反转为「`file.write` 一律确认」**——新建与覆盖都进确认链。**下面这一整节的机制（preflight、pending、TOCTOU 复检、同源升险）逐条仍然成立且是唯一实现方式**，改变的是**触发条件**：`requires_confirmation` 不再由 `target_exists` 决定，而是由注册表基线（`sensitive`）恒真。`target_exists`/`target_key` 因此从「是否确认的判据」降级为**确认文案与 TOCTOU 快照**两项用途——**不要**据此删掉 preflight 或存在性判定，TOCTOU 复检与「覆盖」文案都依赖它。理由与执行方式见 `requirements.md` FR3、`16` §11 第 21 项、`clarifications.md` 拍板登记。

**组件边界（不做 executor 特判）**：动态评估是**工具后端的统一 preflight 能力**，不是 GuardedToolExecutor 对 file.write 的特判——安全执行器只消费标准化结果，P7 接入 MCP 等其他工具后端时即插即用（**2026-09-25 P7b 已兑现**：`17-p7b-mcp-qwenpaw-tool-ecosystem.md` 的 `ToolProvider` + `CompositeToolBackend` 正是这条边界下的接入点，**执行器零改动**。**2026-09-26 订正**：原文写「`ToolBackend` 接口零改动」已被该契约 §2.4 的**必要变更**取代——新增一个带默认实现的 `close()`（进程回收路径所必需）；故准确口径是「**两项零变更 + 一项必要变更**」（事件闭集零扩展、`App` **构造签名**零变更、`ToolBackend` 新增默认 `close()`），本条要求的验收形态不变）：

```python
# core/schemas.py —— 标准化评估结果（工具后端 ↔ 执行器 ↔ App 的唯一交换格式）
@dataclass(frozen=True)
class PreflightReport:
    effective_risk: str            # 该次调用的最高有效风险（max(模型值, 注册表值, 后端动态值)）
    requires_confirmation: bool    # effective_risk 为 sensitive 及以上（**只由风险驱动**）
                                   # 2026-09-20 反转后 file.write 的注册表基线即 sensitive ⇒ 该字段对它恒真，
                                   # 「新建免确认」不再是本项目的口径；字段语义与实现均不变，只是取值随之改变
    target_exists: bool | None     # 目标存在性（无目标语义的工具为 None）
                                   # 反转后仅用于确认文案（「新建」/「将覆盖」）与 TOCTOU 快照一致性比对
    target_key: str | None         # 规范化目标标识（确认快照一致性比对用；无则 None）
    reason: str | None             # 升险原因，如 "target_exists"（反转后仍照常记录，但不再决定是否确认）
    approval_profile: str = "standard"   # 2026-09-16 新增，见 13-approval-profile-high-impact.md §2
                                         # 批准档（standard / high_impact）；与 effective_risk 正交。
                                         # 尾部新增 + 默认值 → 既有位置/关键字构造全部兼容

# core/interfaces.py —— ToolBackend 增加统一 preflight 能力（签名变更，Claude 所有）
class ToolBackend(ABC):
    def preflight(self, tool_name: str, params: dict) -> PreflightReport:
        """无副作用评估单个工具调用：不执行、不写文件、不改任何状态。
        默认实现：按注册表 risk_level 返回静态报告（target_exists/target_key = None）。
        有动态风险语义的后端覆写——BuiltinToolBackend 对 file.write：
        按 §6.2 同一解析规则预检，逃逸/非法路径 → effective_risk="dangerous"、
        reason="workspace_escape"；目标已存在 → target_exists/target_key（2026-09-20 反转后
        这两项只作**确认文案与 TOCTOU 快照**用，不再决定是否确认——注册表基线已是
        sensitive、requires_confirmation 恒真，存在性升险仍照常记录且只升不降）。
        approval_profile（2026-09-16，签名不变）：声明该调用一旦执行、影响面不可由工作区
        边界约束时为 "high_impact"；闭集外值由 read_approval_profile() 兜底为 high_impact。"""
```

- 动态评估实现落 `file_tools.py`（目标存在性、路径规范化、工作区约束预检）；**执行器不 import 任何具体工具实现**。
- `preflight` 必须无副作用（验收断言：调用前后文件系统、审计、状态不变）。

```python
class GuardedToolExecutor:
    def preflight(self, plan: ExecutionPlan, task_id: str = "", intent_id: str = "") -> PreflightReport:
        """无副作用评估整个计划：不执行、不写审计、不改任何状态。
        逐 step：白名单校验 → tool_backend.preflight()（标准化消费）
        → effective_risk = max(step.risk_level, 注册表 risk_level, 后端动态值)。
        plan 级聚合：effective_risk 取最高，requires_confirmation 任一为真，
        approval_profile 取最高（standard < high_impact，只升不降；2026-09-16），
        target_* 取首个非 None step（P6a 仅 file.write 一类目标语义；多目标后端接入时再扩展为列表）。
        任一 step 未注册 → 抛既有 ToolError(TOOL_NOT_FOUND)（与 execute 同一错误形态）。"""
```

**execute 同源动态风险（闭环保证）**——动态升险必须到达真正执行：`execute()` 逐 step 在白名单校验后再次调用 `tool_backend.preflight()`，并以**动态结果替换该 step 的有效风险**（`effective_risk = max(step.risk_level, 注册表值, 后端动态值)`，`replace(step, risk_level=…)`）：

- `safety_policy.check(step)` 与 AuditEvent 看到的都是升险后的风险——确认后覆盖执行的审计 `risk_level="sensitive"` 由同源链路保证，不靠 App 侧转述；
- **（2026-09-16）`approval_profile` 走同一条同源链路**：`execute()` 逐 step 以 `max_approval_profile(step, 注册表值, 后端动态值)` 复评（只升不降，`replace(step, approval_profile=…)`），并在 `dangerous` 拒绝**之后**、`sensitive`/`gate23` 通道**之前**插入 `high_impact` 拒绝（`SAFETY_IMPACT_CLOSED`）——这是执行层的**冗余防线**，保证高影响操作无法经 `gate23_passed=True` 直接放行；
- 该复评兜底「执行前目标被外部创建」方向：风险升为 sensitive 且无确认（gate23 未过）→ 按既有 `SAFETY_NECESSITY` 拒绝；（**2026-09-20 反转后的口径**：`file.write` 已无「新建放行」这一支——所有写操作都经确认，故 gate23 在建计划时对写操作总是已置位；本兜底仍然保留，作用是防止「后端正则变化/注册表基线被改回」时出现无确认的高风险执行，属**只增不减的冗余防线**）
- 「存在→消失」方向由 App 快照比对兜底（target_state_changed，见下）——execute 复评是 max 语义只升不降，不因目标消失把已确认的覆盖降级回 normal。

**App 流程（`_handle_action` PLAN_LOCAL 分支改造，P3 既有 pending 机制不变）**：

1. `plan` → `executor.preflight(plan)`（TOOL_NOT_FOUND 同样进第 2 步通道）；
2. 任一 step `effective_risk == "dangerous"`（或未注册）→ 拒绝，并调用 `executor.record_denial(plan, task_id, intent_id, reason)` 走**统一拒绝审计**（既有公开方法）——被安全层拦截的尝试必须有审计留痕，preflight 阶段也不例外；
2b. **（2026-09-16 新增，步序不可调换）计划级 `approval_profile == "high_impact"` 且 `effective_risk != "dangerous"`** → **扣留执行**：`record_denial(plan, task_id, intent_id, "high_impact_closed")`，返回**不可执行草案**（工具名/动作/脱敏参数/目标 + 五条件说明 + 「当前阶段不执行」），**不**存 pending、**不**返回确认文案、**不抛异常**（App 主线是正常响应，`handle()` 不抛异常；`SAFETY_IMPACT_CLOSED` 只属执行层冗余防线）。规范见 `13-approval-profile-high-impact.md` §3；`04-p3-safety-hardening.md` §4.6b 给硬约束。放在第 3 步**之前**是必须的——放到之后会让高影响操作进入确认链并被一次确认放行。条件**不含**风险值判断（`normal` 与 `sensitive` 一视同仁，见 13 §2.3）；
3. `next_action.requires_user_confirmation` **或** `report.requires_confirmation` → 存 pending（P3 既有字段 + preflight 快照 `target_exists`/`target_key`），返回确认文案（按 target_exists 区分「新建」/「将**覆盖**已存在文件」）——**2026-09-20 反转后 `file.write` 恒走此支**，两步的文案差异仍然保留（用户有权知道这是新建还是覆盖），只是**两支都要确认**；
4. 否则 → 执行前复检（下）通过后 `execute(plan)`。

> **本节的字段与事件面保持不变**：`high_impact` 的留痕走既有 `record_denial` → `AuditEvent.reason`，**不**扩展 §2.2 的事件键集与 stage 集合；`requires_confirmation` 仍然**只由风险驱动**，不因 `approval_profile` 为真——否则高影响操作会流进确认链。

**执行前复检（防确认前后文件状态翻转，TOCTOU）**——App 在调用 `execute` 之前**重跑一次 `executor.preflight(plan)`**，与 pending 快照（无确认路径则与初次报告——2026-09-20 后 `file.write` 恒有确认路径，该分支只对未来的免确认工具有效）比对 `target_exists`/`target_key`：

- 不一致（确认时存在、执行前已消失，或确认时不存在、执行前已出现）→ 拒绝（`FILE_ERROR`，details.reason="target_state_changed"），经 `record_denial` 留痕；确认语义只在快照一致时成立；
- 一致 → `execute(plan)`。execute 内工具层路径校验（§6.2 双层）照旧，不豁免、不特判。

比对在 App 侧完成（executor 不持有快照知识）；App 复检与 execute 复评之间的残余窗口由工具层 L1 校验与工作区约束兜底，P6a 接受该粒度。

AuditEvent：execute 记录的 `risk_level` 即 execute 复评后的有效风险（动态升险在同源链路上）；preflight 本身不落审计（无副作用），**preflight 引发的拒绝一律经 record_denial 通道留痕**。

### 6.4 写入行为

- `open(target, "w", encoding="utf-8", newline="\n")`；content 为 str（模型/意图层保证），非 str → `FILE_ERROR`。
- content 上限 **1,000,000 字符**（超限 `FILE_ERROR`，user_message 说明）。
- 成功返回 `{"path": "<相对 workspace_root 的路径>", "bytes_written": <utf-8 字节数>}`——返回值不含 content。
- 与 P5 留存规则衔接：ExecutionRecord 照常（键名级结构化摘要）；episode 与事件流不得出现 content 原值（§3 禁入清单 + §8 断言）。
- file.write 与 P4 云端边界无交互（写入本地工作区不属外发）。

---

## 7. 配置与 bootstrap

### 7.1 配置（config/default.toml 增段）

```toml
[observability]
event_jsonl_path = ""        # 空 = 不落 JSONL（默认）；非空 = 相对 data/ 的评估事件路径

[tools]
workspace_root = "./data/workspace"
# tool_backend 的 whitelist 中**不得**出现 system.echo（2026-09-20，16 §4.3：
#   echo 是测试替身，生产/试用配置移除它；测试与演示脚本自带白名单）

[capability_routing]         # 2026-09-20 新增（16 §3.1）
enabled = true               # 生产/试用默认开启（16 §9.1 第 1 条：「为什么交付默认不是关态」——
                             #   关态下能力层不参与，诚实失败与相关性边界都不可达）
                             #   关态（P6 基线逐字一致）由评估运行器 --capability-off 构造

[tools.weather]              # 2026-09-20 新增（16 §5.3/§6.2）
provider = "open_meteo"      # 生产/试用默认开启真实能力；"none" = 天气能力不存在（诚实失败，评估/回退档）
[tools.weather.connection]
connect_timeout_seconds = 5  # 必须为正
read_timeout_seconds = 10    # 必须为正；读取截止在分块读取循环内累计（响应上限 64 KiB 是代码常量、不可配）

# ---- P7b 新增（2026-09-25，17 §9.1）----
# [tool_providers.<id>] 子表 = 外部工具来源。**默认无本节 = 零外部来源**（fail-closed 方向，
#   与上面 provider="none" 同纪律）。
# 用子表而非数组：TOML 子表名重复是**解析期错误** ⇒ 「provider id 重复」这一类冲突在语言层不可能发生。
# 配置里**没有一个字段能改变权限**（17 §1.1 的三来源 × 九类事实权威表）：能改的只有「跑不跑」与「跑多久」。
# **2026-09-26 修订（17 裁决 6 / E18）**：「跑哪个进程」**不再由配置回答**——argv 移入本地代码的
#   `ProviderDeclaration`（`src/tools/provider_declarations.py`）。原稿的 `command` 键已**作废**，
#   配置键集收缩为**闭集** {enabled, handshake_timeout_ms, call_timeout_ms}，出现任何其它键（含 `command`）
#   ⇒ CONFIG_ERROR / reason="tool_provider_invalid"。原因：该进程在 bootstrap 期、进入 GuardedToolExecutor
#   **之前**就已启动，配置能决定「跑什么」就等于存在一条不受唯一出口约束的副作用路径。
#
# [tool_providers.demo]
# enabled = false                                  # 缺省 false
# handshake_timeout_ms = 5000                      # 有限正整数且 ≤60000（17 E16）
# call_timeout_ms = 10000                          # 同上
#
# 硬性约束（17 E3）：`[tool_providers]` 存在任一 enabled=true ⇒ [capability_routing].enabled 必须为 true，
#   否则 CONFIG_ERROR / reason="tool_providers_require_capability_routing"。
#   这一条把「外部工具不得绕过能力选择」变成**结构性事实**（关态下外部工具不可能进入提示词）。
#
# 可跑样例：config/mcp.example.toml（2026-09-25 新增）。子进程环境由**极小允许清单**构造
#   （**禁止**把 os.environ 直接传给 Popen；凭据因不在白名单里而结构性不存在，17 §5.2）；
#   stderr **绝不进入任何面**；stdout 只当协议通道（严格 newline-delimited JSON-RPC 2.0）。
# 生命周期（17 §2.4）：App 新增 shutdown()，CLI / 评估运行器 / 诊断脚本必须在 finally 中调用它；
#   `end_session()` **不**关闭 provider（会话边界 ≠ 进程边界）。
```

### 7.2 bootstrap 组装

```python
def bootstrap(
    config_path: str,
    model_backend_override: ModelBackend | None = None,
    event_sink_override: RuntimeEventSink | None = None,   # 新增
    run_id_override: str | None = None,                    # 新增：评估运行器预生成 run_id
    weather_provider_override: object | None = None,       # 新增（16 §5.3）：测试注入脚本化天气替身，零真实网络
) -> App:
```

- `event_sink_override` 非 None → 直接使用（CLI / 场景运行器入口）。
- `run_id_override` 非 None → App 以该值为 run_id（产物命名与 App 事件同一来源）；缺省 App 自生成 uuid4 短码。
- `weather_provider_override` 非 None → 天气工具的 handler 用该替身（`16` §5.3 的**替换性验收**：W1–W10 零真实网络）；缺省按 `[tools.weather].provider` 构造（`open_meteo` / `none`）。该 override 与 `cloud_*` 的现状同法——**测试接缝，CLI 入口不传**。
- 否则按配置：`event_jsonl_path` 为空 → `NoopEventSink`；非空 → `JsonlEventSink(path)`。
- `create_tool_backend` / `create_safety_backend`（rule_only）从 `[tools]` 接收 workspace_root；工厂签名内部扩展，外部形态不变。
- CLI 入口组合：`CompositeEventSink(CliEventSink(trace_on=False), JsonlEventSink(如配置))` 作为 override 传入——CLI 与 JSONL 消费互不依赖。

---

## 8. 工程与验收

### 8.1 单元测试矩阵（要点）

- **事件流**：逐 stage 键集封闭断言（§2.2 逐表）；seq 单调且顺序约束（§3.3）；status/detail 划分正确；**JSONL 落盘分级**（含路径/用户名的 topic_label 与 project_id 在 JSONL 行中仅以 run 内随机别名出现，终端与 last_turn_report 显示原文；同值同别名、跨 run 别名不同；intent_type/reason 整键不落盘；missing_info 以计数出现；白名单外键零落盘）。
- **生命周期**：session_ended 的 turn_id 为 None；异常兜底轮产生 `turn_completed(completion="error", error_code)`；每次 handle() 调用恰好一条终结事件（§3.6 四类）。
- **禁入清单**：输入含 `api_key=sk-…` → 全部事件 data 无原值；口令确认轮事件无口令/确认原文；云端轮事件无 analysis/followup 原文、无 fingerprint/grant 字段；事件不含用户输入原文、chunk 原文、prompt。
- **消毒**：missing_info/intent_type/reason 消毒+截断；幂等。
- **旁路**：sink.emit 抛异常 → handle 正常返回回复；Composite 单成员失败不影响其余；Noop 默认下现有全部测试零回归。
- **Core 不打印**：capsys 断言核心路径 stdout 为空。
- **命令层**：自有 7 命令逐条（/switch 无参、/trace 非法值）；switch 归一化；**透传**——`/cloud allow|cancel|deny|ask|off` 与未知 `/xxx` 均 handled=False 且 handle() 收到原文（P4 授权流在 CLI 下可用，P4 既有测试不回归）；命令层纯函数可独立直测。
- **loop**：EOF = quit；/quit 触发 end_session（tracker 清理 + 会话摘要覆盖 + session_ended 事件）；UTF-8 reconfigure。
- **CliEventSink**：trace off 只显示 status 行且格式符合 §4.4；trace on 追加 detail 行；切换即时生效。
- **file.write**：**新建与覆盖都进确认链**（2026-09-20 反转后；新建：`requires_confirmation=true`、确认成功才写、未确认不写；覆盖：同上且确认文案含「覆盖」）；确认失败一律拒绝且不写；逃逸矩阵（`../`、绝对路径、`C:\`、UNC、前缀相似目录）双层都被拒；中文内容 UTF-8 往返；超限；缺参数；返回值不含 content；ExecutionRecord 与事件流无 content 原值；确认后执行的 AuditEvent `risk_level="sensitive"`（由 execute 同源复评保证，§6.3），覆盖场景 reason 含 target_exists、新建场景 reason 为 None 或注册表基线值（**两者都不得出现 `risk_level="normal"`**——这是反转的回归断言）；**SafetyPolicy 可见性**——execute 期间后端升险的 step 传给 `safety_policy.check` 的 risk_level 为 sensitive。
- **preflight**：无副作用断言（调用前后文件系统、审计、pending 状态不变）；normal/sensitive/dangerous 三档与 App 分支（直接执行 / 进确认 / 拒绝）一致；**组件边界**——`BuiltinToolBackend.preflight` 对 file.write 的动态评估单测（**2026-09-20 反转后**：存在→sensitive+target_exists/target_key，**不存在→sensitive**（注册表基线）**且 target_exists=False**，逃逸→dangerous）；执行器配自定义 ToolBackend（preflight 返回定制报告）→ 升险照常生效，证明无 file 特判；preflight 拒绝（dangerous/未注册）→ `record_denial` 审计出现且无执行。
- **TOCTOU**：确认后、执行前目标被删除 → App 复检不一致 → 拒绝 target_state_changed 并经 record_denial 留痕；确认时目标不存在、执行前被外部创建 → 拒绝；两方向均不执行写入。（2026-09-20 后 `file.write` 两方向都发生在**确认之后**——「新建放行」这一支已不存在）
- **快照接口**：status_snapshot / last_turn_report / topics_snapshot / list_projects 只读性（调用前后 App 状态与存储不变）；last_turn_report 在无轮次时为 None；topics_history 会话隔离。

### 8.2 端到端场景（tests/test_p6a_scenarios.py，mock 模型驱动，全部自动化）

| # | 场景 | 断言要点 |
|---|---|---|
| A1 | 交互全链 | 多轮理解 → dispatch → file.write **新建（2026-09-20 后同样经确认，A1 需含一次确认口令轮）** → /why /status /projects /topics 全部可用且字段正确 |
| A2 | 覆盖确认链 | 同路径二次写入 → 确认提示含「覆盖」→ 口令成功执行；失败轮拒绝且无新 episode。**（A1 与 A2 的确认文案必须可区分：一个「新建」、一个「覆盖」——这是 P7a-0 后 `target_exists` 仅存的两项用途之一）** |
| A3 | 事件完整回合 | 一轮含 topic_decision…turn_completed 全序列，顺序与键集正确 |
| A4 | 禁入端到端 | 含秘密输入 + 云端轮 + 工具轮的组合回合，全事件流无任何禁入原值 |
| A5 | /switch 生效 | /switch B 后下一轮 episode/检索归属 B（走 P5 显式解析路径） |
| A6 | 降级可见（2026-09-15 P6d 修订） | 检索层委派失败（mock `retrieve()` 返回 `Result.err`）→ `degradation(memory_retrieval→none)` 事件出现且回复正常；**假信号回归**：零命中、embedding 未配置、`vec_enabled=False` 三者各自**均不得**产生任何 `degradation` 事件 |

### 8.3 性能（参考值）

NoopEventSink 单次 emit 开销可忽略（<10µs 量级即可，不做硬指标）；JsonlEventSink 同步追加，单事件写入不设缓冲上限，异常即吞并。

---

## 9. 00-* 工程契约同步清单（Codex 实施）

| 契约 | 同步内容 |
|---|---|
| `00-core-interfaces.md` | 新增 `RuntimeEventSink` ABC（§1.2）；`ToolBackend` 增 `preflight(tool_name, params) -> PreflightReport`（默认静态实现，动态后端覆写）；实现清单表加 4 个 sink；接口计数 6→8（+EmbeddingBackend+RuntimeEventSink） |
| `00-adapter-factory.md` | `bootstrap()` 签名增 `event_sink_override`、`run_id_override`；App 参数表增 event_sink/run_id；工厂向 tool/safety 后端传 workspace_root；Core 数据结构区补 `RuntimeEvent` / `RoundTrace` / `RetrievalStats` / `PreflightReport` |
| `00-error-contract.md` | 新增错误码 `FILE_ERROR`（recoverable=true，user_message「文件操作被拒绝：路径必须位于工作区内。」；逃逸/超限/类型错误共用，details.reason 区分：workspace_escape / target_exists / target_state_changed） |

---

## 10. 决策表

| 日期 | 裁决 | 理由 |
|---|---|---|
| 2026-09-10 | App 是唯一 emit 者；子模块以只读快照暴露数据 | 事件顺序天然正确、禁入过滤单点执行、子模块零 sink 依赖（铁律 6）；侵入面最小 |
| 2026-09-10 | 斜杠命令在 CLI 层拦截，命令处理独立成可复用命令层 | `/xxx` 若进 handle() 会被意图解析/话题跟踪/记忆当成用户输入污染（P0a 分支表 + P5 路由）；命令层独立是 FR9 场景运行器复用的前提 |
| 2026-09-10 | /switch 只改 CLI 绑定，下一轮经显式 project_id 走 P5 解析路径 | 复用 P5 归一化与解析语义，不新造项目切换机制；/switch 自身不产生事件不触发 handle |
| 2026-09-10 | 事件 data 字段封闭集 + 消毒双保险 | 封闭集防未来新字段绕过禁入清单；消毒兜住模型输出的自由文本槽位 |
| 2026-09-10 | 覆盖确认实现为 SafetyVerdict 风险维度通用机制（max 三源） | 不把工具语义泄漏进 executor 特判；未来其他工具的条件风险可复用同通道 |
| 2026-09-10 | file.write 新建 normal、覆盖 sensitive | 老板拍板（2026-09-10）：路径受工作区硬约束、新建破坏面小，试用体验优先；覆盖有破坏性必须确认 |
| **2026-09-20** | **反转上一行（P7a-0）：file.write 注册表基线 `normal → sensitive`，`requires_confirmation` 恒真，新建与覆盖都进确认链** | **老板拍板（2026-09-20）**：上一行的前提「写操作只可能由一次**确定性**的意图落下来」在 P7a 后不再成立——`capability` 的选择是**模型给的概率判断**（`16` §2 的相关性只约束「哪些工具能进提示词」，不约束模型一定选对），即允许一次错误的能力/工具选择**在无确认的情况下改变文件系统**，不适合作为基础 Agent 的默认行为。采用**独立前置变更 P7a-0**、不并入 P7a 能力层批次，是为了让 `16` §9.1 第 4 条的「关态/开态」对比可归因（见 `clarifications.md` 拍板登记）。**代价**：翻转后必须重测 P6 基线（「关态 = 基线」的锚点值随之改变） |
| 2026-09-10 | trace 开关是 CLI 显示侧状态 | Core 不关心谁在听、听到什么级别（铁律 5）；JSONL 记录与 trace 无关，评估数据始终全量 |
| 2026-09-10 | 事件不带 chunk/query/工具结果原文 | trace 的「详细」以元数据为界；原文外泄风险一旦放进事件流即难回收，与 P4/P5 禁入清单同源 |
| 2026-09-10 | bootstrap 增 event_sink_override 而非 CLI 反向注入 App | 保持 bootstrap 单向组装；CLI 与场景运行器都是「入口组装者」，Core 不知道入口形态 |
| 2026-09-10 | handle() 签名不变、事件走旁路 | 既有 270 测试与全部调用方零改动；事件失败语义与 _record_turn 一致 |
| 2026-09-10 | 外部审查修订 4 项：① 命令层仅拦自有 7 命令，其余 `/` 行（含 P4 /cloud 指令）原样透传 handle()；② 新增 executor.preflight 无副作用评估，App 据此建立确认链；③ 事件文本槽位分级——JSONL 只落枚举/计数/布尔与 run 内随机别名，用户派生文本（topic/project/intent_type/reason）不落盘，终端与 /why 保留原文；④ turn_id 允许 None（仅 session_ended），turn_completed 增 completion 状态，异常兜底轮也产生终结事件 | 四条均为实现审查发现的真问题：① `/cloud allow|cancel|deny|ask|off` 均以 `/` 开头，全拦即云端授权链失效；② App 在 execute 前凭静态风险建 pending（main.py 确认分支），执行器内事后升险赶不上确认状态建立；③ topic_label 由用户输入派生，正则消毒对任意文本不构成安全保证，持久化必须靠结构分级；④ session_ended 在 handle 之外、异常轮无意图结论，字段需允许缺省而非伪造 |
| 2026-09-10 | 二轮审查修订：低熵文本改 run 内随机别名，弃确定性哈希 | 截断 sha256 对项目名/话题名这类低熵文本可被字典枚举反推，不构成「不可逆匿名」；run 内随机别名保住同 run 聚合能力、杀死跨 run 关联与枚举攻击面；跨 run 关联本就是评估运行器的职责（run_meta 已含 scenario/variant），不值得为此引入本地 HMAC 秘密管理。intent_type（模型自由文本）与 reason（规则层模板串）同为可枚举低熵文本，整键不落盘 |
| 2026-09-10 | 二轮审查修订：动态评估下沉为 ToolBackend 统一 preflight 能力；preflight 拒绝统一走 record_denial 审计 | executor 特判 file.write 会让安全执行器依赖具体工具实现，破坏 P7（MCP 等工具后端）即插即用；标准化 PreflightReport 让执行器只做消费。preflight 拒绝若不留痕，被安全层拦截的尝试就绕过了审计——record_denial 是既有公开方法，复用即可 |
| 2026-09-10 | 二轮审查修订：JsonlEventSink envelope 钉死 `{"v":1,"type":"runtime_event","event":{…}}`；/topics 明确仅本会话；degradation 枚举收窄为 embedding\\|cloud | envelope 是 08 场景运行器的解析契约，两契约必须同一格式；/topics 只看本次会话是现状边界（项目历史话题查询留待按需扩展）；当前实现无模型级降级机制，Ollama 失败走 MODEL_ERROR，"ollama" 枚举值是虚构 |
| 2026-09-10 | 三轮审查修订：execute() 逐 step 复评 tool_backend.preflight() 并以动态结果替换有效风险 | PreflightReport 只是计划级聚合，原 execute 只结合模型值与注册表静态值——动态升险到不了 SafetyPolicy 与 AuditEvent，契约声称的「确认后审计 risk_level=sensitive」无法保证。execute 内复评是改动最小、且保持执行器零工具语义的闭环方案：App 快照比对管「存在→消失」，execute 复评管「不存在→出现」与审计真实性（max 语义只升不降） |
| 2026-09-10 | 三轮审查修订：bootstrap() 增 `run_id_override` | P6b 运行器必须在 bootstrap 之前用 run_id 创建临时目录、JSONL 文件名与子进程参数，而 App 原来自生成 run_id——产物与事件必然两套 id。显式注入让 App.run_id 与评估产物同源、可测试 |
| 2026-09-13 | P6c 增补：`cloud_consult.denied_reason` 封闭集扩展云端失败类四值（auth / endpoint / rate_limited / unavailable），App 按错误码映射（09 §6.2） | 原 `unavailable` 把 401 凭据错配与网络故障混为一谈（GLM Key 错配事件的教训）；评估记录需可辨因。字段封闭集与禁入清单不变，无新采集面 |
| 2026-09-16 | `intent_final` 增 2 键（`risk_draft` `risk_draft_resolution`，均为受限枚举） | 依据 `12-risk-draft-closed-set.md` §3.3：本次 bug（S06/S08/S10/S13 的 `/cloud ask` 被判 `non_normal_risk`）在旧 JSONL 里**只留下否决原因一个面**——看不出模型写了什么值、是闭集内还是乱写。归一化后的 `risk_draft`（闭集三值）与 `risk_draft_resolution`（`declared`/`mapped_legacy`/`absent`/`unrecognized` 四值）回答「模型是不是在乱写、有没有漏字段」，报告分布据此判断非法措辞是否复发。**模型原始字符串不落盘**（自由文本，禁入清单不变）—— 故 `unrecognized` 时只有事实、无原话，与既有无原文采集面一致 |
| 2026-09-15 | P6d 修订：`intent_round` 增 `new_memories`；`intent_final` 增 6 键（`proposal_present` `should_consult` `expected_benefit` `escalation_reason` `no_progress_detected` `stopped_early`）；`dispatch_decision` 增 2 键（`proposal_gate_result` `proposal_denied_reason`）；`degradation` 枚举增 `memory_retrieval→none`；`degraded` 语义收窄为「检索层显式失败」 | 依据 10-p6d：① 事件必须能回答「为什么上云/为什么没上云」（模型侧事实落 `intent_final`，规则侧落 `dispatch_decision`，按**产生者**分工，**不新增 stage**）；② `new_memories` 是零增量提前停止的直接证据，缺它无法区分「零增量」与「检索没跑」；③ 新增 9 键**全部是结构化值或受限枚举**，无原文采集面——禁入清单（`proposed_question` / `candidate_context` / `missing_info` 原文 / 任务原文 / Key）不变；④ `degraded` 旧判定把「零向量命中」谎报成「embedding 故障」，S06/S09 全程假信号，改为只在检索层委派失败时为 True，`embedding→keyword_only` 因接口限制本轮无生产者（10-p6d §5.4 延期恢复） |
| 2026-09-18 | `intent_final` 增 4 键（`tool_intent` `tool_call_resolution` `tool_intent_conflict`，均受限枚举/bool；`suggested_tools_count`，int ≥ 0 计数）；`turn_completed` 增 1 键（`reply_provenance`，三值闭集）；`dispatch_decision.reason` 取值域增 7 值（含 `tool_call_invalid_shape`） | 依据 `15-tool-orchestration-hardening.md` §8：S14 四次真实 run 暴露「工具调用未建立却出完成性回复」；前 3 键是编排链路的证据面，`reply_provenance` 是「完成性陈述可溯源」的判定标签。`suggested_tools_count` 是「迁移期 `tool_call_present` vs `suggested_tools_present` 对比」的**唯一载体**——`suggested_tools` 原文此前不进任何事件，缺此键则 `15 §2.5` 的退役条件不可判定；它是**计数不是内容**，与 `intent_round` 的 `missing_info`/`new_memories` 同法。另：`dispatch_decision` 的准入否决 reason 由 `suggested_tools_present` 改名 `local_action_proposed`（判定源改为 `tool_intent`） |
| 2026-09-18 | §6.2b 新增：读取 / 列目录 / 写入统一工作区边界与 `FILE_ERROR` reason 闭集扩展 | 依据 `15` §6：原双重校验只覆盖 `file.write`，另两条路径直接构造 `Path`，边界不一致 |
| 2026-09-17 | `intent_final` 增 1 键（`resolution_exhausted`，bool；键数 13→14） | 依据 `14-resolution-exhausted.md` §6：本次 bug（S03 `round1` 走满唯一一轮却返回 `RETRIEVE_MORE`）在旧 JSONL 里**完全不可见**——`rounds_used` 只说明跑了几轮，看不出「上限已到」，`no_progress_detected=false` 也无法区分「还有轮次」与「就是最后一轮」。该事实由 `IntentResolver` 在循环自然出口确定，与既有 `no_progress_detected` / `stopped_early` **同源同类**，按本文件「按产生者分工」原则落在同一 stage；**不新增 stage**、`dispatch_decision` 与 `turn_completed` **键集不变**（决策侧由 `NextAction.reason="resolution_exhausted"` 可区分，该字段按既有规则不落盘）。**报告必须与 `no_progress_detected` 分列**：前者是预算侧事实、后者是模型侧停滞事实，合并会让模型停滞率虚高 |
| 2026-09-18 | `cloud_consult.denied_reason` 封闭集新增 `sensitive_policy_grant_forbidden`（本地否决类） | 来源：`12` §3.4 / `05` §3.2——冗余防线（`AuthorizationManager` 拒绝签发非 `normal` 的 policy grant）被触发时的标记，正常实现计数恒 0，报告只能读作「接线缺陷计数」。只在既有 `phase="denied"` 上出现，**不新增 stage / data key / 错误码**，**不写 `CloudAuditEvent`、不计入 `record_denial()`**（后者四值闭集与「恰一条 / 终止语义」不变量不变），字段封闭集与禁入清单不变 |
| 2026-09-20 | **P7a（`16`）**：`intent_final` 增 2 键（`capability_id` 受限枚举、`capability_resolution` 五值闭集）；`tool_call_resolution` 增 2 值（`irrelevant_tool` / `unrouted_tool`）；`dispatch_decision.reason` 工具相关闭集 7→10 值（`capability_unavailable` / `capability_irrelevant` / `capability_unrouted`）；`proposal_gate_result` 的 `not_evaluated` **来源 2→3**（新增「能力终端性失败早裁」，值域不变）；`degradation` 补「工具失败不是降级」的边界 | 来源：老板真实试用（「今天南京市天气怎么样」被连续三轮追问 `location`；补地点后调用 `system.echo`）。两个键与 `risk_draft`/`risk_draft_resolution` 同法：`capability_id` 回答「选了哪个能力」、`capability_resolution` 回答「这个选择是什么性质」，**归因面与值面分离**；`irrelevant_tool` 与 `unknown_tool` **不得合并**（前者「存在但不服务所选能力」，后者「名字不存在」）。`not_evaluated` 的来源扩展是**唯一**改动既有枚举语义的一处（值域不变、只扩来源），**必须**与 `10` §4.3 同步，否则观测面会把能力早裁记成 dangerous 或记成 `admitted`。**不新增 stage、不新增错误码** |
| 2026-09-20 | **P7a 复审联动（Codex 5 条阻塞 + 2 项小修，契约侧裁决见 `16` §12）**——本节**只改一处语义、不加任何采集面**：`turn_completed.rounds_used` 的**取值范围明确含 0**（`16` §4.4 的缺参续接回合零模型调用；P6 基线实现下该值恒 ≥ 1，`sinks.py` 与报告侧**不得**把它当「必然 ≥ 1」处理）。**不加 stage、不加 key、不加错误码**：出站值内容级校验的拒绝（`location_rejected`）是 `TOOL_EXEC_ERROR` 的 `details.reason`（`16` §5.4，八值闭集），在本节的观测面上**只表现为** `tool_execution` 既有的 `outcome != "allowed"` + `error_code`，**不得**为它发 `degradation`（工具失败不是系统降级，与本节既有边界一致）；**`reply_provenance` 三值闭集不变**（续接回合仍须溯源，失败即 `unfulfilled`） | 复审结论：这两处若不写明，报告侧的两个默认假设会失真——①「`rounds_used ≥ 1`」会让零模型调用回合被读成异常（或计数被吞）；②把「出站被拒」记成降级会重演 `10` §5.4 的假信号（`16` §8.1 同一禁令）。**判定依据仍是既有字段**，故无需新增采集面 |
| 2026-09-20 | **P7a 二轮复审联动（Codex 3 条阻塞 + 3 项小修，契约侧裁决见 `16` §12 末六行）**——本节**只扩两个既有枚举的值域**：`dispatch_decision.reason` 工具相关闭集 **10 → 11**（+`param_not_from_input`）、`intent_final.tool_call_resolution` **+1 值**（+`param_not_from_input`）；**不加 stage、不加 key、不加错误码**。**值域区分照实写明**：`param_not_from_input`（准入级拒绝，**没有** `tool_execution`）与执行级 `TOOL_EXEC_ERROR.details.reason="location_rejected"`（**恰一条** `tool_execution` 且 `outcome != "allowed"`）**同名不同层**，报告据「有无该事件」区分，**不得**靠解析字符串。另有一条**不落在本节**的接口变更已在 `16` 钉死：`ToolDef` +2 可选字段（`audit_redact_all_params` / `supply_by_echo`），两者**不进任何事件、不进渲染、不进持久层**（`render_tool_catalog()` 的白名单源码级排除）| 依据：`16` §6.3 第 4 条把出站值校验按「是否需要用户原文」切成准入级（解析层）与执行级（handler）两级——执行期拿不到原文（`ToolContext` 无该字段），故来源层只能在解析层；两级各有唯一生产者，观测面靠事件有无区分，无需新增字段 |
| 2026-09-23 | **P7a 第三轮修订（`16` §0.5）**：`intent_final` **+1 键**（`param_instance_rejected`，参数名 tuple）；**不加 stage、不加错误码、不改任何既有枚举的值域与来源** | 来源：S18 真实 run——模型把用户**整句**填进天气工具的地点参数，**来源级与执行级两道校验都放行**（该串确实是用户原话、也确实能作为字符串发出）⇒ 整句外发、工具失败，应有的「追问缺参」从未发生；加固提示词无效。本键是「参数在、但值不是有效实例」这一格的**唯一可分辨面**（与「模型不省略参数」同结构签名，区别只在这里）。**开态恒出现（空元组也必须落盘）、关态整键不出现**；它是**逐回合事实**，补参续接轮必须重算（带上轮的值会误报并自我触发 `16` §8.3 硬性行）。`16` §6.3 的两级表述此后以**三级**为准，但本节的观测面**不因此扩值**：实例级拒绝走既有 `param_missing`，无新码值 |
