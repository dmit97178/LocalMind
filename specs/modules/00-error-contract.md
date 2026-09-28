# 00-error-contract — 错误与结果契约

> 状态：✅ 待实现
> 性质：编码前必读。所有模块的错误必须遵循此契约。
> 任何模块不得临时抛 `Exception("something wrong")` 或返回字符串错误。

---

## 1. 错误基类

```python
class LocalMindError(Exception):
    """所有错误的基类。"""
    code: str               # 机器可读错误码，如 "MODEL_TIMEOUT"
    message: str            # 给日志的技术描述
    user_message: str       # 给用户的自然语言描述
    recoverable: bool       # 调用方是否可以重试；默认 False，可降级/可重试错误必须显式传 True
    details: Optional[dict] # 额外上下文

class ModelError(LocalMindError):
    """模型调用失败：超时、返回格式错误、模型不可用。"""
    pass

class SafetyDenied(LocalMindError):
    """安全策略拒绝执行。"""
    pass

class ToolError(LocalMindError):
    """工具执行失败：工具不存在、参数错误、执行异常。"""
    pass
```

**不需要建更多子类**。其他错误场景用 `LocalMindError` + 特定 `code` 区分。

---

## 2. 错误码规范

| code | 含义 | 典型 user_message |
|------|------|------|
| `INVALID_INPUT` | 用户输入为空或格式非法 | "输入不能为空。" |
| `MODEL_TIMEOUT` | 模型推理超时 | "模型响应超时，请稍后重试" |
| `MODEL_UNAVAILABLE` | 模型未加载或不可用 | "本地模型尚未就绪，请稍候" |
| `MODEL_PARSE_ERROR` | 模型输出无法解析为预期格式 | "模型返回格式异常，正在重试" |
| `CLOUD_UNAVAILABLE` | 云端传输失败、超时或服务端 5xx | "云端服务暂不可用。" |
| `CLOUD_PARSE_ERROR` | 云端返回无法解析为 AdvisoryResult | "云端返回格式异常。" |
| `CLOUD_AUTH_INVALID` | 云端凭据无效或无权限（401/403） | "云端凭据无效或无权限，请检查提供商的 API Key。" |
| `CLOUD_ENDPOINT_INVALID` | 云端端点、模型或请求配置错误（3xx/其余 4xx） | "云端模型或服务地址配置有误，请检查 provider 与 connection.model。" |
| `CLOUD_RATE_LIMITED` | 云端限流或配额耗尽（429） | "云端请求达到限流或配额上限，请稍后再试。" |
| `CLOUD_CREDENTIAL_MISSING` | 实际外发前发现活动 provider 凭据缺失 | "未配置云端提供商的 API Key。" |
| `CLOUD_TURN_LIMIT` | 云端 sub-turn 达到上限的内部信号 | 不直接暴露用户 |
| `CLOUD_AUTHORIZATION_REQUIRED` | 新 payload 或范围扩大，需要用户授权 | "该云端咨询需要你的确认后才能发送。" |
| `CLOUD_AUTHORIZATION_EXPIRED` | grant 过期、任务/会话/提供商/目的不匹配 | "云端授权已失效，需要重新确认。" |
| `CLOUD_BUDGET_EXCEEDED` | 云端请求轮数预算耗尽 | "本次云端咨询已达到预算限制。" |
| `CLOUD_COOLDOWN_ACTIVE` | 当前任务仍处于云端咨询冷却期 | "云端咨询暂处于冷却期，请稍后再试。" |
| `SAFETY_RELEVANCE` | 三关 ① 不通过 | "此操作与当前任务无关，已阻止" |
| `SAFETY_NECESSITY` | 三关 ② 不通过 | "此操作并非必要，已阻止" |
| `SAFETY_IDENTITY` | 三关 ③ 不通过 | "身份验证未通过，已阻止" |
| `SAFETY_CLOUD_BLOCK` | 云端出站/入站拦截 | "数据发送到云端被安全策略拦截" |
| `SAFETY_DENIED` | L1/L2 安全规则拦截（通用，无法归入三关细分时使用） | "此操作被安全策略阻止" |
| `SAFETY_IMPACT_CLOSED` | `approval_profile == "high_impact"` 且 `effective_risk != "dangerous"`。**只由 `GuardedToolExecutor.execute()` 的冗余防线抛出**——App 主线的扣留是**正常响应**（写 `AuditEvent.reason="high_impact_closed"` + 返回草案文案），**不抛本错误**（`handle()` 有不抛异常契约）。`recoverable=False`，但**有补救路径**（只读分析 / 补充条件 / 草案），故不等同于 `SAFETY_DENIED` 的无补救拒绝 | "此操作属于高影响操作，当前阶段不执行。我可以先给出分析与所需条件。" |
| `TOOL_NOT_FOUND` | 工具不在注册表中 | "所需工具不可用" |
| `TOOL_PARAM_ERROR` | 工具参数与 schema 不匹配；规划与执行边界复用同一校验器 | "操作参数不正确" |
| `TOOL_EXEC_ERROR` | 工具执行时异常。`details.reason` 为**闭集二十四值**：P7a 立八值（`location_not_found` / `provider_parse_error` / `provider_timeout` / `provider_response_too_large` / `provider_redirect_rejected` / `provider_http_error` / `provider_unreachable` / `location_rejected`，16 §5.4），P7b 复用其中四值（`provider_timeout` / `provider_unreachable` / `provider_response_too_large` / `provider_parse_error`）并**新增五值**：`provider_protocol_error`（JSON 合法但协议不合法，**且该 provider 本会话标记不可用**）、`tool_reported_error`（服务端 `isError: true`，工具层失败、provider 仍可用）、`param_secret_rejected`（出站参数命中共享秘密检测，**零外发**）、`param_too_large`（单参数 >8192 码点或请求帧 >32 KiB，**零外发**）（2026-09-25，17 §7.3）；**`provider_unsupported_content`（2026-09-26 新增，17 §7.3/§5.4.4）**——`tools/call` 返回了内容类型白名单之外的项（本系统只认 `text`），**provider 保持健康**：这是本系统的能力缺口，不是链路损坏，因此**不得**与 `provider_protocol_error` 混用（后者意味着链路已作废）。**P7c 新增十一值（2026-09-27，18 §6.1）**——文档解析七值：`parser_unavailable`（该格式的解析模块在**本机不存在**，`recoverable=True`。**注意：四个解析库是正常依赖，不是 optional extra**（2026-09-27 老板裁决），本值覆盖的是**安装损坏 / 部分安装 / 打包剥离**，不是"我们设计成可选所以常见"）、`document_encrypted`、`document_corrupt`、`document_unsupported_format`（扩展名不在支持集，或 `.doc`/`.xls`/`.ppt`）、`document_format_mismatch`（扩展名与容器形态不符，fail-closed、不猜真格式）、`document_extract_failed`（解析器异常兜底，`details` 只允许 `reason`/`parser`/`exception_type` 三个键，**禁止**写 `str(exc)`）、**`document_expansion_too_large`**（2026-09-27 二轮新增：OOXML 的 ZIP 条目数或**总解压大小**超限，**在解析器之前**判定，18 §4.5；**不得**与 `document_corrupt` 混用——它没损坏，它是太大）；搜索四值：`query_invalid`（空查询或 `mode` 越界——**空查询必须失败，不得返回空结果集**，否则模型会如实说出错误结论"工作区里没有 X"）、`glob_invalid`、`search_timeout`（**不返回部分结果**：部分结果取决于超时发生在哪一毫秒，与"结果可复现"冲突）、`search_engine_error`（两引擎均失败）。**`document_encrypted` / `document_corrupt` / `document_unsupported_format` / `document_format_mismatch` / `document_expansion_too_large` 定 `recoverable=False`**（重试同一文件不会成功）。未在闭集内的值不得出现 | "操作执行失败" |
| `FILE_ERROR` | 文件路径逃逸、参数/大小非法或预检后目标状态变化。`details.reason` 为**闭集十一值**（2026-09-27 借 P7c 闭集化，原契约仅举例、未成闭集，此处把实现中既有事实写实，**不改任何行为**）：既有十值——`workspace_escape` / `path_type` / `target_missing` / `not_a_directory` / `content_too_large` / `content_type` / `read_failed` / `list_failed` / `stat_failed`（`src/tools/file_tools.py`）与 **`target_state_changed`**（唯一产出点在 **`src/main.py:1011`** 的 App 侧 TOCTOU 复检，不在 file_tools 内）；P7c **新增一值** `target_too_large`（`document.read` 的目标文件超过 `[tools.documents].max_file_bytes`，**零解析**，18 §3.3） | "文件操作被拒绝：路径必须位于工作区内。" |
| `MEMORY_ERROR` | 记忆存储/检索失败 | "记忆系统暂时不可用" |
| `EMBEDDING_ERROR` | 本地 embedding 计算或超时失败 | "语义检索暂不可用，已切换关键词检索。" |
| `CONFIG_ERROR` | 配置缺失或格式错误；工具目录 schema 非法、重名、超过 32 项或序列化后超过 8192 UTF-8 字节；目录超限时 `details` 分别记录 `tool_count` 或 `catalog_bytes`。**P7b 新增的 `details.reason` 闭集（2026-09-25，17 §7.1，全部 fail-loud、全部判本地作者错误）**：`tool_providers_require_capability_routing`（`[tool_providers]` 非空但 `capability_routing.enabled=false`，17 E3）、`tool_provider_unknown`（配置出现未登记的 provider id，E1）、`tool_provider_invalid`（超时值非法；**配置键集越界——`[tool_providers.<id>]` 表内出现闭集 `{enabled, handshake_timeout_ms, call_timeout_ms}` 之外的键，含已作废的 `command`**，E16/E18；**代码侧 `ProviderDeclaration.argv` 形态非法**——空元组、空元素、元素含 **NUL / CR / LF**、首项不可解析为存在的绝对路径，E17。**2026-09-26 二次修订：`;` `|` `&` `>` `<` 等 shell 元字符是合法字符，不得作为判据**——`shell=False` + argv 数组传参已结构性消灭 shell 注入，再禁字符没有安全收益，还会误伤合法路径（如安装目录含 `&`）；且该禁令曾与本契约 P10「含 `;`/`|` 的参数不被解释」的验收臂**自相矛盾**）、`tool_provider_command_missing`（命令解析失败，**静态可判定**；**2026-09-26 归属订正：判据对象是代码侧的 `ProviderDeclaration.argv[0]`，不是配置**——原稿写"配置侧命令解析失败"已随命令挪进代码而失效，17 §5.2）、`external_tool_declaration_invalid`（准入声明形态/显式字段/字符集/参数契约，E4/E6/E7/E9/E10/E15）、`external_tool_name_conflict`（规范名冲突或覆盖内置，E5）、`external_side_effect_not_supported`（`side_effect_class != "read_only"`，E8）、`egress_contract_invalid`（E11/E12）。**P7c 新增两值（2026-09-27，18 §6.3）**：`tool_config_invalid`——工具配置表的**键集越界**或**取值非法**（非正整数、超出允许区间、`context_lines > 3`），通用且可复用（`[tools.documents]` / `[tools.search]` / `[reflow]` 首批使用者），全部 fail-loud、全部判本地作者错误；**`result_delivery_invalid`**（2026-09-27 二轮新增）——`ToolDef.result_delivery` 的三条注册期不变式 RD1/RD2/RD3 任一不成立（18 §1.3）：取值不在闭集、`model_summary` 而工具属于 `LOCAL_SIDE_EFFECT_TOOLS`、`model_summary` 而工具 `egress=True`。后两条让「让模型改写写入结果」与「外部文本经回流进提示词」成为**注册期不可达**，不是运行期策略。另有跨表不变式 `reflow_disabled_with_model_summary_tools`（18 §1.9：白名单内存在 `model_summary` 工具而 `[reflow].enabled=false`）**同用本值**——与 17 E3 同一构造。**`[tools.search]` 出现可执行文件相关键（如 `ripgrep_path`）⇒ 本值**（与 `[tool_providers.<id>]` 出现 `command` 同一构造：命令由代码签发，配置只控制跑不跑与超时）。**`[reflow]` 的键集是闭集且不含 `timeout_ms`**（2026-09-27 二轮，18 §1.6）——模型接口没有调用级超时参数，回流沿用后端自身超时，因此写 `timeout_ms` 即本值（**该键不是"暂未实现"，是"按现有接口无法实现"**，18 §12.2 R15 以此为探针）。**动态外部事实（进程起不来、握手超时、崩溃、协议破损）一律不抛 CONFIG_ERROR，也不抛任何错误——转「能力不可用」（17 §7.2）** | "系统配置有误，请检查" |
| `CAPABILITY_MISMATCH` | Adapter 能力不满足要求 | "当前后端不支持此功能" |

---

## 3. 错误传播规则

```
Adapter 层错误  →  封装为 LocalMindError 子类  →  Core 不感知 Adapter 原始异常
Core 内部错误   →  直接抛 LocalMindError 子类    →  main.py 作为最后兜底
```

Adapter 捕获的第三方异常（如 `ollama.RequestError`）**必须**转换为 `ModelError` 再向上抛。
Core 代码中**禁止** catch 第三方库的异常类型。

---

## 4. 结果类型

对于可恢复的操作，不使用异常，用 Result 对象：

```python
from typing import Generic, TypeVar, Union

T = TypeVar("T")

class Result(Generic[T]):
    value: Optional[T]
    error: Optional[LocalMindError]

    @property
    def is_ok(self) -> bool: ...
    @property
    def is_err(self) -> bool: ...

    @staticmethod
    def ok(value: T) -> "Result[T]": ...

    @staticmethod
    def err(error: LocalMindError) -> "Result[T]": ...
```

**类型说明**：
- `Result.err(error)` 在运行时不需要 value，但静态类型检查器可能无法自动推断 `T`。
- 必要时由接收方注解返回类型，例如 `def retrieve(...) -> Result[list[MemoryChunk]]:` 中直接 `return Result.err(error)`。
- 如果类型检查器仍无法推断，可显式声明局部变量类型：`result: Result[list[MemoryChunk]] = Result.err(error)`。

**使用规则**：
- `ModelBackend.generate()` — 抛 `ModelError`；`MODEL_UNAVAILABLE` 等可通过 load/retry 恢复的错误应 `recoverable=True`，超时/解析失败等按具体场景决定
- `CloudAdvisoryBackend.advise()` — 抛 `LocalMindError`，不返回 `Result`。传输失败、超时或 5xx → `CLOUD_UNAVAILABLE`；解析失败 → `CLOUD_PARSE_ERROR`；429 → `CLOUD_RATE_LIMITED`，三者 `recoverable=True`。401/403 → `CLOUD_AUTH_INVALID`、3xx/其余 4xx → `CLOUD_ENDPOINT_INVALID`、外发时凭据缺失 → `CLOUD_CREDENTIAL_MISSING`，三者 `recoverable=False`。错误与异常详情不得包含凭据、Authorization、响应体或外发上下文原文。
- `PrivacyPolicy.prepare()` — 单个候选拒绝或替换是正常返回的 `PrivacyPreparation.denied` 项，不抛异常；仅当整包无法安全收敛（如单 package item/byte 上限）时抛 `SafetyDenied(code="SAFETY_CLOUD_BLOCK")`。它不创建 grant，也不发网络。
- `AuthorizationManager.create_user_grant()` / `create_policy_grant()` — 任务台账的累计轮数或边界扩张次数超限时抛 `CLOUD_BUDGET_EXCEEDED`；成功签发即吊销同 task 的旧活跃 grant。`create_policy_grant()` 收到非 `normal` 的有效授权风险时抛 `CLOUD_AUTHORIZATION_REQUIRED`，`details.reason="sensitive_policy_grant_forbidden"`、`recoverable=False`，且不得改变任何授权状态。App 正常分流不调用该方法；若防御性异常出现，使用 `cloud_consult phase="denied"` 运行事件记录接线缺陷，不写 `CloudAuditEvent`，不调用 `SideEffectGateway.record_denial()`。
- `AuthorizationManager.validate()` / `reserve_turn()` — 授权缺失、绑定不匹配、过期、轮数预算耗尽、冷却分别抛对应 `CLOUD_*` 错误；它不接受模型或 App 伪造的消费状态。
- `CloudBoundary.check_request()` — package/grant/usage 快照不一致或仍含未授权、敏感内容时抛 `SafetyDenied(code="SAFETY_CLOUD_BLOCK")`。上述任一失败均不得发网络。
- `SideEffectGateway.execute_cloud_turn()` — 仅在调用 `CloudAdvisoryBackend.advise()` 前将已预留 turn 转为消费；出站拒绝释放 reservation，网络失败或入站拒绝不退款并进入冷却。不得以 `Result` 吞掉这些边界错误。
- `SideEffectGateway.record_denial()` — 仅记录授权等待阶段的最小拒绝审计；只接受契约规定的 reason 枚举，不发网络、不预留或消费 turn、不改变冷却状态；非法 reason 抛 `SafetyDenied(code="SAFETY_CLOUD_BLOCK")`。
- `EmbeddingBackend.embed_documents()` / `embed_query()` — 返回 `Result`；本地 embedding 调用失败返回 `EMBEDDING_ERROR`（recoverable=True），不得抛出 transport 原始异常。
- `MemoryBackend.retrieve()` — 返回 `Result[List[MemoryChunk]]`；embedding 不可用、维度为 0、索引为空或 embedding 返回 `EMBEDDING_ERROR` 时必须降级到关键词检索，不得使整次 retrieve 失败。
- `MemoryBackend.store_episode()` — 抛 `LocalMindError(code="MEMORY_ERROR", ...)`（参数非法或存储失败）
- `MemoryBackend.save_summary()` — 抛 `LocalMindError(code="MEMORY_ERROR", ...)`（参数非法或写入失败）
- `ProjectRecordStore` 写入失败 — 抛 `LocalMindError(code="MEMORY_ERROR", ...)`；ProjectStore 的字段校验失败同样使用该错误码且 recoverable=True。
- `ToolBackend.execute()` — 返回 `Result[dict]`（可降级到错误提示）
- `ToolBackend.preflight()` — 无副作用；未知工具抛 `TOOL_NOT_FOUND`。文件路径逃逸、超限、类型错误和目标状态变化使用 `FILE_ERROR`（recoverable=True），`details.reason` 取值见 §2 的**闭集十一值**（`workspace_escape` / `target_state_changed` / `target_too_large` / …）。
- `SafetyBackend.check_dangerous()` — 返回 `SafetyVerdict`（不是异常也不是 Result）

---

## 5. 用户可见错误

每个抛给用户的错误必须满足：
1. `user_message` 是完整的中文句子，不是技术栈信息
2. 永远不要让用户看到 `KeyError: 'tool_name'` 或 `Connection refused` 之类
3. `details` 可包含技术调试信息，但仅供日志使用

```python
# ❌ 错误
raise ToolError(code="ERR", message="KeyError: tool_name", user_message="出错")

# ✅ 正确
raise ToolError(
    code="TOOL_PARAM_ERROR",
    message="Tool 'check_port' missing required param 'host'",
    user_message="操作参数不完整：缺少目标地址",
    recoverable=True,
    details={"tool": "check_port", "missing_param": "host"}
)
```
