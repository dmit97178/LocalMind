# LocalMind — 本地智能体项目方案

## 一、项目概述

### 1.1 项目定位

**LocalMind** 是一个本地优先的个人办公智能体。

核心目标不是一开始做大而全的平台，而是先跑通一个稳定闭环：

```
用户输入 → 清洗标准化 → 最小上下文检索 → 结构化意图
→ 规则决策 → 安全校验 → 受控工具执行 → 回复用户 → 记录经验
```

云端、多专家、自进化都作为增强能力逐步接入，不进入早期主路径。

### 1.2 核心闭环 vs 增强能力

```
┌─────────────────────────────────────────────────────────┐
│              增强能力（Phase 4+，逐步接入）                │
│  云端建议 · 多专家协同 · 自进化 · 跨会话项目记忆            │
│  ┌─────────────────────────────────────────────────┐    │
│  │             核心闭环（Phase 0-3）                 │    │
│  │  输入清洗 → 意图理解 → 规则决策 →                │    │
│  │  安全校验 → GuardedToolExecutor → 回复 → 记录    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 1.3 核心原则

| 原则 | 说明 |
|------|------|
| 本地为主 | 本地模型负责理解、调度、整合，云端是受控的推理升级工具（以最小任务包换取更强推理，非自主路由） |
| 控制权不交给模型 | 模型提出候选意图，ControlPolicy 做最终调度决策 |
| 安全边界不可绕过 | 本地工具副作用经 GuardedToolExecutor，云端网络副作用经 SideEffectGateway，两者共同构成受保护副作用边界 |
| 上下文最小化 | 每次模型调用只带必要上下文 |
| 记忆分层 | 原始记录、摘要、经验、技能、安全证据分开存储，不同信任等级不混用 |
| 自进化旁路化 | v1 只记录候选经验，不自动执行，不参与高危决策 |
| 外部组件适配化 | QwenPaw、Ollama、EverOS、MCP 都是 Adapter，不反向决定 Core |
| 分阶段交付 | 每阶段有可运行、可验证的产出 |
| CLI 只做壳 | CLI 只负责输入、显示与会话生命周期；不参与意图判断、安全裁决或云端决策。Core 的可观察性经结构化运行事件（RuntimeEventSink）输出，Core 不直接打印 |

### 1.4 主权边界

```
Core-owned（自研，外部组件不可反向决定）：
  主循环、意图状态机、ControlPolicy、GuardedToolExecutor、
  安全策略、记忆信任模型、InputNormalizer、ResponseBuilder

Adapter-owned（可替换基础设施）：
  Ollama、QwenPaw、EverOS、MCP 工具、云端 API、向量库
```

### 1.5 技术基座

| 组件 | 来源 | 归属 | 说明 |
|------|------|:---:|------|
| 多端接入 | QwenPaw Channels | Adapter | CLI + HTTP API |
| 模型推理 | Ollama | Adapter | 本地模型加载 |
| 技能执行 | QwenPaw Skills（MCP 标准） | Adapter | 工具定义与执行，须经 GuardedToolExecutor |
| 安全基础 | QwenPaw ToolGuard | Adapter | L2 语义检测 |
| 记忆存储 | v1: SQLite + JSONL，之后可接 EverOS | Adapter | 通过 MemoryBackend 接口 |
| 主模型 | Qwen3-4B Q4_K_M | Adapter | 常驻核心大脑 |

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户交互层                                      │
│              CLI (自研, P6a) · HTTP API (QwenPaw Channels, P7b 及以后)     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     LocalMind Core（100% 自研）                           │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Input      │  │   Intent     │  │   Context    │  │   Control    │ │
│  │  Normalizer  │  │  Resolver    │  │  Assembler   │  │   Policy     │ │
│  │  输入清洗    │  │  渐进式理解  │  │  上下文最小化│  │  规则调度    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │    Task      │  │   Response   │  │  Reflection  │                   │
│  │   Planner    │  │   Builder    │  │   Recorder   │                   │
│  │  生成本地计划│  │  组装回复    │  │  记录候选经验│                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     LocalMind 安全控制层（不可绕过）                        │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Safety     │  │   Guarded    │  │   Privacy    │  │    Cloud     │ │
│  │   Policy     │  │    Tool      │  │   Policy     │  │   Boundary   │ │
│  │   L1+L2+L3   │  │  Executor    │  │ 分级脱敏/授权 │  │  最终出站复核 │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
│       IdentityVerifier + AuthorizationGrant（身份、有限授权、过期）       │
│                                                                          │
│  铁律：所有外部副作用必须经过此层。任何 Core 模块不得绕过。                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     接口抽象层 (core/interfaces.py)                        │
│         ModelBackend · MemoryBackend · ToolBackend                       │
│         CloudAdvisoryBackend · EvolutionBackend                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      适配器 + 外部组件（Adapter-owned）                    │
│                                                                          │
│  Ollama · QwenPaw · MCP · 云端 API                                       │
│  MemoryBackend 实现 (SQLite / EverOS)                                     │
│  EvolutionBackend 实现 (Noop / EverOS)                                    │
│                                                                          │
│  铁律：任何 Adapter 不能反向决定 Core 的数据模型和控制流                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 核心闭环流程

```
1. 用户输入
       │
2. InputNormalizer
   ├── 基础清洗，生成 InputEvent { text, session_id, project_id?, timestamp }
       │
3. ContextAssembler
   ├── 只加载当前必要上下文（会话摘要 + 项目摘要 + 相关记忆片段）
       │
4. IntentResolver（内循环，最多4轮）
   ├── 模型生成认知报告
   ├── 状态 == READY → 输出 IntentCandidate + 置信度
   ├── 状态 != READY → 检索记忆 → 补充上下文 → 回到模型
       │
5. ControlPolicy（非模型规则层——模型提建议，规则做决定）
   ├── NextAction 类型：
   │   ASK_USER | RETRIEVE_MORE | PLAN_LOCAL | REQUEST_CLOUD | REFUSE
   ├── 先做云端咨询准入判定（只读咨询是否本回合发生，05 §1.3），
   │   再做本地就绪判定（置信度 + 风险等级 + 信息完整度）——两个判定相互独立
   ├── 安全角色（P0a）：意图级——risk_draft=dangerous → REFUSE
   │   （risk_draft 为闭集 normal/sensitive/dangerous，解析层归一化、判定对象为本回合实际请求的动作；
   │    见 12-risk-draft-closed-set.md。它只用于这一处意图级硬锁定 + 本地确认档，**不是云端准入的否决项**）
   │   注意：ControlPolicy 只做「意图级」判定。批准档（approval_profile）是「执行步级」的
   │   确定性事实，只有在 TaskPlanner + preflight 之后才知道，判定点在第 7 步的 App 分支
   │   （见 13-approval-profile-high-impact.md §3.1）
       │
6. TaskPlanner
   ├── 生成 ExecutionPlan（纯本地计划，云端不产生此结构）
       │
7. GuardedToolExecutor（安全执行边界，P0a 双层安全中的执行级）
   ├── 校验工具在白名单内
   ├── 调用 SafetyPolicy.check() → RuleOnlySafetyBackend L1 硬规则
   ├── 执行业务工具
   ├── 记录 AuditEvent 审计日志
       │
8. ResponseBuilder → 返回用户
       │
9. ReflectionRecorder（异步旁路）
    ├── 记录原始对话
    ├── 提取候选经验（draft）
    └── v1 不自动参与决策
```

### 云端调用路径（Phase 4+，不在核心闭环中）

```
模型输出 ConsultationProposal（是否建议升级 + 升级原因 escalation_reason + 候选上下文，仅建议、无权调用；外发单位为本地构建的最小推理任务包 TaskBrief，见 05 契约 §2.5）
    ↓
ControlPolicy 组合裁决（模型建议 + 用户指令 + 确定性否决/预算；云端准入与本地就绪为两个独立判定，05 §1.3）
    ├── 用户「不要联网」→ 最高优先级否决
    ├── 云端开关关闭 / 单任务预算耗尽或冷却期 / 后端不可用 / 真实工具执行态与敏感执行链（App 确定性状态，模型的工具动作声明与 risk_draft 不算）→ 否决
    │   （risk_draft 自 2026-09-17 起**两个路径都不再否决**：它判的是本回合实际请求的动作，
    │    只读分析默认 normal；模型输出不构成安全边界。见 12-risk-draft-closed-set.md §3.2）
    ├── force_cloud（/cloud ask）：绕过模型 READY/置信度/should_consult/一般 missing_info/模型工具建议，但有实质任务文本才升级（空任务本地追问）
    ├── 无 force：proposal 有效（should_consult + benefit≥0.5 + 模型未声明本地动作）且目标明确（有效 READY，或 PARTIAL/ALMOST + intent 非 unknown）→ 升级
    └── 通过 → REQUEST_CLOUD（缺失信息经 TaskBrief brief_unknowns 随包外发）
        ├── 有效授权风险 normal（= max(模型下界, 确定性升险) 仍为 normal）→ 授权按隐私模式（convenient 可 policy grant）
        └── 有效授权风险 sensitive → **强制用户授权**：所有模式（含 convenient）进 AWAITING_AUTHORIZATION，
            只认显式 /cloud allow；不得 policy grant、不得复用旧授权（2026-09-17，05 §1.3a）
        ↓
PrivacyPolicy 本地脱敏（字段分类 config/entity/free_text/secret + 类型/长度 + 凭据检测 + 语义占位；
    含秘密文本就地替换为 [已脱敏:secret]（作用域 = 整个值区 = 标签之后到本行末尾的连续跨度，
    标签独占一行时顺延一个非空行；字段名与分隔符保留）并另产 secret_placeholder，替换后复扫——05 §2.3b；
    检测判据的唯一真源 = secret_scan：命中 = 标签闭集成员 + 边界成分（显式分隔符 / 空白 / 紧邻非 CJK 非空白字符，
    全部与值无关），值区判据只看「是否为空 / 是否等于占位符字面量」——**不做「像不像值」的形态判断**
    （中文口令因此不再漏检），防误伤靠标签闭集与标签侧边界条件而非值形态；
    值区非空一律原地整体替换（出站与本地同源）；某段脱敏后只剩占位符/标签/分隔符/空白/标点 ⇒ 拒绝该段外发（诚实拒绝）；
    覆盖中文自然语言形态，2026-09-24 第三轮定稿，05 §2.3c.3/§2.3c.4）
    ↓
（任务包内跨 section 去重：goal / 逐字事实 / 项目摘要 / 历史片段 / 证据各自去重，确定性文本规则，05 §2.5 规则 8）
    ↓
授权状态机（task/session 绑定）
    ├── PREPARING：生成 task_id，PrivacyPolicy 准备最终 payload
    ├── AWAITING_AUTHORIZATION：展示 payload；拒绝/取消/5 分钟超时/任务切换 → 清理 pending，不发送
    ├── AUTHORIZED：同任务 grant 内 sub-turn 可复用，不跨后续普通用户回合
    └── 越界/过期/超预算/供应商变化 → 新 grant，重新确认
        ↓
CloudBoundary.check_request（最终独立复核）
    ↓
唯一出口原子预留/消费：出站失败释放 reservation；网络尝试开始即消耗 turn；网络/入站失败不退款并进入冷却
    ↓
SideEffectGateway 唯一出口 → CloudAdvisoryBackend.advise（网络）
    ↓
AdvisoryResult（不可信 advisory：纯文本建议 + risks + requires_local_validation）
    ├── CloudBoundary.check_response（拦截 approved/execution_plan/tool_calls）
    └── 本地重解 → 执行强制确认（受云端影响计划）/ 非执行回流整合
    ↓
最终回复经**与普通回合同一条** episode 写入链落盘（2026-09-24，06 §2.4）：
    User 段 = 原回合用户输入（/cloud allow 是控制指令，不入正文）
    Assistant 段带云端来源标记（固定前缀、本地生成）
    冻结原回合 topic/intent（不为补写回重跑意图解析）——快照载体只有 LocalTaskContext
      （PendingCloudAuthorization 不承载），且必须在进入云端咨询**之前**读取
      （成功/失败两条终局路径都会把 LocalTaskContext 置空）
    每任务恰好一条 episode，且只在终结时写——
      产出授权确认提示的那一回合不写（临时提示不入语义记忆/摘要）
      成功收敛／fallback 收敛：各补写唯一一条
      取消／授权失效／跨会话不匹配／被新输入取代／**云端挂起追问**：零条
      （挂起追问不是答案、也不是用户输入，写进去会被检索当成一条结论）
``` 

> PrivacyPolicy 的 convenient 自动 grant 只适用于硬编码低风险枚举：language、database_engine、os_family、runtime_family、error_class、project_kind 的明确值；自由文本/代码/路径/日志一律需要用户确认。

### 运行事件流（P6a，旁路）

```
Core 各阶段（App 为唯一 emit 者）
    │  结构化 RuntimeEvent（stage + level + 脱敏 data）
    ▼
RuntimeEventSink（Core 接口，构造注入，消费失败吞并不影响主循环）
    ├── CliEventSink        终端显示（简洁模式 = status 级；trace 模式 = 全部）
    ├── JsonlEventSink      脱敏评估事件逐行落盘（P6b 评估数据源）
    ├── NoopEventSink       测试 / 静默运行
    └── CompositeEventSink  组合以上（默认 CLI 组合：Cli + Jsonl 可选）
    ▼
未来 GUI：新增事件消费者即可，不改主循环
```

- App.handle() 签名不变；事件是旁路，与 ReflectionRecorder 同一失败语义
- 事件只带元数据（命中数/分数/类别/字节数/verdict），不带 chunk 原文、prompt、口令、秘密、模型隐藏推理、云端 analysis 原文
- trace 开关是 CLI 显示侧状态，Core 永远发全量事件
- 自有斜杠命令（/status /why /projects /topics /switch /trace /quit）在 CLI 层拦截；其余输入（含 P4 /cloud 指令）原样透传 handle()；命令处理为独立命令层，场景运行器复用

### ControlPolicy 决策表（硬编码规则，不对模型开放）

**云端准入与本地就绪是两个独立判定（2026-09-14 拆分，规范见 05 契约 §1.3）**：有效 READY 只服务「本地回答/执行就绪」；只读云端咨询准入有独立确定语义，不得用本地完整度判断（含 `missing_info`）一票否决云端咨询。每轮判定顺序：dangerous → REFUSE；**悬空指代护栏触发（且非 force 轮）→ ASK_USER（2026-09-16 新增，见下）**；**云端准入通过 → REQUEST_CLOUD（判定结束）**；未准入 → 按下表走本地判定（**原「超轮次 → ASK_USER」已于 2026-09-17 删除**：它不可达且是调度规则而非准入规则；轮次用尽改由 `resolution_exhausted` 在本地判定内处理 → `ASK_USER`，见下）。

**悬空指代护栏（2026-09-16 新增，规范见 `11-reference-guard.md`）**：这是 **intent clarity 域的确定性兜底**，**不是第四个判断**、也不参与云端增益判断。当用户的任务对象由指代表达给出（「那个服务」「它」「上述」等），而本轮输入、会话历史、项目状态**都没有**给出该对象的具体身份时，`decide()` 返回 `ASK_USER`（`reason="dangling_reference"`）。**判据是「指称候选词出现在该来源中」的封闭集匹配，不是「上下文非空」**——「有前文/有历史/有项目记录」都不构成已解析（P5 `projects.auto_create` 默认开启，项目记录恒非空，非空判据会让护栏必然失效）；未识别的指代形态一律 **fail-open 不触发**（宁可漏报、退回既有行为，也不误伤自主升级与强制链）。三条要点：① 判定输入**不含任何模型侧字段**（`state`/`entities`/`missing_info`）——理由是这个能力要修的正是「模型自称 READY 却什么都没读懂」；② 它**不**违反上面那条「不得用 `missing_info` 一票否决云端」——拦下的理由是**任务对象不可确定**（云端同样拿不到用户没说出口的对象），与本地完整度无关；③ 云端准入判定**照常计算并如实记录**（`proposal_gate_result` 仍报 `admitted_proposal` 等），护栏只改写实际动作，因此「模型提议上云、准入通过、被护栏拦下」在事件流里可分辨。`force_cloud`（`/cloud ask`）轮护栏让位——用户显式指令优先于规则对「你没说清楚」的判断，且云端只读无执行权。**让位的是动作，不是评估**：force 轮照常计算并如实记录 `reference_guard_result`（`/cloud ask <任务文本>` 只剥离指令头、载荷照常进护栏），只是不把动作改写成 `ASK_USER`——因此 force 轮场景只验收「动作未被改写」，不断言检测结果。护栏只可能把动作**收窄**为 `ASK_USER`，不放宽任何安全边界。

**云端准入判定（摘要）**：

- 不可绕过否决集（force 也不得绕过）：`deny_cloud` / dangerous / 真实工具执行态与敏感执行链（`task_has_sensitive_execution_chain`，App 确定性状态——模型建议的 `suggested_tools` 与 `risk_draft` **不是**否决项）/ 云端禁用或不可用 / **单任务**预算耗尽或冷却期（同一次云咨询任务及其续咨询 sub-turn 的累计口径；普通对话轮次之间不共享，跨轮限流属新需求）/ 空任务（force 且无实质任务文本 → 本地追问，不发空任务）。
- **仅 proposal 自动路径适用的保守条件**：模型声明了本地动作（`candidate.tool_intent == "local_action"`；2026-09-18 前读 `suggested_tools` 非空，`15-tool-orchestration-hardening.md` §2.5）。它是模型输出，模型总能给出通过值，故不构成安全边界，只作为**自动**升级的保守退出；用户显式 `/cloud ask` **不被其锁死**。**`risk_draft` 已于 2026-09-16 / 2026-09-17 两步完全移出全部否决与保守条件**——它同样不是安全边界，用模型措辞决定链路走不走得下去只贡献随机性（见 12-risk-draft-closed-set.md §3.2）。
- **force 路径**（`/cloud ask`）：有实质任务文本 → REQUEST_CLOUD，绕过模型 READY/置信度/`should_consult`/低效用建议/一般 `missing_info`/模型工具建议/`risk_draft`（`dangerous` 除外，走意图级 REFUSE）与 VAGUE/PARTIAL 标签；模型未提议时 TaskBrief 全部由本地构建。
- **proposal 路径**（无显式命令）：`should_consult=True` + `expected_benefit ≥ 0.5` + 模型未声明本地动作（`tool_intent == "none"`），且目标明确——有效 READY（既有行为），或 **PARTIAL/ALMOST 且 intent 非 unknown**（2026-09-14 新增，缺失信息随包外发）；纯 VAGUE/unknown 不自动升级。
- **准入 ≠ 授权（2026-09-17 裁决）**：准入只决定「这一轮是否请求云端」，是否**可以真正外发**由授权形态决定——**有效授权风险**（`max(模型下界, 确定性升险)`）为 `normal` 时按隐私模式（`convenient` 可 policy grant），为 `sensitive` 时**所有模式都强制用户授权**（进 `AWAITING_AUTHORIZATION`，只认显式 `/cloud allow`，不得 policy grant、不得复用旧授权）。这是把 `sensitive` 的保守性从「否决」挪到「用户确认」，外发边界未放宽（05 §1.3a/§3.2）。
- 模型认为缺失的信息经 TaskBrief `brief_unknowns` 外发（05 §2.5），云端可给条件化分析或经既有 followup 协议受限追问。

**本地就绪判定以客观信号为准（P1 补充）**：模型自报的 `state` 只作参考信号。ControlPolicy 依据 (`model_confidence`, `missing_info`, `intent_type`) **客观裁决**是否就绪，与 `state` 矛盾时以客观信号为准。定义：

> **有效 READY** ≝ `state == "READY"` **或**（`model_confidence ≥ 0.7` 且 `missing_info` 为空 且 `intent_type` 为具体值，即非 `unknown`/空）。

下表中「有效READY」按此定义；「非READY」指不满足有效 READY。如此既保留 FR2 的四态认知循环（state 仍由模型输出并驱动多轮检索），又不把最终调度权交给模型自报的状态标签——小模型常出现「参数齐全、置信高，却自报 VAGUE」的矛盾，此规则确定性收敛。**本表只覆盖本地路径**（云端准入未通过或未触发时适用，且**在 dangerous 与悬空指代护栏之后**）；REQUEST_CLOUD 由云端准入判定独立产生，不在本表。

| 状态 | 置信度 | 风险 | 信息完整 | → NextAction |
|------|:---:|:---:|:---:|------|
| 任意 | 任意 | dangerous | 任意 | REFUSE（最高优先级） |
| state=READY | 任意 | 任意 | 不完整 | ASK_USER（模型声称就绪却有缺失信息，矛盾信号） |
| 有效READY | ≥ 0.7 | normal | 完整 | PLAN_LOCAL（`tool_intent` 为 `local_action` 且有草案则执行；`none` 则条件化/纯分析回复） |
| 有效READY | ≥ 0.7 | sensitive | 完整 | PLAN_LOCAL + 用户确认 |
| 有效READY | [0.6, 0.7) | 任意 | 完整 | PLAN_LOCAL + 用户确认 |
| 有效READY | [0.4, 0.6) | 任意 | 任意 | ASK_USER |
| 有效READY | < 0.4 | 任意 | 任意 | ASK_USER |
| 非READY | 任意 | 任意 | 不完整 | RETRIEVE_MORE（**检索仍有增量且本次解析尚有轮次时**；无进展则 ASK_USER 或条件化本地回答，见下；轮次已用尽则 ASK_USER，见「轮次用尽」段；仅本地路径，云端准入按上文独立判定，不适用本行） |
| 非READY + **轮次已用尽**（`resolution_exhausted`） | 任意 | 任意（非 dangerous） | 不完整 | ASK_USER（`reason="resolution_exhausted"`；**不再返回 RETRIEVE_MORE**——本次解析没有下一轮了） |
| 非READY | 任意 | 任意 | 完整 | ASK_USER（未就绪且置信不足或意图不具体） |

> 上表「风险」列的取值域是闭集 `normal` / `sensitive` / `dangerous`（三行恰好穷举；`dangerous` 行优先级最高）。模型输出的其它措辞（`low`/`medium`/`high`/未识别值/缺失值等）在解析层归一化后才会到达本表——`high`/未识别值/缺失值按 `sensitive` 处理（2026-09-16，见 `12-risk-draft-closed-set.md` §2）。

> 说明：`[0.6,0.7)` 与 `[0.4,0.6)` 等档位仅由 `state=="READY"` 分支进入（客观覆盖分支已要求 `≥0.7`）；即「模型显式自报 READY 但置信中等」时按原有确认/追问档位处理。`intent_resolver` 的多轮循环也以「有效 READY」作为提前终止条件，避免为已就绪的首轮候选空转至上限，并防止后续检索漂移覆盖好候选。

**P6d：零增量提前停止（2026-09-15，规范见 `10-p6d-autonomous-escalation.md` §3）**：真实 S06 run 暴露「检索每轮都跑、每轮零新增、候选语义不变、却机械跑满 4 轮」。修订为**确定性无进展判定**——第 N 轮（N≥2）候选的语义签名（`state` + 规范化 `intent_type` + 规范化 `entities` + 规范化 `missing_info`；**排除** `model_confidence` 与自由文本，防止 0.75→0.85 掩盖语义无变化）与上一轮相同**且**本轮检索净增 chunk 为 0 → 提前停止。停止后处置（`decide(..., no_progress=True)`，位置在**云端准入与本地就绪之后**）：

| 停止后的候选 | → NextAction |
|---|---|
| 云端准入通过 | REQUEST_CLOUD（**建议不会被提前停止吞掉**） |
| 有效 READY | 既有本地分档（不变） |
| ALMOST + intent 非 unknown + normal 风险 + 无工具建议 | PLAN_LOCAL（本地条件化回答，**只读、无需确认**：空计划按构造零副作用；提示词须显式列出采用的假设与尚不确定的信息） |
| 其余 | ASK_USER（**不再返回 RETRIEVE_MORE**——检索已证明无增量，继续返回是空转） |

**P6：轮次用尽（2026-09-17，规范见 `14-resolution-exhausted.md`）**：S03 `round1` 真实 run（`7707d503adc5`）暴露——解析只配一轮时，`IntentResolver` 已用尽轮次，但 `ControlPolicy` 只收到「轮数」无法区分「第 1 轮后仍可继续」与「第 1 轮就是上限」，于是返回了一个**无法执行**的 `RETRIEVE_MORE`。修订为**确定性事实转发**：`IntentResolver` 在循环自然出口（走满实例 `max_rounds` 且未有效 READY、未因 `no_progress` 早停）置 `last_resolution_exhausted=True`，App 原样转发给 `decide(..., resolution_exhausted=…)`（**必传、无默认值**——漏传的后果正是本 bug），第 4 步本地分流在该标志为真时 → `ASK_USER`（`reason="resolution_exhausted"`）。

| 该标志为真时的候选 | → NextAction |
|---|---|
| 云端准入通过（force 或 proposal） | REQUEST_CLOUD（**轮次用尽不抢断用户指令，也不再否决自动升级**——原「超轮次不走云端」规则删除） |
| 悬空指代护栏触发（非 force 轮） | ASK_USER（`dangling_reference`，顺序不变） |
| dangerous | REFUSE（最高优先级不变） |
| 其余（非 READY） | ASK_USER（`resolution_exhausted`） |

**与 `no_progress` 的区别（不得混用）**：`no_progress` = 「连续两轮语义签名不变 **且** 本轮检索净增 0」（模型侧停滞，可给条件化本地回答）；`resolution_exhausted` = 「走满本地轮次预算且未 READY」（预算侧耗尽，只追问）。两者**由构造互斥**，观测上必须分列（`intent_final` 的 `no_progress_detected` / `resolution_exhausted` 两个键，键集见 07 §2.2），混用会让模型停滞率虚高并掩盖预算配置问题。**位置在云端准入之后**：轮次用尽只是「不要再向模型要下一轮」，不是「不许上云」。

**边界**：提前停止只能**减少**轮数，不绕过 `max_rounds`、安全否决、用户授权与出站链路；检索**失败**的轮次不判无进展（不把故障固化成「已收敛」）。同时 P6d 让「为什么上云/为什么没上云」可观测——模型侧事实（`proposal_present`/`should_consult`/`expected_benefit`/`escalation_reason`）落 `intent_final`，规则侧（`proposal_gate_result`/`proposal_denied_reason`）落 `dispatch_decision`，逐轮检索增量落 `intent_round.new_memories`（封闭集见 07 §2.2）。**控制权不变**：新增的都是确定性规则与结构化观测，模型仍只提建议。

### 高影响批准流程（P6，2026-09-16，规范见 `13-approval-profile-high-impact.md`）

风险闭集**不变**（仍是三值），但 `dangerous` 的语义收窄为「越权 / 恶意 / 规避安全控制 / **无法形成有界目标**的破坏行为」；「合法但高影响」不再走 `dangerous` 的死路，改由 `sensitive` 内部的**独立确定性批准档**承接：

```
IntentCandidate（意图级；模型无 approval_profile 字段）
    ↓
ControlPolicy：dangerous → REFUSE（最高优先级，不变）/ 其余照旧
    ↓
TaskPlanner.plan() → ExecutionPlan
    ↓
GuardedToolExecutor.preflight()：逐 step 取动态评估
    effective_profile = max(step, ToolDef, 后端 preflight)   ← 只升不降
    （授予源只有两条，均为确定性：工具注册表静态声明 + ToolBackend.preflight 动态声明）
    ↓
App._handle_action() 分支优先级（顺序不可调换）：
    effective_risk == "dangerous"      → 硬拒绝（含 preflight 的 workspace_escape）
    approval_profile == "high_impact"  → 【P6】扣留计划：零工具执行 + 不可执行草案 + 明确说明
                                         不建 pending、不设 requires_confirmation、不可被确认放行
                                         **任意非 dangerous 风险都拦**（normal 与 sensitive 一视同仁）
                                         正常响应，不抛异常；执行层另有同名冗余防线（抛 SAFETY_IMPACT_CLOSED）
    requires_user_confirmation         → P3 确认链（敏感操作单次确认 + 口令）
    否则                                → 直接执行
```

**P6 执行态关闭（无条件）**：`high_impact` 在 P6 只开放「分析、补充条件、生成不可执行草案」，副作用执行保持关闭。理由是五条件中只有 2 条（目标锁定 ← `PreflightReport.target_key`、身份验证 ← `IdentityVerifier`）有确定性载体，**备份/恢复点、回滚方案、范围锁定**无任何表示——让模型「声明已具备」即自证缺陷。五条件固定为**未来执行态的前置条件**，P6 不评估；不得把普通 `sensitive` 的单次确认复用为放行条件。

**与危险语义的边界**：收窄**只针对模型措辞**，**不**豁免确定性升险——`preflight` 对工作区逃逸等确定性事实返回 `effective_risk="dangerous"` 仍是 fail-safe 硬拒绝，且 `approval_profile` 的任何取值都不改变该结果（见 13 §1.3）。

---

## 三、模块划分

### 3.1 架构铁律

1. **受保护副作用边界**：本地工具副作用（文件、Shell、MCP）经 `GuardedToolExecutor` 收口；云端网络副作用经 `SideEffectGateway` 收口（P4）。任何外部操作不得绕过对应出口。
2. **云端输出始终需本地验证**：可包含结构化建议（含工具建议），但必须标记为建议，由 GuardedToolExecutor 验证后执行。v1 可保守使用，根据表现逐步放开。
3. **模型只提候选，ControlPolicy 做决定**：模型输出 IntentCandidate + 置信度，策略层根据规则执行调度。工具调用同样是候选——模型只能提出「工具名 + 参数」的草案（2026-09-18，模块契约 15），**不能**标记批准、确认或已执行。
4. **自进化是旁路系统**：v1 只记录候选经验（draft），不自动执行，不参与高危决策。
5. **Adapter 不反向决定 Core**：外部组件的数据模型和控制流不能侵入 Core。
6. **完成性陈述必须可溯源到执行记录**（2026-09-18）：「已创建/已覆盖/已执行」类陈述只能由真实执行结果确定性构造；模型声明了本地动作而工具调用未建立的回合，可见回复必须是不经模型生成的确定性文案。副作用只经唯一出口（铁律 1）之外，**陈述也必须有唯一来源**。
7. **相关性的权威是作者声明的关系，不是模型的判断**（2026-09-20，模块契约 16）：工具「与当前请求是否相关」的唯一权威是**注册表里作者声明的「能力 → 工具」关系**（`ToolCapability.tools`），运行期判定是对该关系的**集合隶属**；模型只能从**闭集**里选能力、只能在**所选能力的工具集**内给草案。`intent_type` / `tool_intent` / 回复文本 / 模型的任何自述**都不是**相关性判据（同一个模型生成的 `intent_type` 与 `tool_call` 自洽**不构成**证据）。**本铁律的射程（2026-09-20 Codex 复审后收窄）**：它约束的是「**哪一类工具集合可能被执行**」，**不**判定「所选能力是否真的匹配用户意图」——模型选错能力、而草案恰好落在所选集合内时**仍会执行**，本层在结构上发现不了（`16` §0.2 ①）。故「模型能造成的最大错误被压缩为诚实失败」**只在「能力选对、草案越界」这一种错误下成立**；「能力选错但草案在集合内」这一残余风险改由三件事**结构性**限制可达后果：①**只读能力**（`files.read`）的集合内工具全部只读；②**写能力**（`files.write`）按注册期不变式**独占该能力且不得声明可补参**（S1/S2），使「写工具缺参被下一轮输入填满」在注册期即不可达；③**外网工具**的入参值受**来源、实例、内容**三级约束（`16` §6.3 第 4 条，**2026-09-23 由两级扩为三级**）。**同一 doctrine 的第二次应用（2026-09-23，S18 真实 run）**：「参数值是否有效实例」的权威**同样是作者声明的关系、不是模型的自述**——判据住**工具声明**（`ToolDef.param_instance_checks`），Core **只调用、不内置领域知识**（地名 / 时间词表一律住工具层，**不进 Core、不进配置、不进提示词**）。判定在**参数进入判定链之前**（准入级）⇒ 零外发 / 零完成性叙事 / 零云端咨询是**结构性事实**；判定不过的处置是**当缺参**（追问 + 既有续接状态），**不是**失败，也**不新增任何错误码或分类值**（`16` §0.5 / §6.3.x）。**⚠️ 诚实边界（2026-09-20 第二轮复审更正）**：②**不是**确认链兜底——写工具的危险档由**文件是否存在**在 preflight 决定（新建 = `normal` = **免确认直接执行**，`src/tools/registry.py:85` / `src/tools/file_tools.py:71`），所以「模型误选能力落到写工具」**当前仍能免确认新建文件**。**2026-09-20 老板拍板（同日第三轮）**：该缺口改由**产品策略**封堵——`file.write` **一律进确认链**，作为**独立前置变更 P7a-0** 落地（不并入能力层编码批次，以便关/开对比可归因）；**P7a-0 落地后**②升级为「写入前必经用户确认」，最坏后果 = 一次用户可拒绝的确认；**落地前**照实按未覆盖表述（`16` §11 第 21 条、`clarifications.md` 拍板登记）。措辞纪律：这是「**限制错误的可达后果**」，不是「发现错误」。

### 3.2 Core 层模块

#### InputNormalizer
```
职责：将原始输入转为标准 InputEvent
输入：raw_text
输出：InputEvent { text, session_id, project_id?, timestamp, source }
不做复杂安全判断，只做基础清洗和元数据补齐
```

#### IntentResolver
```
职责：多轮按需检索，输出意图候选
状态机：VAGUE → PARTIAL → ALMOST → READY（硬上限4轮）
输出：IntentCandidate {
  state, intent_type, entities, missing_info,
  suggested_tools,                     # 2026-09-18 起降级为纯观测字段，不作任何判定输入
  tool_intent, tool_call, tool_call_resolution,   # 结构化工具草案 + 归一化结论（15 §2）
  risk_draft, model_confidence, reasoning
}
依赖：ContextAssembler、MemoryBackend（接口）、ModelBackend（接口）
```

#### ContextAssembler
```
职责：为每次模型调用组装最小上下文
只允许加载：当前会话摘要、项目摘要、相关记忆片段、工具目录
禁止：一次性加载全部历史
输出：MinimalContext { system_prompt, current_input, relevant_history, project_state?, tool_defs, capabilities }
依赖：MemoryBackend（会话/项目摘要、记忆检索）、ToolBackend（工具目录→ tool_defs）
工具目录（2026-09-18，模块契约 15）：tool_defs 是 ToolBackend.list_tools() 的原样结果，
含 name / description / 完整参数结构（JSON Schema 子集：type / properties / required）/ risk_level；
它是「提示词里的工具清单」与「解析层闭集校验」的唯一来源，逐轮现取、不缓存。
工具数上界 32：bootstrap 为主防线、本模块每轮为冗余防线（数量/重名/schema 合法性，
违例 CONFIG_ERROR fail-loud，禁止截断）。故提示词长度是**每轮被显式校验的有界量**，
不参与 relevant_history 的字节预算。
能力目录（2026-09-20，模块契约 16）：capabilities 是 ToolBackend.list_capabilities() 的
原样结果（ToolCapability{capability_id, summary, tools}），本模块只**校验并写**、**不渲染**
（渲染唯一实现点仍是 IntentResolver）。能力数上界 8 / 序列化 2048 UTF-8 字节，校验纪律同工具目录。
```

#### ControlPolicy
```
职责：非模型化调度决策——模型提候选，策略做决定
实现：纯 Python 规则引擎，不调用模型
输入：IntentCandidate（含 ConsultationProposal，以及工具四字段 `tool_intent` / `tool_call` / `tool_call_resolution` / `tool_intent_conflict`——权威定义见 `15` §2）+ CloudControlState + 确定性事实（`no_progress` / `reference_guard` / `resolution_exhausted` / `tool_defs`）+ 用户指令 + 预算/会话状态（P4）
输出：NextAction
  类型：ASK_USER | RETRIEVE_MORE | PLAN_LOCAL | REQUEST_CLOUD | REFUSE
  附带：reason, requires_user_confirmation
  云端咨询由「模型建议 + 用户显式指令 + 确定性否决条件/预算」组合裁决（P4）；
  云端准入与本地就绪为两个独立判定（2026-09-14）——is_effectively_ready 只服务本地路径，
  云端准入按 05 §1.3 否决集 + force/proposal 两路径裁决，missing_info 不一票否决云端咨询
  草案完备性（2026-09-18，模块契约 15）：模型声明「本回合需要本地动作」（tool_intent）
  时，由策略判定草案是否成立——参数缺失 → ASK_USER（确定性追问，不编造参数）；
  工具名未知 / 参数类型错 / 无草案 / 多个草案 → PLAN_LOCAL + 对应 reason，
  由 App 出确定性失败回复（不走模型自由文本）
```

#### TaskPlanner
```
职责：把 READY 的意图转成本地执行计划
约束：只能生成本地工具计划，云端不产生此结构
     不得出现任何工具名字面量或按工具名分支的逻辑（即插即用，模块契约 15 §4）
输入：IntentCandidate.tool_call（结构化草案）+ MinimalContext.tool_defs（运行时闭集）
输出：ExecutionPlan { steps: [{ tool_name, action, params, risk_level }] }
参数来源（2026-09-18）：params 只来自草案的 arguments；entities 退化为观测字段，
     不再是执行输入。工具名未知或参数校验不通过时不建 step、返回空计划，
     并把「为什么」交给策略层的 reason（空计划的两种含义必须可区分）
```

#### ResponseBuilder
```
职责：整合工具执行结果，组装回复文本
```

#### ReflectionRecorder
```
职责：v1 只做记录，不做自动进化
  - 记录原始对话
  - 提取候选经验（标记 draft）
  - 不自动生成可执行技能
  - 不参与高危操作决策
v4+：接入 EvolutionBackend，draft → validated → active 生命周期
```

### 3.3 安全控制层模块

#### SafetyPolicy
```
L1 硬规则（写死，零开销）：禁止路径、命令模式、敏感信息正则
L2 语义检测（通过 SafetyBackend 接口）：模型判断操作危险性
    - 当前实现：QwenPawSafetyBackend（封装 ToolGuard）
    - 接口隔离：SafetyPolicy 依赖 SafetyBackend，不直接继承 ToolGuard
L3 执行三关（高危操作触发）：
  ① 相关性：操作目标与当前意图关联？
  ② 必要性：此操作真的需要？参数正确？
  ③ 身份：二次确认 + 口令验证
```

#### GuardedToolExecutor（本地工具副作用的收口）
```
职责：本地工具副作用（文件、Shell、MCP）的执行出口
流程：
  1. 校验工具在白名单内
  2. 调用 SafetyPolicy 三关检查
  3. 执行工具
  4. 记录审计日志
约束：任何 Core 模块不得绕过此层直接调用文件/Shell/MCP
```

#### SideEffectGateway（云端网络副作用的收口，P4）
```
职责：云端咨询的受保护执行出口
流程：
  1. CloudBoundary.check_request（出站白名单+脱敏）
  2. CloudAdvisoryBackend.advise（网络调用，仅此一处）
  3. CloudBoundary.check_response（入站验证）
  4. 记录 CloudAuditEvent 审计
约束：云端网络调用只发生在 SideEffectGateway 内部；App/Core 不得直接调用 CloudAdvisoryBackend.advise
```

#### PrivacyPolicy + AuthorizationManager（P4）
```
职责：本地分级隐私与有限授权
PrivacyPolicy：对模型候选上下文做来源分类、类型/长度限制、凭据与高风险模式检测、脱敏和语义占位替换；不调用网络、不信任模型分类
  · 凭据检测**不自持模式集**——委托 `src/safety/secret_scan.py` 单一真源，覆盖中文自然语言形态（2026-09-24，05 §2.3c）；命中 = 标签 + **边界成分**（显式分隔符 / 空白 / 紧邻非 CJK 非空白字符），值区 = 标签之后到行末（独占一行时顺延一次），值区判据只看「空 / 等于占位符字面量」，**不判值形态**（判形态会使 `密码 abc123`、`密码是abc，青山绿水` 一类中文口令漏检）；值区非空一律原地整体替换，出站与本地同源；出站侧另有一条**与凭据无关的诚实拒绝**（脱敏后该段已无任务语义 ⇒ 拒绝外发）
  · TaskBrief 各 section 之间做确定性去重（2026-09-24，05 §2.5 规则 8）
AuthorizationManager：创建/验证 task+session+provider+purpose+类别/payload+预算+过期绑定的 grant；范围扩大、过期、任务/供应商变化须重授权
模式：严格（每次确认）/ 平衡（默认，同任务有效 grant 复用）/ 便捷（仅低风险结构化字段可签发有限自动 grant）
```

#### CloudBoundary
```
职责：云端通信的最终独立出站/入站复核
出站：复核 grant 绑定、字段类别/fingerprint、预算、脱敏结果与秘密/高风险模式；失败拒绝，不做"删一点继续发"
入站：校验返回内容，确保不包含工具调用或批准标记
```

#### 云端 Provider 层（P6c，modules/09-p6c-cloud-provider.md）
```
职责：决定「数据发往哪个云端、用哪个凭据」，不改变任何安全语义
组成：
  - CloudProviderProfile + CloudProviderRegistry：代码白名单的 provider 连接事实
    （api_base / completion_path / default_model / credential_env / openai_compatible），
    首批内置 deepseek、glm，另支持 custom_openai（HTTPS api_base + 自配 model，出站 URL 硬校验）
  - OpenAICompatibleAdvisoryBackend：通用适配器，实现 CloudAdvisoryBackend；
    Bearer 鉴权、请求、超时、响应提取、AdvisoryResult 解析与错误分类统一承载
  - CloudCredentialLoader（接缝）：provider 专属凭据读取（v1 环境变量；
    产品化可替换为系统凭据库，不改主循环与适配器协议）
规则：
  - 活动 provider 由 [cloud_advisory].provider 唯一决定（模型不得选择 provider）；
    provider_id 是 grant/package/审计绑定的稳定标识，不等于类名
  - 同一 provider 的连接字段不可被配置覆盖安全项；provider 切换后旧 grant 一律失效
  - 凭据 provider 专属、缺失 fail-closed；构造期不读 Key
约束：Core 只依赖 CloudAdvisoryBackend 抽象与 provider_id 字符串；注册表与 profile 在 adapter 层
```

#### IdentityVerifier
```
v1 范围：
  - 口令首次启动设置，SHA-256 哈希存本地
  - 连续 5 次失败锁定 10 分钟
  - 行为识别仅记录日志，v2 才作为放行依据
```

### 3.4 增强模块（Phase 4+ 接入，v1 仅 stub）

| 模块 | v1 状态 | 完整形态 |
|------|---------|----------|
| ExpertScheduler | 同模型 + 不同 system prompt | 真实多模型按需加载 + LRU 淘汰 |
| CloudAdvisoryTool | 返回 "云端暂未启用" | AdvisoryResult 硬约束 + sub-turn 检查 |
| EvolutionBackend | Noop 实现 | EverOS / 自研 经验提取 + 技能蒸馏 |

### 3.5 接口抽象层

```python
# ── 模型后端 ──
class ModelCapabilities:
    """Adapter 启动时声明，Core 据此调整策略"""
    supports_structured_output: bool  # 是否支持 JSON schema 约束
    max_context_tokens: int           # 最大上下文长度
    local_only: bool                  # 纯本地还是依赖外部 API

class ModelBackend(ABC):
    def generate(self, prompt: str, response_schema: dict = None) -> dict: ...
    def stream(self, prompt: str) -> Iterator[str]: ...
    def get_capabilities(self) -> ModelCapabilities: ...

# ── 记忆后端 ──
class MemoryBackend(ABC):
    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryChunk]: ...
    def store_episode(self, content: str, metadata: dict) -> str: ...
    def get_summary(self, scope: str, scope_id: str) -> dict: ...

# ── 工具后端（Core 不直接依赖，由 GuardedToolExecutor 内部持有）──
class ToolBackend(ABC):
    def list_tools(self) -> List[ToolDef]: ...
    def list_capabilities(self) -> List[ToolCapability]: ...   # 2026-09-20（契约 16）
    def execute(self, tool_name: str, params: dict) -> dict: ...
# 工具目录即运行时闭集（2026-09-18）：ToolDef 含完整参数结构（JSON Schema 子集，
# 仅 type / properties / required；其它键注册期拒绝，见 15 §1.1），
# 含必填）与 risk_level，是提示词清单、解析层成员校验、参数校验的唯一来源
# 能力目录（2026-09-20，契约 16）：ToolCapability{capability_id, summary, tools}——
# **类型定义在 src/core/schemas.py**（与 ToolDef 同处；2026-09-20 第三轮复审修正：
# 四处消费方里三处在 src/core/ ⇒ 放 src/tools/ 会让 Core 反向依赖工具层并循环 import），
# 由 src/tools/base.py 与 ToolDef 并列重导出；**声明与校验**在 src/tools/capabilities.py；
# 作者声明的「能力 → 工具」关系，是**能力相关性的唯一权威**（铁律 7）——
# 它界定的是**哪一类工具集合可能被执行**，不判定「所选能力是否真的匹配用户意图」
# （2026-09-20 口径收窄，Codex 复审第 1 条；残余风险与后果兜底见 16 §0.2 ① / §2.6）；
# MinimalContext.capabilities 是**三态**（16 §3.8 末条 / §9.2 C6）：
#   None = 路由关闭（唯一来源 = 配置 enabled=false）；() = 开启但目录为空（⇒ 诚实失败）；
#   非空 = 开启。**不得**另立 enabled 状态——层与层的开关只有这一个表示。
#   测试替身的 list_capabilities() 默认返回 []：配 enabled=true ⇒ () ⇒ 诚实失败（安全方向）；
#   要回到 15 基线必须显式 enabled=false（**不再有「空目录 ⇒ 不做能力判定」这条含义**）
# ToolDef 的三个可选字段（2026-09-23 第三次修订后定稿，契约 16 §1.1 / §1.5 / §4.4 / §6.4）：
#   supply_by_echo: tuple[str, ...] = ()   # 声明「可由用户文本直接补参」的参数名白名单。
#       # 它是**唯一**的跨轮补参声明源，同时决定「哪些参数的出站值必须整串逐字来自用户原文」——
#       # 声明与来源校验共用一份声明，二者不会漂移。P7a 只声明 weather.current.location；
#       # **写侧副作用工具（LOCAL_SIDE_EFFECT_TOOLS）不得出现在任何 supply_by_echo 中**（S2）。
#   audit_redact_all_params: bool = False  # 本次审计把该工具**全部参数值**写成 "***"（键名保留）。
#       # 天气工具为 True。该字段不进入提示词渲染（render_tool_catalog 是显式白名单）。
#   param_instance_checks: Mapping[str, ParamInstanceCheck] = {}   # 2026-09-23 新增（契约 16 §1.1/§6.3.x）
#       # 声明「哪些参数的值必须是**有效实例**」以及判据（ParamInstanceCheck{predicate, reject_whole_input}）。
#       # **判据住工具层、Core 只调用**（rejected_instance_params）——领域知识（地名/时间词）不得进 Core/配置/提示词。
#       # 不过则**当缺参**（剔除该键 ⇒ 追问 + 既有续接状态），**不是**失败、不新增错误码或分类值。
#       # 字段本身必须 hash=False（frozen dataclass + Mapping 参与哈希会崩）；谓词必须是模块级稳定对象（R8）。

# ── 安全后端 ──
class SafetyBackend(ABC):
    def check_dangerous(self, operation: dict) -> SafetyVerdict: ...

# ── 云端咨询后端 ──
class CloudAdvisoryBackend(ABC):
    def advise(self, request: CloudRequestPackage) -> AdvisoryResult: ...

# ── 自进化后端（v1 Noop）──
class EvolutionBackend(ABC):
    def reflect(self, task_context: dict) -> List[Experience]: ...
    def get_skills(self, intent: str) -> List[Skill]: ...

# ── 运行事件出口（P6a）──
class RuntimeEventSink(ABC):
    def emit(self, event: RuntimeEvent) -> None:
        ...  # 消费一个脱敏运行事件；实现不得抛出异常影响主循环
```

**架构铁律（防止 Core 依赖具体实现）：**

1. Core 不 import ollama / turbo_llm / qwenpaw / everos
2. Core 只依赖 core/interfaces.py 中的抽象接口
3. 每个 Adapter 启动时声明 ModelCapabilities
4. 所有 Adapter 由配置创建并依赖注入，Core 不手动 new 具体实现
5. P0 测试必须用 MockBackend 跑通全部核心闭环
6. 新增后端只需新增 adapters/xxx_adapter.py + 改配置，不改 Core
7. ToolBackend 执行权不对 Core 暴露——Core 可读取工具目录（list_tools，逐轮现取，作为提示词清单与解析层闭集校验的唯一来源，2026-09-18），但执行工具必须通过 GuardedToolExecutor
8. 外部网络只在工具 handler 内发生（2026-09-20，契约 16）：任何工具的网络调用只由其 handler 触发，而 handler 只由 `GuardedToolExecutor` 调用——**不得**为「预热」「健康检查」「提前校验参数」绕过执行器发起请求；`preflight` hook **不得**发起网络请求（否则确认会在用户看到请求之前把数据发出去）

**统一错误类型：**

```python
class LocalMindError(Exception): ...
class ModelError(LocalMindError): ...
class SafetyDenied(LocalMindError): ...
class ToolError(LocalMindError): ...
# 其他错误用 LocalMindError + code 字段区分，不无限增生子类
```

| 实现 | 实现接口 | 场景 |
|------|:---:|------|
| MockModelBackend | ModelBackend | P0 不调 Ollama |
| OllamaModelBackend | ModelBackend | P1+ 真实模型 |
| SQLiteMemoryBackend | MemoryBackend | v1 默认 |
| EverOSAdapter | MemoryBackend + EvolutionBackend | 之后可选 |
| QwenPawToolBackend | ToolBackend | 工具执行 |
| OpenMeteoWeatherProvider | WeatherProvider（**局部 Protocol，不进 interfaces.py**，与 OllamaTransport/CloudTransport 同法） | P7a：`weather.current` 的数据源，固定两个 HTTPS 主机、禁重定向、两段超时、64 KiB 上限、严格 JSON；由配置 `weather.provider` 选择（`none` = 能力不存在） |
| RuleOnlySafetyBackend | SafetyBackend | P0 默认，L1 规则（无 LLM 依赖） |
| QwenPawSafetyBackend | SafetyBackend | P3 接入，L2 语义检测（封装 ToolGuard） |
| NoopCloudAdvisoryBackend | CloudAdvisoryBackend | enabled=false 一律注入（含已配置具体 provider 时——能力层 fail-closed，09 §5.2）；enabled+noop 为配置矛盾 |
| OpenAICompatibleAdvisoryBackend | CloudAdvisoryBackend | P6c：deepseek / glm / custom_openai 经 profile 复用（09 契约） |
| NoopEvolutionBackend | EvolutionBackend | v1 stub |
| NoopEventSink / CliEventSink / JsonlEventSink / CompositeEventSink | RuntimeEventSink | P6a：静默 / 终端显示 / JSONL 评估记录 / 组合 |

### 3.6 记忆分层与信任等级

| 记忆类型 | 存储 | 信任等级 | 参与决策 |
|----------|------|:---:|:---:|
| RawEpisode（原始对话） | MemoryBackend | 原始数据 | 仅检索 |
| ConversationSummary（会话摘要） | MemoryBackend | 自动生成 | 可自动加载 |
| ProjectState（项目摘要） | ProjectStore（JSON） | 人工维护 | 可自动加载 |
| MemoryChunk（检索片段） | MemoryBackend | 检索结果 | 参考辅助 |
| — 事实身份标注（2026-09-24，`05` §2.5 规则 9） | — | — | 摘要类行（自动生成 / 用户手写）与逐字检索片段**注入上下文与外发时必须带彼此不同的固定来源前缀**；「事实」section 只承载用户逐字陈述，摘要不得扩张事实 |
| ExperienceDraft（候选经验） | EvolutionBackend | 未验证 | **仅检索，不自动执行** |
| ValidatedExperience（已验证经验） | EvolutionBackend | 人工确认 | 可检索参考 |
| SkillDraft（候选技能） | EvolutionBackend | 未验证 | **仅检索，不自动执行** |
| ActiveSkill（已启用技能） | EvolutionBackend | 人工审查 | 可自动执行 |

---

## 四、核心数据结构

### 4.1 InputEvent
```json
{
  "text": "查一下 project-a 的端口是否还在运行",
  "session_id": "sess_001",
  "project_id": "proj_project-a",
  "timestamp": "2026-07-01T10:30:00",
  "source": "cli"
}
```

### 4.2 IntentCandidate（模型输出）
```json
{
  "state": "READY",
  "intent_type": "check_system_status",
  "entities": { "project": "project-a", "target": "port" },
  "missing_info": [],
  "suggested_tools": [],
  "tool_intent": "local_action",
  "tool_call": { "tool_name": "system.check_port", "arguments": { "project": "project-a" } },
  "tool_call_resolution": "resolved",
  "tool_intent_conflict": false,
  "risk_draft": "normal",
  "model_confidence": 0.72,
  "reasoning": "用户明确要求检查 project-a 的端口状态"
}
```

**工具四字段（2026-09-18 新增，权威定义见 `specs/modules/15-tool-orchestration-hardening.md` §2）**：

- `tool_intent ∈ {none, local_action}`——模型对**本回合是否需要本地动作**的显式声明。它是**唯一**的工具侧判定输入（`suggested_tools` 已降级为纯观测）。
- `tool_call`——结构化草案 `{tool_name, arguments}`；`tool_name` 必须落在 `list_tools()` 的运行时闭集内，`arguments` 是**参数的唯一来源**（`entities` 退化为观测字段）。
- `tool_call_resolution ∈ {resolved, absent, invalid_shape, unknown_tool, multiple_proposed}`——**解析层的归一化结论，随候选携带**（与下面的 `risk_draft_resolution` 同法）。四个字段同源同点写入，**任何其它层不得重写**；解析层是唯一归一化点。`resolution != "resolved"` 时下游**不得**调用 `validate_tool_call`（那是解析层职责），直接按失败形态分流。
- `tool_intent_conflict: bool`——**原始**输入自相矛盾的标记（原始 `tool_intent == "none"` 却给出了非空 `tool_call`，被归一化覆盖为 `local_action`）。**纯观测，不改变任何行为**；判定所需原始值在归一化后即丢失，故**结论必须由解析层当场写入本字段**（不得放到 `IntentResolver.last_*` 旁路），App 只做原样转发。

**能力两字段（2026-09-20 新增，权威定义见 `specs/modules/16-p7-practical-tools-capability-routing.md` §2/§3）**：

- `capability_id: str | None = None`——模型对本回合**需求域**的选择，只能取**闭集**（**声明的全量**能力 id + `"none"` + `"unsupported"`；**2026-09-22 更正**：原第 2 项的 `"unavailable"` 是要求模型断言注册表事实，已移除——可用性由系统派生，`"unsupported"` 是需求侧出口「目录不足以覆盖」且**原样落盘**）。它**不是**相关性判据：相关性由「草案工具 ∈ 所选能力的工具集」这一**集合隶属**判定（铁律 7）。
- `capability_resolution ∈ {routed, none, unavailable, unrecognized, absent}`——**解析层的归一化结论**（与 `risk_draft_resolution` / `tool_call_resolution` 同法）。**闭集外值 fail-closed 到「不可用」的**行为**、但保留 `unrecognized` 的**归因**；字段缺失 = `absent`（过渡兼容：无草案时行为与 P6 逐字相同，有草案时一律 `unrouted_tool` 拒绝，**不猜归属**）。
- 两个字段与 `tool_intent` / `tool_call` / `tool_call_resolution` **同源同点一次写完**（解析层是唯一归一化点），**任何其它层不得重写**。

**`risk_draft` 是闭集（2026-09-16 钉死，权威定义见 `specs/modules/12-risk-draft-closed-set.md`）**：合法取值**只有** `normal` / `sensitive` / `dangerous`。该字段**只**表达「**本回合实际请求的动作**是否触及敏感/危险操作」（2026-09-17 钉死判定对象：只读分析 / 排查建议 / 架构权衡 / 迁移规划 / 回滚设计默认 `normal`，即使话题涉及生产、切流、数据库、部署或高影响系统；`sensitive` 的充分条件只有「本回合实际含敏感数据」与「本回合实际请求需确认的副作用」），**不表达**任务难度、重要性、篇幅、影响面或模型自信程度。

- 模型输出的任意其它措辞（`low`/`medium`/`high`/`critical`/中文等级词等）在**解析边界**由唯一实现 `normalize_risk_draft()` 归一化：大小写与首尾空白统一；旧词表固定映射 `low→normal`、`medium→sensitive`、`high→sensitive`；**字段缺失 / 空 / 非字符串 / 未识别值一律 → `sensitive`（fail-closed 到保守档）**——schema 的 `required` 不构成保证（同 §0.3 边界声明），缺失与乱码同为「模型没有给出可用断言」，故同档处理。闭集外的原始字符串**不得**进入 `ControlPolicy`/`TaskPlanner`/`GuardedToolExecutor`。
- 归一化来源以 `IntentCandidate.risk_draft_resolution`（`declared`/`mapped_legacy`/`absent`/`unrecognized`）随候选携带并落 `intent_final` 事件。
- **消费方只读闭集**：ControlPolicy 做闭集精确比较，对闭集外值总量有定义——`strip().lower() == "dangerous"` 的写法变形按 `dangerous` 处理，其余按 `sensitive`，**不得退化为 `normal`**（`12-risk-draft-closed-set.md` §2.1.1）。
- **消费语义**：`dangerous` → 意图级 `REFUSE`（最高优先级，不可绕过）；`normal`/`sensitive` → 本地计划档位（后者需用户确认）；**云端准入的 force 与 proposal 两条路径都不读该字段做否决**（2026-09-16 / 2026-09-17 两步移出）——它对云端链路**唯一**的作用是**授权形态**。见 05 §1.3a/§3.2。
- **该字段不是安全边界，只是风险下界（2026-09-17 补）**：决定授权形态的是**有效授权风险** = `max(模型声明的下界, 确定性升险结果)`——确定性升险源**恰两项**（payload 候选的隐私分类、`task_has_sensitive_execution_chain`）**只能升险**，适用信号缺失即按 `sensitive`（fail-closed）；「隐私扫描没发现问题」**不得**把模型声明的 `sensitive` 降回 `normal`。因此有效风险非 `normal` 的任务在所有隐私模式（含 `convenient`）下都强制用户授权，`create_policy_grant` 收到的是**授权时求出的有效值**（只有它等于 `normal` 才可签发）。**工具计划 / preflight 类风险不进这条判定**（2026-09-18 收窄）：policy grant 发生在云端续咨询阶段，那时通常既无 `ExecutionPlan` 也未跑 preflight，把它们列为输入会让「未求值即 `sensitive`」把自动续咨询整条锁死；它们走本地执行那条正交链路（07 §6.3、13 §2，只升不降）。**双向都验**：既要验升险（`12` E1/E2），也要验 `normal` 仍能签出（`12` E8）——恒返回 `sensitive` 的实现同样违约。权威定义见 `12-risk-draft-closed-set.md` §3.5。
- **它也不复制工具层的动态风险（2026-09-17 补）**：工具层的确定性风险由注册表基线 + 确定性 preflight 只升不降给出，本字段既不复制、也不压低它（07 §6.1/§6.3、`12` §1.2 表注）。**⚠️ 2026-09-20 反转（老板拍板，P7a-0）**：原文此处写的「工作区内新建文件在意图层与注册表基线都是 `normal`、S14『新建无需确认』」**已作废**——`file.write` 的注册表基线改为 `sensitive`、`requires_confirmation=True` 恒真（新建与覆盖都确认）。**本字段本身的口径不变**（意图层风险仍不复制工具层风险），变的是工具层的基线值与 S14 的期望；两层「只升不降、互不压低」的结构不变。

### 4.3 NextAction（ControlPolicy 输出，模型不产此结构）
```json
{
  "action": "PLAN_LOCAL",
  "reason": "意图明确，风险低，工具参数完整",
  "requires_user_confirmation": false
}
```

### 4.4 ConsultationProposal（本地模型输出，仅建议）
```json
{
  "should_consult": true,
  "escalation_reason": "architecture_tradeoff",
  "expected_benefit": 0.72,
  "candidate_context": [
    {"category": "user_entity", "label": "database_engine", "value": "postgresql"},
    {"category": "free_text", "label": "query_summary", "value": "..."}
  ],
  "reasoning": "本地缺少该领域的最新最佳实践"
}
```

- `ConsultationProposal` 只表示模型建议；模型无权调用云端、无权批准任何字段外发、无权扩大既有 grant。`proposed_question` / `local_attempts_summary`（05 §1.1）等新字段是不可信候选素材，仅作 TaskBrief 输入。
- `candidate_context` 中的值按来源和敏感级别分类，由 PrivacyPolicy 重新判定，不能因模型标签自动信任；`label` 本身也是不可信文本通道（05 §2.3 规则 8）。
- 实际外发的任务语义由本地构建的 `TaskBrief`（目标/硬约束/已知事实/相关片段/本地尝试/待推理问题，05 §2.5）承载，经 `context_items` 传输；硬约束与结构化事实优先来自配置、工具结果、记忆系统。

### 4.5 CloudRequestPackage（PrivacyPolicy 产出，已授权）
```json
{
  "task_id": "task_sess_001_...",
  "session_id": "sess_001",
  "provider": "deepseek",
  "purpose": "architecture_tradeoff",
  "grant_id": "grant_...",
  "context_items": [
    {"category": "user_entity", "label": "database_engine", "value": "postgresql", "redacted": false},
    {"category": "secret_placeholder", "label": "api_key", "value": "present", "redacted": true}
  ],
  "allowed_scope": "仅提供分析建议，不生成执行命令或计划",
  "turn": 1
}
```

- 只由 PrivacyPolicy + 有效 grant 共同生成；CloudBoundary 必须独立复核，不信任任何调用方。
- 每个 context item 保留 `category`、`label`、脱敏结果，grant 绑定其允许类别或确切 payload。
- `task_id`/`session_id`/`provider`/`purpose`/`grant_id`/`turn` 及 HMAC fingerprint 都是本地边界字段，适配器**不得**序列化或发往云端。
- `provider` 的取值是 provider_id（09 契约 §1）——用户配置选择的稳定标识，不等于适配器 Python 类名；切换 provider 即切换授权边界（旧 grant 失效）。

### 4.6 AuthorizationGrant（有限授权边界）
```json
{
  "grant_id": "grant_...",
  "task_id": "task_sess_001_...",
  "session_id": "sess_001",
  "provider": "deepseek",
  "purpose": "architecture_tradeoff",
  "authorized_categories": ["user_entity", "free_text"],
  "payload_fingerprints": ["hmac-sha256:..."],
  "max_turns": 3,
  "max_context_items": 12,
  "max_context_bytes": 32768,
  "expires_at": "2026-09-02T11:00:00Z",
  "issued_by": "user"
}
```

- HMAC fingerprint 仅供本地授权比较，HMAC key、fingerprint 均不外发。
- grant 是不可变边界；可变 `GrantUsage` 另存 `reserved_turns`/`consumed_turns`/`consumed_context_bytes`/`cooldown_until`。
- `max_turns` 是网络请求轮数，`max_context_items` 与 `max_context_bytes` 是**单 package**上限，三者单位不混用；示例值取配置默认（`max_context_items=12` 容纳 TaskBrief 6 section + 最多 3 个 `brief_unknowns` item + 实体，2026-09-14 由 8 上调；`context_byte_budget=32768`，2026-09-17 由 2048 上调、同日二次裁决定为 32768，05 §2.5/§8）。
- **`context_byte_budget` 是 TaskBrief 的唯一字节硬边界**（2026-09-17）：`brief_*` section 没有独立字节上限（原「单 section ≤ 400 UTF-8 字节」已删除），整包经清洗与确定性同值去重后仍超预算 → 整包 fail-closed，不截断外发。配置合法范围：`max_context_items ∈ [1,100]`、`context_byte_budget ∈ [256,65536]`（65536 为绝对硬上限），默认 32768，构造期非法值 `CONFIG_ERROR`（05 §8/§10.10）。**超预算不做三件事**：不按字段优先级截取、不动态扩容 grant、不做二次长度确认——既有 `/cloud ask` + 完整授权 preview 就是唯一的外发确认。
- grant 不可扩大：新增类别、新自由文本值、不同 provider/purpose/task/session、超 turn/单包预算或过期均失效并需重新确认。网络尝试开始即消耗 turn；出站失败不消耗；网络失败/入站拒绝不退款并进入冷却。
- 任务级台账（05 §3.3）：同 task 全部 grant 累计 `consumed_turns` ≤ `max_turns_per_task`，边界扩大型新 grant ≤ 2（首次 grant 不计数）；同 task 至多一个活跃 grant，新 grant 签发即吊销旧 grant。

### 4.7 AdvisoryResult（云端返回）

```json
{
  "analysis": "分析结论",
  "suggested_tools": [
    {
      "tool": "db_ops.create_index",
      "params": { "table": "orders", "columns": ["user_id", "created_at"] },
      "rationale": "查询条件包含 user_id 并按 created_at 排序"
    }
  ],
  "risks": ["索引会增加写入成本约 10-15%"],
  "requires_local_validation": true,
  "needs_more_info": false,
  "requested_context_categories": [],
  "followup_question": ""
}
```
- `suggested_tools` 为可选字段，v1 不启用，观察本地模型能力后再决定是否开放
- 无论是否包含工具建议，`requires_local_validation` 始终为 true
- 任何工具建议必须过 GuardedToolExecutor 安全三关
- 云端不能标记自己的建议为 approved，不能跳过本地验证
- `requested_context_categories` 是 follow-up 的**唯一状态机输入**，仅可为 `memory_evidence` / `user_entity`（05 §6.1 白名单）；未知值由本地归一化丢弃，归一后为空或本地产不出新内容时按最终 advisory 收敛
- `followup_question` 是不可信展示文本：仅本地展示并标注「云端非可信提示」，不回传云端、不进模型 prompt、不写入记忆、**审计不记其原文**（05 §4.3/§6.1）

### 4.8 AuditEvent（GuardedToolExecutor 记录，安全/回放/反思的基础）

```json
{
  "audit_id": "audit_001",
  "task_id": "task_20260701_001",
  "intent_id": "intent_001",
  "tool_name": "system.check_port",
  "params_redacted": { "project": "project-a" },
  "risk_level": "normal",
  "verdict": "allowed",
  "reason": "L1/L2/L3 全部通过",
  "timestamp": "2026-07-01T10:30:05"
}
```

### 4.6 后续模块 spec 需钉死的细节（不在此展开）

| 细节 | 归属 spec |
|------|----------|
| 话题切换 4 种关系（same / new / shift_with_reference / ambiguous） | MemoryBackend spec |
| 性能三档指标（目标 / 最低可接受 / 调试模式） | 测试规范 |
| ControlPolicy 6 种边缘情况（JSON 解析失败、工具不在白名单等） | control_policy spec |
| 错误契约 5 字段（code + message + user_message + recoverable + details） | 00-error-contract.md |

---

## 五、项目结构

```
localmind/
├── README.md                       # 项目名 + 一句话定位
├── pyproject.toml                  # 项目元数据 + 依赖 + ruff/mypy/pytest 配置
├── .gitignore
├── .env.example
├── CLAUDE.md                       # Claude Code 协作规范
├── specs/                          # 设计文档（Claude 产出）
│   ├── requirements.md
│   ├── project-plan.md
│   ├── boss-report.md
│   ├── clarifications.md           # Claude ↔ Codex 通信通道
│   └── modules/
│       ├── 00-project-scaffold.md  # 工程初始化规范
│       ├── 00-core-interfaces.md   # 6 个抽象接口完整签名
│       ├── 00-error-contract.md    # 错误类型与传播规则
│       ├── 00-adapter-factory.md   # 配置、bootstrap、依赖注入
│       └── ...                     # 各 Core 模块 spec（按需新增）
├── src/
│   ├── main.py                     # 入口 + bootstrap + 主循环
│   ├── core/
│   │   ├── interfaces.py           # 所有抽象接口（6 个 ABC）
│   │   ├── schemas.py              # 所有数据结构（dataclass）
│   │   ├── input_normalizer.py     # 输入清洗 → InputEvent
│   │   ├── intent_resolver.py      # 意图理解状态机（4 轮上限）
│   │   ├── context_assembler.py    # 上下文最小化
│   │   ├── control_policy.py       # 规则调度（纯 Python，不调模型）
│   │   ├── task_planner.py         # 生成本地执行计划
│   │   ├── response_builder.py     # 组装回复
│   │   └── reflection_recorder.py  # 旁路经验记录
│   ├── safety/
│   │   ├── policy.py               # SafetyPolicy（L1 + L2 + 三关串联）
│   │   ├── guarded_executor.py     # GuardedToolExecutor（本地工具副作用收口）
│   │   ├── side_effect_gateway.py  # SideEffectGateway（云端网络副作用收口，P4）
│   │   ├── cloud_boundary.py       # 云端出站/入站检查
│   │   ├── identity.py             # 口令验证
│   │   └── rule_only_backend.py    # RuleOnlySafetyBackend（P0 L1 硬规则）
│   ├── memory/
│   │   ├── in_memory_backend.py    # InMemoryMemoryBackend（P0 默认）
│   │   ├── sqlite_backend.py       # SQLiteMemoryBackend（P2）
│   │   ├── project_store.py        # 项目摘要管理
│   │   └── retrieval.py            # 检索 + 差异化留存
│   ├── models/
│   │   ├── mock_backend.py         # MockModelBackend（P0 默认）
│   │   └── ollama_backend.py       # OllamaModelBackend（P1）
│   ├── tools/
│   │   ├── base.py                 # ToolDef, ToolBackend 接口重导出
│   │   ├── registry.py             # 工具注册表 + 白名单
│   │   ├── builtin_backend.py      # BuiltinToolBackend（P0 默认）
│   │   ├── file_tools.py
│   │   ├── system_tools.py
│   │   └── cloud_advisory.py
│   ├── evolution/
│   │   ├── noop_backend.py         # NoopEvolutionBackend（P0 默认）
│   │   └── skill_lifecycle.py
│   ├── observability/              # P6a：NoopEventSink / JsonlEventSink / CompositeEventSink
│   ├── cli/                        # P6a：交互式 CLI 入口 + 命令层 + CliEventSink
│   └── adapters/
│       ├── qwenpaw_adapter.py      # P7
│       ├── everos_adapter.py       # 暂不排期（接口保留）
│       └── mcp_adapter.py          # P7
├── config/
│   └── default.toml                # P0a 默认配置（tomllib 零依赖；mock + in_memory + builtin_only + rule_only + noop）
├── data/
│   └── .gitkeep                    # 运行时数据目录，内容 gitignore
├── tests/
│   ├── conftest.py                 # 共享 fixtures（mock 后端实例）
│   ├── test_schemas.py
│   ├── test_interfaces.py
│   ├── test_intent_resolver.py
│   ├── test_control_policy.py
│   ├── test_context_assembler.py
│   ├── test_safety_policy.py
│   └── test_guarded_executor.py
├── docs/
└── scripts/
    └── run_p0a.py                  # P0a 演示脚本
```

---

### 5.1 基础契约文档（编码前优先完成）

| 文档 | 内容 | 说明 |
|------|------|------|
| `specs/modules/00-core-interfaces.md` | 6 个抽象接口的完整签名、参数、返回值、异常约定 | ModelBackend、MemoryBackend、ToolBackend、SafetyBackend、CloudAdvisoryBackend、EvolutionBackend |
| `specs/modules/00-error-contract.md` | 统一错误类型定义、传播规则、处理模式 | LocalMindError + ModelError / SafetyDenied / ToolError |
| `specs/modules/00-adapter-factory.md` | Adapter 创建规范：配置→工厂→依赖注入，Core 不接触具体实现 | 确保换后端只加 Adapter 文件不改 Core |

---

## 六、开发路线图

| 阶段 | 目标 | 外部依赖 | 验证标准 |
|:---:|------|:---:|------|
| **P0** | Mock 核心闭环 | 零 | Mock 模型跑通：输入→理解→决策→RuleOnlySafetyBackend(L1 规则可用)→白名单工具→回复→记录 |
| **P1** | 接入 Ollama | Ollama | 真实本地模型对话可用 |
| **P2** | SQLite 记忆 | 无 | 对话记录存储；按需检索可用；差异化留存生效 |
| **P3** | 安全边界强化 | QwenPaw ToolGuard | GuardedToolExecutor 统一出口；三关检查；口令锁定；L1 规则生效 |
| **P4** | 云端建议工具（重设计） | 云端 API | 受控推理升级：TaskBrief 最小任务包 + 分级授权外发；ConsultationProposal 组合裁决；PrivacyPolicy 脱敏；有限 grant + 任务级扩张上限；AdvisoryResult 硬约束；sub-turn 检查 |
| **P5** | 项目记忆 | 无 | 项目摘要；话题切换检测；两层持久化 |
| **P6** | 可观测真实 Agent 闭环 | Ollama + 云端 API（P6b） | P6a：交互式 CLI + RuntimeEventSink 事件流 + 工作区内 file.write；P6b：16 个真实场景可重复运行（首轮只跑子集，08 §2.4）+ JSONL 评估记录 + 人工评分（G1/G2 匿名 A/B 对照）；P6c 前置：多云 Provider 最小底座（deepseek/glm/custom_openai profile + 专属凭据 + 错误分类，09 契约，使云端评估可使用用户自购平台）；P6c：证据驱动的调整闭环（先采集、再调整，不预设结果，08 §7）；**P6d：自主云端升级与渐进理解效率优化（10 契约）——区分「任务不明确」与「任务明确但本地能力不足」、校准 ConsultationProposal 的提议时机、无新增信息时提前停止不再跑满轮次、让运行事件能解释「为什么上云/为什么没上云」、修掉零命中被谎报为 embedding 降级的假信号；**并行子项：悬空指代识别与追问（`11-reference-guard.md`，2026-09-16 依据 S02 真实复现立项）——无历史、空检索库时模型从不追问「那个服务」所指为何，以确定性护栏兜底，规则产物走独立 `reason`、不改写模型 `missing_info`/`state`/`entities`、不参与云端准入判定，S02 验收拆判 `model_asked`/`guard_rescued`/`unattributed_ask`/`failed` 四态，并硬断言护栏确实触发（`reference_guard_any=true`）**。验收：定向观测集（S05 0/3、S09 ≥2/3、S06 cloud_auto ≥2/3、S11 0/3，各 3 run，不进 pytest）+ 确定性单测；安全不变量一律不变** |
| **P7a** | 实用能力与能力路由 | Ollama + 固定 HTTPS 天气服务 | 能力先于工具名（16 契约）：能力目录（有界、稳定排序）+ 两阶段路由（能力 → 该能力的工具）+ 能力相关性的**集合隶属**边界（铁律 7；**约束的是「哪一类工具集合可能被执行」，不是「所选能力是否匹配意图」**）+ 无匹配能力时确定性诚实失败（零执行 / 零完成性声明 / 不转云端）+ 缺参追问的**确定性续接**（零模型调用）；首个真实工具 `weather.current`（固定主机 + HTTPS + 禁重定向 + 两段超时 + 64 KiB 上限 + 严格 JSON + 键名级审计，只发地点且**出站值过三级校验：准入级（解析层整串逐字来源校验，不过则不产生草案、零工具执行）+ 准入级（实例性，2026-09-23 新增：判据由工具声明承载，不过则当缺参 ⇒ 追问 + 零外发）+ 执行级（形态 / 秘密形态）**；写侧工具按注册期不变式**独占能力且禁止可补参**（S1/S2），但**新建文件免确认**这一残余风险不在 P7a 范围、需需求层决策）；`system.echo` 退出生产/试用配置。验收：16 §9 的 C1–C15 + W1–W10 + 非干扰性五条（关态 = P6 基线逐字段相等）+ S17/S18 + S01–S16 回归（零文本改动、零断言放宽）；**真实 run 之前不得宣称「日常可用性达标」**（16 §9.4 措辞纪律） |
| **P7a-0**（2026-09-20 拍板，**前置小变更**） | `file.write` 一律确认 | 无（纯策略/基线变更） | **老板拍板**：新建与覆盖都进确认链（作废 2026-09-10 的「工作区新建直接执行」）。改动面：工具注册表基线 `normal→sensitive` + `requires_confirmation` 恒真、preflight 语义、`07` §6.1/§6.3/§12、`12` §1.2/§1.2.1/§1.3、`13` §2/§3.2、`15` §6.3、`08` §2.6 硬性行与 S14 期望、`requirements.md` FR3。**为何单列**：它改的是 **P6 的安全基线与 S14 的两种臂**——与能力层同期落地，会让 P7a §9.1 第 4 条的关/开对比**无法归因**（分不清差异来自能力层还是风险策略）。**必须复跑**：P6 基线在变更后重新测量（新的「关态 = 基线」锚点），S14 两臂期望同步反转 |
| **P7b**（2026-09-25 立项，`17-p7b-mcp-qwenpaw-tool-ecosystem.md`） | MCP / QwenPaw 工具生态接入 | MCP（**stdio only**；QwenPaw Skills 按 MCP 标准接入） | **建立可扩展、可替换的通用工具接入底座，并用少量工具验证**（不追求一次接入大量工具）。**权威归属已定**：外部工具要能被用，必须先在**本地代码**里存在一条准入声明（规范名 / 所属能力 / 风险基线 / 副作用分类 / 参数契约全部本地签发）；外部自报只是**候选人**，只能影响 `available`、**永不影响 `allowed`**，且**外部文本零进提示词**。**四条边界**：①两阶段能力路由仍是唯一准入路径（`[tool_providers]` 非空 ⇒ 能力层必须开启，否则 fail-loud）②`GuardedToolExecutor` 仍是唯一执行出口 ③动态变化**只能朝收紧方向**自动生效（不热插拔/不自动重启/忽略 `tools/list_changed`）④v1 只准入 `read_only` + 参数类型只允许 `string` + **只有本地 stdio transport**（远端需独立出站论证）。**兑现 16 §11 第 22 项**：`ToolDef` 新增 `egress`，把 P7a 的源码级断言升级为通用注册期不变式（E11/E12），天气回填。**首批工具**：`file.stat`（新增只读 + `files.info` 能力）、`demo.json_format`（外部，经 `scripts/mcp_demo_server.py`，`text.format` 能力）；`system.get_time` **复用不新增**；**不重复实现天气与既有文件工具**；首批外部工具刻意选纯函数式 ⇒ **不新增网络或文件目标面，新增一个受控的本地进程出站面**（**2026-09-26 措辞修订**：原稿写「引入零新外发面」不准确——用户原文确实离开 Agent 进程进入 MCP 子进程）。**QwenPaw 接入 = MCP 标准 + 换后端接入点**（`ToolProvider` + 工厂单一分支）——**接入点 ≠ 已验证的接入**：本轮无真实 QwenPaw / 第三方 MCP 服务参与互操作验证，报告不得宣称「QwenPaw Skills 已接入」（登记为 `17` §11 第 12 项）；原生 `skills_dir` 适配器与 ToolGuard L2 延后（触发条件见 `17` §11）。**架构边界（2026-09-26 据实修订）**：事件闭集**零扩展**、`App` **构造签名**零变更、`ToolBackend` 接口**新增一个带默认实现的 `close()`**——**两项零变更 + 一项必要变更**（资源生命周期所必需）；**命令由本地代码签发**（`ProviderDeclaration`），配置只留 `enabled` + 两个超时且键集闭集；**子进程环境白名单**（禁止继承 `os.environ`）；**超时即作废协议流**；**帧结构逐方法区分** + 协议版本闭集 + **显示净化**。**据实登记**：FR3（外部工具不得直接产生副作用）**对任意第三方 provider 不成立**——准确称谓是「**受信任的已安装代码**」，命令进代码只是可审查、不是沙箱。验收：`17` §10.2 的 M0–M7 / P1–P11 / X1–X9 / N1–N5（每条含**探针**）+ 新场景 S19 |
| **P7c**（2026-09-27 立项，`18-p7c-local-document-and-search-tools.md`） | 本地文档读取、工作区搜索与只读结果回流 | Python 解析库（`pypdf`/`python-docx`/`openpyxl`/`python-pptx`，**正常依赖**）；可选外部二进制 ripgrep | **只做两个本地只读工具，日常可用性不得以扩大副作用面或泄漏面为代价**（不介入联网搜索）。**`document.read`**：PDF/DOCX/XLSX/PPTX/TXT/MD，带来源定位（页码/段落/表格行/工作表行/幻灯片）的有界结构化文本；**五重上限**（文件大小/提取字符/提取段数/返回段数/返回字符）且超限必须告知未返回数量、未知总数必须为 `null`、**`truncation_reason` 闭集含 `max_extracted_chars` 且哪个提取上限先命中记哪个**、「至少返回一段」**只适用 `extraction="ok"`**；**逐格式提取范围钉死**（DOCX 读正文段落 + 表格、不读页眉页脚；XLSX `read_only=True` + **`data_only=False` 返回公式文本**；PPTX 读文本 + 表格、不读备注）；**OOXML 的 ZIP 条目数与总解压大小上限，检查在解析器之前**；**空文档与扫描 PDF 是成功不是失败**（`extraction="empty"`/`"no_text_layer"` + `notice`）；格式与扩展名不符 ⇒ fail-closed；解析器异常只记类名不记 `str(exc)`。**`file.search`**：文件名（Python 引擎，不按扩展名忽略）与内容（ripgrep 优先 + Python 降级）双模式；内置忽略集为**单一常量、两引擎共用**，配置**只能追加不得豁免**；`--no-ignore` 必需（`data/` 被 gitignore 而 `data/workspace` 正是搜索根）**且必须同时把同一份忽略策略编译为排除参数**（**两段式：引擎裁剪只省遍历且必须保守 / 权威过滤是唯一语义来源**）；**两个引擎都跳过隐藏条目**；**两引擎差异只允许在「候选发现」、不允许在「结果产出」**；排序在收集后自己做（不透传 ripgrep 顺序）；**空查询必须失败**（返回空集会让模型如实说出错误结论）；**超时零结果**（部分结果不可复现）；引擎不能提供的计数填 `null` 不得填 0。**路径安全完全复用 `15` §6.1，零新增判据**；搜索独有的新口子是遍历期软链接 ⇒ **不跟随任何符号链接（含 `os.walk` 会放进 `filenames` 的文件符号链接）** + 结果阶段逐条包含性复检（**定位为纵深防御，靠注入伪造候选验收**）。**新增只读工具结果回流层**：判据是 `ToolDef.result_delivery` **注册期声明**（默认 `deterministic` 保证既有工具逐字不变）、**不得按工具名特判**；RD1–RD3 不变式让「让模型改写写入结果」与「外部文本经回流进提示词」成为**注册期不可达**；唯一实现点、两个 `response.build` 调用点共用；文档内容是**不可信数据**、`notice`/计数置于正文前且**不受截断**；**结构性承诺是「注入不产生动作」**。**变更影响据实**：**两处**接口签名变更（`ToolDef.result_delivery` + `ExecutionRecord.result_delivery`，均追加式带默认值）+ 公开化 `sanitize_display_text()`/`DISPLAY_LIMIT` + 主流程三处变更（两个调用点插入回流 / `_execution_records` 增参 / `App` 增注入口与冻结字段；**"App 零变更"结论作废**）+ `bootstrap()` **签名不变但新增一步内部装配**（构造并注入回流组件；**"`bootstrap()` 步骤零新增"同样作废**）+ 事件**类型**零新增但新增**条件**键 `result_delivery`（两份白名单同步）+ `weather.current` 零改动（且因 RD3 永不进回流）。**回流沿用模型后端自身超时**（`[reflow]` 键集闭集**不含** `timeout_ms`；**禁止**用线程等待伪造超时），本阶段不承诺回流延迟上界。依赖为**正常依赖**（**原「必须明确依赖缺失行为 ⇒ 必须是 extra」的推导不成立**），`parser_unavailable` 保留但覆盖面改为**安装损坏/部分安装/打包剥离**，逐格式独立判定且不影响启动。**不做**：`web.search`/`web.fetch`/OCR/文档编辑/内容索引/旧格式 `.doc`·`.xls`·`.ppt`。验收：`18` §12 的 D1–D16 / F1–F13 / **R1–R21**（每条含**探针**）+ 非干扰 N1–N7 + S20/S21（`docs_on`/`docs_off`，`_EXPECT_KEYS` 新增 **`result_delivery_any` 与 `output_not_contains`**；**S20 为 identity + 确认四步**，第②步另断言口令字面量不出现在用户可见输出里）+ S01–S19 回归；**场景层只能用 `.md`/`.txt` 夹具**（`_SETUP_KINDS` 限制），Office/PDF 由单元矩阵覆盖 |

> 路线图在 P7 后暂时结束（2026-09-10 调整）。原 P7（专家模型调度）与原 P8（自进化旁路）移出：相应接口 stub 保留，待 Agent 真实使用中暴露的问题决定后续方向。
>
> **P7a 的交付默认是「开」**（2026-09-20，`16` §9.1 第 1 条的完整论证）：`config/default.toml` = `capability_routing.enabled=true` + `tools.weather.provider="open_meteo"`。关态（`enabled=false`）与 `provider="none"` 是**评估锚点/回退档**，不是交付形态——关态下能力层完全不参与，FR10 的诚实失败与相关性边界**结构上不成立**（把它们写成「默认关闭」等于交付一个功能上不存在的能力层）。评估运行器用 `--capability-off` 构造关态对照批；真实 run 暴露问题时的**回退顺序**是 `provider="none"`（保住诚实失败与零外网）→ 必要时 `enabled=false`（逐字回到 P6 基线）。
>
> **P7 拆分（2026-09-20）**：原「MCP / QwenPaw 与工具生态」拆为 **P7a 实用能力与能力路由**（先做，16 契约）与 **P7b 工具生态接入**（**2026-09-25 立项，17 契约**）。依据：老板真实试用中「天气提问被连续三轮追问地点 → 补地点后调用 `system.echo`」，暴露的是**能力层的缺失**（无法表达「没有这个能力」、也没有任何语义相关性判据），而 MCP 与插件平台要求**编译期常量之外**的动态能力声明，两者的安全前提不同，不能合成一个阶段。
>
> **P7b 的开工前置已核**（2026-09-25）：①P7a 的能力路由已在真实运行中验证（FPGA 演示 + S17/S18）；②「动态能力声明由谁签发」已裁决——**本地代码签发权限、外部自报只作候选人**（`17` §1.1 的三来源 × 九类事实权威表），使 16 的 R1–R8/S1/S2 与 `capability_relevance()` 集合隶属权威**原样成立**，外部能力与内置能力**合并成同一份目录、跑同一套校验**。**P7b 不引入任何新准入路径、新执行出口或新提示词段**——它是一次**接入**，不是一次架构变更（`17` §2.4：**两项零变更 + 一项必要变更**）。**2026-09-26 补充**：唯一的那一项变更是 `ToolBackend.close()`——它不改变编排逻辑，只补上原稿缺失的**进程回收路径**；同时据实登记**进程级副作用不在 `GuardedToolExecutor` 的约束范围内**（该出口只能约束工具调用），故外部 provider 的准确定位是「**受信任的已安装代码**」，FR3 对任意第三方 provider 不成立。
>
> P6 期内的加固契约（12 risk_draft 闭集、13 批准档、14 轮次用尽、15 工具编排加固）**不新增阶段**：它们修的是 P6 真实 run 暴露的既有缺陷，验收以各自契约的验收矩阵为准（15 为 §9 A1–A13）。**同理，16（P7a）虽引入新阶段，但改动仍在既有主循环内的一层声明 + 首个真实工具，不含新框架**（16 §11 第 6 项）。
>
> **P7c 的范围已被老板刻意收窄（2026-09-27 立项，18 契约）**：P7c **只做两个本地只读工具**（`document.read` / `file.search`），**不介入联网搜索**——不实现通用 `web.search`、不引入 Tavily / SearXNG / 搜索 API Key / 任何搜索 provider 配置，与 16 §11 第 1/2 项一致（搜索是独立能力，不能由云端模型冒充）。**「日常可用」是动机，「不加面」是纪律**：两个工具都是只读、都不进副作用路径、都复用既有路径安全实现（零新增判据）、都复用既有净化出口（零新增实现）。P7c 的**新口子只有一个**：搜索在**遍历期**遇到的软链接（`resolve_workspace_target` 只保护搜索根）⇒ 用「不跟随任何符号链接 + 结果阶段逐条包含性复检」封闭，而不是加参数黑名单。
>
> **P7c 审查后的两处据实修订（2026-09-27，老板 4 个阻塞项 + 3 项补充全部采纳）**：①**新增只读工具结果回流层，并因此作废「App 零变更」的结论**——原稿把 P7c 的目标写成「提取并显示文档原文」；实测执行链是「工具执行 → `ResponseBuilder` 直接显示 → 结束」，`ResponseBuilder` 最多显示 4096 字符且**全程无模型调用**（`narrative_reply` 是常量字符串），模型**看不到工具结果** ⇒「总结这份 PDF」结构上不可能完成，`max_returned_chars=40000` 也失去意义。因此新增一段通用回流层（判据为 `ToolDef.result_delivery` 注册期声明，非工具名特判；RD1–RD3 使「让模型改写写入结果」与「外部文本进提示词」成为注册期不可达；唯一实现点、两个调用点共用；失败回落确定性显示）。**它是 P7c 的能力前提，实施顺序排在两个工具之前**（`18` §13.3 第 1 步）。②**依赖策略反转为正常依赖**：原推导「因为必须明确依赖缺失行为，所以依赖必须是 optional extra」**不成立**——安装损坏/部分安装/打包剥离同样产生模块缺失；P7c 是默认启用的日常能力，"支持 PDF"却让首用普遍失败是产品缺陷。`parser_unavailable` 保留，覆盖面改为异常安装。**未做真实 run 前不得宣称「日常可用性达标」**；报告还须照实写明四条覆盖率天花板（安装状态、无 OCR、跨引擎一致性只对 UTF-8 成立、**注入的后果上界只是「不产生动作」而非「已解决」**）。
>
> **P7c 第二轮审查后的据实修订（2026-09-27，老板 4 个阻塞项 + 2 处文字全部核实成立并采纳）**：四个问题的共同形态是**契约写下了一个在现有代码上兑现不了的东西**（纸上自洽、落地不成立），处置分别为——①**删除回流的单次调用超时配置**：模型接口没有调用级超时参数（超时在后端构造期固定），回流限不住自己这一次调用；回流改为**沿用后端自身超时**，并**明文禁止**用「起线程等 N 秒后放弃」伪造超时（放弃等待不取消底层请求，会把线程泄漏伪装成超时，验收以「回流模块零线程/定时器导入」作源级断言）。②**给执行记录补一个可选字段承载回流状态**（本阶段第二处接口签名变更，追加式带默认值、既有调用零改动）：此前契约只说"回流要在记录事件之前完成"，**没说状态怎么传过去**；明确**按步骤序号关联、不按工具名**（同一次计划可两次调用同名工具），且不得用列表下标冒充步骤序号（记录构造时有过滤逻辑）。③**把回流输出的净化与长度上限真正钉死**：契约曾称"回流输出仍经原有显示净化"，而**真实链路是回流产出文本后直接返回**、根本不经过它 ⇒ 将私有的消毒函数与显示上限常量提升为公开符号，确定性显示与回流两条路径**共用同一份实现、同一个上限数**，回流输入与模型输出都施加它，并实测终端控制字符不会进入命令行。④**修正一个结构上不可达的验收场景**：文档读取默认需用户确认，原场景只写了"读并总结"一步，首轮必然停在等待确认 ⇒ 补齐为「预置身份与文件 → 读请求（断言停在确认）→ 确认口令（断言工具执行且发生回流）」四步；免确认的搜索场景则**不需要**身份预置，其首轮"工具已执行"断言本身就是"免确认"的证明。**文字订正**：删除"较大的返回长度配置用于执行记录留存"的说法（**与代码不符**——执行记录只存字段名摘要、明确不保留返回值，该长度只是**执行期内存上限**，默认口径下大部分内容随回合结束丢弃）；契约末尾的"三项待老板拍板"补齐为**带编号的决策表**，三项按老板意见定稿（两个只读工具的确认语义不变、当前默认上限可接受、本阶段允许修改依赖清单把四个解析库列为**正常依赖**），另两项开放且**不阻塞开工**。验收相应扩为回流层 **R1–R15**。
>
> **P7c 第三轮审查后的据实修订（2026-09-27，老板 3 个阻塞点 + 1 处工程契约残留全部核实成立并采纳；老板明确「暂时不建议开始编码」，本轮只改契约）**：这一轮暴露的不是"漏了东西"或"写了兑不了现的东西"，而是**契约自身的状态与类型缺陷**。①**[状态丢失·严重] 确认路径拿不到原始用户请求**——`src/main.py:223-241` 的九个 `_pending_*` 字段**没有一个保存原始请求**，`_handle_confirmation(passphrase, session_id)`（`src/main.py:792`）签名里拿不到它，确认回合的 `current_input` **就是确认口令**，而 `_record_turn("[身份确认，原文不留存]", …)` 是 P4 **有意**不保留原文 ⇒ 回流会把**口令**当请求喂给模型，「总结这份文档」在确认路径上**结构性不成立**（直连路径无此问题：那里 `current_input` **就是**原始请求）。裁决：**新增冻结载体 `App._pending_user_request`**，进入等待确认时冻结，**必须在 `execute()` 之前先取出到局部变量**（`_clear_pending()` 在 `src/main.py:881` **先于**执行发生）；生命周期挂在**既有 `_clear_pending()`（唯一清理点，加一行）**上，八条路径（取消/拒绝/会话不匹配/口令错误/锁定/预检失败/TOCTOU 变化/执行完成）全部覆盖。**红线**：冻结值**只作回流输入**，不得进 episode / 记忆 / 事件 / 审计 / 云端；`_record_turn` 占位文案**保持不变**（**不放松 P4**——"回流需要原文"≠"可以留存原文"）。**断言分半并照实登记**：提示内容那半**场景层断言不了**（真实 run 只能观测事件与输出，提示词是私有输入、不进持久面）⇒ 归 **R16**（替身模型捕获提示，另含八条路径后冻结值为 `None` 与"冻结值不出现在任何输出面"两臂）；场景层承担**可观测后果**那半——新增 `output_not_contains`，S20 第②步断言口令字面量**不出现在用户可见输出里**。②**[返回类型不足·严重] `reflow()` 只返回 `Mapping[int, str]` 装不下最终回复**——调用方要的是**一句回复文本**，映射只带"哪些 step 走了模型摘要" ⇒ 定义 **`ReflowOutcome(display: str, deliveries: Mapping[int, str])`**（**一处新增 Core 类型**，`00-core-interfaces.md`），**失败回落返回同一结构** ⇒ 两个调用点**零分支**（`outcome = self._reflow(...)` → `return outcome.display`，**不得**出现 `if reflow_succeeded`）。三态钉死：无可回流 ⇒ `display` **逐字节等于** `output.display` 且 `deliveries == {}`；成功 ⇒ 消毒+截断后的模型输出；失败 ⇒ 确定性回落文本。③**[夹具不可构造·中等] R14 原夹具不可能存在**——`result_delivery` 是 **ToolDef 级**固定声明 ⇒ 两个同名 step **声明必然相同**。**先钉死多 step 策略**（**每回合至多一次**回流模型调用，覆盖集 = `outcome == "success"` 且声明 `model_summary` 的全部 step ⇒ 覆盖集内取值**必然相同**；输入按 **`step_index` 升序**、每段标注 `tool_name` + `step_index`、**共享同一份 `max_chars` 预算**；逐 step 调用会产生 N 个独立候选文本而每回合只有一句回复，成本还线性增长），**再改写 R14** 为**直接对 `_execution_records` 注入 step_index 映射**（两个同名 `document.read` step + `deliveries={1: "model_summary"}` ⇒ 断言 step_index=1 有值、step_index=0 仍为 `None`），断言对象从"计划能否构造"改为"**回填会不会按工具名串写**"。④**[残留·中等] `00-adapter-factory.md` 仍把 `timeout_ms` 列为 `[reflow]` 合法键**（第二轮只清了 `18`、漏了镜像）⇒ 该处改为**仅 `enabled` / `max_chars`**，同一事实在两处不一致本身就是缺陷。验收扩为回流层 **R1–R18**（新增 R16 确认路径的冻结原文 / R17 每回合至多一次调用 / R18 多 step 归属可区分），`_EXPECT_KEYS` 再 **+1**（`output_not_contains`），并新增**第六条不得宣称**：**不得把"S20 通过"读成"确认路径的回流输入已在真实 run 里验证过"**——场景能证明的是后果，提示内容只有 R16 覆盖。
>
> **P7c 第四轮审查后的据实修订（2026-09-27，老板 1 个阻塞性接线遗漏，核实成立并采纳；口径仍为"暂不编码"）**：这一轮的形态与前四轮都不同——不是"漏了东西"、也不是"写了兑不了现的东西"，而是**契约内部两处规定互相不接**：一处说 `App` 增加 `reflow` 参数，另一处（示范的装配代码）**既不构造它、也不传它**。由于新参数**带默认值 `None`**，照此实现能通过全部类型检查、进程正常启动，**但真实配置下回流永不发生**：声明了"结果交给模型总结"的文档读取工具会退化成"打印一截结构化文本"，第一轮那个缺口原样复现。**最危险的地方是它不易被发现**——单元测试通常直接构造 `App(reflow=替身)`，于是回流层验收**可以全绿而缺陷仍在**。裁决：①装配示范**新增构造与注入这一步**（解析配置 → 构造回流组件 → 传入 `App`）；②`App.__init__` 的签名块补上该参数（**追加置尾 + 默认值**，既有构造调用零改动）；③**口径订正**——"装配函数步骤零新增"**作废**，准确表述是"**签名零变更，但装配步骤有新增**"；④**新增 R19**：**必须走真实装配路径**（不得直接构造 `App` 注入替身），断言返回的 `App` 确实持有**启用**的回流组件、且端到端确实发生了模型调用。**探针 = 删掉那一处构造与传参 ⇒ 只有 R19 变红、其余回流条目仍可全绿**，这正是它存在的理由。⑤同一份配置的键集与默认值**只有一处实现**，装配侧与工具后端侧调用**同一个函数**，不得各写一份默认值（那就是第二份真源，属同型缺陷）。**通用纪律（已写入契约的完成判据）**：凡新增的是**带默认值的可注入组件**，必须同时钉住**构造点**与**注入点**，并给一条**只走真实装配路径**的验收条目——**"接口加了参数"与"装配处传了参数"是两件事**，默认值会把缺失伪装成可选项。验收扩为 **R1–R19**，新增**第七条不得宣称**：**不得把"回流层验收通过"写成"文档总结在生产配置下可用"**——两者之间没有蕴含关系，该蕴含只由 R19 承担。
>
> **P7c 第五轮修订（2026-09-27，由 Codex 在进入 RED 阶段时提出，两个契约级输入缺口，经源码核实成立；仍未编码）**：契约给出的回流调用 `self._reflow(plan, results, original_request)` **缺少两项必需输入**，且**都无法从实参推出**——①**判不出哪些步骤声明了"结果交给模型总结"**：该声明在**工具定义级**（注册期固定），而计划与执行结果里**都不带工具定义**（步骤结构上只有工具名等字段，**没有**该声明）⇒ 裁决**在构造回流组件时冻结一份工具目录**（来源与执行器内部构造注册表**同一个**，因此是执行面的超集），回流层**只从它读那一个声明字段**，**不读**风险等级/参数/描述（准入与风控已由注册期与执行器负责，再判一次就是**第二份准入真源**）；目录里查不到的工具名按"不回流"处理而**不报错**（该分支不可达；回流是呈现层，"少一个声明"不该让一个**已经成功执行**的回合失败）。**不给执行步骤加字段**——那会变成第三处接口签名变更，并把注册期事实复制进每一条步骤。②**产不出"无需回流/回流失败"时要显示的那段文本**：两态都要求它与原有的确定性显示**逐字节相同**，而该文本只有调用点手里有 ⇒ 调用时**增传一个参数**（本回合的确定性显示）。由此回流层**永不自己合成回落文本**，两态**共用同一份字节**、只由状态映射区分——"回流失败的用户可见后果与没有回流层时逐字节相同"因此是**构造性事实**而非实现自觉。**两项输入按生命周期分流**：配置期数据（目录、开关、预算）走构造，本回合数据（确定性显示）走调用，**不得互换**；关闭态的**唯一**实现点在主流程那个薄包装里（两种关闭来源行为等价，两个调用点仍写成**零分支一行**）。**顺带核实出的一处契约措辞错误（实现同样会撞上）**：前版把覆盖集判据写成"执行成功且声明回流"，但**执行器在任何失败上都抛错**（未注册/参数被拒/危险/高影响/敏感未确认/策略拒绝/工具返回错误，共七条路径），结果集合里**只会有成功步骤**，执行记录里的"成功"是**硬编码** ⇒ **"成功"是构造性事实、不是运行时判据**，实现者若去找"成功标志"会发现结果里**根本没有该字段**；据此订正相应验收臂，并明确**执行抛错 ⇒ 零回流**、**部分成功的中间结果不做"事后回流"**（那是新的产品语义，本阶段明确不做）。**另修一处前版漏掉的调用点**：同一个回合里执行记录构造有**三个**调用点（两处在确认路径、一处在直连路径），前版只说了两个 ⇒ 新增验收要求**三处共用同一份状态映射**（只给事件侧传值会让 episode 侧退化成空，同一事实在两处不一致）。验收扩为 **R1–R21**（新增"事件面与 episode 面取值一致""执行抛错零回流"两条）。

---

## 七、配置示例

```toml
[model_backend]
type = "ollama"                       # 可换: turbo_llm / lm_studio / mock

[model_backend.config]
model = "qwen3:4b-q4_K_M"
keep_alive = "30m"

[execution]
intent_max_rounds = 4
# Phase 开关
expert_scheduler_enabled = false      # P7 启用
reflector_enabled = false             # P8 启用

[cloud_advisory]
enabled = false                       # P4 启用
provider = "noop"                     # noop | deepseek | glm | custom_openai（P6c，09 契约；兼容期接受旧键 backend）
privacy_mode = "balanced"             # strict | balanced | convenient
max_turns_per_task = 3
max_context_items = 12                 # 2026-09-14 由 8 上调（05 §8：brief_unknowns 逐条 item 化，最坏 6+3=9）；合法范围 1..100
context_byte_budget = 32768             # 2026-09-17 由 2048 上调、同日二次裁决定为 32768（05 §8：TaskBrief 的唯一字节硬边界）；合法范围 256..65536（65536 = 绝对硬上限）
cooldown_seconds = 300
grant_ttl_seconds = 600

[cloud_advisory.connection]
model = ""                            # 留空 = profile.default_model；custom_openai 必填
request_timeout_seconds = 60
# api_base 仅 provider = "custom_openai" 时允许（HTTPS、无 userinfo/query/fragment、拒本地/私网地址）

[cloud_advisory.policy]
allowed_scope = "仅提供分析建议，不生成执行命令或计划"
# 凭据不进 toml：LOCALMIND_DEEPSEEK_API_KEY / LOCALMIND_GLM_API_KEY / LOCALMIND_CUSTOM_OPENAI_API_KEY

[safety]
backend = "rule_only"                 # P0a: rule_only, P3: qwenpaw
l2_enabled = false                    # P3 启用
passphrase_hash_file = "./data/.passphrase"
lockout_attempts = 5
lockout_minutes = 10

[safety.l1_rules]
forbidden_commands = ["rm -rf /", "dd if=", "mkfs.", ":(){ :|:& };:"]
forbidden_paths = ["/etc/passwd", "/etc/shadow", "C:\\Windows\\System32", "~/.ssh"]
sensitive_patterns = ["\\b(password|passwd|secret|token|api_key)\\s*=\\s*\\S+"]
# 2026-09-24：本键只被 RuleOnlySafetyBackend 读取（L1 硬规则），**不构成**凭据检测的通用配置面——
# 凭据检测的唯一真源是 src/safety/secret_scan.py（05 §2.3c.1），本键为**追加**语义、内建模式恒生效、无法被清空绕过

[memory]
backend = "sqlite"                    # P0-P1: sqlite, 之后可选: everos
db_path = "./data/memory.db"

[observability]
event_jsonl_path = ""                 # P6a：空 = 不落评估事件；非空时 JsonlEventSink 写脱敏事件

[tools]
workspace_root = "./data/workspace"   # P6a：file.write 的工作区根（realpath 约束）
```
