# 04-p3-safety-hardening — 安全边界强化模块契约

> 状态：✔️ 完成
> 阶段：P3（强化安全层：三关检查、确认机制、口令锁定、危险操作链路打通）
> 性质：编码前必读。本契约定义 P3 安全层的升级行为边界。
> 前序依赖：`00-core-interfaces.md`、`00-error-contract.md`、`00-adapter-factory.md`、`01-p0a-main-loop.md`（含已标注的 P3 已知缺口）、P1/P2 已完成闭环。

---

## 0. 范围与不变量

P0a 的安全层有一个故意留的缺口：**非 `normal` 风险的操作直接拒绝**。这保证了 P0a 不会意外执行危险操作，但同时也让 `file.read` 这类合法但需要小心的操作在 P0a 完全不可用。P3 要做的是把这条硬拦截线替换成真正的**三层关卡**，让 sensitive 操作在满足条件时可以通过、dangerous 操作仍然被锁死。

**P3 做的 5 件事**：

1. 补齐 P0a 已知缺口：让安全检查能拿到意图上下文（intent_type、entities），不只是工具名和参数
2. 实现身份验证：口令设置、哈希存储、连续错误锁定
3. 实现确认恢复机制：需要确认的操作不再直接拒绝，用户可以在下一轮确认后继续
4. 实现三关检查（仅对高危操作触发）：相关性 → 必要性+正确性 → 身份确认
5. 移除 P0a 的 `sensitive` 硬拦截，替换为三关流程

**P3 **不做**的事**：
- 不接入 QwenPaw ToolGuard（L2 语义检测适配器**不在 P6 接入**，随工具生态（P7b 及以后）一并论证，接口已预留——P6 已于 2026-09-20 关闭且未接入。**该论证已于 2026-09-25 在 `17-p7b-mcp-qwenpaw-tool-ecosystem.md` §11 第 2 项完成，结论 = 延后**：v1 准入的外部工具**全部只读**且不引入带副作用的动态工具，L2 的收益面（语义危险检测）尚未出现；触发条件 = 首个带副作用的动态工具立项时，与 QwenPaw 原生 `skills_dir` 适配器同批）
- 不改 `RuleOnlySafetyBackend` 的 L1 硬规则（已经生效，保持不变）
- 不改 `CloudBoundary`（仍是 P0a stub，P4 才启用）
- 不实现多工具执行计划（仍是 P0a 的至多 1 工具）

---

## 1. 补齐 P3 已知缺口：SafetyPolicy 接收意图上下文

### 1.1 问题

`01-p0a-main-loop.md §9` 标注：`SafetyBackend.check_dangerous()` 的 operation 契约要求包含 `intent_type` 和 `entities`，但当前 `SafetyPolicy.check()` 仅从 `ExecutionStep` 提取 `tool_name`/`action`/`params`/`risk_level`。P3 实现三关中的"相关性"检查（Gate ①）和 L2 语义检测（P6）都需要知道原始意图。

### 1.2 方案

**扩展 `ExecutionStep`，不扩展 `SafetyPolicy.check()` 签名**：

在 `src/core/schemas.py` 中为 `ExecutionStep` 增加两个字段：

```python
@dataclass(frozen=True)
class ExecutionStep:
    tool_name: str
    action: str
    params: dict = field(default_factory=dict)
    risk_level: str = "normal"
    intent_type: str = "unknown"       # 新增：来自 IntentCandidate
    entities: dict = field(default_factory=dict)  # 新增：来自 IntentCandidate
    user_input: str = ""               # 新增：来自 InputEvent.text（Gate ① 对照用户原始输入）
    gate23_passed: bool = False        # 新增：App 在确认+身份验证通过后置 True（Gate ②+③ 证据）
```

`TaskPlanner.plan()` 从 `IntentCandidate` 复制这两个字段到 `ExecutionStep`。

`SafetyPolicy.check()` 签名不变，内部将 `step.intent_type` 和 `step.entities` 填入 operation dict 传给后端。

**优势**：不改 GuardedToolExecutor.execute() 签名（它已经接收 plan），不改 SafetyPolicy.check() 签名——只扩展数据载体。下游 P6 接入 L2 语义检测时数据流已经就绪。

> **实现注意**：`ExecutionStep` 是 frozen dataclass，不能原地 `step.gate23_passed = True`。App 在确认恢复路径中需用 `dataclasses.replace(step, gate23_passed=True)` 创建已授权副本；对多 step plan 需逐 step replace 后组装新 `ExecutionPlan`。此为实现细节，不影响架构契约。

### 1.3 影响范围

- `src/core/schemas.py` — ExecutionStep 加 4 字段（intent_type、entities、user_input、gate23_passed，均含默认值，向后兼容）
- `src/core/task_planner.py` — plan() 从 candidate 复制 intent_type/entities，从 context.current_input 复制 user_input
- `src/safety/policy.py` — check() 在 operation dict 中加 intent_type、entities；normal 跳过 Gate ①；sensitive/dangerous 执行 Gate ①（失败抛 SafetyDenied）
- 现有测试中构造 ExecutionStep 的位置——因有默认值，不传继续工作

---

## 2. IdentityVerifier：身份验证

### 2.1 当前状态

`src/safety/identity.py::IdentityVerifier` 是 stub——`verify()` 永远返回 `True`。P0a 不调用它。

### 2.2 口令设置（首次启动）

```python
class IdentityVerifier:
    def __init__(self, passphrase_config: dict) -> None:
        """
        passphrase_config 键：
        - hash_file: str  — 口令哈希存储路径，默认 "./data/.passphrase"
        - lockout_attempts: int — 连续失败锁定阈值，默认 5
        - lockout_minutes: int — 锁定持续分钟数，默认 10
        """
```

初始化行为：
1. 若 `hash_file` 指定的文件**不存在** → 视为**未设置口令状态**。`is_set()` 返回 `False`，`verify()` 返回 `True`（未设口令时不阻拦）。首次调用 `set_passphrase(plaintext)` 时写入文件。
2. 若文件**存在** → 读取哈希，进入已设置状态。

**不自动弹口令设置流程**——P3 为 CLI 阶段，由调用方（`run_p3.py` 或首次 `App.handle()` 启动时）提示用户设置。

### 2.3 口令存储

```
文件格式（单行）：<salt>$<hash_hex>
算法：SHA-256
流程：随机 16 字节 salt → PBKDF2-HMAC-SHA256(salt, plaintext, 100000 iterations) → hex
```

`salt` 和 `hash` 之间用 `$` 分隔。文件权限：不额外设置（Python 不跨平台控制文件 ACL），文档提示用户确保 data 目录不被他人读取。

### 2.4 验证与锁定

```python
def verify(self, passphrase: str) -> bool:
    """
    验证口令。
    - 未设置口令 → 返回 True
    - 已设置且在锁定期内 → 返回 False（不检查口令，直接拒）
    - 已设置且不在锁定期 → 验证口令
      - 正确 → 重置失败计数器、返回 True
      - 错误 → 递增失败计数器；达到 lockout_attempts → 记录锁定开始时间；返回 False
    """
```

锁定元数据存在内存中（不持久化——重启即解锁）。锁定期间 `verify()` 返回 `False`，并附带剩余锁定秒数供 `user_message` 提示"身份验证已锁定，请 X 分钟后再试"。

### 2.5 新增方法

| 方法 | 说明 |
|------|------|
| `is_set() -> bool` | 是否已设置口令 |
| `set_passphrase(plaintext: str) -> None` | 设置新口令，写入 hash_file。**仅在未设置时可用**；已设置后调用抛 `LocalMindError(code="CONFIG_ERROR", ...)` |
| `verify(passphrase: str) -> bool` | 验证口令（原 stub，现真实实现） |
| `locked_until() -> float \| None` | 当前锁定结束的时间戳，未锁定返回 None |

### 2.6 测试

使用 `tmp_path` 下的临时 hash_file，不影响真实口令文件。覆盖：未设置时 verify 返回 True → 设置后返回 False → 正确口令返回 True → 错误累计锁定 → 锁定期间 verify 返回 False → 锁定期满后可再试。

---

## 3. 确认恢复机制

### 3.1 问题

P0a 中 `PLAN_LOCAL + requires_user_confirmation=True` 直接返回"此操作需要确认后才能执行，当前版本暂不支持。"——操作被丢弃，无法在下一轮恢复。P3 需要让用户能在下一轮说"确认执行"，然后真正执行。

### 3.2 方案：App 持有"待确认任务"状态，绑定会话

`App` 新增属性：

```python
class App:
    _pending_plan: ExecutionPlan | None = None   # 待确认的执行计划
    _pending_session_id: str = ""                 # 创建待确认任务的会话（必须匹配才能恢复）
    _pending_task_id: str = ""                    # 待确认任务的 task_id
    _pending_intent_id: str = ""                  # 待确认任务的 intent_id
```

**确认词解析规则（单一规则，消除 §3/§4 矛盾）**：

输入先 `strip()`。按**首个空白符**（空格/tab）切分：第一段为候选确认词，剩余全部文本为口令（可为空串）。

```python
_CONFIRM_WORDS = {"yes", "y", "ok", "okay", "确认", "执行", "继续", "是", "确定", "好的", "行", "可以"}

tokens = raw_text.strip().split(maxsplit=1)
if not tokens or not tokens[0]:       # 空输入或纯空白 → 非确认
    is_confirmation = False
else:
    first_word = tokens[0].lower()
    is_confirmation = first_word in _CONFIRM_WORDS
    passphrase = tokens[1] if len(tokens) > 1 else ""
```

- 空白输入（`raw_text.strip() == ""`）→ `tokens` 为空 → `is_confirmation = False` → 交给 `InputNormalizer` 走正常流程（由其抛 `INVALID_INPUT`），不会触发 IndexError。

- `"确认"` → 确认 + 空口令
- `"确认 mypassword"` → 确认 + 口令 `"mypassword"`
- `"确认 我的 口令"` → 确认 + 口令 `"我的 口令"`（第二个 token 起全算口令）
- `"你好"` / `"yeah but not really"` → **不是**确认（首词不在确认词集合中，算法不进入确认路径）

**流程（含会话绑定）**：

```
handle(raw_text, session_id, project_id):

1. 如果 is_confirmation(raw_text)：
   a. 若 _pending_plan 为空 → **直接返回** "没有待确认操作。"。
      **不走正常流程**——输入中可能包含口令，进入模型/记忆路径会造成泄漏。
   b. 若 session_id != _pending_session_id → 
      拒绝："待确认操作属于其他会话，已取消。"；清空 _pending_*
   c. 提取 passphrase（见解析规则）
   d. 若 self.id_verifier.is_set() 为 False:
      → 返回 "此操作需要身份验证，但尚未设置口令。请先设置口令后再试。"
      （fail-closed：未设口令不放行敏感操作。清空 _pending_*）
   e. 若 not self.id_verifier.verify(passphrase):
      → 返回 "身份验证未通过，操作已取消。"；清空 _pending_*
   f. verify 通过 → GuardedToolExecutor.execute(pending_plan)
      （执行前将各 step 的 gate23_passed 置为 True——见 §4.2）
   g. 正常返回结果，清空 _pending_*

2. 否则（普通请求）：
   a. 清空 _pending_*（新请求覆盖旧待确认——用户改了主意）
   b. 走现有 8 步闭环
   c. 若 NextAction 是 PLAN_LOCAL：
      - 调用 `TaskPlanner.plan()` 生成 ExecutionPlan
      - **计算 effective_risk 并回写到 plan（关键——不回写则下游看不到真实风险）**：
        对 plan 中每个 step，通过 `executor.tool_backend.list_tools()` 查找 `ToolDef`。
        `effective_risk = max(step.risk_level 对应序数值, ToolDef.risk_level 对应序数值)`。
        用 `dataclasses.replace(step, risk_level=effective_risk)` 生成**风险已提升的 step**，再用新 steps 组装新 ExecutionPlan。
        **此 plan 是后续所有流程的唯一载体**——确认提示、Gate ①、Gate ③、Executor 都只看到这份风险已回写的 plan。
      - `effective_risk == "dangerous"` → 拒绝执行（ControlPolicy 已截住，此处冗余）
      - `effective_risk == "sensitive"` 或 `requires_user_confirmation=True`：
          把 ExecutionPlan 存入 _pending_plan
          设置 _pending_session_id = session_id
          不执行
          返回确认提示（含工具名、动作、脱敏参数、风险等级——见 §4.3 提示格式）
      - 否则（normal + 无需确认）→ 直接执行 executor.execute(plan)
```

**关键**：`effective_risk` 以 `ToolDef.risk_level` 为底线（`_effective_risk` 逻辑，复用 `guarded_executor` 的模块级函数）。ControlPolicy 的 `requires_user_confirmation` 可**额外**触发确认（如模型自报敏感或置信中等），但不能**豁免**——sensitive 工具即使模型标 normal，此处仍强制进入确认流程。Executor 的 `gate23_passed` 检查保留为冗余防线。
```

### 3.3 确认词列表

不调模型——硬编码关键词匹配（见上）。按解析规则：首词必须完全等于集合中某个值，不做模糊匹配。

### 3.4 约束

- 待确认任务绑定 `session_id`——跨会话确认被拒。
- 待确认任务的存活周期 = 仅下一轮**同一会话**的对话。非确认输入到达即作废（不累积）。
- 确认任务**不重新走 ControlPolicy**——计划已生成、已判定需要确认，确认后直接执行。
- `App.handle()` 仍只返回字符串、不抛异常。
- **口令不得写入记忆**：确认恢复路径不调用 `store_episode`（或脱敏后存储——去除口令部分）。口令不得出现在 AuditEvent 中（审计日志的参数脱敏规则已将 `passphrase`/`password` 类键值替换为 `***`，P3 沿用）。
- 口令不得写入普通日志：`logging` 调用中不包含 `passphrase` 变量。

### 3.5 测试

- 确认词识别正确（中文/英文变体）
- 非确认词不触发恢复
- 确认后走 IdentityVerifier 门禁
- 确认失败后 plan 被丢弃
- 新请求覆盖旧待确认
- P0a 拒绝路径（原先的"暂不支持"）变更为返回确认提示

---

## 4. 三关检查（Guard ①②③）

### 4.1 触发条件

**仅高危操作**（`risk_level` 为 `sensitive` 或 `dangerous`）触发三关。`normal` 操作跳过三关，直接走 L1 规则（当前行为，不变）。

### 4.2 Gate ①：相关性检查

**责任方**：`SafetyPolicy.check()` 在调用 `self.backend.check_dangerous()` **之前**执行 Gate ①。不委托给 Backend——这是 Core 拥有的策略，不应依赖后端实现。

**检查逻辑**：提取 `ExecutionStep.user_input` 的 token，检查 `step.params` 中是否至少有一个字符串值与用户原始输入有 token 交集。

- 无交集 → SafetyPolicy **直接抛** `SafetyDenied(code="SAFETY_RELEVANCE", user_message="此操作与当前任务无关，已阻止。")`（不使用 SafetyVerdict 返回值——SafetyVerdict 无 code 字段，Executor 无法区分 Gate ① 拒绝与 L1 拒绝）。GuardedToolExecutor 需捕获此异常、记录审计、再重抛。
- 有交集 → 继续调用 `self.backend.check_dangerous(operation)`，返回 SafetyVerdict。

**为什么抛异常而非返回 SafetyVerdict**：`SafetyVerdict` 只有 `{allowed, risk_level, reason}` 三个字段，没有机器可读的 `code`。若返回 `SafetyVerdict(allowed=False)`，Executor 无法判断拒绝来自 Gate ①（应为 `SAFETY_RELEVANCE`）还是 L1 规则（应为 `SAFETY_DENIED`）——两者在审计日志和用户提示上需要区分。Gate ① 是 SafetyPolicy 自身的 Core 规则（不委托 Backend），直接抛 `SafetyDenied` 是最清晰的方式。

**触发范围限定**：Gate ① 仅在 `step.risk_level` 为 `sensitive` 或 `dangerous` 时执行。`normal` 操作跳过 Gate ①——无字符串参数的普通工具（如 `system.get_time`）不应被相关性检查阻断。跳过时 SafetyPolicy 直接调用 `self.backend.check_dangerous(operation)` 走 L1 规则。

**分词**：SafetyPolicy 需要中英文分词能力。为避免安全层反向依赖 `src.memory.retrieval`（层次颠倒），P3 将 `tokenize` 函数提取到 `src/core/text_utils.py`（Core 自有，无后端依赖），供 `SafetyPolicy` 和 `retrieval.py` 共用。或 SafetyPolicy 内联一段极简实现（仅 `_CJK_RE` + `_WORD_RE` 正则，无新增文件）。Codex 二选一，约束：不引入 `src.memory` 依赖到 `src.safety` 或 `src.core`。

**定位说明**：Gate ① 能拦住"模型幻觉出跟用户输入完全无关的操作"——如用户要求查端口、模型却去读一个无关联文件。这是基于关键词的浅层检查，不是语义理解。真正的语义相关性检查需 P6 L2 语义检测。

**示例**：用户说"查一下 project-a 的端口" → tokenize 得 `{"project-a","端口",...}`；模型请求 `file.read`，`params={"path":"/etc/passwd"}` → `/etc/passwd` 与用户输入无 token 交集 → Gate ① 拒绝。若用户说"读一下 /etc/passwd 的内容" → 有交集 → 通过 Gate ①，继续 L1 检查。

### 4.3 确认提示格式

待确认操作的返回消息必须让用户**知情**（Gate ② 的核心要求）。提示格式：

```
⚠ 操作需要确认
工具：{tool_name}
动作：{action}
参数：{_redact(params)}
风险等级：{risk_level}

如需继续，请回复"确认 <口令>"。
```

- `tool_name`、`action`、`risk_level` 直接取自 ExecutionStep。
- `params` 经过 `GuardedToolExecutor._redact()` 脱敏（敏感键替换为 `***`），再展示。
- 多 step 的 plan（P3+）逐 step 列出。

**不展示**的内容：口令（不在提示中出现）、intent_type/entities（用户不需要看内部表示）。

### 4.4 Gate ②：必要性断言 + 用户确认

Gate ② 不靠模型自动判定（小模型不可靠），而是通过**用户二次确认**实现：向用户展示即将执行的操作详情并请求确认。这正是 §3 的确认恢复机制——`PLAN_LOCAL + requires_user_confirmation=True` 就是 Gate ② 的触发方式。

`sensitive` 操作 → App 在 `_handle_action` 中查工具注册表计算 `effective_risk=sensitive` → 强制创建待确认（不依赖 ControlPolicy 的 `requires_user_confirmation`）→ 显示确认提示 → 用户回复确认 → Gate ③ 触发。

### 4.5 Gate ③：身份确认

触发确认恢复时，在 GuardedToolExecutor 执行前调用 `IdentityVerifier.verify()`。

**P3 交互模式**（CLI 阶段，无 GUI 弹窗）：
- 用户输入确认词（如"确认"）
- App 检测到确认意图
- App 提示"请输入口令："——**需要单独的 read 交互**
- 用户输入口令
- verify 通过 → 执行；失败 → 取消

考虑 CLI 限制，口令交互可简化：确认后可再发一条 `handle()` 调用带口令（`raw_text = "确认 我的口令"`），App 检测确认词后从 raw_text 中提取剩余部分为口令。

实际实现建议：确认词之后的文本即口令。如用户输入 `确认 mypassword`，`确认` 触发恢复流程，`mypassword` 作为口令传给 `IdentityVerifier.verify("mypassword")`。

### 4.6 `dangerous` 操作的三关结果

`dangerous` 操作在 P3 仍**不可执行**，无论三关结果——`ControlPolicy` 对 `risk_draft=dangerous` 直接 `REFUSE`，不进入 PLAN_LOCAL 分支。P3 只打开 `sensitive` → 三关的大门。`dangerous` 的解锁留待后续阶段（需要更强的身份验证或人工审批流程）。

> **`dangerous` 的来源受闭集约束（2026-09-16）**：该值是产品级硬锁定（无用户补救路径），因此在 **`risk_draft` 解析层**——即模型产出的风险措辞这一路——**只能**由模型显式声明 `dangerous` 产生，**不得**由字段缺失、格式错误或未识别措辞构造（解析层归一化见 `12-risk-draft-closed-set.md` §2.4）。`sensitive` 同样是三值闭集的一员，`high` 等旧词表与未识别值一并归入该档。这条约束保护的是**可用性**：一个解析抖动不应把一次合法请求变成永久拒绝。
>
> **反向边界（2026-09-16 代码审查补）**：本条**不**豁免工具层的确定性升险。`preflight`（`07-p6a-observability-cli.md` §6.3）对工作区逃逸等确定性事实返回 `effective_risk="dangerous"` 并硬拒绝——那是 fail-safe，合法且必须保持；本节仅禁止**把模型措辞的不确定性**翻译成硬锁定。
>
> **`dangerous` 的语义已于 2026-09-16 收窄**（规范见 `13-approval-profile-high-impact.md` §1）：收窄后的定义是「越权 / 恶意 / 规避安全控制 / **无法形成有界目标**的破坏行为」，**明确排除**「重要 / 生产 / 规模大 / 复杂」这类措辞。合法但高影响的意图改由 `sensitive` 内的 `approval_profile` 承接。本节的三关流程、`REFUSE` 最高优先级、以及 `preflight` 的确定性升险**一律不变**。

### 4.6b `high_impact`（高影响批准档）在 P6 **不可执行**（2026-09-16 新增）

`sensitive` 档内部新增一条**独立的确定性批准轴** `approval_profile ∈ {standard, high_impact}`（来源：工具注册表静态声明 + `ToolBackend.preflight()` 动态声明；**模型无此字段**）。规范见 `13-approval-profile-high-impact.md`。

**与 `dangerous` 的区别在于「有补救路径」**：

| | 判定源 | P6 结果 | 补救路径 |
|---|---|---|---|
| `dangerous` | 模型显式声明 / 确定性 preflight | `REFUSE` | **无**（产品级硬锁定，解锁留待后续阶段） |
| `high_impact` | **仅确定性**（注册表 + preflight） | **扣留执行 + 不可执行草案** | **有**：只读分析、补充条件、生成草案；执行态待未来阶段另行启用 |

**P6 的硬约束**（三关流程**不**适用于此档，也不得被复用为放行条件）：

1. **零工具执行**——计划级 `approval_profile == "high_impact"` 时整份计划扣留（P6 不引入分段执行）；任一 step 为 `high_impact` 即计划级为 `high_impact`；
2. **不得建立待确认计划**（`_pending_plan` 保持 `None`）；
3. **`gate23_passed=True` 不能放行**——`high_impact` **不**进入 §4.7 的 `gate23_passed` 通道。P3 的「确认 + 口令」是一次确认，**不得**被当作高影响操作的放行条件；
4. `PreflightReport.requires_confirmation` **不得**因 `high_impact` 为真——它只由风险驱动，否则该操作会流进本节的确认链；
5. 扣留一律经 `executor.record_denial()` 留痕（`reason="high_impact_closed"`）。**扣留条件为 `approval_profile == "high_impact"` 且 `effective_risk != "dangerous"`——`normal` 与 `sensitive` 一视同仁**，不得写成 `sensitive and …`（否则 `normal + high_impact` 会落到「无需确认 → 直接执行」）；
6. **错误码的作用域**：`SAFETY_IMPACT_CLOSED`（`recoverable=False`）**只由 `GuardedToolExecutor.execute()` 的冗余防线抛出**；App 主线是**正常响应**（写审计 + 返回草案文案），**不抛异常**——`handle()` 有不抛异常的既有契约（§3.4）。

> **为什么 P6 不做条件验证**：上游要求的五条件（目标与范围锁定 / 备份恢复点 / 回滚方案 / 强身份验证 / 二次确认）中，只有「目标锁定」（`PreflightReport.target_key`）与「身份验证」（`IdentityVerifier`）有确定性载体；其余三条**无任何表示**，若由模型声明「已具备」即为被否决方自证（`12-risk-draft-closed-set.md` §0.2 第 1 条已否掉的缺陷）。故五条件固定为**未来执行态的前置条件**，P6 不评估。

### 4.6c 参数形状层（2026-09-18 新增）

三关管的是「这个操作该不该做」，不管「这个参数长得对不对」。参数形状层是本契约之前的**空层**（全链路无类型校验），2026-09-18 由 `15-tool-orchestration-hardening.md` §3 补上，位置与分工如下：

| 层 | 位置 | 判什么 | 失败后果 |
|:---:|---|---|---|
| **0 参数形状** | `validate_tool_call()` 纯函数：`ControlPolicy`（判定 ASK_USER / 失败 reason）、`TaskPlanner`（建步前）、`GuardedToolExecutor.execute()`（执行前冗余复核） | 工具名 ∈ 运行时闭集、参数键 ⊆ 声明的属性、必填齐全非空、类型匹配（**纯函数，无 IO**） | 前两处：不建 step + 确定性失败回复（不调模型）；执行层：抛 `TOOL_PARAM_ERROR` |
| 1 意图级 | `ControlPolicy` + `_upgrade_plan_risk` | `risk_draft` 闭集、注册表风险下界（只升不降） | ASK_USER / 确认 / REFUSE |
| 2 执行级 | `GuardedToolExecutor` → `SafetyPolicy` → `RuleOnlySafetyBackend` | 三关、dangerous、high_impact、sensitive+gate23 | `SafetyDenied` |
| 3 语义事实 | `ToolBackend.preflight`（各后端自己的 hook） | 只有后端知道的事实：工作区路径边界、目标存在性、内容长度 | 只升不降的 `effective_risk` → 硬拒 / 确认链 |

- **唯一实现**：形状校验只有 `validate_tool_call` 一份（`builtin_backend._missing_params` 已删除，见 15 §3.1）。参数**类型**永远不在 preflight 里判——那是形状层的事。
- **防线分层同构**：形状层在主防线上 fail-closed 到「不执行 + 显式失败」，在执行层上 fail-closed 到拒绝（`TOOL_PARAM_ERROR`），与 §4.7 的「主防线正确分流 / 冗余防线保证拒绝」完全一致。
- **不变的**：`ToolDef` 的风险语义、`effective_risk` 的来源与只升不降合成、preflight 的调用位置（仍在本节流程的 decisive 位置：`GuardedToolExecutor.execute()` 的注册校验之后、`_max_risk` 之前）。

---

### 4.7 GuardedToolExecutor 变更

P0a 阻断点（`effective_risk != "normal" → CAPABILITY_MISMATCH`）替换为：

```
validate_tool_call(ToolCallDraft(tool_name=step.tool_name, arguments=step.params), tool_defs)
  → 不通过则抛 TOOL_PARAM_ERROR（2026-09-18 新增，层 0 冗余复核，§4.6c；
     与主防线的校验共用同一函数，不写第二份实现）
  —— 此处**由 step 重建草案**再验：执行层只持有 ExecutionStep（`tool_name` + `params`），
     重建不引入第二份归一化（不解释原始 raw、不推断缺失参数），只是把同一份数据再验一次；
     重建后的 `tool_name` 若已不在当前 `tool_defs` 中同样判失败（`unknown_tool`）
effective_risk == "dangerous" → 拒绝（ControlPolicy 已截住，此处为防线冗余）
effective_profile == "high_impact" → 拒绝（2026-09-16 新增，见 §4.6b）：
  raise SafetyDenied(code="SAFETY_IMPACT_CLOSED", user_message="此操作属于高影响操作，当前阶段不执行。…")
  —— 位置在 dangerous 之后、sensitive 之前：dangerous 优先级更高，且 high_impact 必须
     抢在 gate23_passed 通道之前（不得被一次确认放行）
effective_risk == "sensitive"：
  - 若 step.gate23_passed is False → 拒绝：
    raise SafetyDenied(
        code="SAFETY_NECESSITY",
        user_message="此操作需要确认与身份验证后才能执行。",
        ...
    )
  - 若 gate23_passed is True → 放行到 SafetyPolicy.check() + ToolBackend
effective_risk == "normal" → 放行到 SafetyPolicy.check()（不变）
```

`effective_profile = max_approval_profile(step.approval_profile, tool_def.approval_profile, dynamic.approval_profile)`——只升不降，与 `_max_risk` 同一模式；来源与闭集读取规则见 `13-approval-profile-high-impact.md` §2。**本条是执行层的冗余防线**：主防线在 `App._handle_action()` 的 preflight 消费点（同 04 §3.2 的分工）。

闭集外的 `risk_level` 不可能到达此处（解析层归一化，`12-risk-draft-closed-set.md` §2）；`_RISK_ORDER.get()` 的兜底一律取**保守档**而非 `normal`（01 §8.2 已钉）。

**gate23_passed 的设置者**：仅 `App.handle()` 在确认恢复路径中、身份验证通过后，将待确认 plan 的每个 step 的该字段置为 `True`，然后传入 `executor.execute()`。其他任何代码路径不得置为 `True`。

**防线分层**：

- **主防线（App）**：模型标 normal → App 查注册表计算 effective_risk=sensitive → `replace(step, risk_level="sensitive")` 回写 → 强制创建待确认 → 用户确认+口令 → gate23_passed=True → 执行。模型降级无法绕过确认流程。
- **冗余防线（Executor）**：若上游因任何原因未设置 `gate23_passed=True`（不应发生，但防御纵深），Executor 对 sensitive 操作拒绝执行并抛 `SafetyDenied(code="SAFETY_NECESSITY")`。
- **参数维度的同构分层**（2026-09-18 补，§4.6c）：主防线在 `ControlPolicy`/`TaskPlanner`（校验不过就不建 step、不留副作用），冗余防线在 `GuardedToolExecutor.execute()`（同函数复核，抛 `TOOL_PARAM_ERROR`）。**接线错误不得伪装成功**——这是本契约在参数维度上要求 fail-closed 的理由。

> **该模式不只用于执行层**（2026-09-17 补）：云端授权同样按「主防线在 App / 冗余防线在持权对象」分层——`sensitive` 所致升级由 App 正常分流进 `AWAITING_AUTHORIZATION`（**不调用** `create_policy_grant()`），`AuthorizationManager` 只在被误调用时拒绝签发并抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"`。原则是共通的：**主防线负责正确分流、冗余防线负责在上游接线出错时仍然拒绝**；冗余防线抛出的错误**不得**直接抵达用户——App 侧捕获后转入授权等待（`handle()` 的不抛异常契约不变）。**痕迹通道两者也对齐**（2026-09-18 补）：执行层这一侧靠 `SafetyDenied` 沿既有错误链上抛、由 App 的既有错误路径留痕；云端那一侧靠**结构化运行事件**（`cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"`），**都不新增审计入口**——云端侧尤其**不得**写 `CloudAuditEvent`，因为 `record_denial()` 的四值闭集与「每条清理路径恰一条 / 终止语义」不变量只适用于**任务终止**路径（05 §3.2）。权威表见 `05-p4-cloud-advisory.md` §3.2、`12-risk-draft-closed-set.md` §3.4。

---

## 5. L1 规则确认 + L2 接口预留

### 5.1 L1 规则

`RuleOnlySafetyBackend` 已在 P0a 生效：禁止命令、路径、敏感信息正则三条规则。P3 **不改它**——只确认它被正确串联在 GuardedToolExecutor 的执行链路中（已在 P0a 到位）。

### 5.2 L2 语义检测接口预留

`SafetyBackend.check_dangerous(operation: dict) -> SafetyVerdict` 的 `operation` dict 在 P3 补全为：

```python
{
    "tool_name": str,
    "action": str,
    "params": dict,
    "risk_level": str,
    "intent_type": str,     # 新增（来自 ExecutionStep）
    "entities": dict,        # 新增（来自 ExecutionStep）
}
```

后续接入 `QwenPawSafetyBackend`（封装 ToolGuard）时，直接实现 `SafetyBackend` 接口，放入工厂即可。P3 不写 `QwenPawSafetyBackend` 代码——只确保**数据链路**已完整（ExecutionStep → SafetyPolicy → SafetyBackend），届时只需一个适配器文件 + 一行工厂分支。**接入阶段变更（2026-09-20）**：P6 已关闭且未接入该适配器，实际接入随工具生态（P7b 及以后，见 `project-plan.md` §六 与 `16-p7-practical-tools-capability-routing.md` §11）——本节其余内容（数据链路与工厂接缝）不受影响。**P7b 已立项（2026-09-25）但该适配器仍不在其内**：`17` §11 第 2 项给出结论与触发条件（v1 外部工具全只读 ⇒ L2 收益面未出现；触发 = 首个带副作用的动态工具立项）。**接入时仍需遵守 `00-adapter-factory.md:217` 的既有义务**（经 `read_approval_profile()` 归一化、不得自行放宽、`requires_confirmation` 只由风险驱动）。

---

## 6. 错误码补充

在现有错误码基础上，P3 确保以下三关专用码被使用（已在 `00-error-contract.md` 预留）：

| code | 触发场景 | user_message |
|------|---------|------|
| `SAFETY_RELEVANCE` | Gate ① 失败 | "此操作与当前任务无关，已阻止。" |
| `SAFETY_NECESSITY` | Gate ② 失败（用户拒绝确认） | "操作已取消。" |
| `SAFETY_IDENTITY` | Gate ③ 失败（口令错误或锁定） | "身份验证未通过，已阻止。" |

---

## 7. 配置

`config/default.toml` 中 safety 段现有配置不动：

```toml
[safety]
backend = "rule_only"
l2_enabled = false

[safety.l1_rules]
forbidden_commands = ["rm -rf /", "dd if=", "mkfs.", ":(){ :|:& };"]
forbidden_paths = ["/etc/passwd", "/etc/shadow", "C:\\Windows\\System32", "~/.ssh"]
sensitive_patterns = ['\b(password|passwd|secret|token|api_key)\s*=\s*\S+']
# 2026-09-24：本键只被 RuleOnlySafetyBackend（L1 硬规则）读取，不是凭据检测的通用配置面。
# 凭据检测的唯一真源 = src/safety/secret_scan.py（05 §2.3c.1），覆盖中文自然语言形态；本键为追加语义，不可清空绕过

[safety.passphrase]
hash_file = "./data/.passphrase"
lockout_attempts = 5
lockout_minutes = 10
```

P3 后 `IdentityVerifier` 真正读取这些配置，工厂传 `config["safety"]["passphrase"]`。

---

## 8. 测试要求

### 8.1 IdentityVerifier

- 未设置口令时 `is_set()` 返回 False、`verify()` 返回 True
- `set_passphrase()` → `is_set()` 返回 True
- 正确口令 → verify True
- 错误口令 → verify False
- 连续 5 次错误 → 锁定；锁定期间 verify 返回 False
- 锁定期间 `locked_until()` 返回有效时间戳
- 锁定期满后可再次尝试验证
- 已设置后再次 `set_passphrase()` → `CONFIG_ERROR`

### 8.2 确认恢复

- 确认词解析：`"确认"`（空口令）、`"确认 mypassword"`（口令）、`"yeah sure"`（非确认——首词不在确认词集合中）各种变体正确
- 会话绑定：会话 A 创建待确认 → 会话 B 发确认 → 拒（session 不匹配）
- 确认后口令错误 → `SAFETY_IDENTITY`，plan 丢弃
- 未设口令时确认敏感操作 → 提示先设口令（fail-closed），plan 丢弃
- 新请求替代旧待确认（同会话内）
- `PLAN_LOCAL + confirmation=True` 不再返回"暂不支持"，改为确认提示

### 8.3 三关 + GuardedToolExecutor

- `ExecutionStep` 新增字段有默认值——不传的旧测试不受影响
- `TaskPlanner.plan()` 正确复制 intent_type、entities、user_input（来自 MinimalContext.current_input）
- `SafetyPolicy.check()` 的 operation dict 包含 intent_type 和 entities
- **Gate ①**：params 中的字符串值与 user_input 有 token 交集 → 通过；无交集 → `SAFETY_RELEVANCE`
- **风险升级 + Gate ① 不绕过**：模型将 `file.read` 标为 normal → App._handle_action 查注册表计算 effective_risk=sensitive → `dataclasses.replace(step, risk_level="sensitive")` 回写到 plan → 创建待确认 → 用户确认+口令通过 → SafetyPolicy 看到 `step.risk_level="sensitive"` → **执行 Gate ①**（而非因 normal 跳过）。验证：params 与 user_input 有交集 → 通过 Gate ① 进入 L1；无交集 → SAFETY_RELEVANCE 阻止。确保风险回写生效、Gate ① 不会因模型标记 normal 而被跳过
- GuardedToolExecutor 对 `gate23_passed=True` 的 sensitive 操作放行
- GuardedToolExecutor 仍拒绝 dangerous（防线冗余）
- **确认提示格式**：提示含工具名、动作、脱敏参数、风险等级——验证脱敏生效（password 类键替换为 ***）
- **无待确认时拒收**：确认词格式输入 + 无 pending_plan → 直接返回"没有待确认操作。"，不进入模型/记忆路径（验证 store_episode 未被调用）

### 8.4 集成测试

`scripts/run_p3.py` — 端到端演示：设置口令 → 请求 sensitive 操作（如 file.read）→ App 查注册表计算 effective_risk=sensitive 并强制确认 → 用户确认 + 口令 → 执行 → 返回结果。

### 8.5 回归

现有 141 个测试继续全绿。`RuleOnlySafetyBackend` 行为不变。GuardedToolExecutor 审计日志不变。

---

## 9. 验收标准（P3 Done 定义）

1. `python scripts/run_p3.py` 走通"设置口令 → 请求敏感操作 → 确认 + 口令验证 → 执行"完整链路。
2. 确认恢复机制可交互：确认词触发执行、非确认词取消、口令错误拒绝。
3. 连续 5 次口令错误后锁定，锁定期内拒绝验证。
4. `python -m pytest` 全绿（含新增 P3 测试 + 现有 141 个测试）。
5. `ruff check .` 通过。
6. GuardedToolExecutor 仍是唯一副作用出口（Grep 确认 Core 无绕过）。
7. `src/core/**` 无对 `sqlite3` / `hashlib` / `src.models` / `src.memory` 的不当引用。

---

## 10. 实现清单

| 项 | 位置 | 说明 |
|----|------|------|
| ExecutionStep 扩展 | `src/core/schemas.py` | 加 intent_type、entities、user_input、gate23_passed（均带默认值） |
| TaskPlanner 传递上下文 | `src/core/task_planner.py` | plan() 从 candidate 复制 intent_type/entities，从 context.current_input 复制 user_input |
| SafetyPolicy 补全 operation | `src/safety/policy.py` | check() 在 operation dict 中加 intent_type、entities、user_input |
| IdentityVerifier 真实实现 | `src/safety/identity.py` | set/verify/lockout/is_set/locked_until |
| App 确认恢复 | `src/main.py` | _pending_plan + 确认词检测 + Gate ③ 调用 |
| GuardedToolExecutor 解禁 sensitive | `src/safety/guarded_executor.py` | dangerous 仍拒，sensitive 放行 |
| 演示脚本 | `scripts/run_p3.py` | 端到端：口令设置 + 敏感操作 + 确认执行 |
| 单元测试 | `tests/test_identity.py`、`tests/test_safety_policy.py`（扩展） | 覆盖 §8.1–8.3 |
| 集成测试 | `tests/test_main.py`（扩展） | 确认恢复 + 三关串联 |

---

## 11. 审查修订记录

| 日期 | 级别 | 审查发现（Codex） | 处理 |
|------|:---:|------|------|
| 2026-07-20 | 高 | 确认词规则自相矛盾：§3 要求完全等于确认词；§4 要求支持 `确认 mypassword`。按前者口令无法提交 | 采纳：§3.2 改为首 token 解析规则——第一个空白符前为确认词，剩余文本均为口令。纯确认词 = 空口令 |
| 2026-07-20 | 高 | 模型降级 risk_draft 可绕过三关：ControlPolicy 只看 candidate.risk_draft，Executor 内才计算真实风险。模型标 normal → 无确认 → P3 放行 sensitive | 采纳：§4.6 Executor 对 sensitive 校验 `gate23_passed`。确认+身份证据（gate23_passed）必须由 App 的确认恢复流程设置。模型降级 → 无确认 → gate23_passed=False → Executor 拒绝。补"模型标 normal 仍被 Executor 拒"的测试 |
| 2026-07-20 | 高 | 待确认任务未绑定会话：会话 A 的待确认可被会话 B 的"确认"执行 | 采纳：§3.2 `_pending_plan` 绑 `_pending_session_id`，跨会话确认拒并清空 |
| 2026-07-20 | 高 | 未设口令时 sensitive fail-open：verify() 在未设口令时返回 True，Gate ③ 名义存在实际失效 | 采纳：§3.2 确认恢复路径中，`is_set()` 为 False 时直接拒绝——"此操作需要身份验证，但尚未设置口令"。普通操作无需口令不变 |
| 2026-07-20 | 中 | Gate ① 循环自证：entities 和 params 来自同一次模型输出，比较二者几乎必然匹配，无法证明与用户请求相关 | 采纳：§4.2 Gate ① 改为对照 `ExecutionStep.user_input`（用户原始输入文本），用 token 交集判定。`user_input` 由 TaskPlanner 从 MinimalContext.current_input 复制。承认这是关键词级浅层检查、非语义理解，真正语义相关性需 P6 L2 |
| 2026-07-20 | 高 | 真实工具风险仍不能触发确认：ControlPolicy 只看 risk_draft，sensitive 工具标 normal 时 Executor 拒绝但不创建待确认，用户无法确认 | 采纳：§3.2 App._handle_action 中 PLAN_LOCAL 分支先查工具注册表计算 effective_risk，sensitive 强制创建待确认。Executor 的 gate23_passed 检查保留为冗余防线 |
| 2026-07-20 | 高 | Gate ① 无明确责任方：规约定义了规则但未指定谁执行 | 采纳：§4.2 指定 SafetyPolicy.check() 在调 Backend 前执行 Gate ①。分词函数提取到 `src/core/text_utils.py` 或内联，不依赖 `src.memory` |
| 2026-07-20 | 高 | 无待确认任务时确认词格式输入进入普通流程，口令可能写入记忆 | 采纳：§3.2 确认词格式 + 无 pending_plan → 直接返回，不进入模型/记忆路径 |
| 2026-07-20 | 中 | 确认提示未展示操作详情，用户不知即将执行什么 | 采纳：新增 §4.3 确认提示格式——含工具名、动作、脱敏参数、风险等级 |
| 2026-07-20 | 轻微 | 确认词示例与算法矛盾：`"yes but not really"` 按算法是确认但文档说不是 | 采纳：§3.2 示例改为 `"yeah but not really"`（首词不在确认词集，算法和文档一致） |
| 2026-07-20 | 高 | 三关专用错误码无法实现：SafetyVerdict 无 code 字段，Executor 无法区分 Gate ① 与 L1 拒绝 | 采纳：§4.2 Gate ① 改为 SafetyPolicy 直接抛 `SafetyDenied(code="SAFETY_RELEVANCE")`。Executor 捕获、记审计、重抛。normal 操作跳过 Gate ① |
| 2026-07-20 | 中 | 确认解析空输入：`raw_text.strip()` 得到空串时 `split` 返回 `[]` → `tokens[0]` 触发 IndexError | 采纳：§3.2 解析规则加 `if not tokens` 保护，空输入 → 非确认 → 交 InputNormalizer |
| 2026-07-20 | 中 | Gate ① 未限定触发范围：normal 工具也可能被无参匹配阻断 | 采纳：§4.2 明确 Gate ① 仅在 sensitive/dangerous 时执行，normal 直接走 L1 |
| 2026-07-20 | — | 实现注意：frozen dataclass 不能原地赋值 gate23_passed | 采纳：§1 加 `dataclasses.replace()` 提示 |
| 2026-07-20 | 高 | 模型标 normal → App 算 effective_risk 后未回写 step.risk_level → SafetyPolicy 仍看到 normal → 跳过 Gate ① | 采纳：§3.2 App 计算 effective_risk 后用 `dataclasses.replace(step, risk_level=effective_risk)` 回写；此 plan 是后续唯一载体。补"风险回写后 Gate ① 执行"测试 |
| 2026-07-20 | 轻微 | §8 测试描述仍说 `"yes but not"` 非确认（首词 yes 在确认集中，算法会识别为确认） | 采纳：改为 `"yeah sure"` |
