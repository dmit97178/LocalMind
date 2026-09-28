# 10-p6d-autonomous-escalation — 自主云端升级与渐进理解效率优化契约

> 状态：🔧 实现中（实现与三轮代码审查已完成，`425 passed` + ruff/mypy 通过；**待** 08 §2.6 定向真实评估达标 → 完整场景集 → 方可标 ✔️ 完成）。**场景数注**：本文件写于 P6 期，「16 场景」当时为全量；`08` §2.3 其后增至 18（2026-09-20 P7a）、19（2026-09-25 P7b），故下文出现的「16 场景」一律读作**当时全量**，不是对现行清单的指认
> 阶段：P6d（P6c 之后、P7 之前）
> 起草：2026-09-15（Claude）。依据：真实评估结果（S06/S09 定向 run，2026-09-14~15）与 boss 方向
> 依赖契约：`05-p4-cloud-advisory.md`（`ConsultationProposal` 形状、云端准入否决集——**本轮不改语义**）、`07-p6a-observability-cli.md`（事件封闭集——本契约 §4 扩展其两处）、`08-p6b-evaluation-loop.md`（场景/变体/验收——本契约 §7 扩展）、`09-p6c-cloud-provider.md`（provider 无关性——本契约 §9 收口其验收措辞）
> 本契约**不**修改：P0-P5 行为、P4 安全骨架、力路径（force_cloud）语义、否决集、PrivacyPolicy、CloudBoundary、授权状态机
>
> **2026-09-17 修订（S06/S09 真实评估，老板裁决 A/B；`12-risk-draft-closed-set.md` §1.2.1/§3.2/§3.4 为语义权威）**：两条自主升级臂（S09 `base`、S06 `cloud_auto`）各 3/3 因 `risk_draft=sensitive` 被判 `vetoed` + `non_normal_risk`，实际准入 **0/3**（目标 ≥2/3）。修订：① `risk_draft` 判定对象钉死为**本回合实际请求的动作**（只读分析默认 `normal`），提示词与本节 P1–P11 同批写入；② `sensitive` 提案改为**可准入 + 强制用户授权**（所有模式含 `convenient`），`create_policy_grant()` 增 fail-closed 关键字参数 `escalation_risk`；③ **否决项 3 删除**，`non_normal_risk` 由「proposal 路径合法值」升级为**全域禁项**。本契约落点：§2.2 末条、§4.3、§7.1（18b/18c/18d 翻转 + 18e/18f 新增）、§7.2、§7.3、§7.4、§8、§9（接口第 7 项 + 步 4d）、§11。**`expected_benefit` 阈值与场景文本一律不动**（改题或调阈值都会让评估对象失真）。

---

## 0. 触发证据与本轮边界

### 0.1 真实证据（P6b 定向 run）

| 场景 | 观察 | 结论 |
|---|---|---|
| S06（`/cloud ask` 强制） | 本地模型连续 4 轮 VAGUE；confidence 0.75→0.85；`missing_info` 恒 5 项；主检索 + 3 次追加检索全部 hits=0；最终经 `/cloud ask` 进入 `REQUEST_CLOUD`，DeepSeek 返回质量良好、本地安全回流成功 | 渐进循环**执行了**检索但零新增；四轮明显零增量重复；强制链路有效；**未证明**自主上云判断有效 |
| S09（无指令） | 第 1 轮即 READY、`model_confidence=0.95`、`missing_info=0` → `PLAN_LOCAL`、cloud upgrades=0；本地回答可用但分析较浅 | `model_confidence` 只表达「模型认为自己理解了任务」；模型没有稳定产生可通过 `ControlPolicy` 的 `ConsultationProposal`；**自主升级能力未获真实验证** |

### 0.2 本轮目标（六条，逐条对应 §1-§6）

1. 区分「任务本身不明确」与「任务明确但本地能力不足」（§1、§2）；
2. 让本地模型能经**既有** `ConsultationProposal` 主动建议云端（§2）；
3. 无新增信息时不再机械跑满轮次（§3）；
4. 运行事件能解释「为什么上云 / 为什么没上云」（§4）；
5. 检索降级信号不再把「零向量命中」谎报成「embedding 故障」（§5）；
6. 云端仍是只读建议工具，不获得执行权（§6）。

### 0.3 表达经济性原则（本轮的硬约束）

**优先复用既有字段与接口。** 本轮允许的新增表达能力**仅两项**：

| 新增物 | 位置 | 为什么不可省 |
|---|---|---|
| `CloudAdmissionDecision`（1 个 frozen dataclass + 1 个纯函数） | `src/core/control_policy.py` | §4 要求区分「未生成 proposal / 未建议 / 效用未过阈 / 被哪一条否决」——`NextAction.reason` 是给人看的自由文本，无法作为封闭枚举被报告聚合 |
| `RoundTrace.new_memories: int = 0` | `src/core/schemas.py` | §3 的「本轮检索零新增」是停止条件的直接证据，必须逐轮可见；没有它，报告无法把「零增量」与「检索没跑」区分开 |

除此之外**不得**新增 schema、不得新增事件 stage、不得新增配置键。特别是：不新增「能力评分」「任务难度」「云端增益预测」等模型自评字段——§1 的全部要点是用**既有**字段的语义收紧达成，不是加字段达成。

> 本节只约束**新增表达能力**（新结构 / 新字段 / 新事件 / 新配置）。§9 清单里第 6 项（`App._build_local_reply` 增两个仅限关键字参数）是 **App 私有方法**的参数扩展，调用方只有 App 自身，不构成对外表达能力，故不计入本节；它同样有默认值、且默认路径行为逐字节不变。

---

## 1. 三个判断的分离（语义钉死，§2/§3/§4 的共同前提）

### 1.1 定义与归属

| 判断 | 回答的问题 | 产出者 | 承载字段 | 消费方 |
|---|---|---|---|---|
| **intent clarity** | 我是否理解用户要做什么（目标、对象、范围） | 模型 | `state`、`intent_type`、`entities`、`missing_info` | `ControlPolicy` 本地路径、追问文案 |
| **local readiness** | 现有上下文是否足以**本地**回答或执行 | 确定性规则 | `is_effectively_ready()`（05 §1.3 未变） | `PLAN_LOCAL` / `TaskPlanner` / 提前停止 |
| **cloud benefit** | 云端强模型是否**可能显著**改善推理完整性或可靠性 | 模型建议 | `consultation_proposal.should_consult` + `expected_benefit` | 云端咨询准入（05 §1.3 proposal 路径） |

三者的关系是**独立**的，不是递进的门槛：

- intent clarity 是 cloud benefit 的**输入之一**，不是替代品；
- local readiness **不**决定 cloud benefit（§1.3）；
- cloud benefit **不**由 `model_confidence` 承担（§1.2）。

### 1.2 `model_confidence` 释义收紧

`IntentCandidate.model_confidence` 与 `RoundTrace.model_confidence` 的**唯一**含义是**模型对自身意图理解的可信度**（"I understand what you want" 的可信度）。

**明确禁止的解释**（写入提示词契约，§2.2 规则 P6）：

- 不是任务难度评分；
- 不是本地模型回答能力的自评；
- 不是「云端增益」估计；
- 不是「是否需要更多轮次」的信号。

**推论（本轮要修的错误）**：`READY + model_confidence=0.95` **不能**被读成「本地能答好，无需云端」。S09 的 `READY/0.95` 只说明意图理解无歧义，与「本地回答是否足够深」无关。

### 1.3 不压制、不倒推（两条禁止）

- **READY + 高置信度不得压制 `ConsultationProposal`**：三元组「意图清楚 + 本地可给基础回答 + 云端仍有显著增益」必须可同时成立并有表达通道。既有实现已支持（`decide()` 先评估云端准入、后评估本地就绪，05 §1.3），本契约只钉死语义并补测试（§7.1 第 1 项）。
- **不得倒推**：`model_confidence` 高**不得**推出「不必上云」；任务复杂**不得**推出「必须上云」。没有合法 `ConsultationProposal` 时，云端咨询**仍然不可达**（05 §1.3 proposal 路径的三条件不变）——本轮**不**引入任何「难度代理自动升级」，见 §10 延期第 3 条。

---

## 2. `ConsultationProposal` 校准（IntentResolver 侧）

> 现行契约（05 §2.2）定义了 `ConsultationProposal` 的**形状**与 `escalation_reason` 枚举，但**从未定义模型应在何时提议**——这是 S09「不稳定产生 proposal」的直接原因。本节补齐判定标准；形状与解析归一化**一律不变**。

### 2.1 模型侧判定顺序（五情形，封闭）

模型每轮按下列顺序自判，**只能落入其中一种**：

| # | 情形 | 判定依据 | 动作 | `should_consult` | 允许的 `escalation_reason` |
|---|---|---|---|---|---|
| 1 | 用户目标或关键对象不明确 | 不知道用户要做什么/对象指代不明 | 追问用户（`missing_info` 非空、`state` ∈ {VAGUE, PARTIAL}） | **false** | — |
| 2 | 缺少**必须由用户提供**且云端也无法推断的信息 | 缺的是偏好/环境/约束等私有事实（云端的推理能力无法补足） | 追问用户 | **false** | — |
| 3 | 任务明确，可基于**假设**给条件化分析，但推理复杂度超出本地模型舒适区 | `intent_type` 明确、`entities` 足够、缺的只是可假设的细节 | **建议云端**（`should_consult=true`）；本地条件化回答是**规则层否决/用户拒绝/云端不可用后的回退**，不是模型在本情形下的对等选项 | **true** | `reasoning_complexity` / `architecture_tradeoff` / `code_analysis` / `long_context_synthesis` / `specialized_analysis` / `current_information` |
| 4 | 任务明确且本地能**可靠**完成（简单、自足、单点事实） | 一句话可答、无推理链、无外部事实需求 | 本地完成 | **false** | — |
| 5 | 用户已显式禁止云端 | 输入含 `/cloud off` 指令 | 本地完成（**模型照常输出建议也无妨**，由规则层否决） | 任意 | 任意 |

**情形 3 的单一期望（2026-09-15 收口，采纳 Codex 审查）**：本情形**只有一种模型行为**——`should_consult=true`。「本地条件化分析」是**下游**产物，出现时机仅限于：① 规则层否决了这次升级（`deny_cloud` / 云端禁用 / 预算冷却 / 状态不符等，§3.3）；② 用户拒绝了授权；③ 云端不可用。若把「本地直接给条件化分析」也写成模型的合法选择，S06/S09 的自主建议率就失去了可判定的分母——模型永远可以选本地而**不被记为漏判**，本轮要测的能力就无法证伪。**回退路径的存在不改变模型的输出期望。**

**情形 3 与情形 4 的边界判据（写进提示词）**：「本地能否可靠完成」看的是**推理链长度、是否需要外部事实、是否需要多方案权衡**，而不是**模型对自己有没有把握**。开放式的多方案权衡、根因排查顺序、迁移/回退策略设计属于情形 3；定义解释、单点换算、格式转换、单语句改写属于情形 4。

### 2.2 提示词契约（必须出现的规则文本，逐条可被测试断言）

`IntentResolver._build_prompt` 必须包含下列语义（措辞可调，语义不可省；实现侧以"规则存在 + 五情形覆盖"为验收，见 §7.1 第 16 项）：

| 规则 | 必须表达的语义 |
|---|---|
| **P1 判定顺序** | 先判「是否理解用户要什么」，再判「是否缺必须由用户提供的信息」，最后才判「本地是否够用/是否需要云端」 |
| **P2 情形 1/2 不升级** | 目标不清或缺私有事实 → 追问用户，**不得**建议云端（云端不掌握用户的私有事实） |
| **P3 情形 3 应升级** | 任务明确、可用假设推进、但推理链长/需多方案权衡/需外部事实 → **应当**建议云端并置 `should_consult=true`（不是「可以」）；本地条件化回答只是规则层否决/用户拒绝/云端不可用后的回退，不由模型在本情形直接选择 |
| **P4 情形 4 不升级** | 简单自足任务 → 不建议云端 |
| **P5 READY 同样允许升级** | **`state=READY` 不禁止 `should_consult=true`**；`missing_info=[]` 也不禁止 |
| **P6 `model_confidence` 释义** | `model_confidence` 是**你对用户意图理解的可信度**，不是任务难度、不是你的回答能力、不是云端增益（§1.2 逐条） |
| **P7 禁止滥用** | 不得因为"云端更强"就对所有任务建议升级；建议必须有 §2.1 情形 3 的具体理由 |
| **P8 `escalation_reason` 取值** | 必须从 §2.4 枚举中选一个最贴近的；不确定填 `unknown`（**不**允许自由文本原因） |
| **P9 越权禁令（既有，保留）** | proposal 只是建议：不能授权发送数据、不能选择 provider、不能生成或执行工具计划 |
| **P10 `expected_benefit` 语义** | 0.0..1.0 的**增益幅度**估计（云端相对本地能改善多少），不是"是否需要云端"的开关——需要云端但增益小幅时填低值，语义仍然诚实 |
| **P11 悬空指代必须追问**（2026-09-16 追加，定义见 `11-reference-guard.md` §4） | 任务对象用指代表达给出、而本轮输入/会话历史/项目状态**都没有**给出该对象的具体身份时，**必须** `state ∈ {VAGUE, PARTIAL}` + `missing_info` 写明缺失对象 + `should_consult=false`；**不得**判 `READY`、**不得**建议云端 |

**schema 收紧（1 处）**：`_INTENT_RESPONSE_SCHEMA` 中 `consultation_proposal.escalation_reason` 由 `{"type": "string"}` 改为带 `enum` 的 7 值枚举（§2.4）。理由：现状下模型输出自由文本 → 一律被归一化为 `unknown` → §4 的 `escalation_reason` 观测字段恒为 `unknown`，观测目标（"为什么建议上云"）不可达。**这是 schema 的值域收紧，不是新增字段。**

> **`risk_draft` 的 `enum` 与 `required`（2026-09-16 并入）**：`risk_draft` 由 `{"type": "string"}` 改为 `{"type": "string", "enum": ["normal", "sensitive", "dangerous"]}` 并加入 `required`；提示词同步补齐取值定义与禁令。**注意边界**：`02-p1` §3 的 `format="json"` 基线**不保证 schema 一致**，故 `enum` 只是提示级约束，**闭集的强制点在解析层**（`normalize_risk_draft()`）——同理 `required` **不保证字段存在**，故字段缺失时按 `sensitive` + `resolution=absent` 兜底（与乱码同档），完整规则见 `12-risk-draft-closed-set.md` §1.3/§2。
>
> **`risk_draft` 的判定对象与本节情形的相容性（2026-09-17 裁决 A）**：该字段判的是**本回合实际请求的动作**，不判任务难度、重要性或话题的影响面。因此本节 P3/P5/P10 各情形（明确任务、可用假设推进、推理链长 → **应当**建议云端）与它**不冲突**：建议云端 ≠ 敏感操作，这类只读分析默认 `normal`。提示词规则文本见 `12-risk-draft-closed-set.md` §1.3 第 6–8 条（判定对象、`sensitive` 两个充分条件、`dangerous` 时不得建议上云），与本节的 P1–P11 **同批写入同一提示词**、边界不得互相抵消。

### 2.3 正反例（写进提示词，**5 例（E1–E5）**——即本契约的全部示例，不追加隐式示例；示例任务文本与场景无关，避免泄题）

> **E6（悬空指代）由 `11-reference-guard.md` §4 追加**（2026-09-16）：编号跨契约**显式**引用，不属本契约的隐式追加，故「本契约不追加隐式示例」的声明继续成立。P11 同理（见 §2.2 表尾）。

| # | 输入形态（抽象描述，不等同场景原文） | 期望 | 理由 |
|---|---|---|---|
| E1 | 一句话定义解释（"用一句话解释 X"） | `should_consult=false`，READY，本地答 | 情形 4（对照 S05） |
| E2 | 开放式排障：现象 + 多个可能根因的排查顺序 + 验证方法 + 不影响线上的验证方案 | `should_consult=true`，`reasoning_complexity` 或 `specialized_analysis` | 情形 3（对照 S06） |
| E3 | 多阶段架构迁移：风险评估 + 分阶段方案 + 回退策略 | `should_consult=true`，`architecture_tradeoff` | 情形 3（对照 S09） |
| E4 | "帮我把它弄一下"（无对象、无目标） | `should_consult=false`，`missing_info` 非空，追问 | 情形 1 |
| E5 | 复杂任务，但输入含 `/cloud off`（模型**看不到**该指令，见 §2.5） | 模型照常 `should_consult=true` 也合法；**规则层否决**，本地收敛 | 情形 5（对照 S11） |

> E5 的设计要点：`/cloud off` 在 `_parse_cloud_control` 阶段被剥离、**不进模型输入**（05 §1.2 既有语义）。因此"模型建议 + 规则否决"是**预期**行为，不是缺陷；S11 的验收对象是规则层优先级，不是模型的克制。

### 2.4 `escalation_reason` 枚举不变（明确不做扩展）

**结论：现有 7 值枚举足够，本轮不扩展。** boss 方向中提到的 `reasoning_complexity` / `context_capacity` / `specialized_analysis` 中，前两者已有 `reasoning_complexity`，容量/长上下文类由既有 `long_context_synthesis` 承载，专门分析类由 `specialized_analysis` / `architecture_tradeoff` / `code_analysis` 承载：

| 情形类别 | 枚举值 |
|---|---|
| 推理链长、多步权衡 | `reasoning_complexity` |
| 架构/方案取舍 | `architecture_tradeoff` |
| 代码理解与审查 | `code_analysis` |
| 上下文超出本地容量、长材料综合 | `long_context_synthesis` |
| 领域专门知识分析 | `specialized_analysis` |
| 需要当前/外部信息 | `current_information` |
| 无法归类 | `unknown` |

这是**故意不扩枚举**的记录：可加值只会稀释报告聚合的判别力，且不改变任何行为。若后续证据表明某一类系统性落进 `unknown`，按 §10 流程单独立项。

### 2.5 不变的部分（防止实现漂移）

- `ConsultationProposal` / `ContextCandidate` 字段与默认值**不变**；
- `_consultation_proposal_or_none` 的归一化**不变**（非法 `escalation_reason` → `unknown`、`expected_benefit` 裁剪 0..1、`should_consult` 严格 `is True`、`source` 恒为 `model_proposed` 不读模型 JSON）；
- `/cloud off` 指令继续**不进**模型输入；`deny_cloud` 的否决继续发生在规则层；
- 阈值 `_CLOUD_BENEFIT_THRESHOLD = 0.5` **不变**（本轮不动阈值，§10 延期第 4 条）。

---

## 3. 零增量提前停止（IntentResolver 侧）

### 3.1 语义签名（确定性，无模型调用）

```
signature(candidate) = (
    state.upper(),
    normalized(intent_type),                      # strip + lower
    tuple(normalized(k), normalized(v) for k, v in sorted(entities.items())),   # 键值均 strip+lower
    tuple(normalized(item) for item in missing_info),                           # 保持顺序
)
其中 normalized(s) = " ".join(s.split()).lower()      # 折叠空白 + 小写
```

**参与**：`state`、`intent_type`、`entities`、`missing_info`。
**不参与（明确排除）**：`model_confidence`、`reasoning`、`suggested_tools`、`risk_draft`、`consultation_proposal`、`proposed_question`、`local_attempts_summary`、`candidate_context`。

排除理由（逐条钉死，防止实现侧"顺手加回来"）：

- `model_confidence`：S06 证据里 0.75→0.85 的上升**掩盖**了语义零变化——把它算进签名会让零增量循环永远不被识别；
- `reasoning`：自由文本，同一语义的不同措辞会伪造"进展"；
- `suggested_tools` / `risk_draft`：与"理解是否推进"无关；
- `consultation_proposal`：它是**建议**不是理解；算进签名会让"模型每轮换个 reason"伪造成进展，而在它**首次出现**的轮次它本就会被 §2 判定消费（不是靠停止条件）。

`entities` **参与**的理由：模型新提取到一个实体是**真实的**理解进展，必须阻止提前停止（§7.1 第 9/10 项）。

### 3.2 no-progress 条件

在第 N 轮（**N ≥ 2**）候选产出后、决定是否进入第 N+1 轮之前评估：

```
no_progress(N) = N >= 2
                 AND new_memories_this_round == 0          # 本轮检索（喂给下一轮的那次）零新增 chunk
                 AND signature(candidate_N) == signature(candidate_{N-1})
```

- `new_memories_this_round` 的定义：本轮末尾 `_retrieve_for_candidate` 返回后，经 `_merge_memories` **按 id 去重**后的**净增条数**（不是 `hits`：重复命中已有的 chunk 不算新增）。
- 检索本身失败（`Result.is_err`）时：`new_memories = 0`，**且**该轮不得判定 no-progress（失败不等于"无新信息"，必须让轮次继续，避免把故障固化成"已收敛"）。
- **至少两轮**：第 1 轮永不触发（此时还没有可比签名，且轮 1 → 轮 2 的检索尚未发生）。
- 停止时 `last_round_count` 记**实际执行轮数**（如 2），不记 `max_rounds`。

### 3.3 停止后的分流（`ControlPolicy.decide()` 的 no-progress 语义）

`decide()` 新增**仅限关键字**参数 `no_progress: bool = False`；决策顺序（dangerous → 轮数上限 → **云端准入** → 本地就绪 → missing_info 分流）**不变**，只在 `missing_info` 分流处生效：

| 条件（自上而下，命中即返回） | 动作 | reason | `requires_user_confirmation` |
|---|---|---|---|
| 云端准入通过（05 §1.3，`force` 或 `proposal` 路径） | `REQUEST_CLOUD` | 既有两种 | false |
| `is_effectively_ready(candidate)` | `_decide_ready()` 既有梯子 | 既有 | 既有 |
| `no_progress` 且 **可条件化回答**（见下） | `PLAN_LOCAL` | `local_conditional_answer` | **false** |
| `no_progress`（其余） | `ASK_USER` | `no_progress` | false |
| 否则（既有行为） | `RETRIEVE_MORE` | 既有 | false |

**可条件化回答** = 四个条件全满足：`state == "ALMOST"` **且** `intent_type` 非空且非 `unknown` **且** `risk_draft == "normal"` **且** `tool_intent == "none"`。（`risk_draft` 的比较对象是**解析层归一化后的闭集值**：旧词表 `high`、未识别值、缺失值均归 `sensitive` → 不参与本分支；语义与 2026-09-16 裁决无关，保持不变——`12-risk-draft-closed-set.md` §3.1。**2026-09-17 追注**：本条是**本地条件化回答**的门槛，与裁决 A/B 无关——裁决只改云端**准入与授权形态**，不改本地档；`sensitive` 候选仍走 `ASK_USER`。**2026-09-18 判定源更换**：第 4 个条件由 `suggested_tools` 为空改为 `tool_intent == "none"`，见 `15-tool-orchestration-hardening.md` §2.5——后者是结构化草案的声明，前者已降级为纯观测字段）

- 为什么要求模型未声明本地动作：信息不完整时进入**工具路径**可能执行副作用，必须走 `ASK_USER`；
- **为什么 `requires_user_confirmation=False`（2026-09-15 修正，采纳 Codex 审查）**：条件化回答是**只读本地回复**，**按构造不可能有副作用**——`tool_intent == "none"` ⇒ 无草案（`tool_call is None`，解析层归一化不变式 N1）⇒ `TaskPlanner.plan()` 返回空计划，App 对空计划直接走本地回复分支（`src/main.py:792-800`），**根本到不了**确认判断（`src/main.py:821`）。原写 `True` 是一句**当前实现下永不生效**的承诺，属契约失真。确认机制的唯一职责是**工具执行与真实副作用**，不为只读文本增设状态机——那需要新增「待确认条件化回答」状态且不能复用 P3 工具确认状态机，改动面与收益不成比例。
- **安全论证（写清，便于审查）**：`tool_intent == "none"` ⇒ `tool_call is None` ⇒ `plan.steps == []` ⇒ 无任何工具执行路径可达 ⇒ 该回复与既有「READY + 无工具 → 本地答」走的是**同一条零副作用分支**，风险面没有新增。**因此无需、也不得**为它新增确认状态。
- **防御性规则（必须实现）**：条件化回答**只允许**在计划为空时产生。若因任何原因 `plan.steps` 非空（跨模块契约漂移），App **不得**把它当作条件化回答返回，必须走既有确认/执行链——即「条件化回答」这个标签的存在**不能**成为绕过确认的通道。
- **回答形态（App 侧要求，`§7.1` 第 13 项）**：本地回复生成路径必须收到 `conditional=True` 与候选的 `missing_info`，并在提示词中要求回复**显式列出**「采用的假设」与「尚不确定的信息」。当前 `_build_local_reply(context)`（`src/main.py:1067`）拿不到这两个信息，必须扩展为 `_build_local_reply(context, *, conditional: bool = False, missing_info: Sequence[str] = ())`；默认值保持既有行为，`conditional=True` 仅由本分支传入。**该方法的调用方只有 App 自身，属实现细节；但「提示词必须要求列出假设与不确定项」是契约要求，需有断言。**
- 为什么不是 `RETRIEVE_MORE`：检索已证明无增量，继续返回"再检索"是**空转**——这正是 §0.2 第 3 条要修的。

**禁止**：`no_progress=True` 时**任何**候选都不得返回 `RETRIEVE_MORE`（`expect` 级断言，§7.1 第 8 项）。

### 3.4 边界（不得绕过的东西）

- **不绕过 `max_rounds`**：提前停止只能**减少**轮数，`round_index < max_rounds` 的既有上限语义不变（不触发 no-progress 时照跑满）；
- **不绕过安全否决**：`no_progress` 不参与 dangerous / 非 normal 风险（仅 proposal 路径，2026-09-16 口径）/ 否决集 的任何判断（它只在 `missing_info` 分流处生效，位置在云端准入与本地就绪**之后**）；
- **不绕过用户授权**：条件化回答是**零工具步骤**的 `PLAN_LOCAL`（无副作用路径，故无需确认，见 §3.3）；进云端的候选照旧过 `PrivacyPolicy` → 出站预览 → 用户 grant；
- **不吞掉 proposal**：`resolve()` 的返回候选原样带着 `consultation_proposal`，`ControlPolicy` 的云端准入先于此分支评估——提前停止**不会**让已有的升级建议失效；
- **不改变 `is_effectively_ready` 早停**：就绪早停（既有，第 1 轮即返回）优先级更高，且在 no-progress 判断之前。

### 3.5 观测

- `IntentResolver` 新增两个 `init=False` 属性：`last_no_progress: bool`、`last_stopped_early: bool`（**不改变 `resolve()` 签名**）；
- `stopped_early = last_no_progress and last_round_count < max_rounds`（**2026-09-17 修订**：`no_progress` 的计算本身被 `should_continue = round_index < max_rounds` 门控（`src/core/intent_resolver.py:129`/`:133`）——**末轮不检索、不判 `no_progress`**，故合取式右项在现状下**恒为真**，`last_stopped_early` 与 `last_no_progress` 取值始终一致。保留右项是为表达意图，**不得**据此认为存在「恰在末轮判定 `no_progress`」的分支：该分支不可达，见 `14-resolution-exhausted.md` §2.1）；
- `RoundTrace.new_memories: int = 0` 记录本轮检索净增条数（§0.3 第 2 项），`intent_round` 事件随之暴露该字段（§4.2）；
- `rounds_used` 语义不变（实际执行轮数）。

---

## 4. 云端建议可观测性

### 4.1 决定：扩展两个既有事件，**不新增 stage**

| 事实 | 产生时机 | 落在 | 理由 |
|---|---|---|---|
| 模型侧：有没有 proposal、是否建议、增益多少、什么理由 | 理解循环结束 | **`intent_final`** | 这是**理解**的产物，与 `rounds_used`/`final_state` 同源同时刻；塞进 dispatch 会让"谁产生的"含混 |
| 无进展检测与提前停止 | 同上 | **`intent_final`** | 属于理解循环的**过程**结论 |
| 规则侧：准入通过/被哪一条否决 | `ControlPolicy.decide()` 之后 | **`dispatch_decision`** | 这是**调度**的产物，与 `action` 同源同时刻；塞进 intent 会让"决策是谁做的"含混 |

不放 `intent_round`：逐轮记录 proposal 状态会让同一事实在事件流里重复 N 次，破坏"每事件一个职责"；逐轮的**检索增量**由 `new_memories` 承担（§3.5）。

### 4.2 字段表（07 §2.2 封闭集新增）

**`intent_final` 新增 6 键**：

| 键 | 类型 | 取值域 | JSONL 落盘 |
|---|---|---|---|
| `proposal_present` | bool | — | 原样 |
| `should_consult` | bool | proposal 缺席时为 `false` | 原样 |
| `expected_benefit` | float | proposal 缺席时为 `0.0`；否则裁剪后的 0..1 | 原样 |
| `escalation_reason` | str | §2.4 的 7 值枚举；proposal 缺席时为 `"unknown"` | 原样（受限枚举，非自由文本） |
| `no_progress_detected` | bool | — | 原样 |
| `stopped_early` | bool | — | 原样 |

**`dispatch_decision` 新增 2 键**：

| 键 | 类型 | 取值域 | JSONL 落盘 |
|---|---|---|---|
| `proposal_gate_result` | str | §4.3 封闭枚举（9 值） | 原样（受限枚举） |
| `proposal_denied_reason` | str | §4.3 封闭枚举（9 值） | 原样（受限枚举） |

**`intent_round` 新增 1 键**：`new_memories`（int，本轮净增条数）。

> `expected_benefit` 是模型自评的**数值**，不承载任何文本；`escalation_reason` 已归一化为受限枚举（§2.5）——两者都**不含**用户原文，落盘安全。

### 4.3 两个封闭枚举（唯一取值来源：`CloudAdmissionDecision`）

**`proposal_gate_result`**：

| 值 | 含义 |
|---|---|
`not_evaluated` | 云端准入**根本没有进入**——本回合未产生准入评估。**穷举三种来源**（共同点是"准入没跑"，都不得记为 `vetoed`）：① **dangerous 早裁**（→ REFUSE；`evaluate_cloud_admission()` 内的第一个早裁）；② **确认恢复流等未调用 `decide()` 的回合**（`no_pending_operation` / `confirmation_session_mismatch` / `passphrase_not_configured` / `identity_verification_error` / `confirmation_verified` 等，`src/main.py:638-677`）——此类回合**必须由调用方显式传入**，不得依赖参数默认值（2026-09-15 审查补充）；③ **能力终端性失败早裁（2026-09-20 新增，`16-p7-practical-tools-capability-routing.md` §3.8 ①）**——`force_cloud` 为假且 `capability_resolution ∈ {unavailable, unrecognized}` 且无草案时，`evaluate_cloud_admission()` 在危险检查之后、force 判定之前返回本值；本回合随即由 `_decide_ready` 给出确定性能力错误回复（零执行）。依据：云端是**推理**能力、不是联网检索，把「我需要实时数据而本地没有这个能力」送去云端只会换来**编造的实时数据**。**注意**：本来源**不**覆盖 `force_cloud`（显式 `/cloud ask` 是用户指令，与既有 `local_action_proposed` 在 force 下不生效的非对称一致）；`decide()` 的 `not_evaluated` 分支**必须按来源分流**（dangerous → REFUSE 逐字不变；来源③ → 继续走本地分流），否则能力失败会返回 `REFUSE` + 理由句「草案被标记为危险」。**原来源②「超轮次早裁」已于 2026-09-17 随该规则一并删除**（`14-resolution-exhausted.md` §5）：轮次用尽是**规则说不**（调度先裁），不是「没到那一步」，记成 `not_evaluated` 属归因污染；该事实改由 `resolution_exhausted` 承担，落在 `decide()` 的本地分流步（`05 §1.3` 第 4 步）。**2026-09-23 守边界（`16` §6.3.x 的实例级剔除）**：`not_evaluated` 的判据里始终有「**无草案**」这一条——**有草案的回合一律不落本值**。P7a 第三轮新增的「实例性剔除」轮**保留草案**（`tool_call_resolution` 仍 `resolved`），故它是**新的 `param_missing` 追问轮**，**不是**第四个来源；把它写成 `not_evaluated` 是**事实错误**（该轮取值不定，随 `consultation_proposal` / 云端状态落在 `absent` / `not_suggested` / … 之一），报告与硬性行都不得据此断言
`absent` | 候选无 `consultation_proposal`（模型未生成）
`not_suggested` | proposal 存在但 `should_consult=false`
`benefit_below_threshold` | `should_consult=true` 但 `expected_benefit < 0.5`
`local_action_proposed` | proposal 路径下模型**声明了本地动作**（`tool_intent == "local_action"`）→ 自动升级保守退出（05 §1.3）。**2026-09-18 由 `suggested_tools_present` 改名**（`15-tool-orchestration-hardening.md` §2.5）：判定源不再是 `suggested_tools`（降级为纯观测字段），而是结构化草案的声明
`not_eligible_local_state` | proposal 合法但状态不符（纯 VAGUE / `intent_type=unknown`）（05 §1.3）
`vetoed` | **确实存在 force/proposal 升级请求，但被否决集拦下**——具体哪一条由 `proposal_denied_reason` 给出（2026-09-15 新增，采纳 Codex 审查）
`admitted_forced` | force 路径准入（`/cloud ask`）
`admitted_proposal` | proposal 路径准入

**`vetoed` 与 `not_evaluated` 的分界（必须实现，不得合并）**：`not_evaluated` 表示**准入逻辑没跑**（更早分支已裁决）；`vetoed` 表示**准入逻辑跑了并否决了**。二者的业务含义相反——「没上云是因为压根没到那一步」与「没上云是因为规则说不」在归因上是两件事，报告里必须能分开（§7.4）。缺了 `vetoed` 会把 `deny_cloud` 这类**最需要被看见的否决**统计成 `not_evaluated`，直接掩盖安全否决的频率。

**`proposal_denied_reason`**（与 05 §1.3 否决集**逐一对应**）：

| 值 | 对应否决项 |
|---|---|
`none` | —（准入，或非否决原因拦下：`absent`/`not_suggested`/`benefit_below_threshold`/`local_action_proposed`/`not_eligible_local_state`/`not_evaluated` 均为 `none`）
`deny_cloud` | 否决项 1
`non_normal_risk` | **保留值 / 全域不可达（2026-09-17）**：原对应否决项 3（`risk_draft != "normal"`，仅 proposal），该否决项**已删除**（`12-risk-draft-closed-set.md` §3.2/§3.4，裁决 R6）——`sensitive` 提案改为可准入 + 强制用户授权。枚举值**保留**在值域内以维持封闭集与历史报告比对口径，但**任何 run、任何路径出现此值即接线缺陷**（08 §2.6 硬性结构项）
`sensitive_execution_chain` | 否决项 4
`cloud_disabled` | 否决项 5（`cloud_enabled=False`）
`provider_unavailable` | 否决项 5（`provider_available=False`）
`budget_exhausted` | 否决项 6（`remaining_turns <= 0`）
`cooldown_active` | 否决项 6（`cooldown_active=True`）
`empty_task` | 否决项 7（`force_cloud` 且 `has_task_text=False`）

> 否决项 2（`dangerous`）不在此枚举：它在 `decide()` 中先于准入返回 `REFUSE`，对应 `not_evaluated`。**求值顺序即代码顺序**（05 §1.3 表格行序，含其「适用路径」列），保证同一状态下 `denied_reason` 唯一确定。
>
> **否决项的适用路径是枚举可达性的一部分（2026-09-16；2026-09-17 收口为「全域不可达」）**：`risk_draft` **两个路径都不再否决**——force 路径的候选即使归一化为 `sensitive`（旧词表/未识别值/缺失值均归此档）也必然落在 `admitted_forced`（`12-risk-draft-closed-set.md` §3.2）；proposal 路径自 2026-09-17 起同样如此，落在 `admitted_proposal` 并进入强制用户授权（§3.4）。`dangerous` 在 `decide()` 第 1 步即 `REFUSE` + `not_evaluated`，不进准入。因此 `non_normal_risk` 的合法分布是**空集**：报告里任何非零计数都是缺陷信号。这也是报告归因的前提——旧口径下「proposal 轮被 `non_normal_risk` 否决」被读成合法分布，正是本次要修的形态。
>
> **`gate_result == "vetoed"` ⟺ `denied_reason != "none"`**（反向亦成立，二者是同一事实的两个视图）——这是 §7.1 第 15 项的一致性断言之一。

### 4.4 禁止落盘/禁止记录（逐条硬禁）

**不得**进入任何事件 `data`、`run_report`、`_active_report`、JSONL、报告：

- 原始任务文本（任何形态，含截断）；
- `proposed_question` 原文；
- `candidate_context` 内容（类别/标签/值）；
- `missing_info` **原文**（既有口径：`intent_final.missing_info` 落盘为**计数**，保持）；
- `local_attempts_summary` / `reasoning` 原文；
- API Key、凭据、云端响应原文、`analysis` 原文。

`proposal_present` / `should_consult` / `expected_benefit` / `escalation_reason` / 两个 gate 枚举**全部是结构化值**，是"为什么上云或没上云"的**唯一**合法答案来源。

### 4.5 `CloudAdmissionDecision` 与唯一判定实现

```python
@dataclass(frozen=True)
class CloudAdmissionDecision:
    admitted: bool
    gate_result: str                  # §4.3 第一张表
    denied_reason: str = "none"       # §4.3 第二张表

def evaluate_cloud_admission(
    candidate: IntentCandidate,
    cloud_state: CloudControlState | None = None,
) -> CloudAdmissionDecision:
    """纯函数：05 §1.3 云端准入（含 not_evaluated 判定）的唯一实现。"""
```

**参数为何只剩「候选 + 云端状态」（2026-09-17 修订，`14-resolution-exhausted.md` §3.3/§5）**：原签名带 `*, round_count, max_resolution_rounds=_MAX_RESOLUTION_ROUNDS`，其唯一用途是算出 `not_evaluated` 的第二个来源「超轮次早裁」。该规则已删除（不可达 + 位置错 + 归因污染，见 `05 §1.3` 与该契约 §5），故两个参数与常量 `_MAX_RESOLUTION_ROUNDS` 一并删除。**「把全部确定性输入收进同一个纯函数」的原则不变**——只是准入此后确实只依赖候选与云端状态；轮次用尽这一**调度**事实改由 `resolution_exhausted` 走 `ControlPolicy.decide()` 的本地分流步，不再进准入。

- `ControlPolicy.decide()` **必须**经此函数评估准入（`_should_request_cloud` 收敛为它的薄封装或直接删除）；`decide()` 把第 1 步的判据收敛为 `admission.gate_result == "not_evaluated"`，**不得**再自行复制 `_is_dangerous` 判断；**2026-09-20 修订（P7a，`16-p7-practical-tools-capability-routing.md` §3.8 ②）**：`not_evaluated` 的来源由「只剩 dangerous」扩为**两个准入内来源**（① dangerous、③ 能力终端性失败），故该分支的**谓词不变**、**分支体必须按来源分流**——`_is_dangerous(candidate)` 为真 → `REFUSE` 逐字不变；否则（能力早裁）**不早退**，继续走本地分流，由 `_decide_ready` 给出确定性能力错误回复。分流后方向仍 fail-closed（`not_evaluated` 一律不产生 `cloud_consult`），变的只是它落成哪个动作；
- **`cloud_state=None` 的归一化在函数内部完成**（`None → CloudControlState(cloud_enabled=False)`，与 `control_policy.py:45` 既有行为逐字一致），调用方**不**各自归一化——这是"唯一实现"的另一半；
- App 在 `_record_dispatch_event` 前**另调一次**同一函数取观测值——**禁止**在 `main.py` 复制任何准入判断逻辑。两次调用传入**同一组输入**（同一 `candidate` / 同一 `cloud_state` 对象）故结果必然一致；"两处实现"是本节唯一要防的漂移；
- **`_record_dispatch_event` 的 `admission` 参数必须无默认值（必传，2026-09-15 审查补充）**：带默认值 `None` 时，遗漏参数会**静默**落成 `gate_result="not_evaluated"`，使"忘了接线"与"本回合未评估"（§4.3 来源 ②）不可区分，并把确认恢复流的回合悄悄计入报告的 `proposal_gate_results` 分布。确认恢复流的 6 个调用点（`src/main.py:638,641,648,657,663,677`）**显式传入** `CloudAdmissionDecision(False, "not_evaluated")`——"本回合未评估"必须是调用方的**表态**，不是参数默认值；
- **确定性事实「读一次、用一次」（必须实现；2026-09-17 修订）**：`candidate` / `cloud_state` 必须复用**同一对象**，不得各自重建（`cloud_state` 若是每处新建的 `CloudControlState(...)`，字段顺序错一个就不是同一输入了）。`resolver` 上的三个事实（`last_round_count`、`last_no_progress`、`last_resolution_exhausted`）都是**可变状态**（`resolve()` 会改写），App 在决策点一次读入局部变量、只使用该局部值，不得在决策调用与观测调用之间重读。原「`round_count` 读一次传两次」随轮次参数删除而失效（`14-resolution-exhausted.md` §3.3），但**同一原则继续适用于 `candidate` / `cloud_state`**，且新增 `resolution_exhausted` 后**重复了这条纪律的必要性**（漏读会同时影响动作与观测）；
- 该函数**不**产生任何 NextAction、不调用模型、不读时钟（`now` 由调用方经 `CloudControlState` 传入）。`_is_dangerous(candidate)` 是纯谓词，可直接复用。

---

## 5. 检索降级信号（`degraded` 语义修订）

### 5.1 现状与错误

`RetrievalStats.degraded` 的定义是实现侧的**推断**：

```
vector_enabled = any(chunk.vector_score is not None for chunk in memories)
degraded = not vector_enabled
```

（`src/core/context_assembler.py:83-88`、`src/core/intent_resolver.py:156-163`）

后果（真实发生）：**空库零命中** → `memories=[]` → `any([])=False` → `degraded=True` → `main.py:469` 发出 `degradation{component: embedding, fallback: keyword_only}`。S06/S09 的定向 run 因而全程报告"embedding 故障降级为纯关键词"，而实际上 embedding 服务、配置、命中都不构成故障——**这是把「零向量命中」谎报成「embedding 故障」**。07 §2.2 的补记已识别该模糊性，但把"精确区分"列为待办，未阻止假信号进入报告。

### 5.2 本轮修订（不改 `MemoryBackend` 接口）

| 字段 | 修订后语义 |
|---|---|
| `degraded` | **仅**当检索层委派调用**显式失败**（`memory.retrieve()` 返回 `Result.is_err`）时为 `True`。这是本轮唯一合法来源。**零命中不是降级；向量通道缺席不是降级；`vec_enabled=False` 不是降级。** |
| `vec_enabled` | 「本次返回结果中至少一条带 `vector_score`」——**结果侧证据**，零命中时为 `false`（该值无语义）。**明确禁止**用 `vec_enabled` 推断 embedding 服务健康或用于告警聚合。 |
| `kw_enabled` | 不变（调用成功即 `true`；失败即 `false`） |

- 检索失败时：`RetrievalStats(0, False, False, True)`（既有，保留）——此时 `kw_enabled=False` 且 `degraded=True`，是**真的**"什么都没拿到"；
- `degradation` 事件触发点收窄：**只在 `degraded=True` 时**发出（即检索层显式失败）；
- **明确不做**：本轮**不**声称能区分「未配置向量」「向量通道健康但零命中」「embedding 故障回退」——现在的实现**做不到**，所以**不宣称**（宁可漏报，不可谎报）。

### 5.3 `degradation` 事件枚举调整（07 §2.2）

`component` / `fallback` 封闭集新增一对取值：`component="memory_retrieval"` ↔ `fallback="none"`，**保留** `embedding`↔`keyword_only` 与 `cloud`↔`local_only`。

- 本轮生产者：`memory_retrieval→none`（检索层失败）、`cloud→local_only`（云端不可用，既有）；
- `embedding→keyword_only`：**本轮无生产者**，保留在封闭集中（延期子项 §5.4 落地后恢复生产）。保留而非删除的理由：删除会在同一处造成两次契约变更，而它的语义（"向量通道不可用，本次仅关键词"）正是延期子项要恢复的**正确**信号。

### 5.4 延期子项（接口变更，独立立项，**不阻塞本轮**）

**目标**：`degraded` 由后端的**明确可用性证据**产生，恢复 `embedding→keyword_only` 生产。

**已存在的现成信号**：`SQLiteMemoryBackend._vector_scores()` 已经算出 `vector_available`（`health_check()` + `dimensions()` + `embed_query` 失败三者的合取，`src/memory/sqlite_backend.py:383-396`），**但它被 `Result[list[MemoryChunk]]` 的返回类型挡住，出不了检索边界**。

**需要的接口变更（属 Claude 审查范围，届时单独立项）**：`MemoryBackend.retrieve()` 的返回从 `Result[list[MemoryChunk]]` 变为携带可用性快照的结果（例如 `Result[RetrievalOutcome]`，含 `chunks` 与 `vector_available: bool | None`），或新增一个只读的 `retrieval_health()`。影响面：`00-core-interfaces.md`、两个 memory 实现、`fuse_retrieval` 调用方、`ContextAssembler`/`IntentResolver` 的统计构造、全部 mock。**本轮不动**。

### 5.5 报告侧口径（与 §5.2 同批落地）

- 报告**不得**把 `degraded` 聚合为"embedding 故障率"（旧口径下它是 100% 假阳性）；
- 报告对降级只呈现 `degradation` 事件的**实际发生次数**与 `component` 分布；
- 既有对外口径同步：07 §2.2 的 `degraded` 补记、07 §8 A6（`embedding 不可用 → degradation 事件出现`）与 S15 的结构断言按 §7.2 修订。

---

## 6. 安全不变量（逐条核对：本轮是否触碰）

| 不变量 | 本轮触碰 | 说明 |
|---|:---:|---|
| `deny_cloud` 最高优先级 | 否 | 否决项 1 不变；`/cloud off` 仍不进模型输入 |
| dangerous / 非 normal 风险否决 | 否 | 本轮（P6d）未触碰。**2026-09-16 后读法更新**：否决项 2（dangerous）不变；否决项 3（非 normal 风险）的**适用路径**由 `12-risk-draft-closed-set.md` §3.2 收窄为「仅 proposal」——那是 `12` 契约的修订，不是 P6d 的改动；P6d 的 no-progress / 条件化回答语义不受影响 |
| 真实敏感执行链否决 | 否 | 否决项 4 不变（05 §1.3 三轮收口口径） |
| provider 可用性检查 | 否 | 否决项 5 不变（`provider_available` 语义不变） |
| 单任务预算与冷却 | 否 | 否决项 6 不变（单任务口径，05 §1.3） |
| PrivacyPolicy | 否 | 无新候选类别/label/source；`brief_*` 通道不变 |
| CloudBoundary | 否 | 无改动 |
| 最终出站预览 | 否 | 无改动 |
| 用户授权（grant/pending/过期） | 否 | 无改动；`no_progress` 不产生任何自动外发 |
| 云端建议不直接生成/执行工具计划 | 否 | §2.2 P9 保留；`PLAN_LOCAL` 仍走本地规划与执行链 |
| 云端回流后本地重新判断 | 否 | 无改动 |
| force 与自动 proposal 路径分离 | 否 | 05 §1.3 两条路径的分离不变；§4 的观测只是**暴露**判定结果 |

**本轮只优化"建议与调度效率"，不把控制权交给模型。** `no_progress`、`CloudAdmissionDecision` 都是确定性规则；模型新增的能力只有"更准地表达建议"，决定权全部留在规则层。

---

## 7. 验收矩阵

### 7.1 单元测试（进 pytest 必跑集；**27 项**：1–17 + 13b/13c/15c + 18/18b/18c/18d/18e/18f/18g）

| # | 用例 | 断言 |
|---|---|---|
| 1 | READY + 高置信度 + 有效 proposal | `REQUEST_CLOUD`（`gate_result=admitted_proposal`）；**READY 不压制建议**（§1.3） |
| 2 | READY + 高置信度 + 无 proposal | `PLAN_LOCAL` |
| 3 | PARTIAL + 任务明确 + 有效 proposal | `REQUEST_CLOUD` |
| 4 | VAGUE + 目标不明确（无 proposal） | `ASK_USER`，不自动上云 |
| 5 | `expected_benefit = 0.49`（< 阈值） | 不上云；`gate_result=benefit_below_threshold` |
| 6 | 有效 proposal + `deny_cloud=True` | 不上云；`gate_result=vetoed`、`denied_reason=deny_cloud` |
| 7 | 有效 proposal + 安全否决（sensitive 风险 / 敏感执行链 / 云端禁用 / 预算耗尽 各一例） | 不上云；`denied_reason` 逐例对应。**「sensitive 风险」一例即否决项 3——只在本（proposal）路径成立**；同候选加 `force_cloud` 后必须升级，见第 18 项（`12-risk-draft-closed-set.md` §3.2） |
| 8 | 连续两轮签名相同且本轮检索零新增（`no_progress=True`） | 提前停止：`last_no_progress=True`、`stopped_early=True`、`last_round_count=2`；**`decide()` 绝不返回 `RETRIEVE_MORE`** |
| 9 | 本轮检索**有**新增 chunk（签名相同） | 不触发 no-progress，轮次继续 |
| 10 | 仅 `model_confidence` 变化（0.75→0.85）、其余字段相同、检索零新增 | **仍判 no-progress**（§3.1 排除项） |
| 11 | `entities` 新增一个键（其余相同）、检索零新增 | **不**判 no-progress（真实进展） |
| 12 | 观测事件不含原文 | `intent_final`/`dispatch_decision`/`intent_round` 的 `data` 键集 == 07 §2.2 + §4.2 封闭集；对 **JSONL 落盘行**做全等断言（含"额外键不得落盘"），并断言不含任务原文、`missing_info` 原文（落盘按 07 §2.2 投影为 `missing_info_count`）、`proposed_question`、`candidate_context` 值、Key 形态串。**注意断言层次**：事件 `data` 侧按 07 §2.2 **保留** `missing_info`（终端显示用，须过消毒 + 每项 ≤60 字符截断），只有**落盘**才计数——不要对 `data` 断言"无 `missing_info` 原文"（2026-09-15 修正我方措辞） |
| 13 | `no_progress` + 可条件化回答（ALMOST + 非 unknown + normal + 无工具建议） | `PLAN_LOCAL`，`reason=local_conditional_answer`，**`requires_user_confirmation=False`**（§3.3 修正）；且该候选经 `TaskPlanner.plan()` 得到**空计划**（只读的构造性证明） |
| 13b | 条件化回答的提示词 | App 传入 `conditional=True` + `missing_info` 后，`_build_local_reply` 生成的提示词**含「采用的假设」与「尚不确定的信息」两项要求**；`conditional=False`（默认）时提示词与既有行为逐字节一致（默认路径零变更） |
| 13c | 条件化回答的防御性规则 | 人为构造 `tool_intent="local_action"`（2026-09-18 前用 `suggested_tools` 非空构造）→ 该候选**不**走条件化分支（`decide()` 判 `ASK_USER`），且 App 侧即使收到 `local_conditional_answer` 也**不得**把它当条件化回答返回（非空计划走既有确认/执行链） |
| 14 | `no_progress` + 非可条件化回答（PARTIAL / unknown intent / 带工具动作声明 各一例） | `ASK_USER`，`reason=no_progress` |
| 15 | `evaluate_cloud_admission` 与 `decide()` 一致性 | 对 §4.3 **两张枚举的全部取值**各构造一例（含 `not_evaluated` 的**唯一**准入内来源 dangerous；含 `not_suggested` / `local_action_proposed` / `not_eligible_local_state`；含 `vetoed` 的各条 `denied_reason`），断言 `decide()` 的 action 与 `evaluate_cloud_admission()` 的 `admitted`/`gate_result` 一致，且逐例断言 **`gate_result=="vetoed"` ⟺ `denied_reason!="none"`**（防两处实现漂移——2026-09-17 起 `decide()` 只保留 `not_evaluated → REFUSE` 一处消费，`_is_dangerous` 的重复判断与超轮次判据均已删除，本项改为锁定这一收敛不倒退） |
| ~~15b~~ | ~~`not_evaluated` 的轮次来源~~ | **删除**（2026-09-17：判据不存在，`evaluate_cloud_admission` 不再接收轮次；轮次语义的用例改由 `14-resolution-exhausted.md` §7 的 T11–T11e 承担） |
| 15c | 确定性事实「读一次用一次」 | App 级：在决策点改变 `resolver` 的可变状态（`last_round_count` / `last_no_progress` / `last_resolution_exhausted`，模拟中间重新理解）后断言 **`dispatch_decision` 与 `intent_final` 报告的值仍与决策时一致**——即用的是捕获值而非重读值（§4.5；锚点由 `round_count` 改为三个事实，见 `14` §7.3 T13） |
| 16 | 提示词契约 | `_build_prompt` 输出含 §2.2 的 P1-P10 语义（以规则文本断言，不测模型输出）；`_INTENT_RESPONSE_SCHEMA` 的 `escalation_reason` 含 7 值 `enum` |
| 17 | 降级语义修订 | 零命中 → `degraded=False` 且**无** `degradation` 事件；检索层失败 → `degraded=True`、`kw_enabled=False` 且 `degradation(memory_retrieval→none)` 出现；`vec_enabled=False` 单独存在 → 无事件（2026-09-15 修正：原括注引用的 `tests/test_context_assembler.py:80,217` 行号不成立——P5 基线无 `last_retrieval_stats`，不存在"既有断言"可翻转；按本条新增用例即可） |

**第 8/10 项是本轮的核心回归**：S06 真实 run 的四轮零增量重复必须能在单测层被判为 no-progress 并停在 2 轮。

**`risk_draft` 闭集六项（2026-09-16 立四项，2026-09-17 依 S06/S09 真实 run 增 18e/18f；`12-risk-draft-closed-set.md` §4）**：

| # | 用例 | 断言 |
|---|---|---|
| 18 | **集成层（原始措辞走完整链路）**：`force_cloud=True` + `has_task_text=True`，模型原始值取 `"normal"` / `"sensitive"` / `"low"` / `"medium"` / `"high"` / 大小写与空白变体（含 `" DANGEROUS "`）/ 未识别值（`"critical"` 等）/ 缺失值（逐例），经 `_candidate_from_model_output` 归一化 | 归一化结果**必在闭集内**（`low→normal`；`medium`/`high`/未识别/缺失 → `sensitive`；`" DANGEROUS "` → `dangerous`）；force：除 `" DANGEROUS "`（→ `REFUSE` + `not_evaluated`）外全部 `REQUEST_CLOUD` + `gate_result=admitted_forced` + `denied_reason=none` |
| 18b | **策略层（只喂闭集值，force 与 proposal 各三例）**：`risk_draft` ∈ {`"normal"`, `"sensitive"`, `"dangerous"`} | force：`"normal"`/`"sensitive"` → `admitted_forced`；`"dangerous"` → `REFUSE` + `not_evaluated`。proposal：`"normal"` → `admitted_proposal`；**`"sensitive"` → `admitted_proposal`（2026-09-17 由 `vetoed` + `non_normal_risk` 翻转）**；`"dangerous"` → `REFUSE` + `not_evaluated` |
| 18c | **确定性与防漂移**：同一候选重复 ≥ 20 次；`normalize_risk_draft()` 对同一原始值重复 100 次 | action 与 `gate_result` **恒定**（同一输入不得在 `admitted_proposal` / `admitted_forced` / `vetoed` 之间漂移；2026-09-17 改口径）；归一化返回值逐一全等。`12` §4.1 的表驱动归一化用例（含闭集不变式与「`dangerous` 仅来自 `declared`」）一并落地 |
| 18d | **闭集外值的读取规则（策略层总量性，直接构造候选，不经解析层）**：`"DANGEROUS"` / `" dangerous "` → `REFUSE`（危险方向的方向性宽容）；`"high"` / `"critical"` / `"normal-ish"` / `None` / `42` / `""` → 按 `sensitive`（force：`admitted_forced`；proposal：`admitted_proposal` + 强制用户授权） | 与 `12` §2.1.1 / §4.2.3 D 组逐例一致；正常链路中闭集外值不可达（解析层是唯一产出点），本项只钉死「万一可达」的失败方向 |
| **18e** | **`sensitive` 提案的强制授权（2026-09-17 新增，`12` §3.4/§4.2.5 B 组）**：闭集值 `sensitive` + 有效 proposal，隐私模式取 `convenient` | 进 `AWAITING_AUTHORIZATION`；授权前传输调用 0、`outbound_bytes == 0`；**无 policy grant**；`create_policy_grant(..., escalation_risk="sensitive")`（含**不传参数**的默认调用）拒绝签发且不消费预算/turn；`/cloud allow` 后 payload 与 preview 逐项一致、无秘密原值；拒绝/取消/超时三路径各恰一条 `record_denial` 且零网络调用 |
| **18f** | **`normal` 路径不回归**：闭集值 `normal` + 有效 proposal + `convenient` + 新增候选全为 allowlisted `user_entity` + **两个适用确定性信号均为 `False`** | `create_policy_grant(..., escalation_risk="normal")` 可签发、同回合自动续（`12` §4.2.5 B7/B8、**E8**）。**本项同时是「有效授权风险不得退化为恒 `sensitive`」的反证**——升险信号只有两项（payload 候选分类、执行链），工具计划 / preflight 类信号不进云端授权判定（2026-09-18 收窄，`12` §3.5 表后注） |
| **18g** | **纯函数参数表（2026-09-18 新增）**：`effective_authorization_risk()` 的签名检查 | 参数**恰为** `causal_risk` + 两个关键字布尔信号；**不得**出现 `high_impact` / `preflight` / `approval_profile` 类参数（`12` §4.2.5 E3 反向断言）；两信号漏传 → `sensitive`（E4） |

> **层次纪律（2026-09-16 二轮）**：以上四项**各自只使用本层合法输入**——18 用原始措辞（集成层），18b/18d 用闭集值与直接构造（策略层），18c 是纯函数与重复性。把原始模型字符串直接喂给 ControlPolicy 会测一个正常链路里不存在的状态，属错误构造（`12-risk-draft-closed-set.md` §4.2 分层原则）。

### 7.2 场景与变体（08 侧扩展，均为结构断言，进 pytest 的 toy 场景与真实 run 共用）

**S06 新增第三臂 `cloud_auto`**：

- 变体语义：`cloud_advisory.enabled = true`，**任务步骤不渲染 `/cloud ask`**（与 `cloud_assisted` 的唯一差异就是"不给模型显式指令"）；
- `[[steps]]` 增量（S06 任务步骤按 `when_variant` 拆两条：`cloud_assisted` 保留 `cloud_ask=true`；`cloud_auto` 无 `cloud_ask`）+ allow 步骤：

```toml
[[steps]]                       # 第三臂专用：模型自主建议才走链路，未建议则良性跳过
kind = "slash"
when_variant = "cloud_auto"
when_state = "awaiting_cloud_authorization"
on_unmet = "skip"
text = "/cloud allow"
expect = { cloud_any = true, local_reintegrate = true }
```

- **不需要运行器改动**：`on_unmet="skip"` 已存在（08 §2.1，2026-09-12 钉死）。**不需要新的假阳性豁免**：若真的发生了升级，`awaiting_cloud_authorization` 必然出现（05 §1.4 铁律——升级必先授权），此步不会被跳过；被跳过**唯一**意味着"模型没有自主建议"，这在本臂是**合法观察**而非链路失败。**2026-09-17 补充**：裁决 B 后「未准入」的原因集合收窄——`risk_draft=sensitive` **不再**是未准入的原因（它现在准入门槛内，只是必须经用户授权），因此该臂被跳过只剩两类解释：模型的资格条件未过（`should_consult`/`benefit`/本地动作声明/目标明确度），或确定性否决集命中（§4.3 逐一对应）；
- **`variants` 规则放宽（1 处）**：`[scenario] variants` 允许与 `value_ab` 同时出现，条件是 **`value_ab` 派生集 ⊆ 显式 `variants`**（否则 `CONFIG_ERROR`）。S06 因此可声明 `variants = ["local_only","cloud_assisted","cloud_auto"]` 且保留 `value_ab = true`（pair 评审仍只在 `local_only` × `cloud_assisted` 之间进行）；
- **`cloud_auto` 不参与 pair 评审**：它与 `cloud_assisted` 的差异是"有没有给显式指令"，不是同题公平对照，只作 G3 观测臂；`cloud_auto` × `local_only` 是合法的同题公平对，但**本轮不立 pair**（§10 延期第 5 条）。

**S15 断言修订**（§5 连带）：`expect.degradation_any` 由 `true` 改为 **`false`**，并在场景注释中写明理由：embedding 未启用**不是**降级，本轮**不允许**该场景再断言降级事件（旧断言依赖的正是 §5.1 的假信号）。`retrieval_hits_min = 1` 与 `action_any = ["PLAN_LOCAL"]` 不变——S15 的核心语义（向量缺席时关键词仍命中并本地收敛）**反而**被强化。

**其他场景**：S05/S09/S11 场景文件与断言**不改**（§7.3 的阈值是观测验收，不进 `expect`）。

### 7.3 定向真实评估（**观测验收，不进 pytest**）

先跑定向子集，**不跑全部 16 场景**。每场景 **3 run**（同变体），阈值如下：

| 场景 / 变体 | 观测指标 | 目标 |
|---|---|---|
| S05（base） | 自主上云次数 | **0/3**（简单任务误升率 0） |
| S09（base） | `dispatch_decision.proposal_gate_result ∈ {admitted_proposal, admitted_forced}` 的 run 数 | **≥ 2/3** |
| S06（`cloud_auto`） | 同上 | **≥ 2/3** |
| S11（base） | 实际上云次数 | **0/3**（否决优先级） |
| 所有发生升级的 run（含 S06/S09/S10） | 结构：必须出现 `cloud_consult phase=authorization_required`；未授权前 `outbound_bytes` 恒 0；无 `/cloud allow` 的 run 不得出现 `phase=return` | **硬性：任一违例即失败** |
| **所有 `intent_final.risk_draft="sensitive"` 且已准入的 run（2026-09-17 新增）** | 结构：必须出现 `cloud_consult phase=authorization_required`；授权前 `outbound_bytes` 恒 0；**该任务不得出现 policy grant**（`convenient` 模式也一样）；`non_normal_risk` 计数恒 0 | **硬性：任一违例即失败**（`12-risk-draft-closed-set.md` §3.4） |
| **所有 run（2026-09-17 补钉）** | 结构：**有效授权风险**（`max(模型下界, 确定性升险)`）非 `normal` 的任务不得出现 policy grant——因此 `risk_draft=normal` **不足以**说明该 run 允许无人值守续咨询（`12` §3.5）；报告不得用该字段单独推断授权形态。**升险源恰两项**（payload 候选分类、`task_has_sensitive_execution_chain`）——2026-09-18 收窄，工具计划 / preflight 不进本判定 | **硬性：任一违例即失败**（`12` §3.5、05 §1.3a） |
| **所有 run（2026-09-18 新增）** | 结构：**不得**出现 `cloud_consult.denied_reason="sensitive_policy_grant_forbidden"`——它是**冗余防线被触发**（主防线接线错误）的标记，正确计数为 **0**；它**不写 `CloudAuditEvent`**，故计数须从**事件流**取，且不得与 `no_safe_context` / 用户否决混算（`12` §3.4、05 §3.2、`07` §2.2） | **硬性：出现即失败** |

**性质声明（防止把随机输出写成必过断言）**：真实模型输出带随机性，上表是**观测验收**——达标表示能力成立，不达标表示"进入复现轮 + 按 08 §7 处理"，**不**写成单次必过的 pytest 用例。定向达标后再跑完整回归（08 §2.4 首轮范围）。

**裁决 A/B 落地后重跑的口径（2026-09-17）**：S09 `base` 与 S06 `cloud_auto` 的达标**不再依赖**「模型把纯分析题判成 `normal`」——裁决 B 已保证即使模型仍判 `sensitive`，链路也能准入（代价是多一步强制用户授权、`cloud_auto` 臂的允许步骤仍按 `when_state` 正常命中）。因此该两行的 ≥2/3 是**准入口径**的观测：`admitted_proposal` 计入达标，与其因果风险是否为 `sensitive` **无关**。两条红线不变：**不得**调低 `expected_benefit` 阈值（真实 run 中 3/3 都已过阈值，阈值不是原因），**不得**改写 S06/S09 场景文本（改题目迁就实现，评估对象就变了）。

### 7.4 报告新增聚合（08 §6）

G3 区新增（数据来自 §4.2 字段，**无原文**）：

- **自主建议率**：S09 与 S06 `cloud_auto` 各自的 `REQUEST_CLOUD` run 占比；
- **`proposal_gate_result` 分布**：逐值计数——直接回答"为什么没上云"（`absent` = 模型没生成；`not_suggested` = 模型不建议；`benefit_below_threshold` = 建议但低估收益；`vetoed` = 规则否决；**`not_evaluated` = 准入根本没跑（2026-09-20 起有三种来源：dangerous 早裁 / 未调 `decide()` 的回合 / **能力终端性失败早裁**）——报告必须按 `intent_final.capability_resolution` 把「能力早裁」与前三者**分列**，否则会把「本地没有这个能力」读成「安全拒绝」或「确认流回合」**）；
- **`proposal_denied_reason` 分布**：被哪一条否决；**`non_normal_risk` 是全域禁项（2026-09-17 升级）——正确计数恒为 0**，任何 run、任何路径出现即接线缺陷（08 §2.6 硬性结构项；旧口径「只允许出现在 proposal 路径」已废，见 §4.3 该行）；
- **`sensitive` 所致升级的联合计数（2026-09-17 新增）**：`admitted_proposal` 且同回合 `intent_final.risk_draft="sensitive"` 的 run 数，以及其中出现 `cloud_consult phase="authorization_required"` 的比例——用于观察裁决 A（模型是否还在把纯分析题判 `sensitive`）与裁决 B（是否确实走到了用户面前）的分离效果。**不新增枚举**（`12-risk-draft-closed-set.md` §3.3）；
- **`risk_draft` / `risk_draft_resolution` 分布**（2026-09-16，`12-risk-draft-closed-set.md` §3.3）：归一化后的闭集值分布 + 取值来源分布（`declared`/`mapped_legacy`/`absent`/`unrecognized`）——回答「模型是不是在乱写风险值、有没有漏字段」；`unrecognized`/`mapped_legacy`/`absent` 持续偏高即立「提示词/schema 未约束住措辞」候选（08 §2.6）；
- **`no_progress_detected` / `stopped_early` 比例与轮次分布**：回答"理解阶段为什么停下来"（模型侧停滞）；**2026-09-17 增补**——"为什么**跑满**四轮"由 `resolution_exhausted`（`intent_final`）回答，两者**必须分列**（`14-resolution-exhausted.md` §6：前者是模型侧停滞信号，后者是预算侧耗尽信号，混用会让「模型停滞率」虚高）；
- **未授权外发断言**：发生升级的 run 中 `authorization_required` 出现率必须 100%，且授权前 `outbound_bytes` 恒 0。

---

## 8. 与既有契约的关系

| 契约 | 关系 | 落点 |
|---|---|---|
| 05-p4-cloud-advisory | **2026-09-15 轮：语义不变**，只补指针与观测 | 05 §2.2 加一行指针（提议判定标准见 10 §2.2）；05 §1.3 加一行（无进展提前停止不改变准入语义，见 10 §3.3） |
| 05-p4-cloud-advisory（2026-09-17 新增） | **本轮改动 05 的准入与授权语义**（方向相反于上行）：删除§1.3 否决项 3、新增 §1.3a 强制用户授权、§3.2 `create_policy_grant` 前置条件、§1.4 规则 8、§10.9 第 16–19 例、§11 第 11 项 | 05 §14 决策表；本契约 §7.1/§7.3/§7.4/§9 与之逐条对齐 |
| 07-p6a-observability-cli | §2.2 封闭集扩展 9 键 + `degradation` 枚举加一对 + `degraded` 语义修订 | 07 §2.2 表内就地更新；07 §8 A6 与 S15 断言同批修订；07 决策表加行 |
| 08-p6b-evaluation-loop | §2.1 `variants` 规则放宽、§2.3 变体总表加 `cloud_auto`、§2.5 不变、§6 报告聚合扩展、§8.2 定向验收协议 | 08 决策表加行 |
| 09-p6c-cloud-provider | 验收措辞 provider 化（当前写死 GLM） | 09 §11.4 改为 provider-neutral（保留"任选一个真实 provider"的阻塞验收语义） |
| 01-p0a-main-loop | `RETRIEVE_MORE` 的 P0a 注记（"P0a 已无更多检索能力，等同于 ASK_USER"）在本轮后语义收紧 | 01 补一行指针（不再需要改行为） |
| 00-*（Codex 属地） | 见 §9 同步清单 | Codex 更新 |

---

## 9. Codex 实现顺序（每步可独立验证）

**接口签名变更（Claude 已授权，Codex 落 00-* 与代码）**：

1. `ControlPolicy.decide()` 增加**仅限关键字**参数 `no_progress: bool = False`（默认值保持既有行为，既有调用零改动）；
2. 新增 `evaluate_cloud_admission()` + `CloudAdmissionDecision`，`_should_request_cloud` 收敛为其薄封装（**禁止双实现**）；签名与归一化按 §4.5（`cloud_state=None` 在函数内部归一化；**2026-09-17 起签名删去 `round_count` / `max_resolution_rounds`**，见 §4.5 与 `14-resolution-exhausted.md` §3.3）；
3. `RoundTrace` 增加 `new_memories: int = 0`；
4. `RetrievalStats` / `ConsultationProposal` / `ContextCandidate` / `NextAction` **签名不变**；
5. `MemoryBackend.retrieve()` **不变**（延期子项 §5.4）；
6. `App._build_local_reply` 增加仅限关键字参数 `*, conditional: bool = False, missing_info: Sequence[str] = ()`（App 私有方法，调用方只有自身；默认值保持既有行为逐字节一致）；
7. `AuthorizationManager.create_policy_grant()` 增加**仅限关键字**参数 `escalation_risk: str = "sensitive"`（**fail-closed 默认值**：不显式传 `"normal"` 即拒绝签发）；`create_user_grant()` 签名**不变**（2026-09-17 裁决 B，`12-risk-draft-closed-set.md` §3.4/§5，落点见 `05-p4-cloud-advisory.md` §3.2/§12）。

**步骤**：

| 步 | 内容 | 验证 |
|---|---|---|
| 1 | `degraded` 语义修订（§5.2）+ `degradation` 枚举（§5.3）+ 新增 `RetrievalStats` 用例 + S15 断言改 `false` | 单测全部 21 项通过；S15 toy 场景 |
| 2 | `RoundTrace.new_memories` + resolver 的净增计数 + no-progress 判定 + `last_no_progress`/`last_stopped_early`（§3） | 单测 8/9/10/11 |
| 3 | `decide()` 的 `no_progress` 分流（§3.3）+ `_build_local_reply` 的 `conditional` 参数与提示词要求 | 单测 13/13b/13c/14 |
| 4 | `evaluate_cloud_admission` + `CloudAdmissionDecision` + main 侧观测接线（§4，含确定性事实透传与同一组输入） | 单测 1/2/3/4/5/6/7/12/15（~~15b~~ 已于 2026-09-17 删除） |
| 5 | 事件封闭集扩展 9 键（07 §2.2 同步，**含两张枚举的取值域指针到 §4.3**）+ `_sanitize_event_data` 白名单同步 | 单测 12；`test_runtime_events` |
| 6 | 提示词契约 P1-P10 + schema 枚举收紧（§2.2）+ **5 例**正反例 E1–E5（§2.3） | 单测 16 |
| 7 | 场景：S06 `cloud_auto` 三臂 + `variants` 规则放宽 + S15 断言（§7.2） | 运行器自身测试 + toy 场景 |
| 8 | 报告聚合（§7.4，含 `vetoed`/`not_evaluated` 分列） | `test_p6_scenarios_runner` + `p6_report` smoke |
| 9 | 定向真实评估（§7.3，3 run × 4 场景/变体） | 观测达标 → 完整回归 |

**步 1 与步 2-3 相互独立**，可并行；步 4-5 依赖 `CloudAdmissionDecision` 定稿；步 6 与步 7 独立。

**步 0（审查后补充，先做）**：把 `_guard_unresolved_reference` 及其测试从本轮**移出**（`src/core/intent_resolver.py:63,119,256-268`、`tests/test_intent_resolver.py:117-145`），并把该规则作为独立子项追加到 `specs/clarifications.md`。理由见 `specs/reviews/p6d-review.md` 第 1 项：它在 S02（`rounds_ab` 的 G1 观测门）的设计条件下必然触发，使该场景**无论模型输出什么都必过**，同时把报告里的 `missing_info` 从模型输出变成规则产物——本轮要测的能力因此不可证伪。该规则本身合理，但需要独立契约（含 `这个/此/该`、排除句内自解、不改写 `missing_info`）。

**步 4b（审查后补充）**：`_record_dispatch_event` 的 `admission` 去默认值（必传）+ 6 个确认恢复流调用点显式传 `CloudAdmissionDecision(False, "not_evaluated")`（§4.5 末条、§4.3 来源 ③）。

**步 4d（2026-09-17 新增，裁决 A/B；`12-risk-draft-closed-set.md` §3.2/§3.4/§3.5）**：① 删除 `decide()` proposal 准入里的 `risk_draft == "normal"` 条件与否决项 3（`non_normal_risk` 变为不可达——`evaluate_cloud_admission()` 的否决集同步）；② 提示词补 `12` §1.3 第 6–8 条（判定对象 / `sensitive` 两个充分条件 / `dangerous` 时不得建议上云），与本节 P1–P11 同批写入；③ App 把被准入候选的归一化 `risk_draft` 作为**模型下界**记入 `LocalTaskContext`，并在**授权时**用当时信号求**有效授权风险**（`effective_authorization_risk()`，`12` §3.5）后传给两处 `create_policy_grant()` 调用点——**不得**把准入时的下界当最终值，也**不得**用确定性信号把风险降回 `normal`；④ `create_policy_grant()` 增 fail-closed 前置条件 + 防御性拒绝的错误契约（见上「接口签名变更」第 7 项、05 §3.2 防线表）；**误调用的痕迹走既有 `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` 事件，不写 `CloudAuditEvent`、不动 `record_denial` 四值闭集（2026-09-18 收口）**；⑤ `risk_draft` **不复制工具层的确定性风险**（工作区内新建文件 = `normal`，覆盖/越界由确定性 preflight 升险，`12` §1.2 表注）。**2026-09-20 追注（P7a-0）**：本项结论不变，但「新建文件 = `normal`」的**理由变了**——`07` §6.1 的写操作注册表基线已反转为 `sensitive`（新建也确认），而 `risk_draft` 判的是**请求语义**（是否为破坏性/不可逆/外发），**不表达「会不会被确认」**；两个字段互不推导，本项的分层结论继续成立（`12` §9 末行）。验证 = §7.1 第 18b/18e/18f/**18g** 项 + `12` §4.2.5 B/C/**E** 组（含 E8 正例） + 05 §10.9 第 16–**23** 例。

**步 4c（2026-09-17 修订，`14-resolution-exhausted.md`；改的是步 2/步 4 的产物，非新增步骤）**：`ControlPolicy.decide()` 增必传关键字参数 `resolution_exhausted`、删位置参数 `round_count`；`evaluate_cloud_admission()` 删 `round_count` / `max_resolution_rounds` 与常量 `_MAX_RESOLUTION_ROUNDS`；`decide()` 第 1 步收敛为 `not_evaluated → REFUSE`（不再复制 `_is_dangerous`），第 4 步本地分流新增 `resolution_exhausted → ASK_USER`（在 `no_progress` 之后、`missing_info` 之前）；`IntentResolver` 记录 `last_resolution_exhausted`（循环自然出口置位、与 `no_progress` 构造互斥）并由 App 原样转发（两处调用点）；`intent_final` +1 键；**报告与状态均不变**。验证 = `14` §7 的 T1–T16。

---

## 10. 延期与未决（明确不做，避免被读成"已承诺"）

| # | 事项 | 为什么延期 | 触发条件 |
|---|---|---|---|
| 1 | `MemoryBackend` 可用性快照（`degraded` 的精确来源） | 接口签名变更，影响面大；本轮先用"只漏报不谎报" | §5.4；评估需要精确 embedding 故障率时 |
| 2 | `embedding→keyword_only` 恢复生产 | 依赖第 1 条 | 同上 |
| 3 | **难度代理自动升级**（无 proposal 时按任务复杂度自动上云） | 等于把升级决定权交给启发式规则，与"不把控制权交给模型/规则以外的推断"冲突；本轮的路径是让模型**表达**建议 | **需 boss 决策**，且须先有 §7.3 的定向数据 |
| 4 | `_CLOUD_BENEFIT_THRESHOLD` 调参（0.5） | 调参必须挂 run_id 证据（08 §7 禁止无证据调参）；本轮先让观测字段落地 | §7.3 完成、`proposal_gate_result` 分布可见后 |
| 5 | `cloud_auto` × `local_only` 的同题 pair 评审 | 需要新一轮 pair 评审产物与评分；本轮只立观测臂 | §7.3 达标后由 boss 决定是否立 pair |
| 6 | 会话级/用户级云端限流、有界终态台账、provider 真实可用性探测 | 05 §14 既有遗留（2026-09-14 三条） | 05 §14 遗留条目 |
| 7 | 语义签名的进阶形态（如按 missing_info 语义聚类而非字面规范化） | 字面规范化已能识别 S06 的零增量形态；语义聚类需 embedding，与第 1 条耦合 | 字面签名被证据证明无效时 |

---

## 11. 决策表

| 日期 | 决策 | 内容 |
|---|---|---|
| 2026-09-16 | **悬空指代护栏移出本契约、独立立项**（Claude） | 本契约不再承载该能力；新契约为 `11-reference-guard.md`（✅ 待实现）。本契约只做两处**指针级**修订：§2.2 表尾加 **P11**、§2.3 加 **E6** 跨契约指针（E6 定义在 11 §4），两者均**显式引用**、不构成隐式示例追加。**依据**：移除未备案的 `_guard_unresolved_reference` 后 S02 真实复现 6/6 失败（`round1`/`round4` 各 3 run；5 例 `READY`+`missing_info`=2+`should_consult=true` → `admitted_proposal` → `REQUEST_CLOUD`，1 例 `READY`+`missing_info`=0 → `PLAN_LOCAL` → 模型自拟工具 `TOOL_NOT_FOUND`），证明「模型自称 READY 即提前返回、渐进循环不启动」是**结构性**缺陷，不是轮次不够。该能力涉及独立判定层、独立事件键与独立验收口径，摊进本契约会稀释两轮的验收边界 |
| 2026-09-15 | **第二轮复核：`is_effectively_ready()` READY 分支语义变更不予授权，要求回滚 → `[已修复]`**（Claude 判，Codex 执行 A） | 修复轮把 `is_effectively_ready()` 的 READY 分支从 P5 基线的 `return True`（`git show HEAD:src/core/control_policy.py:133-134`）改为 `return not candidate.missing_info`（`src/core/control_policy.py:165-166`），本契约 §1.1 表已把该函数列为「05 §1.3 未变」，故属未授权偏离。三处规范冲突：`project-plan.md:235` 定义式「有效 READY ≝ `state == "READY"` **或**（…）」，READY 项不带 `missing_info` 条件；`05 §1.3:111/143`「语义不变 / 既有行为不变」；本契约 §1.1。**改动方向与 boss 批准的 2026-09-14 双判定拆分相反**（`project-plan.md:224`、`05 §11`：不得用本地完整度判断含 `missing_info` 一票否决云端咨询）——READY + `missing_info` 重新被否决 → `not_eligible_local_state`，同时抵触 §2.2「P5 READY 同样允许升级」与 §1.1「READY + 高置信度不得压制 ConsultationProposal」。**另有一处未声明的连带影响**：`intent_resolver.py:116` 的轮次 1 提前返回对 READY + `missing_info` 失效，改为继续检索+再提示词，`last_round_count` 上升并进入本契约 §3 的 no-progress 判定，影响 `rounds_max`/`rounds_ab=true` 场景（S02）验收，方向与 §3「减少无谓轮次」相反。**改动被 `control_policy.py:87` 的第一个析取项意外屏蔽在 `decide()` 层**（READY → `_decide_ready` → `ASK_USER`，P5 行为），仅从 `decide()` 观察会误判「未变」；真实变化在 `resolve()` 早停与云端准入两处。**对已观测问题零收益**：`05 §11:799` 的真实证据是模型判 `PARTIAL`/`VAGUE` + `missing_info`，走 `eligible` 第二项，本次改动对它们无影响。判定：**回滚**（READY 分支恢复 `return True`；`test_ready_label_with_missing_info_is_not_eligible_for_automatic_cloud` 改为断言既有语义，成为锁定测试；回滚后 `control_policy.py:87` 第一析取项恢复冗余，可删，非阻塞）。若认为确需区别对待，走独立子项提案 + 真实运行证据，并同步修订 `project-plan.md:235` / `05 §1.3,§11` / 本契约 §1.1,§11 四处定义，本轮不做。详见 `specs/reviews/p6d-review.md` §六。**执行结果（2026-09-15，采纳 A）**：`is_effectively_ready()` READY 分支已恢复 `return True`（与 `git show HEAD:src/core/control_policy.py:133-134` 逐字一致）；测试改名为 `test_ready_label_with_missing_info_remains_eligible_for_automatic_cloud`，断言翻转为 `is_effectively_ready(candidate) is True` + `gate_result == "admitted_proposal"`，成为**锁定既有语义**的回归测试；`control_policy.py:87` 的第一个析取项随回滚重新变为冗余并已删除；连带影响（`intent_resolver.py:116` 的轮次 1 提前返回对 READY + `missing_info` 恢复生效）随回滚自然消除。`425 passed`、ruff/mypy 通过。**上一轮基于临时改动得到的 S02 结果作废，不作为验收证据** |
| 2026-09-15 | P6d 契约立项（Claude，依据 S06/S09 真实 run + boss 方向） | **新增薄契约而非修改 05/07/08**：本轮三个改动主体分属 IntentResolver（提议判定、零增量停止）、ControlPolicy（准入可观测性）、检索统计（降级语义），摊进 05 会为一个已 ✔️ 的云端契约装入与 P4 无关的内容；且本轮有独立验收口径（自主建议率、零进展停止率），是阶段而非补丁。05/07/08 只做指针与封闭集级修订 |
| 2026-09-15 | 表达经济性（§0.3） | 只新增 `CloudAdmissionDecision`（1 结构 + 1 纯函数）与 `RoundTrace.new_memories`（1 int）。不加"能力/难度/增益"模型自评字段——§1 的三个判断分离靠**既有字段语义收紧**达成 |
| 2026-09-15 | `escalation_reason` **不扩枚举**（§2.4） | 现有 7 值已覆盖 boss 列举的三类（`context_capacity` 由 `long_context_synthesis` 承载）；加值只稀释报告判别力。改为把枚举**写进 schema**（消除"自由文本→一律 unknown"的观测盲区） |
| 2026-09-15 | no-progress 三条件 + 签名排除项（§3.1/§3.2） | 排除 `model_confidence` 与 `reasoning` 是为 S06 的 0.75→0.85 现象；**纳入 `entities`** 是为"新提取到实体 = 真实进展"必须阻止误停。检索失败轮不得判 no-progress（不把故障固化为已收敛） |
| 2026-09-15 | 停止后分流：可条件化回答 → `PLAN_LOCAL(requires_user_confirmation=False)`（§3.3，**次日修正见下**） | 要求 `suggested_tools` 为空是为"信息不全不进工具路径"——空计划 ⇒ `TaskPlanner.plan()` 返回 `ExecutionPlan()`（`task_planner.py`）⇒ **按构造零副作用**，故无需确认；确认机制只服务工具执行。**任何情况下不再返回 `RETRIEVE_MORE`** |
| 2026-09-15 | 观测落在 `intent_final` + `dispatch_decision`，不新增 stage（§4.1） | 模型侧事实与规则侧事实的**产生者**不同、**时刻**不同，分放两事件保持职责边界；逐轮 proposal 不放 `intent_round`（避免同一事实重复 N 次） |
| 2026-09-15 | `degraded` 语义收窄为「检索层显式失败」（§5.2），S15 断言改 `false`（§7.2） | 「零向量命中」不是降级；本轮**不宣称**能区分"未配置向量/健康零命中/故障回退"——做不到就不说。精确信号需 `MemoryBackend` 返回可用性快照（§5.4 延期）。**本决策把一条假信号从报告里删掉**，S15 由"断言降级事件"翻转为"断言无假降级事件"，其核心语义（向量缺席仍命中并收敛）反而被强化 |
| 2026-09-15 | `variants` 允许与 `value_ab` 并用（§7.2） | S06 需要第三臂 `cloud_auto` 而保留 pair 语义；规则收敛为"派生集 ⊆ 显式集"。`cloud_auto` **不**进 pair（它是能力观测臂，不是同题公平对照） |
| 2026-09-15 | 定向真实评估为**观测验收**（§7.3） | 阈值（0/3、≥2/3）绑定随机模型输出，**不写进 pytest**；达标才跑完整回归。未授权外发断言是唯一的硬性结构项 |
| 2026-09-15 | **Codex 实现前审查五条全部采纳**（3 阻塞 + 2 澄清） | ① **条件化回答不再要求确认**（`requires_user_confirmation` true→false）：`TaskPlanner.plan()` 在 `suggested_tools` 为空时返回**空计划**，App 对空计划直接走本地回复（`main.py:707-710`），**根本到不了**确认判断（`main.py:722`）——原承诺永不生效，属契约失真。改为只读回复（**按构造零副作用**，与既有「READY + 无工具 → 本地答」同一分支）+ 提示词必须显式列出「采用的假设 / 尚不确定的信息」（`_build_local_reply` 增 `conditional` 与 `missing_info`，默认值保持既有行为）+ **防御性规则**：非空计划不得被当作条件化回答返回。确认机制仍只服务工具执行与真实副作用。② **`proposal_gate_result` 补第 9 值 `vetoed`**，并钉死 `gate_result=="vetoed" ⟺ denied_reason!="none"`；`not_evaluated` 收窄为「准入逻辑根本没跑」（dangerous / 超轮次）——两者业务含义相反，合并会把 `deny_cloud` 这类最需被看见的否决统计成「没到那一步」。③ **`evaluate_cloud_admission` 补确定性输入** `*, round_count, max_resolution_rounds=_MAX_RESOLUTION_ROUNDS`：`not_evaluated` 的轮次来源需要它，缺了就只能让 App 自己补判 → 枚举值分散到两处实现，直接违反「唯一实现」。同时把 `cloud_state=None → CloudControlState(cloud_enabled=False)` 的归一化收进函数内部，与 `control_policy.py:45` 逐字一致。④ **「8-shot」改「5 例（E1–E5）」**并声明本契约不追加隐式示例；修 §2.2 的错误交叉引用（原指向 §7.1 第 12-14 项，应为第 16 项）。⑤ **情形 3 的模型行为钉死为 `should_consult=true`**（原文写「本地条件化分析或建议云端两者都合法」，P3 却要求建议云端——自相矛盾且会让自主建议率失去可判定分母：模型永远可选本地而**不被记为漏判**，本轮要测的能力就无法证伪）；本地条件化回答降级为**规则层否决/用户拒绝/云端不可用后的回退**，不由模型在该情形直接选择 |
| 2026-09-15 | **实现后审查：2 阻塞 + 3 测试缺口 + 1 我方措辞修正**（`specs/reviews/p6d-review.md`） | ① **`_guard_unresolved_reference` 移出本轮**（未记载的确定性规则，改写模型 `missing_info`）——它恰在 S02 的设计条件下触发，使该 `rounds_ab` 观测门无论模型输出什么都必过，报告里的 `missing_info` 也变成规则产物；规则本身合理但需独立契约（含 `这个/此/该`、排除句内自解），已在 `clarifications.md` 立项。② **`_record_dispatch_event(admission=...)` 去默认值（必传）**：默认 `None` 让"忘了接线"与"本回合未评估"共用 `not_evaluated`，并把确认恢复流回合计入报告 `proposal_gate_results`；6 处调用点显式传值，§4.3 的 `not_evaluated` 定义同步**穷举三种来源**。③ 补 §7.1 第 13c（防御性规则）、第 9（有新增 chunk 不得判无进展）、第 15（两枚举全取值 + 不变量，`decide()` 在 `control_policy.py:62,69` 重复实现 dangerous/超轮次正是该防的对象）三项测试。④ 我方修正：§7.1 第 12 项的断言层次（`missing_info` 原文只在**落盘**计数，事件 `data` 按 07 §2.2 保留）与第 17 项失效行号括注；§9 补步 0（移出该规则）与步 4b（`admission` 必传） | ✔️ **已全部修复并经变异探针证伪**（详见本文件末行与 `p6d-review.md` 第三轮）
| 2026-09-17 | **「超轮次不走云端」删除 + 轮次事实改由 `resolution_exhausted` 承担**（S03 `round1` 真实 run `7707d503adc5`：`RETRIEVE_MORE` 而场景要求 `ASK_USER`；根因是 Resolver 知道轮次用尽、Policy 不知道——`14-resolution-exhausted.md`） | ① `IntentResolver` 新增 `last_resolution_exhausted`（循环自然出口置位；与 `no_progress` **构造互斥**，不得复用该参数的证据语义）；② `ControlPolicy.decide()` 增**必传**关键字参数 `resolution_exhausted`、**删**位置参数 `round_count`（唯一消费者是被删的轮次判据；必传理由沿用 §4.5 的 `admission` 先例——漏传的后果正是本 bug）；③ 新增本地分流步：`no_progress` 之后、`missing_info` 之前 → `ASK_USER`(reason 与 `no_progress` 区分)，**不改变** force/proposal 准入、悬空护栏、dangerous 早裁与各否决项；④ `evaluate_cloud_admission()` 删 `round_count` / `max_resolution_rounds` 与 `_MAX_RESOLUTION_ROUNDS`，`not_evaluated` 由**三源收窄为两源**（dangerous 早裁 + 未调用 `decide()` 的回合）；⑤ **行为变更照实声明**：proposal 路径在轮次用尽时不再被否决（P6d 的目标即「本地卡住时由强模型补足」）；⑥ 可观测：`intent_final` +1 键（键数 13→14，按 §4.2 产生者分工与 `no_progress_detected` 同 stage），`dispatch_decision` / `turn_completed` 键集不变，决策侧由 `reason` 可区分；⑦ §7.1 第 15b 项删除、15c 锚点改为三个确定性事实 |
| 2026-09-17 | **§3.5 的括注「若恰在末轮判定 `no_progress`，则不算提前停止」被证伪**（Codex 复核 `14-resolution-exhausted.md` 时发现） | 事实：`no_progress` 的计算被 `should_continue = round_index < max_rounds` 门控（`intent_resolver.py:129`/`:133`），**末轮不检索、不判 `no_progress`**，故 `stopped_early = last_no_progress and last_round_count < max_rounds` 的右项**恒为真**、`last_stopped_early` 与 `last_no_progress` 取值始终一致。§3.5 已改写并在行内标明「该分支不可达」。**不改代码、不改字段语义**（既有的 `round_index < max_rounds` 表达式保留原文案所表达的比较意图），仅为消除「存在一条末轮分支」的误读；构造性证明见 `14` §2.1 |
| 2026-09-17 | **同日四处补钉（Codex 复审提出，Claude 裁定）**：授权形态若只听模型，则「确定性」只是传递模型结论；「写文件即 `sensitive`」与 `07 §6.1` 冲突；含秘密文本仍整段拒绝使 S12 不可达；防御性拒绝的错误/审计归属未定义 | ① §7.3 新增硬性行——**有效授权风险**非 `normal` 不得出现 policy grant，`risk_draft=normal` 不足以推断授权形态（`12` §3.5）；② §9 步 4d 补 ⑤（`risk_draft` 不复制工具层的确定性风险：工作区内新建文件 = `normal`，覆盖/越界由 preflight 升险）。**2026-09-20 追注**：该行当时的论据是「`07 §6.1` 新建基线为 `normal`」，该前提已被 P7a-0 反转；**结论仍成立**，理由改为「判据是请求语义，不是会不会进确认链」（`12` §1.2 表注/§1.3 第 7 条）；③ §9 步 4d 的验证清单纳入 `12` §4.2.5 **E 组**与 05 §10.9 第 16–22 例；④ §7.1 第 18b/18e/18f 与 18f 的 `normal` 口径按「有效授权风险」复核（确定性信号未同时为否时不得自动续） |
| 2026-09-17 | **S09 `base` / S06 `cloud_auto` 两条自主升级臂被 `risk_draft=sensitive` 整体锁死**（真实 run：3/3 + 3/3 `vetoed` + `non_normal_risk`，实际准入 0/3，目标 ≥2/3；老板裁决 A/B，Claude 修订契约） | 两点结论，**都不是本节的提议标准有问题**（3/3 `should_consult=true`、`benefit=0.8`、`escalation_reason` 正确）：① **判定对象**（裁决 A）——`risk_draft` 判**本回合实际请求的动作**，只读分析/架构权衡/迁移规划默认 `normal`，`sensitive` 只有两个充分条件（实际含敏感数据 / 实际请求需确认副作用）；提示词与本节 P1–P11 同批写入（`12` §1.3 第 6–8 条，指针见 §2.2 末条）；② **准入与授权**（裁决 B）——`sensitive` 提案改为可准入 + **强制用户授权**（所有模式含 `convenient`），**否决项 3 删除**，`non_normal_risk` 成为全域禁项。**本节改动**：§4.3 该值改为「保留 / 全域不可达」+ 适用路径段收口、§7.1 增 18e/18f 并翻转 18b/18c/18d、§7.2 补 `cloud_auto` 未准入原因收窄、§7.3 增 `sensitive` 升级的硬性结构行与重跑口径、§7.4 增联合计数并升级该值为全域禁项、§9 增接口第 7 项与步 4d。**阈值与场景文本一律不动**：`expected_benefit` 不调、S06/S09 场景一字不改（`12` §0.1.1、05 §14） |

---

> 契约完成标志（§11 Done 对偶）：步 1-8 的单元/结构验收全绿（`420+ passed` 量级）+ 步 9 定向真实评估达标 → 09 §11.4 的 provider 化验收随之收口 → P6d 关闭，进 P7。
| 2026-09-18 | **两处收口（Codex 复审上轮补钉后提出）**：① 有效授权风险的确定性输入含 `high_impact`/preflight，但 policy grant 发生在续咨询阶段——那时通常既无 `ExecutionPlan` 也未跑 preflight，「未求值即 `sensitive`」会把该信号恒判 `sensitive`，`normal + convenient` 的自动续咨询（§7.1 第 18f 项）重新不可达；硬传 `False` 又违反「不得降险」。② `create_policy_grant` 误调用那条要求的「审计」过不了 `record_denial()` 的固定四值闭集，第 18e/18f 的配套断言无法实现 | **① 升险源收窄为两项**（payload 候选分类、`task_has_sensitive_execution_chain`）：工具计划 / preflight 是**正交链路**（`07` §6.3、`13` §2，只升不降），真实敏感执行链本就是准入硬否决，故无缺口；§7.1 新增 **18g**（参数表断言：不得出现 `high_impact`/`preflight` 类参数），18f 补「两信号均为 `False`」并指明它同时是「恒 `sensitive` 实现」的反证；§7.3 硬性行改写为「升险源恰两项」。**② 审计出口改道**：误调用的痕迹由 App 发**既有** `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` **事件**承担（`07` §2.2 新增该本地否决类取值），**不写 `CloudAuditEvent`**（`record_denial` 四值闭集与「恰一条 / 终止语义」不变量不变）；§7.3 新增全域硬性行：该 `denied_reason` 计数**恒为 0**，且须从**事件流**取、不得与 `no_safe_context` / 用户否决混算 |
| 2026-09-20 | **`not_evaluated` 来源由 2 扩为 3（P7a，`16-p7-practical-tools-capability-routing.md` §3.8 ①）**：新增「能力终端性失败早裁」 | 老板真实试用暴露「本地没有这个能力时，系统既不能说没有、也无法阻止它把这句失败送去云端」。裁决：`force_cloud` 为假 + `capability_resolution ∈ {unavailable, unrecognized}` + 无草案 ⇒ 在 `evaluate_cloud_admission()` 内早裁为本值（**值域不变、只扩来源**，与 dangerous 早裁同类同法：都是「准入逻辑没跑」）。**不覆盖显式 `/cloud ask`**（用户指令优先，与 `local_action_proposed` 在 force 下的既有非对称一致）。连带要求：`decide()` 的 `not_evaluated` 分支**必须按来源分流**，否则该回合会返回 `REFUSE` + 理由句「草案被标记为危险」（`16` §3.9 ②） |
| 2026-09-23 | **P7a 第三轮（`16` §6.3.x）新增的「实例级剔除」轮不是本值的第四个来源** | §4.3 的 `not_evaluated` 行补一条**守边界**：该值的判据里始终含「**无草案**」，而实例级剔除轮**保留草案**（`tool_call_resolution` 仍 `resolved`）⇒ 它落在**既有的 `param_missing` 追问**上，`proposal_gate_result` 取值**不定**（随 `consultation_proposal` 与云端状态变化）。**不扩来源、不改值域**；报告与硬性行**不得**把该轮写成 `not_evaluated`（写入即事实错误）。动机：本轮契约初稿正是在这里写错了一次 |
| 2026-09-18 | **工具编排加固联动（`15-tool-orchestration-hardening.md` §2.5）**：本契约的 `proposal_gate_result` 值 `suggested_tools_present` 与条件化回答的第 4 个条件都建立在 `suggested_tools` 上；而该字段不受运行时闭集约束、其 `entities` 又被旧 `TaskPlanner` 当作参数（S14 连续 4 次真实 run `tools.executed=0` 的根因） | ① `suggested_tools_present` **改名 `local_action_proposed`**（本契约 §4.3 为权威），判定源改为 `intent_final.tool_intent`；② §3.3 条件化回答第 4 个条件由「`suggested_tools` 为空」改为 `tool_intent == "none"`，安全论证按 N1（`local_action` ⇒ 有草案 ⇒ 非空计划）**重写，结论不变**；③ §4.4 的 `proposal_denied_reason` `none` 列表、§7.1 第 13c/15 项同步改名。**取值域个数（9）、阈值、S05/S06/S09/S11 场景文本一律不动** |
