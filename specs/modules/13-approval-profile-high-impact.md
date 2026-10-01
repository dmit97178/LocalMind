# 13-approval-profile-high-impact — `dangerous` 语义收窄与高影响批准档契约

> **状态：✅ 待实现**（2026-09-16 立项，Claude 裁决，Codex 实现）
> **依赖**：`04-p3-safety-hardening.md`（§4.6/§4.7 三关与危险语义）、`07-p6a-observability-cli.md`（§6.3 preflight 能力）、`08-p6b-evaluation-loop.md`（§2.3 S03 场景口径）、`12-risk-draft-closed-set.md`（§1.2 三值语义、§2 归一化）
> **上游**：`clarifications.md` 条目「`sensitive` 高影响约束与 `dangerous` 语义收窄」（2026-09-16，boss 提出）
>
> 本契约**不新增**模型能力、**不新增**安全机制、**不改变**任何既有不变量（deny_cloud / PrivacyPolicy / CloudBoundary / 出站预览 / 用户 grant / 预算 / 冷却 / 敏感执行链 / 回流后本地重判 / L1 规则 / 三层校验）。它把「合法但高影响」从 `dangerous` 的死路里拆出来，并**在 P6 内无条件关闭其执行态**。

---

## 0. 裁决摘要（对上游五点的逐条回复）

| # | 上游提议 | 裁决 | 依据 |
|:---:|---|---|---|
| ① | 公开风险三值不变，`dangerous` 收窄为越权/恶意/规避安全控制/无界破坏 | **采纳**，但**只改提示词语义**——闭集、归一化、消费规则零改动 | §1：收窄不移动任何**确定性**检查（`workspace_escape → dangerous` 属「越权」，语义恰好落在收窄后的定义内） |
| ② | `sensitive` 增加确定性批准档 `approval_profile ∈ {standard, high_impact}`，模型不得自行批准或降级 | **采纳形状；砍掉模型候选信号**（上游说「模型只能提供候选信号」，本契约进一步判：**连候选信号都不引入**） | §2.5：新增模型字段只带来「只能关不能开」的随机收紧，而它唯一能覆盖的形态（无注册工具的高影响意图）本来就零执行——白加一条提示词规则 + schema + 归一化 + 校准轮 |
| ③ | `high_impact` 至少要求五条件，任一缺失 → `ASK_USER` / 只读方案，不得 `REFUSE` 后结束 | **采纳目标；P6 不评估条件**——执行门**无条件关上**，条件列表降为「为什么不能执行」的说明，不做判定 | §3.4：五条件中只有 2 条（目标锁定 ← `PreflightReport.target_key`；身份验证 ← `IdentityVerifier`）有确定性载体，**备份/恢复点、回滚方案、范围锁定**无任何表示。让模型「声明已具备」即 `12 §0.2` 已否掉的**被否决方自证** |
| ④ | P6 若尚无验证能力，`high_impact` 只开放分析/补条件/不可执行草案，副作用执行保持关闭 | **采纳，并升级为机检**：用字段默认值 + 执行层防线把「P6 不开放执行态」变成**代码事实**而非文档记忆 | §3 |
| ⑤ | S03 原任务归「合法高影响但条件不足」验收 `ASK_USER`；否则改文本并另立高影响场景 | **改文本：采纳。另立场：偏离，改为直接构造的测试** | §5.1/§5.2：P6 内**无任何确定性触发源**能产生 `high_impact`，端到端场景只能靠模型措辞触发——那正是本次要消除的失败模式。**不得为场景通过而削弱 `dangerous` 硬拒绝** |

### 0.1 一处关键落点偏离（必须记录）

上游建议「ControlPolicy 应 `ASK_USER`」。**判定点不放 ControlPolicy**：

- `ControlPolicy.decide()` 是**意图级**、跑在 `TaskPlanner.plan()` 与 `preflight` **之前**；而批准档是**执行步**的确定性事实，只有在 plan + preflight 之后才知道；
- 且 Core 不得依赖工具实现（批准档来源是工具侧确定性事实，见 §2.2）。

落点与 `07 §6.3` 已有的 preflight 消费点是**同一处**（`main.py::App._handle_action` 的 PLAN_LOCAL 分支），与 `04 §4.7` 把确定性事实放在 App/执行层的既有分工一致。**可观测目标（用户被问到、零工具执行）完全保留**，只是不把工具知识上移到 Core。

### 0.2 两件必须照实说的事

1. **收窄有残余风险，不粉饰**：提示词收窄是**概率性**的，模型可能对「删库」类意图改说 `sensitive`，于是从 `REFUSE`（死路）变成一次确认即可执行。承接物是**不变的** L1 规则、工作区边界、执行层三层校验。置信度上**没有新增暴露类别**——原本模型说 `sensitive` 就已放过同名操作（`12 §0.2` 第 1 条），只是该类别略宽。因此：**「合法高影响」的确定性保护不建立在提示词上**，而建立在 §2/§3（批准档只升不降 + 执行态关闭）。这与 `12 §0.3`「schema 的 `enum` 是提示级约束，强制点只能是解析层」是同一条方法论。
2. **P6 内 `high_impact` 端到端不可达**：P6 不注册任何声明 `high_impact` 的工具（§2.5）。本契约的真实收益是三条——(a) **消除 S03 的结构冲突、恢复其有效评估**（见下）；(b) 合法重任务不再吃死路 `REFUSE`；(c) 在 P7 工具接入前**先把「未知值默认关门」这道棘轮装上**——否则将来第一个该是高影响的工具会静默继承 `sensitive` 的单次确认路径，且没有任何代码位置记录「这个决定从未做过」。

> **关于 S03，不得写成「确定性通过」**（照实澄清）：改文本消除的是 `dangerous → REFUSE` 与 `action_any=["ASK_USER"]` 之间的**结构互斥**——原文本下该断言**在构造上不可能达成**，S03 因此不是「难通过」而是「**不可能通过**」，其对渐进理解的评估能力是失效的。去掉破坏性框架后，S03 **恢复为一次有效评估**。但真实模型仍可能输出其它状态（不到轮次上限就收敛、低置信走别的分支、甚至乱执行被 `tool_none` 抓住），**通过与否仍由模型行为决定**。评估场景的本分就是**可失败**：把「消除结构冲突」表述成「保证通过」既不符合事实，也会诱导实现侧把红线读成待满足的指标。

---

## 1. 风险语义（`dangerous` 收窄）

### 1.1 不变的部分（先钉死，防止实现侧顺手放宽）

| 项 | 状态 |
|---|---|
| 闭集 `RISK_LEVELS = ("normal","sensitive","dangerous")` | **不变**（不新增第四档） |
| `normalize_risk_draft()` 与 §2.2 四条规则、`LEGACY_RISK_MAP` 三条映射 | **不变** |
| `read_risk()` 消费层总量规则（危险方向宽容 → `REFUSE`，其余 → `sensitive`） | **不变** |
| `dangerous → REFUSE` 最高优先级、force 不可绕过 | **不变** |
| 确定性升险 `preflight: workspace_escape → effective_risk="dangerous"`（`07 §6.3`） | **不变，且明确属于收窄后的定义**（越权 = 越过授权范围） |

本节是 `12 §2.4` 反向边界的**再次确认**：收窄只针对**模型措辞**，不针对确定性事实。

### 1.2 收窄后的 `dangerous` 定义

| 值 | 含义（**只**表达这一件事） |
|---|---|
| `dangerous` | 越权（超出授权范围）、恶意、**规避安全控制**，或**无法形成有界目标**的明确破坏行为 |

**明确排除项（必须逐字写进提示词）**——以下**都不**是 `dangerous` 的理由：

- 任务重要 / 关键 / 影响面大 / 涉及生产环境
- 任务规模大（全量、批量、整体）
- 任务复杂 / 篇幅长 / 推理困难
- 模型的自信程度高低

排除项的落点：这类意图若合法且有界 → `sensitive`；若无界但合法 → 仍 `sensitive`（P6 由 §3 的批准档或「无注册工具」承接，不由此处承接）。

### 1.3 残余风险的机检边界

必须在测试中钉死：**该收窄不得被实现成「确定性危险也可降级」**。断言方式（对应 §5.2）：

- `preflight` 返回 `effective_risk="dangerous"` 时，任何 `approval_profile` 取值都不改变结果——仍走 `SAFETY_DENIED` / `REFUSE` 路径；
- 提示词中「仅在确有把握是破坏性/不可逆/**越权**时使用 `dangerous`」这句**保留**（`12 §1.3` 第 5 条），收窄只**追加**排除项，不删除硬锁定语。

---

## 2. `approval_profile`：确定性批准档

### 2.1 值域与排序

```
APPROVAL_PROFILES = ("standard", "high_impact")     # 小写，规范化后的唯一合法取值
_APPROVAL_RANK    = {"standard": 0, "high_impact": 1}
```

- `standard`：既有 `sensitive` 单次确认链（P3 三关）即可放行的普通敏感操作；
- `high_impact`：一旦执行则影响面**不可由工作区边界约束**的操作。**P6 内执行态关闭**（§3）。

### 2.2 唯一来源（穷举，全部确定性）

| # | 来源 | 落点 | 说明 |
|:---:|---|---|---|
| 1 | **工具注册表静态声明** | `ToolDef.approval_profile`（`src/core/schemas.py`） | 由**开发者**在 `registry.py` 声明。P6 全部内置工具保持默认 `standard` |
| 2 | **工具后端动态评估** | `PreflightReport.approval_profile`（`ToolBackend.preflight()` 返回值，`src/core/interfaces.py` 契约） | 与既有 `effective_risk` 同一条标准化链路。P6 无实现产出 `high_impact` |

**穷举声明**：这两条是**全部**来源。**不得**由模型输出、配置文件、环境变量或 App 硬编码产生（若未来需要，属新契约）。

### 2.3 合成规则（与 `effective_risk` 正交）

对每个 step：

```
effective_profile = max_approval_profile(
    step.approval_profile,        # 上游写回值
    tool_def.approval_profile,    # 注册表静态
    dynamic.approval_profile,     # 后端动态 preflight
)
```

- **只升不降**，与 `_max_risk` 同一模式；实现同处 `src/safety/guarded_executor.py`（`_max_approval_profile`）。
- 计划级聚合：`PreflightReport.approval_profile = max over steps`（与计划级 `effective_risk` 同口径）。
- **正交性（两条真正独立的轴，已穷举，无第三档）**：

  | `effective_profile` | `effective_risk == "dangerous"` | 其余任意风险（`normal` / `sensitive`） |
  |---|---|---|
  | `standard` | 硬拒绝（**只由风险决定**，与批准档无关） | 走 `12 §3.1` 的既有本地分档 |
  | `high_impact` | 硬拒绝（同上——**扣留语义在此不可达**，不改变危险结论） | **扣留执行**（§3） |

  - **`dangerous` 优先级最高**：该行 `high_impact` 不产生额外语义，也**不得**被读成「批准档可以放行/加重危险」；
  - **`normal` + `high_impact` 同样扣留**（fail-closed）：`risk_level` 与批准档回答的是**两个不同问题**——前者是「是否触及敏感数据/需确认」，后者是「一旦执行影响面是否不可由工作区边界约束」。一个工具完全可以**无敏感数据、无需确认，却是高影响**（如集群故障转移：不碰凭据、不写文件，但影响面不可约束）。因此**不得**把扣留条件写成 `effective_risk == "sensitive" and profile == "high_impact"`——那会让 `normal + high_impact` 直接落到「无需确认 → 直接执行」，是本契约唯一可能的 fail-open 入口。机检见 §5.2 A9；
  - **`standard` 不产生任何语义**（不建 pending、不提示、不加确认），完全退回既有链路。

### 2.4 闭集读取：`read_approval_profile(raw: object) -> str`

**唯一实现**，与 `RISK_LEVELS` 同处 `src/core/risk_vocabulary.py`（若 Codex 认为需独立模块亦可，约束是**单一实现、无第二份手写判断**）。

| 输入 | 结果 | 理由 |
|---|---|---|
| `strip().lower()` 精确命中 `APPROVAL_PROFILES` | 该值 | 正常路径 |
| 其余任意输入（`None` / `42` / `"HIGH_IMPACT"` 以外的畸形值 / `""` / 未知字符串） | **`high_impact`** | **fail-closed 到最受限档** |

**与 `12 §2.1.1` 的对称性说明（防止实现侧照抄错方向）**：`12` 的兜底是 `sensitive`（三值中的**保守中间档**），因为那边兜的是「本地执行需确认」；这里兜的是「**直接关闭执行**」，保守方向就是**最受限档**。故此处**不需要**危险方向的方向性宽容——兜底值本身已是上限。

可达性：正常链路上不可能出现闭集外值（`step`/`tool_def`/`dynamic` 全部由代码或注册表构造）。本函数是给**未来适配器**（P7 MCP 等第三方工具后端）的防御，属接口层义务（§4）。

### 2.5 明确**不做**的（本契约的「薄」在这里）

| 不做 | 理由 |
|---|---|
| **不引入模型字段**（`impact_draft` 之类） | 上游说「模型可提供候选信号」，本契约进一步判定**不必且不该**：该字段只能**关闭**、不能放行，安全上无收益；而它唯一能覆盖的形态是「意图高影响但**无注册工具**」——那类意图本来就产生空计划、零执行（§0 第 2 条）。为它加一条提示词规则 + schema 键 + 归一化 + 映射表 + 校准轮，与「最薄」相悖 |
| **不新增配置面** | 批准档来源是代码/适配器，不是运行时配置。新增 `[safety.high_impact]` 之类会与既有 `l1_rules.forbidden_paths`（**拒绝**语义）产生命名与语义混淆 |
| **不扩展 `07 §2.2` 的封闭事件集** | `high_impact` 的留痕走既有 `executor.record_denial()` → `AuditEvent.reason`（`07 §6.3` 已规定「preflight 引发的拒绝一律经 `record_denial` 通道留痕」），报告可据此聚合。为 P6 不可达的档位新增事件键不值得 |
| **不注册任何 `high_impact` 工具** | P6 无验证能力（§3.4），注册即等于开放一个无法安全执行的档位 |

---

## 3. P6 的执行态：**无条件关闭**

### 3.1 判定优先级（插入点）

```
工具未注册 (TOOL_NOT_FOUND)
  → effective_risk == "dangerous"      → 硬拒绝（含 workspace_escape）  ← 最高，不可被 profile 影响
  → effective_profile == "high_impact" → 【新】扣留执行（**任意非 dangerous 风险**：
                                          normal 与 sensitive 都拦，零工具执行）
  → effective_risk == "sensitive" 且未 gate23_passed → SAFETY_NECESSITY
  → SafetyPolicy.check()（Gate ①/L1/L2）
  → 执行
```

> **扣留条件与风险值无关**（§2.3 正交性表的机检形式）：分支写作 `effective_profile == "high_impact"`，**不得**写作 `effective_risk == "sensitive" and ...`。`normal + high_impact` 必须同样落到扣留分支——这是本契约唯一的 fail-open 入口（§5.2 A9）。

- **App 主线**（`App._handle_action`，`src/main.py`）：在既有 `preflight` 调用与 `dangerous` 分支**之后**、`requires_user_confirmation` 分支**之前**插入 `high_impact` 分支。**顺序不可调换**——放到 pending 分支之后会让高影响操作建立待确认计划，从而被一次确认放行（上游明确禁止）。
- **执行层冗余防线**（`GuardedToolExecutor.execute()`）：与 App 同样的顺序插入。这是 `04 §4.7` 的既有模式（主防线 + 冗余防线）。

### 3.2 缺少安全条件时的动作（上游第 3 点的确定性形式）

**P6 不评估条件**（§3.4），因此动作是**无条件**的——触发条件是**计划级 `approval_profile == "high_impact"` 且 `effective_risk != "dangerous"`**（`normal` 与 `sensitive` **一视同仁**，见 §2.3）：

1. **零工具执行**——整份计划被扣留，**不做部分执行**（`plan.steps` 中任一 step 为 `high_impact` → 计划级 `approval_profile == high_impact` → 全计划扣留）。P6 不存在「只执行只读步」的路径：计划执行一直是全有全无，本契约不引入分段执行；
2. **不建立待确认计划**——`_pending_plan` 必须保持 `None`；
3. **不设置 `requires_confirmation`**——`PreflightReport.requires_confirmation` **只**由风险驱动（`07 §6.3` 既有规则），**不得**因 `high_impact` 为真。否则该操作会流进确认链；
4. **返回不可执行草案 + 诚实文案**（§3.3）——`normal + high_impact` 同样返回该文案，**不是**静默执行；
5. **审计留痕**——调 `executor.record_denial(plan, task_id, intent_id, "high_impact_closed")`，**只写审计 `reason`，不抛异常**（见 §4.1 的作用域钉死）。

> **计划级全有全无必须在通往 `execute()` 的每一条路径上成立**（2026-09-17 代码审查补）：「不做部分执行」是**计划级**性质，而执行层的冗余防线是**逐 step** 判定的（`04 §4.7`，它是 defense-in-depth，**不得**作为该性质的唯一保证）。因此凡在执行前拿到新的 `PreflightReport` 的复检点（App 执行前复检、确认流程的 TOCTOU 复检）**都必须**把 `approval_profile == "high_impact"` 一并纳入 fail-closed 判定，否则「pending 期间某步的动态批准档翻档」会让冗余防线先执行前面的步骤再拒绝后面的步骤。当前不可达（P6 无后端产出 `high_impact`），P7 接入第三方工具后端后成为真实窗口。判定点仍留在 App，不因此把执行层升为计划级（两种实现形态与取舍见 `specs/reviews/13-approval-profile-high-impact-review.md` F1）。

### 3.3 不可执行草案的文案要求

文案**必须**：

- 列出 `tool_name` / `action` / `_redact(params)` / `target_key`（若 preflight 提供）——沿用 `04 §4.3` 的知情原则；
- 列出五条件清单**作为原因说明**，并写明「**当前阶段不执行此类操作**」；
- 提供**真实可行**的下一步（要求只读分析 / 补充条件）。

文案**禁止的是「可执行的确认引导」，不是「确认」这个词**——五条件清单里本来就要写「二次确认」，禁词式规则会与本条自相矛盾：

- **禁止**：复用 `App._confirmation_prompt()` 及其特征串（「如需继续，请回复」+ 「确认 <口令>」形式）；口令输入提示；任何声称「确认后即可执行 / 即可继续 / 待你确认后执行」的措辞；引导用户进入 pending 的措辞；
- **允许**：说明性出现——「这类操作在启用执行前至少需要**二次确认**」「**确认**+身份验证是一次确认，不足以放行本类操作」等陈述句。

> **真防线不在措辞，在状态**：即使文案误导，用户下一轮输入 `确认 <口令>` 也只会走到 `_pending_plan is None` 的既有分支（返回「没有待确认操作。」），**不可能**执行——`_CONFIRM_WORDS` 只是入口，放行条件是有 pending 计划。因此机检以**状态**为主、文案为辅（§5.2 A5）。

### 3.4 五条件的地位（照实写）

| 条件 | 有确定性载体？ | P6 处置 |
|---|:---:|---|
| 目标与范围锁定 | 部分（`PreflightReport.target_key` / `target_exists`） | 不评估 |
| 强身份验证 | 部分（`IdentityVerifier`：口令 + 连续失败锁定） | 不评估——「强」的判定标准未定义，不声称已满足 |
| 二次确认 | 部分（P3 确认链） | **不评估，且明令不得复用**（上游第 4 点） |
| 备份 / 恢复点 | **无任何表示** | 不评估 |
| 回滚方案 | **无任何表示**（纯模型文本） | 不评估 |

**结论**：五条件是**未来执行态的准入前置条件**，本契约只把它们**固定下来**（防止未来阶段重新定义），**不**在当前实现任何判定。任何「模型说具备即通过」的实现都属违约——那是 `12 §0.2` 第 1 条已论证过的自证缺陷。

### 3.5 不得被确认放行（上游第 4 点的机检形式）

`gate23_passed=True` **不**构成 `high_impact` 的放行条件。执行层断言：

- 直接构造 `ExecutionStep(risk_level="sensitive", approval_profile="high_impact", gate23_passed=True)` → `GuardedToolExecutor.execute()` **必须拒绝**，抛 `SafetyDenied(code="SAFETY_IMPACT_CLOSED")`，审计 `verdict="denied"`，且**未调用** `tool_backend.execute()`。

---

## 4. 接口签名变更

| 变更 | 落点 | 兼容性 |
|---|---|---|
| `ToolDef` **尾部**新增 `approval_profile: str = "standard"` | `src/core/schemas.py` | 带默认值，既有位置构造与关键字构造**全部兼容** |
| `PreflightReport` **尾部**新增 `approval_profile: str = "standard"` | `src/core/schemas.py` | 同上（`builtin_backend` 的位置构造 `PreflightReport("normal", False)` 保持可用） |
| `ExecutionStep` **尾部**新增 `approval_profile: str = "standard"` | `src/core/schemas.py` | 同上 |
| 新增纯函数 `read_approval_profile(raw: object) -> str`；常量 `APPROVAL_PROFILES` | `src/core/risk_vocabulary.py` | 新增，无既有调用方 |
| 新增 `_max_approval_profile(*profiles: str) -> str` | `src/safety/guarded_executor.py` | 内部函数 |
| `GuardedToolExecutor.execute()` / `.preflight()` | 同文件 | **签名不变**；`execute()` 新增 `high_impact` 拒绝分支，`preflight()` 聚合计划级 profile |
| `App._handle_action()` PLAN_LOCAL 分支 | `src/main.py` | **签名不变**；新增 `high_impact` 分支 |
| `App._apply_preflight_risk()` | `src/main.py` | 改为同时写回 `effective_risk` 与 `approval_profile`（沿用既有 `replace` 车道） |
| 新增错误码 `SAFETY_IMPACT_CLOSED` | `src/safety/guarded_executor.py` + `00-error-contract.md` | `recoverable=False`；user_message 见 §4.1 |
| `_build_prompt()` 规则文本 | `src/core/intent_resolver.py` | 改写 `12 §1.3` 第 2 条定义 + 追加 §1.2 排除项；**schema 不变（不新增字段）** |

**无变更（明确声明）**：`ControlPolicy.decide()` 及其全部签名、`CloudControlState`、`CloudAdmissionDecision`、`evaluate_cloud_admission()`（**云端准入不因批准档改动**，与 `12 R2` 的非对称一致）、`TaskPlanner.plan()`、`NextAction.action` 闭集、`07 §2.2` 事件键集与 stage 集合、`IdentityVerifier`、`SafetyPolicy.check()`、`RegisteredTool` 结构、`config/*.toml`。

> `_INTENT_RESPONSE_SCHEMA` **不新增** `approval_profile` 键——这是 §2.5 的接口级表达。

### 4.1 新错误码与**作用域钉死**

| code | 抛出者 | 触发场景 | user_message |
|---|---|---|---|
| `SAFETY_IMPACT_CLOSED` | **仅** `GuardedToolExecutor.execute()`（冗余防线） | 执行层复评后 `effective_profile == "high_impact"` 且 `effective_risk != "dangerous"` | 「此操作属于高影响操作，当前阶段不执行。我可以先给出分析与所需条件。」 |

**作用域钉死（防止两处实现分叉）**：

- **App 主线不抛异常**。`App.handle()` 的契约是**只返回字符串、不抛异常**（`04 §3.4`），扣留是**正常响应**而非错误：App 分支只做两件事——`executor.record_denial(plan, task_id, intent_id, "high_impact_closed")` 写审计 + 返回 §3.3 的草案文案。**不构造、不捕获、不向上传播** `SAFETY_IMPACT_CLOSED`；
- **`SAFETY_IMPACT_CLOSED` 只由执行层的冗余防线抛出**，即「上游本应已扣留、却仍然把 `high_impact` 步送到了 `execute()`」这一**不应发生**的情形（`04 §4.7` 的防线分层模式：主防线在 App，冗余防线在执行层）；
- 两处的**审计 `reason` 统一为 `"high_impact_closed"`**（App 经 `record_denial`，执行层经自身 `_record`），使报告与 `/why` 不必区分来源即可聚合；
- **不得**让 App 也抛该错误（会破坏 `handle()` 的不抛异常契约），**也不得**让执行层退回静默返回（会丢掉冗余防线的断言能力）。

> 一致性机检见 §5.2 A5（App 路径：不抛异常 + pending 为 None + `record_denial` 已留痕）与 A3（执行层路径：抛该码 + 未调用 `tool_backend.execute()`）。

---

## 5. 验收

### 5.1 S03 场景（`08 §2.3`）——改文本，不改验收目标

**口径裁决**（Codex 在本文本内自选具体字串，须满足全部约束）：

- **必须保留**：缺对象/缺约束的信息不足题；`rounds_max = 4`；`action_any = ["ASK_USER"]`；`tool_none = true`；
- **必须移除**：任何「全量迁移 / 直接切换线上流量」式的**破坏性或不可逆**框架——它使模型合法地（在收窄前的定义下）输出 `dangerous`，于是 `REFUSE` 在第 1 步早裁，`ASK_USER` 断言**在结构上不可能达成**；
- **不得**为了让 S03 通过而放宽 `dangerous → REFUSE`（上游明确约束）。

> 判定依据（`08 §2.3` + `12 §4.2.3`）：`dangerous` 是第 1 步最高优先级早裁，与 `rounds` 上限和 `ASK_USER` 互斥。故冲突必须靠**改场景文本**消解，不能靠改策略消解。

### 5.2 高影响行为：**直接构造的测试**（对上游第 5 点的偏离）

新建 `tests/test_approval_profile.py`（并扩展 `tests/test_guarded_executor.py`）。**不**新增端到端场景，理由见 §0.2 第 2 条（P6 无确定性触发源；靠模型措辞触发等于重造本次失败模式）。

| # | 层 | 构造 | 断言 |
|:---:|---|---|---|
| A1 | 闭集读取单测 | `read_approval_profile` 全部输入（`"standard"`/`" high_impact "`/`"HIGH_IMPACT"`/`None`/`42`/`""`/`"critical"`/`"low"`） | 输出恒 ∈ `APPROVAL_PROFILES`；**闭集外值恒为 `high_impact`** |
| A2 | 合成规则单测 | `step=standard` + `tool_def=high_impact` | 结果 `high_impact`（只升）；反向 `step=high_impact` + `tool_def=standard` **不降级** |
| A3 | 执行层 | `ExecutionStep(risk_level="sensitive", approval_profile="high_impact", gate23_passed=True)` | `SafetyDenied(code="SAFETY_IMPACT_CLOSED")`；`tool_backend.execute` **未被调用**；`AuditEvent.verdict == "denied"` |
| A4 | 执行层（优先级） | `effective_risk="dangerous"`（preflight `workspace_escape`）+ `approval_profile="high_impact"` | 仍走 `SAFETY_DENIED`/dangerous 路径——**profile 不改变危险语义**（§1.3） |
| A5 | App 集成（sensitive 基线） | 自定义 `ToolBackend.preflight()` 返回 `PreflightReport(effective_risk="sensitive", requires_confirmation=True, approval_profile="high_impact")` | `handle()` **不抛异常**、返回 §3.3 草案文案；`App._pending_plan is None`；零工具执行；`record_denial` 已留痕 `reason="high_impact_closed"`；文案**不含**「如需继续，请回复」特征串与口令引导（说明性的「二次确认」允许出现）。**追加行为断言**：紧接着发一轮 `确认 <口令>`，仍返回「没有待确认操作。」且零执行 |
| A6 | 正交性 | `high_impact` + `requires_confirmation` 由 risk 驱动的既有用例 | `PreflightReport.requires_confirmation` **不**因 profile 为真 |
| A7 | **排除模型字段**（机检） | `dataclasses.fields(IntentCandidate)` / `_INTENT_RESPONSE_SCHEMA` / `_build_prompt()` 输出 | 均**不含** `approval_profile` 字样——锁死 §2.5，未来若要加模型字段必须显式改契约 |
| A8 | 提示词（`12 §4.3` 风格） | `_build_prompt()` 输出 | 含收窄后的 `dangerous` 定义 + §1.2 排除项（点名「重要/生产/规模/复杂」不是 `dangerous` 的理由） |
| A9 | App 集成（**`normal` + `high_impact` fail-closed**） | 同 A5，但 `PreflightReport(effective_risk="normal", requires_confirmation=False, approval_profile="high_impact")`，且 `next_action.requires_user_confirmation == False` | **必须扣留**（走 §3.3 草案文案），**不得**落到「否则直接执行」分支；`_pending_plan is None`；零工具执行；`record_denial` 已留痕。**变异探针**：把扣留条件写成 `effective_risk == "sensitive" and ...` 必须让本用例变红 |
| A10 | 执行层（`normal` + `high_impact`） | `ExecutionStep(risk_level="normal", approval_profile="high_impact")`，不经 App | `SafetyDenied(code="SAFETY_IMPACT_CLOSED")`；`tool_backend.execute` 未被调用 |

### 5.3 回归

- `tests/test_p3_safety_hardening.py`——`dangerous` 仍拒、三关不变；
- `tests/test_builtin_tools.py` / `test_guarded_executor.py`——`preflight` 默认 `standard`；**`file.write` 的 `risk_level` 与 `requires_confirmation` 期望值已按 P7a-0 反转**：新建与覆盖**都**为 `sensitive` / `requires_confirmation=True`（`07 §6.1`/`§6.3`），覆盖场景仍期望 `target_exists=True`、新建场景 `False`（**`target_exists` 只断言文案与 TOCTOU 快照，不再断言确认与否**）；
- 默认 pytest 与 `ruff check .` 全绿；无 §4 之外的改动面。

---

## 6. 需同步的文档（Claude 属地，随本契约一并完成）

| 文档 | 同步内容 |
|---|---|
| `CLAUDE.md` | 关键设计文档表新增 `13-approval-profile-high-impact.md` 一行（P6 编码前必读） |
| `project-report.md` | §4.3 概述工具确认链；高影响批准档、关闭执行态及其与 `dangerous` 的优先级由本契约定义 |
| `12-risk-draft-closed-set.md` | §1.2 三值语义表：`dangerous` 行改写为收窄后的定义 + 排除项；§2.4 反向边界处加指向本契约的链接 |
| `04-p3-safety-hardening.md` | §4.6 补危险语义收窄说明 + **新增 §4.6b**（`high_impact` 在 P6 不可执行、与 `dangerous` 的区别是**有补救路径**、5 条硬约束、错误码作用域：App 不抛异常 / 仅执行层抛 `SAFETY_IMPACT_CLOSED`）；§4.7 补执行层优先级插入点 |
| `07-p6a-observability-cli.md` | §6.3：`preflight` 能力与 `PreflightReport` 新增 `approval_profile`；确认/扣留分支的区分（高影响**不**建 pending）；事件字段**不变**（明确声明不扩展 §2.2 封闭集） |
| `08-p6b-evaluation-loop.md` | §2.3 S03 场景口径改为「非危险、信息不足的规划题」；§2.6 或场景说明处记录高影响行为**由直接构造的测试承接**、不设端到端场景及其理由 |
| `00-core-interfaces.md` | `ToolDef` / `PreflightReport` / `ExecutionStep` 三个数据结构的字段新增；`ToolBackend.preflight()` 返回值契约补 `approval_profile`（**签名不变**） |
| `00-error-contract.md` | 新增错误码 `SAFETY_IMPACT_CLOSED`，并注明**只由执行层抛出**、App 主线为正常响应不抛异常（§4.1） |
| `00-adapter-factory.md` | 仅在含默认值镜像处同步（`ToolDef` 默认 `standard`）；无 bootstrap 变更 |
| `specs/clarifications.md` | 对应条目移入「已解决」，保留裁决记录 |

---

## 7. 决策记录

| 日期 | 决策 / 发现 | 处理 |
|---|---|---|
| 2026-09-16 | 上游（boss）：`dangerous → REFUSE` 把「越权/恶意」与「合法但高影响」混为一类；倾向三值不变 + 收窄 `dangerous` + `sensitive` 增独立批准档 | 采纳主轴；三处判定：**只改提示词语义**（闭集/归一化零改动）、**砍掉模型候选信号**、**P6 不评估五条件**（执行门无条件关闭） |
| 2026-09-16 | 上游建议「ControlPolicy 应 `ASK_USER`」 | **偏离**：ControlPolicy 是意图级、跑在 plan/preflight 之前，Core 亦不得依赖工具实现；判定点落在 `App._handle_action` 的 preflight 消费处（与 `07 §6.3` / `04 §4.7` 同一分工），可观测目标不变 |
| 2026-09-16 | 五条件的可实现性 | 只有 2/5 有确定性载体；**不实现条件判定**——让模型声明「已具备」即 `12 §0.2` 已否掉的自证缺陷。条件清单固定为**未来执行态的前置条件**，P6 不评估 |
| 2026-09-16 | `read_approval_profile` 的兜底方向 | **未知 → `high_impact`**（最受限档）。与 `12 §2.1.1`（未知 → `sensitive`，保守中间档）**方向不同但同一条原理**：兜底取「更受限的方向」；此处兜底值即上限，故**不需要**危险方向的方向性宽容 |
| 2026-09-16 | S03 原任务「全量迁移 + 切流」 | **改场景文本**：该文本使 `dangerous`（第 1 步早裁）与 `ASK_USER` 断言**结构互斥**，冲突必须靠改文本消解，**不得**放宽 `dangerous → REFUSE` |
| 2026-09-16 | 上游要求「另立高影响行为场景」 | **偏离**：P6 无确定性触发源，端到端场景只能靠模型措辞触发（即本次要消除的失败模式）；改为**直接构造的测试矩阵**（§5.2 A1–A10），端到端场景待未来阶段真实注册 `high_impact` 工具后补 |
| 2026-09-16 | 收窄 `dangerous` 的残余风险 | **采纳并照实记录**（§0.2 第 1 条）：提示词是概率性的，可能使破坏性意图改说 `sensitive`；承接物是**不变**的 L1 规则、工作区边界、执行层三层校验；无新增暴露类别。确定性保护建立在 §2/§3，不建立在提示词上 |
| 2026-09-17 | **实现后代码审查（`specs/reviews/13-approval-profile-high-impact-review.md`，只审逻辑不重跑）**：主体通过——§1–§5 判定点全部落码，无 fail-open 入口（`normal + high_impact` 扣留条件不含风险值、`execute()` 的 dangerous 早裁在 high_impact 之前、闭集读取单一实现）。发现 1 中 + 3 轻微 | **① 中（F1）**：执行层冗余防线是逐步级，无法兑现 §3.2 第 1 条的「计划级全有全无」——在「pending 期间动态批准档翻档」窗口会先执行前面的步骤；当前不可达、P7 起可达。**契约侧裁定**：计划级性质必须在通往 `execute()` 的每条路径上成立，App 的执行前复检与确认流程的 TOCTOU 复检须纳入 fail-closed（§3.2 补段）；实现形态由 Codex 二选一；**② 轻微（F2）**：`execute()` 的 dynamic/static 两个批准档来源无用例，删掉参数变异可存活 → 补三来源参数化用例；**③ 轻微（F3）**：`_apply_preflight_risk` 对批准档为无条件覆盖、与风险 raise-only 不对称（当前可证不降级），且与 `12` 审查 F3 是同一处接缝 → 合并裁定；**④ 轻微（F4）**：三处「必须」缺机检（§3.3 五条件文案、A7 的 `dataclasses.fields`、§2.5 不注册 `high_impact` 工具） |
| 2026-09-16 | **二轮审查（boss）四处修正**：① §2.3 曾写「profile 只在 `effective_risk == "sensitive"` 时有消费语义」，与 §3.1 拦截全部非 `dangerous` 的流程自相矛盾；② §3.3 既要求列出含「二次确认」的五条件、又禁止文案出现「确认」，两条无法同时满足；③ §4.1 说 `SAFETY_IMPACT_CLOSED` 同时用于 App 主线与执行层，但 §3.2 规定 App 只写审计并返回草案；④ §0.2 称 S03 将「从概率性通过变为确定性通过」，与场景语义不符 | **四条全部采纳**：① §2.3 改为穷举的正交性表——`high_impact` 扣留**任意非 `dangerous` 风险**（含 `normal`），并点明 `normal + high_impact` 是本契约唯一可能的 fail-open 入口，补 §5.2 A9 变异探针（把条件写成 `sensitive and …` 必须变红）；② §3.3 改为只禁**可执行的确认引导**（`确认 <口令>` 形式 / 口令提示 / 声称「确认后即可执行」），**允许**「二次确认」等说明性出现，并写明真防线是 `_pending_plan is None` 这一状态而非措辞（A5 追加「照文案再发一轮确认仍不执行」的行为断言）；③ §4.1 钉死作用域——App 主线是**正常扣留响应**（只写 `reason="high_impact_closed"`，**不抛异常**，`handle()` 有不抛异常契约），`SAFETY_IMPACT_CLOSED` **只由 `GuardedToolExecutor.execute()` 冗余防线抛出**，两处 reason 统一；④ §0.2 改为「**消除结构冲突、恢复有效评估**」，并单列一段澄清**不得表述为确定性通过**——评估场景的本分是可失败，把结构修复读成待满足的指标会反过来诱导放宽红线 |
