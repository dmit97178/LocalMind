# 00-core-interfaces — 核心接口契约

> 状态：✅ 待实现
> 性质：编码前必读。所有 Core 模块只能依赖此文档定义的接口。
> Core 代码中不得出现 `import ollama` / `import qwenpaw` / `import everos`。

---

## 1. ModelBackend

```python
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Protocol

class ModelCapabilities:
    """每个 Adapter 在 load() 后填充，Core 据此调整策略。v1 字段允许后续扩展。"""
    supports_structured_output: bool      # JSON schema 约束
    max_context_tokens: int               # 模型最大上下文窗口
    local_only: bool                      # 纯本地推理 vs 依赖外部 API

class ModelBackend(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        response_schema: Optional[dict] = None,
    ) -> dict:
        """
        同步生成。

        - 传入 response_schema 时：返回符合该 JSON Schema 的 dict（结构化输出）。
        - 不传 response_schema 时：返回 {"text": str}——text 字段包含模型生成的完整文本。
        - 失败抛 ModelError；recoverable 由具体错误码决定（见 00-error-contract.md）。
        """
        ...

    @abstractmethod
    def stream(self, prompt: str) -> Iterator[str]:
        """流式生成，用于 CLI 实时输出。"""
        ...

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        """返回当前模型的能力声明。必须在 load() 之后调用。"""
        ...

    @abstractmethod
    def load(self) -> None:
        """加载模型到内存。幂等。"""
        ...

    @abstractmethod
    def unload(self) -> None:
        """从内存卸载。幂等。"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """探测模型是否可用。失败不抛异常，返回 False。"""
        ...
```

**实现**：`MockModelBackend` / `OllamaModelBackend` / 未来 `TurboLLMBackend`

---

## 2. MemoryBackend

```python
from typing import List, Optional, Protocol, Sequence

class MemoryChunk:
    id: str
    text: str
    metadata: dict          # { topic, timestamp, session_id, project_id?, referenced_topic?, ... }
    similarity_score: float       # P5 起为 [0, 1] 的融合分
    vector_score: float | None    # 仅向量侧命中时可用
    match_source: str             # "keyword" | "vector" | "both"

class ProjectRecordStore(Protocol):
    """ProjectStore 使用的低层持久化原语；不承载业务规则。"""

    def get_project_record(self, project_id: str) -> dict | None: ...
    def put_project_record(self, record: dict) -> None: ...
    def list_project_ids(self) -> list[str]: ...


class MemoryBackend(ABC):
    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        max_bytes: int | None = None,
        topic_hints: Sequence[str] = (),
        project_id: str | None = None,
    ) -> "Result[List[MemoryChunk]]":
        """
        语义 + 关键词混合检索。
        失败或参数非法时返回 Result.err(LocalMindError(code="MEMORY_ERROR", ...))，不抛异常。
        未命中时返回 Result.ok([])。project_id 是归一化后的当前项目：None 时只检索
        未归属池；topic_hints 非空时允许全库定向检索，但候选必须命中 hint。
        max_bytes 为 None 时使用后端 retrieval.max_context_bytes 配置。
        """
        ...

    @abstractmethod
    def store_episode(self, content: str, metadata: dict) -> str:
        """
        存储一个对话片段，返回 chunk_id。metadata 需包含 topic 和 session_id。
        content 为空、metadata 缺必需字段、存储失败时抛 LocalMindError(code="MEMORY_ERROR", ...)。
        实现必须在写入和 embedding 前消毒全部文本；原始工具结果不得作为 content 写入。
        """
        ...

    @abstractmethod
    def get_summary(self, scope: str, scope_id: str) -> Optional[dict]:
        """
        获取指定范围的摘要。
        scope = "conversation" → scope_id = conversation_id
        scope = "project"       → scope_id = project_id
        未命中返回 None；读取失败时抛 LocalMindError(code="MEMORY_ERROR", ...)。
        """
        ...

    @abstractmethod
    def save_summary(self, scope: str, scope_id: str, summary: dict) -> None:
        """
        保存指定范围的摘要。幂等——同 scope + scope_id 覆盖旧值。
        summary 格式由调用方决定，建议至少包含 {"title": str, "summary": str, "last_updated": str}。
        scope/scope_id/summary 非法或写入失败时抛 LocalMindError(code="MEMORY_ERROR", ...)。
        实现必须在持久化前消毒全部文本字段。
        """
        ...

    @abstractmethod
    def detect_topic_relation(
        self, current_input: str, current_topic: str
    ) -> str:
        """
        返回: "same_topic" | "new_topic" | "shift_with_reference" | "ambiguous"
        """
        ...
```

**实现**：`InMemoryMemoryBackend` / `SQLiteMemoryBackend` / 未来 `EverOSAdapter`。
P5 起两个内置 MemoryBackend 必须同时实现 `ProjectRecordStore`，以支持 bootstrap
将同一持久化后端注入 ProjectStore；未来替代后端若不支持该 Protocol，不得进入 P5 bootstrap。

### EmbeddingBackend（P5）

```python
class EmbeddingBackend(ABC):
    """本地文本向量化边界；实现不得向非 loopback 端点发送文本。"""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> "Result[list[list[float]]]": ...

    @abstractmethod
    def embed_query(self, text: str) -> "Result[list[float]]": ...

    @abstractmethod
    def dimensions(self) -> int:
        """返回向量维度；0 表示当前不可用，调用方降级为关键词检索。"""
        ...

    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def health_check(self) -> bool: ...
```

Embedding 失败以 `Result.err(LocalMindError(code="EMBEDDING_ERROR", recoverable=True))`
返回；MemoryBackend 必须吞并该旁路失败并继续关键词检索。向量索引是 memory adapter 内部细节，
不得出现在 Core 可见签名中。

P5 共享 schema 同步项：`MinimalContext.project_id: str | None` 保存归一化项目 ID，
供 IntentResolver 的后续检索原样透传；`ProjectState` 与 `TopicDecision` 是 Core 数据结构，
不得包含 SQLite 或向量索引类型。

---

## 3. ToolBackend

```python
from collections.abc import Callable, Mapping
from dataclasses import field
from typing import List

class ParamInstanceCheck:
    predicate: Callable[[str], bool]
    reject_whole_input: bool = False

class ToolDef:
    name: str
    description: str
    parameters: dict         # 15 §1.1 的浅层 JSON Schema 子集：type/properties/required
    risk_level: str          # "normal" | "sensitive" | "dangerous"
    approval_profile: str = "standard"   # 2026-09-16 新增（尾部 + 默认值，位置/关键字构造全兼容）
                             # "standard" | "high_impact"——该工具一旦执行、影响面不可由工作区边界
                             # 约束时声明为 "high_impact"。批准档见 13-approval-profile-high-impact.md
    supply_by_echo: tuple[str, ...] = ()
    audit_redact_all_params: bool = False
    param_instance_checks: Mapping[str, ParamInstanceCheck] = field(
        default_factory=dict,
        hash=False,
    )
                             # 工具作者声明的参数实例判据；不进入模型提示词
    egress: bool = False     # 2026-09-25 新增（17 §2.3，兑现 16 §11 第 22 项）
                             # **出站工具标记**：本工具的参数值会离开 Agent 进程
                             # （送交外部进程或网络）。语义刻意收窄：
                             #   离开**本进程** ⇒ True（子进程、socket 都算）
                             #   在本进程内被用作路径/键/索引 ⇒ False
                             #   ⇒ file.read/file.list_dir/file.write 均为 False；
                             #     weather.current 必须回填 True。
                             # 两条**通用**注册期不变式（对含内置在内的所有工具成立，
                             # fail-loud，17 §3）：
                             #   E11  egress ⇒ set(properties) ⊆ set(supply_by_echo)
                             #                ⊆ set(param_instance_checks)
                             #   E12  egress ⇒ audit_redact_all_params=True
                             # 外部工具（17）的 egress 由准入管道**强制**为 True，
                             # 不由作者填写（准入记录里没有这个字段）。
                             # **不进入模型提示词**（渲染白名单排除，与
                             # audit_redact_all_params 同处断言，16 §9.4 C15 ⓐ 适用）
    result_delivery: str = "deterministic"
                             # 2026-09-27 新增（18 §1.3，P7c 只读工具结果回流层）
                             # 闭集："deterministic" | "model_summary"
                             #   deterministic  —— 沿用现状：ResponseBuilder.build() 的产出即回复
                             #                     （**默认值**，既有工具行为逐字不变）
                             #   model_summary  —— 执行成功后由**本地模型**基于
                             #                     「本回合用户请求 + 有界工具结果」生成回复
                             # 判据必须是**注册期声明**，不得做成 App 主循环里的工具名特判
                             # （18 §1.3 / §12.1 N5：main.py 等运行期模块零工具名字面量）。
                             # 三条**通用**注册期不变式（fail-loud，
                             # CONFIG_ERROR / details.reason="result_delivery_invalid"）：
                             #   RD1  result_delivery ∈ {"deterministic", "model_summary"}
                             #   RD2  model_summary ⇒ tool ∉ LOCAL_SIDE_EFFECT_TOOLS
                             #        （写入类工具继续确定性结果 ⇒ 「让模型改写是否写入成功」
                             #          是**注册期不可达**，不是策略）
                             #   RD3  model_summary ⇒ egress == False
                             #        （回流把工具结果送进提示词；egress 工具的结果是外部来源
                             #          文本，回流会绕开 17 的「外部文本零进提示词」边界）
                             # ⇒ weather.current（egress=True）永久不进回流。
                             # **不进入模型提示词**（渲染白名单排除；本字段只被主循环读取，
                             # 与 egress / audit_redact_all_params 同处断言）

# ---------------------------------------------------------------------------
# 2026-09-27 第二处接口签名变更（18 §1.2）：ExecutionRecord 追加**尾部可选字段**
#
# @dataclass(frozen=True)
# class ExecutionRecord:
#     tool_name: str
#     verdict: str                    # allowed | denied
#     risk_level: str
#     outcome: str                    # success | failure
#     sanitized_summary: str
#     error_code: str | None = None
#     result_delivery: str | None = None   # ← 新增（追加式 + 默认值 ⇒ 既有构造调用零改动）
#                                          # 闭集（非 None）："model_summary" | "model_summary_failed"
#                                          # None ⇒ tool_execution 事件**不发**该键（条件键，07）
#                                          # 按 **step_index** 回填，不按工具名
#
# 载体必要性（老板阻塞项 2）：`_record_tool_events(records)` 只收记录列表，
# 若不把状态写在记录上，「回流已完成」这个事实**没有通道**到达事件层；且
# `_execution_records` 内有 `if not 0 <= step_index < len(plan.steps): continue`
# 的过滤 ⇒ **列表下标 ≠ step_index**，用 enumerate 对齐是隐式假设。
# 同一计划可多次调用同名工具，按工具名关联会把两条记录写成同一状态。
# 契约全文与探针：18 §1.2 / §12.2 R14。
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 2026-09-27 新增 Core 类型（18 §1.2.1，老板第三轮阻塞点 2）：ReflowOutcome
#
# 回流组件的返回形态。**不是**对既有签名的修改（没有任何既有方法改签名），
# 而是把一个此前不存在的跨组件值写进 Core —— 因此同属 Claude 主导的接口面。
#
# 为什么必须是一个结构而不是一个 Mapping：
#   调用方（App 的两个 response.build 调用点）要的是**一句回复文本**，
#   而 `Mapping[int, str]` 只带「哪些 step 走了模型摘要」。前版把返回类型
#   写成 Mapping[int, str]，等于「回流算完了但没人拿到回复」——
#   调用方只能要么自己再拼一次文本（两处逻辑分叉），要么丢弃模型输出。
#
# 三态口径（钉死，18 §1.2.1）：
#   ① 无可回流 step ⇒ display **逐字节等于** ResponseBuilder 的 output.display，
#                     deliveries == {}（此时回流是纯函数式的空操作）
#   ② 成功         ⇒ display = 模型输出，已过 sanitize_display_text() 且截到
#                     DISPLAY_LIMIT；deliveries[step_index] == "model_summary"
#   ③ 失败回落     ⇒ display **同样是实参 fallback_display**（与①逐字节相同！），
#                     deliveries[step_index] == "model_summary_failed"。
#                     **同一个结构** ⇒ 调用点零分支；**①与③只由 deliveries 区分**。
#
# 由此，两个调用点的形态统一为（不得有 if reflow_succeeded 这类分支）：
#   outcome = self._reflow(plan, results, original_request, fallback_display=output.display)
#   ...
#   return outcome.display
#
# 生产者在 src/core/result_reflow.py（18 §1.2.4，**2026-09-27 第五轮钉死**）：
#   ResultReflow(backend, tool_defs, enabled=True, max_chars=4000)
#     - tool_defs = tool_backend.list_tools()，**构造期冻结**成 name -> result_delivery
#       （ExecutionStep 没有该字段、声明在 ToolDef 级 ⇒ 只能由目录提供判据；
#        查不到的工具名按 deterministic 处理，不抛错，该分支不可达）
#     - 只读 result_delivery 这一个字段：准入与风控由注册期与执行器负责，
#       回流层再判一次就会成为第二份准入真源
#   __call__(plan, results, original_request, fallback_display) -> ReflowOutcome
#     - fallback_display 是**本回合数据**（output.display），必须调用时传入：
#       "无可回流"与"失败回落"两态都要**逐字节保留**它，回流层**永不自己合成**回落文本
#       （否则就是第二份确定性显示实现，两条路径输出会分叉）
#     - 关态（App._reflow 为 None，或 enabled=False）⇒ 返回
#       ReflowOutcome(display=fallback_display, deliveries={})，行为与①等价
#
# 契约全文、多 step 策略与探针：18 §1.2 / §1.2.1 / §1.2.2 / §1.2.4 / §12.2 R17–R18、R20–R21。
#
# 文件位置：代码落 **src/core/result_reflow.py**（与它的唯一生产者同处）。
# 本文件是**接口面文档**、不是逐文件清单——既有先例是 ExecutionRecord 记在这里
# 而代码落 src/core/schemas.py（18 §1.2 / 00-adapter-factory.md 的 ExecutionRecord 块）。
# ---------------------------------------------------------------------------
# @dataclass(frozen=True)
# class ReflowOutcome:
#     display: str                      # 用户可见的最终文本（已消毒、已按上限截断）
#     deliveries: Mapping[int, str]     # step_index -> "model_summary" | "model_summary_failed"
#                                       # 未参与回流的 step **不出现在映射里**

class ToolProvider(ABC):
    """动态工具来源的抽象（2026-09-25 新增，17 §2.2）。**Core 定义、零平台依赖**。

    只负责「此刻存在哪些工具」与「执行」两件事。刻意**没有**
    list_capabilities()，也没有任何风险/渲染相关方法——外部来源拿不到
    「声明能力」的入口（17 裁决 1 的结构化表达）。

    住 Core 的理由：它跨层（src/tools/ 的聚合后端消费、src/adapters/ 实现），
    否则 src/tools/ 会依赖 src/adapters/。与 ToolCapability 搬回 Core 同源。

    实现落 src/adapters/mcp_adapter.py（MCPStdioToolProvider，stdio only）。
    """

    provider_id: str

    @abstractmethod
    def handshake(self) -> "ProviderSnapshot":
        """建立连接并返回一次快照。v1 只调用一次（不重试、不热插拔、不自动重启）。"""
        ...

    @abstractmethod
    def execute(self, raw_name: str, params: Mapping[str, object]) -> "Result[dict]":
        """执行一个**已准入**的工具。raw_name 是服务端原始名，不是规范名。

        与 ToolBackend.execute 同纪律：只在唯一执行出口（GuardedToolExecutor）
        的调用链上被调用；参数值由聚合后端的**出站边**做过秘密检测与大小检查。
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接与子进程。**幂等，不得抛异常，不得留孤儿进程。**

        **2026-09-26 补全语义（17 §2.2，审查第 3/4 项的接口侧）**：
        （1）正常终止：关 stdin → terminate → 给一段宽限期；
        （2）宽限期到仍未退出 ⇒ **强杀 + 回收**（waitpid/join），不得留下孤儿；
        （3）对**从未握手成功**、**已崩溃**、**已因超时被终止过**的 provider 调用
            都必须安全（不抛、不挂）；
        （4）关闭过程自身的超时**不得向上抛异常**（与 ToolBackend.close 同纪律）。
        调用方是聚合后端的 close()，见下方 ToolBackend。
        """
        ...
class ToolBackend(ABC):
    """仅供 GuardedToolExecutor 内部调用。Core 不直接持有此接口的引用。"""

    @abstractmethod
    def list_tools(self) -> List[ToolDef]:
        """返回所有已注册工具的定义。"""
        ...

    @abstractmethod
    def execute(self, tool_name: str, params: dict) -> "Result[dict]":
        """执行工具。此方法只在 GuardedToolExecutor 内部调用。可降级操作。"""
        ...

    def preflight(self, tool_name: str, params: dict) -> "PreflightReport":
        """无副作用执行前评估（P6a 新增，默认实现，后端可覆写）。

        返回标准化 PreflightReport（schemas 定义）：effective_risk /
        requires_confirmation / target_exists / target_key / reason /
        approval_profile（2026-09-16 新增，签名不变）。
        有动态风险语义的后端（如 BuiltinToolBackend 的 file.write：目标已存在
        → 升 sensitive）覆写本方法。实现必须无副作用：不执行、不写文件、
        不改任何状态。GuardedToolExecutor 只消费此标准化结果，
        不感知具体工具语义。

        approval_profile 的闭集外值由 read_approval_profile() 兜底为
        "high_impact"（13 §2.4）；requires_confirmation 仍只由风险驱动，
        不得因 approval_profile 为真。"""
        # 默认实现：静态报告（复用自身注册表，零改动即可用于任何后端）
        registered = {t.name: t for t in self.list_tools()}
        if tool_name not in registered:
            raise ToolError(code="TOOL_NOT_FOUND", ...)
        tool = registered[tool_name]
        risk = tool.risk_level
        return PreflightReport(
            effective_risk=risk,
            requires_confirmation=risk in {"sensitive", "dangerous"},
            target_exists=None, target_key=None, reason=None,
            approval_profile=read_approval_profile(tool.approval_profile),
        )

    def close(self) -> None:
        """释放**进程级**资源（2026-09-26 新增，17 §2.4）。

        **幂等；不得抛异常**；默认实现 = 无资源可放（内置后端因此零改动）。
        聚合后端（CompositeToolBackend）覆写本方法并关闭其持有的全部
        ToolProvider。关闭之后 list_tools() 返回空、execute() 一律
        TOOL_NOT_FOUND（不是「继续工作」也不是「抛错」）。

        调用方是 App.shutdown()（新增方法），由 CLI / 评估运行器 /
        诊断脚本在 finally 中调用。**不得挂在 end_session() 上**：
        会话边界 ≠ 进程边界，否则会出现「另一会话仍在用的 provider 被关掉」
        与「从未开过会话的 provider 永不回收」两种缺陷。
        """
        return None
```

**实现**：`BuiltinToolBackend`（白名单本地工具；覆写 `preflight` 提供 file.write 动态评估；`close()` 用默认实现）/ `MCPToolBackend`（`ToolProvider` 聚合，覆写 `close()`；P7b）/ `QwenPawToolBackend`（P7 后续）/ 未来其他

> 2026-09-10：`preflight` 为接口签名变更（Claude 所有），随 P6a 落地；默认实现保证既有后端零改动即可工作。
>
> 2026-09-26：`ToolBackend.close()` 为**接口签名变更**（Claude 所有），随 P7b 落地（`17` §2.4）。这是 P7b 对
> 「三项零变更」的唯一一处必要推翻——外部来源会启动子进程，而 `ToolProvider.close()` 在原稿里**没有任何调用方**，
> 「不得留孤儿进程」因此写在了一个无法实现的设计上。`App` **构造签名**不变（新增的是方法 `shutdown()`）。

---

## 4. SafetyBackend

```python
class SafetyVerdict:
    allowed: bool
    risk_level: str          # "normal" | "sensitive" | "dangerous"
    reason: str              # 拒绝时必须给出原因

class SafetyBackend(ABC):
    @abstractmethod
    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        """
        判断单个操作是否危险。
        operation 必须包含字段: { tool_name, params, intent_type, entities }
        """
        ...
```

**实现**：`RuleOnlySafetyBackend` (P0) / `QwenPawSafetyBackend` (P3)

---

## 5. CloudAdvisoryBackend

P4 的请求包、候选建议、TaskBrief 和审计事件定义在 `src/core/schemas.py`；具体的
`AuthorizationGrant` 与 `GrantUsageSnapshot` 由 `src/safety/authorization.py`
实现。Core 只通过以下最小协议传递授权边界，不 import safety 的具体类。

```python
class CloudGrant(Protocol):
    """已授权云端请求的只读边界；实现由 safety 层提供。"""
    grant_id: str
    task_id: str
    session_id: str
    provider: str
    purpose: str

class CloudRequestPackage:
    task_id: str
    session_id: str
    provider: str
    purpose: str
    grant_id: str
    context_items: list[PreparedContextItem]
    allowed_scope: str
    turn: int

class AdvisoryResult:
    analysis: str                     # 分析结论
    suggested_tools: Optional[list]   # 可选，工具建议列表，仅作本地参考
    risks: list                       # 风险提示
    requires_local_validation: bool   # 始终为 True
    needs_more_info: bool             # 云端请求补充信息
    requested_context_categories: tuple[str, ...]
                                      # 仅可为 memory_evidence / user_entity；状态机唯一输入
    followup_question: str            # 不可信展示文本；不回传、不进 prompt、记忆或审计

class ConsultOutcome:
    status: str                       # "completed" | "suspended"
    result: AdvisoryResult | None     # completed 时的最终 advisory
    requested_categories: tuple[str, ...] = ()
                                      # suspended 时归一化后的白名单类别

class CloudAdvisoryBackend(ABC):
    @abstractmethod
    def advise(self, request: CloudRequestPackage) -> AdvisoryResult:
        """向云端请求建议。云端不能直接产生 ExecutionPlan。"""
        ...

class CloudTurnGateway(Protocol):
    """云端单轮副作用出口；Core 仅依赖该抽象。"""

    def execute_cloud_turn(
        self,
        package: CloudRequestPackage,
        grant: CloudGrant,
        task_id: str,
        intent_id: str,
        turn: int,
    ) -> AdvisoryResult:
        """执行出站检查、云端调用、入站检查和脱敏审计。"""
        ...

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        """记录一次无云端轮次的最小拒绝审计。"""
        ...
```

**实现**：`OpenAICompatibleAdvisoryBackend`（deepseek / glm / custom_openai
经 provider profile 复用）/ `NoopCloudAdvisoryBackend`；`SideEffectGateway` 实现
`CloudTurnGateway`。`CloudAdvisoryBackend.advise()` 只可由 `SideEffectGateway` 调用。

P4 的云端载荷可以包含经本地 `PrivacyPolicy` 脱敏且已被有限 grant 授权的
结构化 `context_items`。`fingerprint`、grant/task/session/provider/purpose/turn
等本地边界字段不得被 Adapter 序列化、记录或发往云端；秘密原值永不外发。
首轮 package 必须由 `PrivacyPolicy.build_package()` 生成。若云端请求产生新类别，
`CloudAdvisoryService` 返回 `ConsultOutcome(status="suspended")`，由 App
重新走 PrivacyPolicy、grant 与授权状态机；App 和模型不得自行构造 package。

---

## 6. EvolutionBackend

```python
from typing import List

class Experience:
    id: str
    task_type: str
    content: str             # 经验描述
    confidence: float        # 0.0-1.0
    status: str              # "draft" | "active" | "deprecated"

class Skill:
    id: str
    name: str
    trigger_condition: str
    steps: list
    status: str              # "draft" | "active" | "deprecated"
    maturity: dict           # { completeness, executability, evidence, clarity }

class EvolutionBackend(ABC):
    @abstractmethod
    def reflect(self, task_context: dict) -> List[Experience]:
        """从任务上下文中提取候选经验。v1 全部返回 draft 状态。"""
        ...

    @abstractmethod
    def get_skills(self, intent: str) -> List[Skill]:
        """检索与意图相关的已启用技能（仅 active 状态）。"""
        ...

    @abstractmethod
    def collect_experience(self, task: dict, outcome: str) -> None:
        """存储一次任务的结果，供后续 reflect() 聚合使用。"""
        ...
```

**实现**：`NoopEvolutionBackend` (v1) / 未来 `EverOSAdapter` / LoRA 训练管道

---

## 7. RuntimeEventSink（P6a）

```python
class RuntimeEventSink(ABC):
    @abstractmethod
    def emit(self, event: RuntimeEvent) -> None:
        """消费 App 已消毒的运行事件；实现失败不得影响主流程。"""
        ...
```

`RuntimeEvent`、`RoundTrace`、`RetrievalStats` 与 `PreflightReport` 定义在
`src/core/schemas.py`。App 是唯一事件生产者；Core 子模块只暴露只读快照，不持有 sink。

**2026-09-16 批准档字段新增（`13-approval-profile-high-impact.md` §4）**：`ToolDef` /
`PreflightReport` / `ExecutionStep` 三者**尾部**各新增 `approval_profile: str = "standard"`
（带默认值，既有位置构造与关键字构造全部兼容）。批准档是**执行步级**的确定性事实，
**模型侧无对应字段**——`IntentCandidate` 与 `_INTENT_RESPONSE_SCHEMA` 均不新增该键（机检见 13 §5.2 A7）。

P6d 起 `RoundTrace.new_memories` 记录本轮检索去重后的净增条数；
`RetrievalStats.degraded` 仅在 `MemoryBackend.retrieve()` 显式返回错误时为真，
零命中或返回结果没有 `vector_score` 不代表降级。

**实现**：`NoopEventSink` / `JsonlEventSink` / `CompositeEventSink` / `CliEventSink`。

---

## 实现清单

`src/core/risk_vocabulary.py` 是 `IntentCandidate.risk_draft` 闭集、旧词表映射和
解析归一化的唯一实现。任何新增的外部输入到 `IntentCandidate` 构造路径必须先调用
`normalize_risk_draft()`；Core 消费方不得维护第二份旧词表。

同模块提供 `effective_authorization_risk(causal_risk, *,
payload_candidates_sensitive=True, sensitive_execution_chain=True)`。它只合并模型风险下界、
实际 payload 分类和既有敏感执行链状态；两个确定性信号只能升险，缺参即按 sensitive。
工具计划、preflight 与 approval_profile 属本地执行链，不得接入该函数。

**（2026-09-16）同处新增批准档闭集与读取函数**：`APPROVAL_PROFILES = ("standard", "high_impact")`
与 `read_approval_profile(raw: object) -> str`（闭集外值一律兜底 `high_impact`，见
`13-approval-profile-high-impact.md` §2.4）。**接口义务**：任何新增的
`ExecutionStep.approval_profile` / `ToolDef.approval_profile` 构造路径（含 P7 的 MCP 等第三方工具后端）
必须先过 `read_approval_profile()`；消费方一律 `import` 同一函数，**不得**再手写
`in APPROVAL_PROFILES` / `.lower()` 判断（与 `read_risk()` 同一条「一条规则一份实现」义务）。

| 接口 | v1 实现（P0-P1） | 后续实现 |
|------|:---:|------|
| ModelBackend | `MockModelBackend` → `OllamaModelBackend` | `TurboLLMBackend` |
| MemoryBackend | `InMemoryMemoryBackend` → `SQLiteMemoryBackend` | `EverOSAdapter` |
| ToolBackend | `BuiltinToolBackend`（只含白名单本地工具，零外部依赖；`close()` 用默认实现） | `CompositeToolBackend`（P7b，聚合 `ToolProvider`，覆写 `close()`） → `QwenPawToolBackend`（P7 后续） |
| SafetyBackend | `RuleOnlySafetyBackend` | `QwenPawSafetyBackend` |
| CloudAdvisoryBackend | `NoopCloudAdvisoryBackend`（禁用态零外发）→ `OpenAICompatibleAdvisoryBackend`（deepseek / glm / custom_openai） | 非 OpenAI 兼容 provider 的专用适配器 |
| EvolutionBackend | `NoopEvolutionBackend` | `EverOSAdapter` / LoRA管道 |
| EmbeddingBackend | `OllamaEmbeddingBackend`；禁用时注入 `None` | 未来本地 embedding 后端 |
| RuntimeEventSink | `NoopEventSink` / `JsonlEventSink` / `CompositeEventSink` / `CliEventSink` | GUI / 评估消费者 |
