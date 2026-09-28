# 00-adapter-factory — 适配器工厂契约

> 状态：✅ 待实现
> 性质：编码前必读。定义 Adapter 的创建、配置、生命周期规范。
> Core 不 import 具体后端，不手动 new 具体实现。

---

## 1. 工厂签名

```python
from typing import Protocol

class AdapterFactory(Protocol):
    """每个 Adapter 必须提供此工厂函数。"""

    def __call__(self, config: dict) -> object:
        """
        输入：config dict（来自 config/default.toml 的对应 section）
        输出：实现了对应接口的具体 Adapter 实例
        失败：抛 LocalMindError(code="CONFIG_ERROR", ...)
        """
        ...
```

每类接口对应一个工厂函数，集中在 `main.py` 初始化阶段调用：

```python
# main.py 示例
def create_model_backend(config: dict) -> ModelBackend:
    backend_type = config["model_backend"]["type"]
    if backend_type == "mock":
        from src.models.mock_backend import MockModelBackend
        return MockModelBackend()
    elif backend_type == "ollama":
        from src.models.ollama_backend import OllamaModelBackend
        return OllamaModelBackend(config["model_backend"]["config"])
    else:
        raise LocalMindError(code="CONFIG_ERROR", ...)

def create_safety_backend(config: dict) -> SafetyBackend:
    backend_type = config.get("safety", {}).get("backend", "rule_only")
    if backend_type == "rule_only":
        from src.safety.rule_only_backend import RuleOnlySafetyBackend
        return RuleOnlySafetyBackend(config.get("safety", {}))
    elif backend_type == "qwenpaw":
        from src.adapters.qwenpaw_adapter import QwenPawSafetyBackend
        return QwenPawSafetyBackend(config.get("safety", {}))
    else:
        raise LocalMindError(code="CONFIG_ERROR", ...)

def create_cloud_advisory_backend(config: dict) -> CloudAdvisoryBackend:
    settings = normalize_cloud_advisory_config(config["cloud_advisory"])
    profile = CloudProviderRegistry.resolve(settings["provider"])
    validate_cloud_connection(settings, profile)
    if not settings["enabled"]:
        return NoopCloudAdvisoryBackend()
    credential_loader = EnvCredentialLoader()
    if not credential_loader.exists(profile):
        raise LocalMindError(code="CONFIG_ERROR", recoverable=False, ...)
    return OpenAICompatibleAdvisoryBackend(
        profile=profile,
        model=resolve_cloud_model(settings, profile),
        request_timeout_seconds=settings["connection"]["request_timeout_seconds"],
        credential_loader=credential_loader,
    )
```

`cloud_advisory.enabled=true` 且 `provider="noop"` 是无效组合，必须在
`bootstrap()` 中抛 `LocalMindError(code="CONFIG_ERROR", recoverable=False, ...)`。
活动 provider 由新键 `provider` 唯一决定；兼容期旧键 `backend` 只按
`09-p6c-cloud-provider.md` §5.3 在启动期归一化。`enabled=false` 时仍校验
provider 与连接配置，但一律注入 `NoopCloudAdvisoryBackend`，不构造具有
真实外发能力的对象，也不调用 credential loader。

Adapter 层提供 `CloudProviderProfile`、封闭的 `CloudProviderRegistry`、
`CloudCredentialLoader` 与 `EnvCredentialLoader`。Loader 协议包含
`exists(profile) -> bool`（启动/自检期只返回存在性）和
`get(profile) -> str`（仅 `advise()` 外发前读取值）。同一个 loader 实例必须
完成启动检查并注入 `OpenAICompatibleAdvisoryBackend`；凭据不得保存到实例字段。
DeepSeek、GLM 与 custom_openai 均经 profile 复用通用适配器；未知 provider、
连接配置非法或启用时凭据缺失均抛 `CONFIG_ERROR`。

P0a 必须提供 6 个工厂函数签名：

```python
def create_model_backend(config: dict) -> ModelBackend: ...
def create_memory_backend(config: dict) -> MemoryBackend: ...
def create_tool_backend(config: dict) -> ToolBackend: ...
def create_safety_backend(config: dict) -> SafetyBackend: ...
def create_cloud_advisory_backend(config: dict) -> CloudAdvisoryBackend: ...
def create_evolution_backend(config: dict) -> EvolutionBackend: ...
```

所有未知 `type/backend`、缺失必需配置、配置格式错误都必须抛
`LocalMindError(code="CONFIG_ERROR", recoverable=False, ...)`。

P5 的 `create_memory_backend()` 读取 `memory_backend.config.embedding.type`：`none` →
注入 `None`（纯关键词路径），`ollama` 创建 `OllamaEmbeddingBackend` 后注入 MemoryBackend。embedding
的 `base_url` 必须是 loopback；`keyword_weight + vector_weight` 必须等于 1.0（容差 1e-9），
否则工厂抛 `CONFIG_ERROR`。embedding 探测失败不是配置错误，后端必须保留关键词降级能力。
工厂还从唯一真源 `safety.l1_rules.forbidden_paths` 读取路径规则，并将其副本注入
MemoryBackend 的写入消毒器；`memory_backend.config` 不定义第二份路径规则。

**规则**：
- 制造函数**只在 main.py 或专用的 `bootstrap.py` 中存在**
- Core 模块**绝对不能**包含 `if backend_type == "xxx"` 分支
- Core 模块通过构造函数接收已创建好的接口实例

---

## 2. 配置结构

```toml
# config/default.toml（完整参考示例，含未来阶段选项）
# 格式：TOML（Python 3.11+ stdlib tomllib）

[model_backend]
type = "ollama"                       # mock | ollama | turbo_llm

[model_backend.config]
model = "qwen3:4b-q4_K_M"
base_url = "http://localhost:11434"
keep_alive = "30m"

[memory_backend]
type = "sqlite"                       # in_memory | sqlite | everos

[memory_backend.config]
db_path = "./data/memory.db"

[memory_backend.config.embedding]
type = "none"                       # none | ollama；CI 默认 none
base_url = "http://localhost:11434"  # 仅允许 loopback
model = "nomic-embed-text"
dim = 0                               # 0 = 构造期探测；失败则降级关键词检索
timeout_seconds = 5

[memory_backend.config.retrieval]
keyword_weight = 0.6
vector_weight = 0.4                   # 两权重之和必须为 1.0，容差 1e-9
max_context_bytes = 4096
same_project_boost = 0.1

[projects]
auto_create = true
summary_max_chars = 2000

[tool_backend]
type = "builtin_only"                 # 聚合入口固定；外部来源由 [tool_providers] 独立开关

[tool_backend.config]
whitelist = ["system.get_time", "file.read", "file.list_dir", "file.stat", "file.write"]

# P7b：无此节 = 零外部来源。命令不属于配置，由 ProviderDeclaration 在代码中签发。
[tool_providers.demo]
enabled = true
handshake_timeout_ms = 5000
call_timeout_ms = 10000

[tools]
workspace_root = "./data/workspace"      # bootstrap 创建并解析为真实绝对路径

# P7c（2026-09-27）：三个新表，**键集闭集**，多一键即 CONFIG_ERROR / tool_config_invalid；
# **表缺席 ⇒ 用默认值，不报错**（既有示例配置不必新增本节）。
# 权威定义与全部默认值见 18 §9.1，此处只列键名，不复制第二份真源。
[tools.documents]        # max_file_bytes / max_extracted_chars / max_segments_total
                         # / max_returned_segments / max_returned_chars
                         # / max_zip_entries / max_uncompressed_bytes
[tools.search]           # max_results / max_results_per_file / max_line_chars
                         # / context_lines / timeout_ms / max_file_bytes / ignore
                         # 出现可执行文件相关键（如 ripgrep_path）⇒ tool_config_invalid
[reflow]                 # enabled / max_chars（只读工具结果回流层，18 §1）
                         # **没有 timeout_ms**：模型接口无调用级超时参数，回流沿用模型后端
                         # 自身超时（18 §1.6）。写该键 ⇒ CONFIG_ERROR / tool_config_invalid
                         # 跨表不变式：白名单内存在 model_summary 工具而 enabled=false
                         # ⇒ CONFIG_ERROR / reflow_disabled_with_model_summary_tools

[observability]
event_jsonl_path = ""                    # 空=Noop；非空必须是 data/ 内相对路径

[safety]
backend = "rule_only"                 # rule_only | qwenpaw
l2_enabled = false                    # P3 启用

[safety.l1_rules]
forbidden_commands = ["rm -rf /", "dd if=", "mkfs."]
forbidden_paths = ["/etc/passwd", "/etc/shadow", "~/.ssh"]
sensitive_patterns = ["\\b(password|passwd|secret|token|api_key)\\s*=\\s*\\S+"]

[safety.passphrase]
hash_file = "./data/.passphrase"
lockout_attempts = 5
lockout_minutes = 10

[cloud_advisory]
enabled = false                       # P4 启用
provider = "noop"                     # noop | deepseek | glm | custom_openai
privacy_mode = "balanced"             # strict | balanced | convenient
max_turns_per_task = 3
max_context_items = 12                 # 允许范围 1..100
context_byte_budget = 32768            # 允许范围 256..65536
cooldown_seconds = 300                 # 允许 1..3600，构造期非法值 CONFIG_ERROR
grant_ttl_seconds = 600

[cloud_advisory.connection]
model = ""                            # 空=内置 profile 默认；custom_openai 必填
request_timeout_seconds = 60
# api_base = "https://..."             # 仅 custom_openai 可配置

[cloud_advisory.policy]
allowed_scope = "仅提供分析建议，不生成执行命令或计划"
# 凭据不进配置文件：分别读取 LOCALMIND_DEEPSEEK_API_KEY、
# LOCALMIND_GLM_API_KEY 或 LOCALMIND_CUSTOM_OPENAI_API_KEY。
# deepseek 在 P7 前可回退 LOCALMIND_CLOUD_API_KEY。

[evolution]
enabled = false                       # P8 启用
backend = "noop"                      # noop | everos | lora_pipeline

[execution]
intent_max_rounds = 4
expert_scheduler_enabled = false      # P7 启用
```

### 2.1 P6a Core 数据结构

`src/core/schemas.py` 新增以下后端无关结构，字段以
`07-p6a-observability-cli.md` §1/§6.3 为准：

- `RuntimeEvent`：run/turn/session 标识、进程级 seq、UTC ts、stage、level、封闭 data；
- `RoundTrace`：单次渐进理解轮的 state/confidence/missing_info、检索净增条数与可选检索统计；
- `RetrievalStats`：hits、关键词/向量结果侧状态与 degraded；`degraded` 仅表示检索调用显式失败；
- `PreflightReport`：有效风险、确认要求、可选目标状态快照与**批准档**
  （`approval_profile`，2026-09-16 尾部新增、默认 `"standard"`——见 `13-approval-profile-high-impact.md` §4）。
  批准档由工具侧确定性事实声明（`ToolDef.approval_profile` 静态 + 本方法动态），
  Adapter 实现（P7 的 MCP 等第三方工具后端）**必须**经 `read_approval_profile()` 归一化，
  不得自行放宽；`requires_confirmation` 仍只由风险驱动，不因批准档为真。

这些结构不得引用具体 CLI、文件工具或 Adapter 类型。

P6d 的 `CloudAdmissionDecision` 定义在 `src/core/control_policy.py`，只承载云端准入是否
通过、封闭 gate 结果与确定性否决原因；它不是 Adapter 接口数据结构。

P6d 悬空指代护栏的 `ReferenceGuardResult` 与纯函数 `detect_unresolved_reference()`
定义在 `src/core/reference_guard.py`（`11-reference-guard.md`），无状态、无 IO、无依赖；
它同样不是 Adapter 接口数据结构，`ControlPolicy.decide()` 仅以**仅限关键字参数**接收其
结果，为 `None` 时不得回退成默认通过。

---

## 3. 依赖注入

```python
# main.py 初始化顺序
def bootstrap(
    config_path: str,
    model_backend_override: ModelBackend | None = None,
    event_sink_override: RuntimeEventSink | None = None,
    run_id_override: str | None = None,
):
    config = load_config(config_path)

    cloud_settings = normalize_cloud_advisory_config(config.get("cloud_advisory", {}))
    if cloud_settings["enabled"] and cloud_settings["provider"] == "noop":
        raise LocalMindError(
            code="CONFIG_ERROR",
            message="cloud_advisory.enabled requires a non-noop provider",
            user_message="云端咨询已启用，但未配置可用后端。",
            recoverable=False,
        )

    # 1. 创建所有 Adapter
    if model_backend_override is not None:
        model_backend = model_backend_override
    else:
        model_backend = create_model_backend(config)
    memory_backend   = create_memory_backend(config)

    # 1.5 模型生命周期：load → health_check → 注入
    model_backend.load()
    if not model_backend.health_check():
        raise LocalMindError(
            code="MODEL_UNAVAILABLE",
            message="Model health check failed after load",
            user_message="本地模型启动失败，请检查 Ollama 是否运行",
            recoverable=False,
        )
    # [tools].workspace_root 解析、创建后，同源注入工具层与 L1 安全层。
    tool_backend     = create_tool_backend(config)
    safety_backend   = create_safety_backend(config)
    cloud_backend    = create_cloud_advisory_backend(config)
    evolution_backend = create_evolution_backend(config)

    # 2. 组装 Core 模块（传接口，不传具体类型）
    audit_log: list[AuditEvent] = []
    cloud_audit_log: list[CloudAuditEvent] = []
    max_rounds = config.get("execution", {}).get("intent_max_rounds", 4)
    if not isinstance(max_rounds, int) or max_rounds < 1 or max_rounds > 4:
        raise LocalMindError(
            code="CONFIG_ERROR",
            message=f"intent_max_rounds must be 1..4, got {max_rounds}",
            user_message="系统配置有误，请检查 execution.intent_max_rounds。",
            recoverable=False,
        )
    retrieval_settings = config.get("memory_backend", {}).get("config", {}).get("retrieval", {})
    max_context_bytes = retrieval_settings.get("max_context_bytes", 4096)
    normalizer  = InputNormalizer()
    project_store = ProjectStore(
        records=memory_backend,
        auto_create=config.get("projects", {}).get("auto_create", True),
        summary_max_chars=config.get("projects", {}).get("summary_max_chars", 2000),
    )
    topic_tracker = TopicTracker()
    assembler   = ContextAssembler(
        memory=memory_backend,
        tools=tool_backend,
        max_context_bytes=max_context_bytes,
    )
    resolver    = IntentResolver(model=model_backend, memory=memory_backend, max_rounds=max_rounds)
    policy      = ControlPolicy()
    planner     = TaskPlanner()
    safety      = SafetyPolicy(backend=safety_backend)
    executor    = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=safety,
        audit_log=audit_log,
    )
    privacy_policy = PrivacyPolicy(
        mode=cloud_settings.get("privacy_mode", "balanced"),
        max_context_items=cloud_settings.get("max_context_items", 12),
        max_context_bytes=cloud_settings.get("context_byte_budget", 32768),
    )
    authorization = AuthorizationManager(
        grant_ttl_seconds=cloud_settings.get("grant_ttl_seconds", 600),
        max_turns_per_task=cloud_settings.get("max_turns_per_task", 3),
        max_context_items=cloud_settings.get("max_context_items", 12),
        max_context_bytes=cloud_settings.get("context_byte_budget", 32768),
        cooldown_seconds=cloud_settings.get("cooldown_seconds", 300),
    )
    cloud_bnd   = CloudBoundary()
    cloud_gateway = SideEffectGateway(
        boundary=cloud_bnd,
        cloud_backend=cloud_backend,
        authorization=authorization,
        audit_log=cloud_audit_log,
    )
    cloud_service = CloudAdvisoryService(
        gateway=cloud_gateway,
        max_turns=cloud_settings.get("max_turns_per_task", 3),
    )
    id_verifier = IdentityVerifier(config["safety"]["passphrase"])
    recorder    = ReflectionRecorder(evolution=evolution_backend)
    response    = ResponseBuilder()

    # 2.5 P7c 只读工具结果回流层（18 §1）——**必须有"构造 + 注入"这一步**。
    #     只改 App.__init__ 的签名而此处不构造，生产环境就不会启用回流：声明了
    #     result_delivery="model_summary" 的工具会退化成"打印一截结构化文本"，
    #     「总结这份文档」仍然不可用（18 §1.1 的缺口原样复现）。
    #     解析走 normalize_reflow_config()——**键集闭集校验与默认值的唯一实现点**
    #     （[reflow] 只允许 enabled / max_chars，多一键 ⇒ CONFIG_ERROR / tool_config_invalid；
    #      表缺席 ⇒ 默认 enabled=true, max_chars=4000，18 §9.1）。
    #     跨表不变式（白名单内存在 model_summary 工具而 enabled=false ⇒ CONFIG_ERROR /
    #     reflow_disabled_with_model_summary_tools）由 create_tool_backend() 侧用
    #     **同一个函数**的结果判定——那里才知道白名单与工具声明，两个事实在那里才同时可见。
    #     **不得**在 bootstrap 与工具后端各写一份默认值/键集（那就是第二份真源）。
    #     **`tool_defs` 必须来自 `tool_backend.list_tools()`**（18 §1.2.4）——即活跃集，
    #     与 GuardedToolExecutor.execute() 内部构造 registered_tools 的来源**同一个**；
    #     回流层只从它提取 name -> result_delivery，**不读 ToolDef 的其它字段**
    #     （准入与风控已由注册期与执行器负责，再判一次就是第二份准入真源）。
    #     位置说明：本段是**示意**——真实代码里 `App(...)` 的构造发生在 `_finish_bootstrap()` 内
    #     （`bootstrap()` 负责建 `model_backend` 后转交）。**判据不是"写在哪一行"，而是
    #     "真实装配路径上确实构造并被传进去了"**：构造与 `reflow=` 传参必须落在**同一条
    #     实际执行的路径**上，且 `model_backend` 在该处可见（必要时沿参数链传下去）。
    reflow_settings = normalize_reflow_config(config.get("reflow", {}))
    reflow = ResultReflow(
        backend=model_backend,
        tool_defs=tool_backend.list_tools(),   # 构造期冻结（18 §1.2.4）：判据只在这里
        enabled=reflow_settings["enabled"],
        max_chars=reflow_settings["max_chars"],
    )

    # 3. 返回组装好的应用
    return App(
        memory=memory_backend,
        normalizer=normalizer,
        assembler=assembler,
        resolver=resolver,
        policy=policy,
        planner=planner,
        safety=safety,
        executor=executor,
        cloud_enabled=cloud_settings.get("enabled", False),
        privacy_policy=privacy_policy,
        authorization=authorization,
        cloud_service=cloud_service,
        id_verifier=id_verifier,
        recorder=recorder,
        response=response,
        reflow=reflow,
        projects=project_store,
        topics=topic_tracker,
        event_sink=(
            event_sink_override
            if event_sink_override is not None
            else configured_event_sink
        ),
        run_id=run_id_override,
    )
```

**关键约束**：
- Core 模块构造函数**只接受接口类型**，不依赖具体实现
- 新增后端只需改 `create_xxx_backend` 工厂函数 + config/default.toml，不碰 Core
- 所有 `if backend_type == "xxx"` 集中在 `bootstrap()` 中

---

### 3.1 App 类

```python
class App:
    """组装好的 LocalMind 应用。bootstrap() 的返回值。"""

    def __init__(
        self,
        memory: MemoryBackend,
        normalizer: InputNormalizer,
        assembler: ContextAssembler,
        resolver: IntentResolver,
        policy: ControlPolicy,
        planner: TaskPlanner,
        safety: SafetyPolicy,
        executor: GuardedToolExecutor,
        cloud_enabled: bool,
        privacy_policy: PrivacyPolicy,
        authorization: AuthorizationManager,
        cloud_service: CloudAdvisoryService,
        cloud_provider: str,
        id_verifier: IdentityVerifier,
        recorder: ReflectionRecorder,
        response: ResponseBuilder,
        projects: ProjectStore,
        topics: TopicTracker,
        event_sink: RuntimeEventSink | None = None,
        run_id: str | None = None,
        reflow: "ResultReflow | None" = None,     # P7c（18 §1）；**追加式置尾 + 默认值**
                                                  # ⇒ 既有构造调用零改动（含按位置传参的调用方）。
                                                  # None ⇒ 关态，与"白名单内无 model_summary 工具"等价。
    ) -> None: ...

    def handle(self, raw_text: str, session_id: str, project_id: str | None = None) -> str:
        """
        执行一次完整的核心闭环：

        1. InputNormalizer.normalize(raw_text, session_id, project_id) → InputEvent
        2. ProjectStore.resolve() + TopicTracker.on_turn() → TopicDecision；
           ContextAssembler.assemble(input_event, topic, project_state) → MinimalContext
           （按需加载会话摘要、项目状态、相关记忆片段）
        3. IntentResolver.resolve(minimal_context) → IntentCandidate
           （多轮认知循环，最多 4 轮）
        4. ControlPolicy.decide(candidate, cloud_state, resolution_exhausted=..., tool_defs=context.tool_defs) → NextAction
        5. TaskPlanner.plan(candidate, context) → ExecutionPlan
        6. GuardedToolExecutor.execute(plan) → {step_index: result_dict}
           （内部逐 step 调用 SafetyPolicy.check() + ToolBackend.execute()）
        7. 有工具结果时 ResponseBuilder.build(plan, results) → 回复文本；READY 且计划为空时，
           App 调本地 ModelBackend.generate() 直接生成自然语言回答，不伪造工具执行
        8. ReflectionRecorder.record(...) → 旁路记录

        P5：每轮先解析项目、生成 TopicDecision，再装配上下文；记忆写入仅接收
        narrative_reply 与 ExecutionRecord。确认成功的执行使用固定 User 占位写入，
        口令、确认 token 和失败确认均不进入记忆。

        失败时返回 user_message 而不是抛异常——用户不应看到 traceback。
        """
        ...

    def end_session(self, session_id: str) -> None:
        """Finalize one CLI session at EOF.

        The CLI entry must call this method when it receives EOF. Flush the rolling conversation
        summary, then call topics.end_session(session_id).
        Summary generation or persistence failure is non-blocking and must not expose an exception
        at CLI shutdown.
        """
        ...

    def shutdown(self) -> None:
        """进程级收尾：幂等调用 executor.tool_backend.close()，不得抛异常。"""
        ...

    def status_snapshot(self) -> dict: ...
    def last_turn_report(self) -> dict | None: ...
    def topics_snapshot(self, session_id: str) -> tuple[str, ...]: ...
    def list_projects(self) -> list[str]: ...
```

P6a 四个查询方法均只读，不产生事件、不写记忆、不改变状态机。`event_sink=None`
等价于 `NoopEventSink`；`run_id=None` 时 App 自生成短 uuid。每次 `handle()` 必须恰好
产生一个 `turn_completed`，`end_session()` 产生 `turn_id=None` 的 `session_ended`。

`cloud_enabled` 是 App 保存的安装级配置。App 每轮调用 `ControlPolicy` 前，以该值、
`AuthorizationManager.remaining_turns()`、`AuthorizationManager.cooldown_active()`
及本轮用户指令组装唯一的 `CloudControlState`；`ControlPolicy` 本身不保存云端状态。

**P7c 增补（2026-09-27，18 §1 / §1.2.3）——App 的四项变更，逐项照实记录**：

1. **`__init__` 追加一个**带默认值**的参数 `reflow: "ResultReflow" | None = None`**（追加式、置尾、
   默认 `None` ⇒ 默认行为等价于"回流关闭"，既有构造调用零改动，与 `event_sink` 同法）。
   注入点在 `bootstrap()` 内部，**`bootstrap()` 自身签名不变**。
2. **`bootstrap()` 内新增一步装配**（第四轮审查发现的**接线遗漏**；§3 的 2.5 段）：`normalize_reflow_config(config["reflow"])` →
   构造 `ResultReflow(backend=model_backend, tool_defs=tool_backend.list_tools(), enabled=…, max_chars=…)`
   → 作为 `reflow=` 传入 `App`（`tool_defs` 见下方第 3 条）。
   **光改 `App.__init__` 的签名而不构造，生产环境不会启用回流**——`model_summary` 工具会退化成
   "打印一截结构化文本"（18 §1.1 的缺口原样复现）。因此 `bootstrap()` 的准确口径是
   **"签名零变更，但装配步骤有新增"**，前版写的"`bootstrap()` 步骤零新增"**作废**。
   `[reflow]` 的**键集闭集校验与默认值只有一处实现**（`normalize_reflow_config()`，住 `src/main.py`
   的配置解析区，与 `normalize_cloud_advisory_config` 同处；**不得**在工具后端再写一份默认值/键集）；
   跨表不变式由 `create_tool_backend()` 调**同一个函数**后判定（它才知道白名单与工具声明）。
3. **两个 `response.build` 调用点插入共享回流**，调用形态**零分支**：
   `outcome = self._reflow(plan, results, original_request, fallback_display=output.display)`
   → `return outcome.display`；且必须**排在 `_record_tool_events()` 之前**
   （`ExecutionRecord.result_delivery` 要靠它回填）。**`fallback_display` 是本回合数据、
   走实参**（"无可回流"与"失败回落"两态都要逐字节保留 `output.display`，回流层
   **永不自己合成**回落文本——否则就是第二份确定性显示实现，两条路径输出会分叉）。
   **`App._reflow()` 是关态的唯一实现点**（`self._reflow is None ⇒` 直接返回
   `ReflowOutcome(display=fallback_display, deliveries={})`；`enabled=False` 由组件内部短路），
   因此两个调用点仍是零分支一行。
   **本回合的 `_execution_records` 有三个调用点**（`src/main.py:885` / **`:893`（写 episode，
   前版契约漏掉的正是这一个）** / `1020`），**必须传同一份 `outcome.deliveries`**——只给事件侧
   传值会让 episode 记录退化成 `None`（18 R20）。**失败路径（`except LocalMindError`）零回流**
   （`output` 都没构造，没有 `fallback_display`；部分成功的中间结果**不**做事后回流，18 R21）。
4. **新增私有状态 `App._pending_user_request: str | None`** —— 计划进入等待确认时冻结原始请求，
   清理点**只有 `_clear_pending()` 一处**（**加一行**，不要在各分支里分别清理）；
   确认成功分支**必须在 `execute()` 之前**先取出到局部变量（`src/main.py:881` 的
   `_clear_pending()` 先于执行发生）。
   **红线**：该值**只作回流输入**，不得进 episode / 记忆 / 事件 / 审计 / 云端；
   `_record_turn("[身份确认，原文不留存]", …)` **保持不变**（不放松 P4）。全文：18 §1.2.3。

### 3.3 P7b 外部工具装配

- `create_tool_backend()` 无论 provider 是否启用，都先校验全部代码侧
  `ProviderDeclaration`、`ExternalToolAdmission` 与合并能力目录（E1-E18）。
- `[tool_providers.<id>]` 只允许 `enabled`、`handshake_timeout_ms`、
  `call_timeout_ms`；未知键（含 `command`）直接 `CONFIG_ERROR`。
- provider 启用时，bootstrap 只从代码声明取得 argv，握手失败降为能力不可用；
  静态声明错误 fail-loud。
- 能力路由开启时，即使 provider 未启用，也使用 `CompositeToolBackend` 暴露完整能力声明，
  使对应能力确定性落到 `unavailable`，而不是误报为未知能力。
- tool backend 创建成功后，后续任一步装配失败都必须补偿调用 `close()`；正常运行由
  `App.shutdown()` 在 CLI、评估子进程和演示脚本的 `finally` 中关闭。

### 3.2 Core 模块构造函数签名

以下签名是 `bootstrap()` 组装时的权威参考。P0a 标 "stub" 的模块只需可实例化、方法返回合法空值即可，完整实现在后续阶段。

```python
# ── InputNormalizer ──
class InputNormalizer:
    def __init__(self) -> None: ...
    def normalize(self, raw_text: str, session_id: str, project_id: str | None = None) -> InputEvent: ...

# ── ContextAssembler ──
class ContextAssembler:
    def __init__(
        self,
        memory: MemoryBackend,
        tools: ToolBackend,
        max_context_bytes: int,
    ) -> None: ...
    def assemble(
        self,
        input_event: InputEvent,
        topic: TopicDecision,
        project_state: ProjectState | None,
    ) -> MinimalContext: ...
    # max_context_bytes 由 bootstrap 的 memory_backend.config.retrieval 注入；组装后
    # 对 relevant_history 执行总 UTF-8 字节预算裁剪。
    # 仅依赖 Core 数据结构；retrieve 必须透传 topic.project_id 与定向 topic_hints。
    # ContextAssembler 不 import ProjectStore 或任一 memory adapter。
    # 每轮从 ToolBackend.list_tools() 现取目录并校验数量、重名、schema 与 8192 字节上限；
    # 只把 ToolDef 元组写入 MinimalContext，不负责提示词渲染。

# ── IntentResolver ──
class IntentResolver:
    def __init__(self, model: ModelBackend, memory: MemoryBackend) -> None: ...
    def resolve(self, context: MinimalContext) -> IntentCandidate: ...

# ── ControlPolicy ──
class ControlPolicy:
    def __init__(self) -> None: ...
    def decide(
        self,
        candidate: IntentCandidate,
        cloud_state: CloudControlState | None = None,
        *,
        resolution_exhausted: bool,
        no_progress: bool = False,
        reference_guard: ReferenceGuardResult | None = None,
        tool_defs: Sequence[ToolDef] | None = None,
    ) -> NextAction:
        """P4 起 App 每轮必传 cloud_state；P6d 由 no_progress 阻止空转检索。
        P6：resolution_exhausted 必传，由 App 原样转发 Resolver 的循环出口事实，
        使轮次用尽时不再返回 RETRIEVE_MORE。
        P6d 悬空指代护栏：reference_guard 由 App 用 MinimalContext 计算后传入
        （11-reference-guard.md §1.2/§1.3）；为 None 时记 not_evaluated，
        不得默认成 not_triggered（确认恢复流转 None 属合法）。
        """

# ── reference_guard（11-reference-guard.md）──
@dataclass(frozen=True)
class ReferenceGuardResult:
    triggered: bool
    resolved_by: str = "none"   # none | self_referential | same_turn | history | project_state
    marker_text: str = ""       # 仅内存；禁止落任何持久层

def detect_unresolved_reference(
    input_text: str,
    *,
    relevant_history: Sequence[str] = (),
    project_state: Mapping[str, object] | None = None,
) -> ReferenceGuardResult: ...
# 注：签名中不得出现 IntentCandidate/entities/missing_info/state（§1.2，结构测试 §7 第 18 项）

def evaluate_cloud_admission(
    candidate: IntentCandidate,
    cloud_state: CloudControlState | None = None,
) -> CloudAdmissionDecision:
    """云端准入与归因的唯一纯函数实现；App 与 ControlPolicy 复用同一组输入。"""

# ── TaskPlanner ──
class TaskPlanner:
    def __init__(self) -> None: ...
    def plan(self, candidate: IntentCandidate, context: MinimalContext) -> ExecutionPlan:
        """仅从 candidate.tool_call 构建单工具计划，并以 context.tool_defs 复核。"""
        ...

# ── SafetyPolicy ──
class SafetyPolicy:
    def __init__(self, backend: SafetyBackend) -> None: ...
    def check(self, step: ExecutionStep) -> SafetyVerdict: ...

# ── GuardedToolExecutor ──
class GuardedToolExecutor:
    def __init__(self, tool_backend: ToolBackend, safety_policy: SafetyPolicy, audit_log: list[AuditEvent] | None = None) -> None: ...
    def execute(self, plan: ExecutionPlan, task_id: str = "", intent_id: str = "") -> dict[int, dict[str, object]]:
        """逐 step 执行。task_id/intent_id 用于 AuditEvent。返回 {step_index: result}。
        拒绝优先级（2026-09-16，不可调换）：dangerous → high_impact → sensitive(未 gate23)。"""
    def preflight(
        self, plan: ExecutionPlan, task_id: str = "", intent_id: str = ""
    ) -> PreflightReport:
        """无副作用聚合计划风险与批准档；不执行工具、不写审计。
        计划级 approval_profile 取各 step 最高（只升不降）。"""

# ── P4 隐私、授权与云端边界 ──
class PrivacyPolicy:
    def __init__(
        self,
        mode: str,
        max_context_items: int,
        max_context_bytes: int,
        allowed_scope: str = "仅提供分析建议，不生成执行命令或计划",
    ) -> None: ...
    def prepare(
        self,
        proposal: ConsultationProposal | None,
        context: MinimalContext,
        task_id: str,
        session_id: str,
        provider: str,
        purpose: str,
    ) -> PrivacyPreparation:
        """App 将 TaskBrief section 作为 source=local_task_context、label=brief_* 的
        free_text ContextCandidate 并入候选；仅本地来源可使用 brief_* 固定 label。
        """
    def build_package(
        self,
        preparation: PrivacyPreparation,
        grant: AuthorizationGrant,
        turn: int = 1,
    ) -> CloudRequestPackage:
        """首轮组装：验证 grant 覆盖类别/fingerprint，并只生成其授权子集。"""

class AuthorizationManager:
    def __init__(
        self,
        grant_ttl_seconds: int,
        max_turns_per_task: int,
        max_context_items: int,
        max_context_bytes: int,
        cooldown_seconds: int,
    ) -> None:
        """max_turns_per_task 同时是单个 grant.max_turns 签发上限和任务台账的
        累计网络轮数上限；P4 两者同源同值。
        """
    def create_user_grant(
        self,
        preparation: PrivacyPreparation,
        task_id: str,
        session_id: str,
        provider: str,
        purpose: str,
        now: float,
    ) -> AuthorizationGrant:
        """purpose 必须是归一化 escalation_reason。

        签发前检查任务累计 consumed_turns 与边界扩张次数；首次 grant 不计扩张，
        仅新 preparation 的类别或 fingerprint 不属于该任务历史授权集合时计数。
        增量候选（fingerprint 不在任务台账历史集合）必须非空且全部为 allowlisted
        user_entity；已确认的候选可随包继承重发。超限抛 CLOUD_BUDGET_EXCEEDED；
        签发成功即吊销同 task 的旧活跃 grant。
        """
    def create_policy_grant(
        self,
        preparation: PrivacyPreparation,
        task_id: str,
        session_id: str,
        provider: str,
        purpose: str,
        now: float,
        *,
        escalation_risk: str = "sensitive",
    ) -> AuthorizationGrant:
        """purpose 必须是归一化 escalation_reason。

        escalation_risk 承载授权时求出的有效授权风险；仅 normal 可签发。
        非 normal 时抛 CLOUD_AUTHORIZATION_REQUIRED，details.reason 固定为
        sensitive_policy_grant_forbidden，且不改变 grant、预算、轮次或 pending 状态。
        签发前检查任务累计 consumed_turns 与边界扩张次数；首次 grant 不计扩张，
        仅新 preparation 的类别或 fingerprint 不属于该任务历史授权集合时计数。
        超限抛 CLOUD_BUDGET_EXCEEDED；签发成功即吊销同 task 的旧活跃 grant。
        """
    def validate(
        self,
        grant: AuthorizationGrant,
        package: CloudRequestPackage,
        task_id: str,
        session_id: str,
        provider: str,
        purpose: str,
        now: float,
    ) -> GrantUsageSnapshot: ...
    def reserve_turn(self, grant: AuthorizationGrant, now: float) -> None: ...
    def release_turn(self, grant: AuthorizationGrant) -> None: ...
    def consume_reserved_turn(
        self, grant: AuthorizationGrant, package_context_bytes: int, now: float
    ) -> GrantUsageSnapshot:
        """转为已消费的 grant 轮次，并同步更新任务级累计台账。"""
    def enter_cooldown(self, grant: AuthorizationGrant, now: float) -> None: ...
    def revoke_task(self, task_id: str, session_id: str) -> None: ...
    def remaining_turns(self, task_id: str) -> int:
        """无活跃记录的新任务返回本管理器的 max_turns_per_task。"""
    def cooldown_active(self, task_id: str, now: float) -> bool:
        """无活跃记录的新任务返回 False。"""

class CloudBoundary:
    def __init__(self) -> None: ...
    def check_request(
        self,
        package: CloudRequestPackage,
        grant: AuthorizationGrant,
        usage_snapshot: GrantUsageSnapshot,
    ) -> CloudRequestPackage: ...
    def check_response(self, result: AdvisoryResult) -> AdvisoryResult: ...

# ── SideEffectGateway（P4 云端副作用出口）──
class SideEffectGateway:
    def __init__(
        self,
        boundary: CloudBoundary,
        cloud_backend: CloudAdvisoryBackend | None,
        authorization: AuthorizationManager,
        audit_log: list[CloudAuditEvent] | None = None,
    ) -> None: ...
    def execute_cloud_turn(
        self,
        package: CloudRequestPackage,
        grant: CloudGrant,
        task_id: str,
        intent_id: str,
        turn: int,
    ) -> AdvisoryResult:
        """先拒绝非 AuthorizationGrant，再 reserve → validate → boundary → consume → advise → response/audit。"""

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        """记录 pending 授权取消、超时、跨会话或被新输入取代的最小拒绝审计。"""

# ── CloudAdvisoryService（P4 sub-turn 编排）──
class CloudAdvisoryService:
    def __init__(self, gateway: CloudTurnGateway, max_turns: int = 3) -> None: ...
    def consult(
        self,
        package: CloudRequestPackage,
        grant: CloudGrant,
        task_id: str,
        intent_id: str,
    ) -> ConsultOutcome:
        """只编排当前 grant 的同值/子集 sub-turn。

        合法的新类别追问返回 suspended；App 负责重新准备、授权并以新 grant 续咨询。
        """

# ── IdentityVerifier（P0a stub）──
class IdentityVerifier:
    def __init__(self, passphrase_config: dict) -> None: ...
    def verify(self, passphrase: str) -> bool: ...                         # P0a: 直接返回 True

# ── ReflectionRecorder（P0a stub）──
class ReflectionRecorder:
    def __init__(self, evolution: EvolutionBackend) -> None: ...
    def record(self, task_context: dict, outcome: str) -> None: ...        # P0a: no-op

# ── ResponseBuilder ──
@dataclass(frozen=True)
class ResponseOutput:
    """同一次工具响应的显示与记忆安全形态。"""

    display: str
    narrative_reply: str

@dataclass(frozen=True)
class ExecutionRecord:
    """唯一允许进入 P5 记忆的工具执行结果形态。"""

    tool_name: str
    verdict: str                    # allowed | denied
    risk_level: str
    outcome: str                    # success | failure
    sanitized_summary: str
    error_code: str | None = None
    result_delivery: str | None = None
                                    # 2026-09-27 新增（18 §1.2，只读工具结果回流层）。
                                    # 闭集（非 None 时）："model_summary" | "model_summary_failed"。
                                    # None = 该 step 未声明 model_summary ⇒ tool_execution 事件**不发**该键
                                    # （条件键，见 07 §tool_execution 行）。
                                    # **追加式 + 默认值 ⇒ 既有构造调用零改动**；
                                    # 按 step_index 回填，**不按工具名**（同一计划可多次调用同名工具）。

class ResponseBuilder:
    def __init__(self) -> None: ...
    def build(self, plan: ExecutionPlan, results: dict[int, dict[str, object]]) -> ResponseOutput: ...
    """display 可含工具原文；narrative_reply 不得含工具原文，供 P5 记忆写入。"""
    # 2026-09-27：_sanitize_display_string → 公开 sanitize_display_text()；
    #            _DISPLAY_LIMIT → 公开 DISPLAY_LIMIT（18 §1.4/§1.5，回流复用同一份实现与同一个数）

# ── ResultReflow（P7c，18 §1）──
# 2026-09-27 新增 Core 类型（第三轮审查，老板阻塞点 2）。
@dataclass(frozen=True)
class ReflowOutcome:
    display: str                       # 用户可见的最终文本（已消毒、已按上限截断）
    deliveries: Mapping[int, str]      # step_index -> "model_summary" | "model_summary_failed"
                                       # 未参与回流的 step **不出现在映射里**
    # 三态：无可回流 ⇒ display **逐字节等于**实参 fallback_display（= output.display）且 deliveries == {}；
    #       成功     ⇒ display = 模型输出（过 sanitize_display_text() + 截到 DISPLAY_LIMIT）；
    #       失败回落 ⇒ display **同样是 fallback_display**（与"无可回流"同一份字节），
    #                   deliveries 值为 "model_summary_failed"。
    # **①与③只由 deliveries 区分** ⇒ 回流层**永不自己合成回落文本**，"回流失败的用户可见
    # 后果与没有回流层时逐字节相同"因此是**构造性事实**，不靠实现自觉。
    # 同一个结构覆盖三态 ⇒ 两个调用点**零分支**：outcome = self._reflow(...); return outcome.display
    # 权威定义与探针：18 §1.2.1 / §1.2.4 / §12.2 R17–R18、R20–R21。

class ResultReflow:
    def __init__(
        self,
        backend: ModelBackend,
        tool_defs: Sequence[ToolDef],     # 构造期冻结（18 §1.2.4）：只提取 name -> result_delivery
        enabled: bool = True,
        max_chars: int = 4000,
    ) -> None: ...
    def __call__(self, plan: ExecutionPlan, results: dict[int, dict[str, object]],
                 original_request: str, fallback_display: str) -> ReflowOutcome: ...
    # **每回合至多一次模型调用**，覆盖集 = `results` 里出现、且其 tool_name 在冻结目录中
    # 声明 model_summary 的全部 step（18 §1.2.2）⇒ 覆盖集内 deliveries 取值必然相同。
    # **"成功"是构造性事实、不是判据**：GuardedToolExecutor.execute() 在任何失败上都 raise，
    # results **只含成功步骤**，结果 dict 里**没有** outcome 字段（18 §0.8）。
    # original_request：**发起本次操作的那句原始请求**——直连路径传 current_input，
    # 确认路径传冻结的 App._pending_user_request（18 §1.2.3，**不得**传本回合的确认口令）。
    # fallback_display：本回合的 ResponseBuilder output.display，**调用时传入**（§3 增补第 3 条）。
    # tool_defs 的来源必须是 tool_backend.list_tools()（与执行器的 registered_tools 同源）；
    # **只读 result_delivery 这一个字段**，不读 risk_level/parameters/description（不做第二份准入判断）。
    # 实现落 src/core/result_reflow.py。
```

---

## 4. 新增后端的 checklist

如果要新增 TurboLLM 替换 Ollama：

1. 新建 `src/models/turbo_llm_backend.py`，实现 `ModelBackend`
2. 在 `create_model_backend()` 中加一个 `elif backend_type == "turbo_llm"`
3. 修改 `config/default.toml` 中 `model_backend.type` 为 `turbo_llm`
4. **不改任何 `src/core/` 中的代码**

同样的步骤适用于替换 MemoryBackend、SafetyBackend、CloudAdvisoryBackend 等。
