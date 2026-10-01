# LocalMind 项目报告

## 一、项目概述

### 1.1 项目定位

LocalMind 是一个本地优先、云端受控协同、后端可替换的个人办公智能体。

项目重点不是堆叠尽可能多的功能，而是建立一条稳定、可观察、可验证的智能体闭环：

```text
用户输入
  -> 最小上下文组装
  -> 渐进式意图理解
  -> 确定性规则决策
  -> 本地回答 / 受控工具执行 / 云端推理升级
  -> 结果整合
  -> 安全化记忆与运行事件
```

本地模型负责理解用户、提出候选意图、选择能力类别和整合结果；确定性代码负责风险判定、工具与参数校验、授权、隐私、路径边界和资源上限。云端模型用于补充本地模型的推理能力，但不拥有本地工具执行权。

### 1.2 项目特色

| 特点 | 说明 |
|------|------|
| 渐进式理解 | 本地模型可在最多四轮内结合新检索到的记忆修正理解，而不是一次调用后直接执行 |
| 本地云端协同 | 本地模型可建议升级，规则层综合用户指令、收益、风险、预算和可用性决定是否上云 |
| 确定性安全边界 | 模型只能提出候选，不能绕过工具白名单、参数校验、授权和副作用出口 |
| 项目与话题记忆 | 会话、话题和项目状态分层管理，可选关键词与向量混合检索 |
| 能力优先路由 | 模型先判断需要哪类能力，再在该能力允许的工具闭集中选择具体工具 |
| 可替换基础设施 | 本地模型、云端 Provider、记忆、Embedding 和工具 Provider 均通过接口接入 |
| 可观察与可评估 | CLI 状态、结构化事件和场景测试共同说明系统为何追问、执行、拒绝或上云 |

### 1.3 当前完成状态

P0 至 P7c 的主体能力已经完成，包括本地模型、受控云端协同、分层记忆、安全工具执行、CLI、场景评估、能力路由、MCP 接入底座、本地文档读取和工作区搜索。

当前交付形态是可运行的终端智能体。默认记忆随进程结束清除；SQLite 持久化和向量检索已经实现，但作为可选配置提供。

---

## 二、设计原则

### 2.1 核心原则

1. **本地优先**：普通理解、调度、记忆和工具编排在本机完成。
2. **模型与控制分离**：模型给出候选，`ControlPolicy` 决定下一步动作。
3. **副作用唯一出口**：本地工具经 `GuardedToolExecutor`，云端网络经 `SideEffectGateway`。
4. **运行时闭集**：能力、工具、参数结构和风险值必须来自本地注册表。
5. **有限授权**：授权绑定任务、会话、Provider、用途和实际外发内容，不能跨任务复用或静默扩大。
6. **事实可溯源**：完成性陈述必须来自执行记录，模型建议和摘要不能冒充执行事实。
7. **最小上下文**：每次模型调用只加载完成当前判断所需的信息。
8. **失败关闭**：安全、隐私、协议或配置不确定时拒绝执行，或明确降级到本地路径。
9. **组件可替换**：Core 只依赖稳定接口，具体实现由工厂和配置装配。
10. **有界运行**：理解轮次、检索、上下文、工具输出、网络响应和日志均受上限约束。

### 2.2 主权边界

```text
Core-owned
  主循环、渐进式理解、规则决策、能力路由、上下文组装、
  工具计划、安全策略、记忆信任模型、结果整合

Adapter-owned
  Ollama、本地或云端模型 API、SQLite、Embedding、MCP Provider、
  文档解析库和具体工具实现
```

外部组件不能反向定义 Core 的数据模型和控制流。替换 Ollama、云端平台、记忆数据库或工具 Provider 时，主循环和安全边界应保持不变。

---

## 三、整体架构

### 3.1 分层架构

```text
┌──────────────────────────────────────────────────────────────┐
│ 交互与评估层                                                  │
│ CLI · Slash Commands · Scenario Runner · Runtime Event Sinks │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ LocalMind Core                                               │
│ InputNormalizer · ContextAssembler · IntentResolver          │
│ ControlPolicy · TaskPlanner · ResponseBuilder · ResultReflow │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼────────────────┐  ┌──────────▼───────────────┐
│ 记忆与上下文层                 │  │ 安全与授权层             │
│ MemoryBackend · ProjectStore  │  │ SafetyPolicy             │
│ TopicTracker · VectorIndex    │  │ GuardedToolExecutor      │
│ RetentionPolicy               │  │ PrivacyPolicy            │
│                               │  │ AuthorizationManager     │
│                               │  │ CloudBoundary            │
└───────────────┬───────────────┘  └──────────┬───────────────┘
                │                              │
┌───────────────▼──────────────────────────────▼───────────────┐
│ 接口与适配器层                                                │
│ ModelBackend · CloudAdvisoryBackend · ToolBackend            │
│ MemoryBackend · EmbeddingBackend · RuntimeEventSink          │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼────────────────┐  ┌──────────▼───────────────┐
│ 本地基础设施                   │  │ 外部服务                 │
│ Ollama · SQLite · Builtin Tool│  │ OpenAI-compatible API    │
│ Local Files · MCP Subprocess  │  │ Weather Provider · MCP   │
└────────────────────────────────┘  └──────────────────────────┘
```

运行事件是旁路观察面，只记录经过脱敏的阶段、动作、原因和计数，不能反向改变业务决策。

### 3.2 技术基座

| 能力 | 当前基座 | 替换边界 |
|------|----------|----------|
| 本地推理 | Ollama + Qwen3 系列模型 | `ModelBackend` |
| 云端推理 | DeepSeek、GLM 或自定义 OpenAI 兼容接口 | `CloudAdvisoryBackend` |
| 临时记忆 | In-memory backend | `MemoryBackend` |
| 持久记忆 | SQLite | `MemoryBackend` / `ProjectRecordStore` |
| 向量检索 | Ollama Embedding + SQLite vector index | `EmbeddingBackend` / `VectorIndex` |
| 内置工具 | Python 标准库和受控 Provider | `ToolBackend` |
| 外部工具 | MCP stdio Provider | `ToolBackend` / Provider loader |
| 可观测性 | CLI sink、JSONL sink、组合 sink | `RuntimeEventSink` |

---

## 四、关键运行流程

### 4.1 渐进式意图理解

```text
当前输入 + 最小上下文
  -> 本地模型生成 IntentCandidate
  -> 判断理解状态、置信度、缺失信息和风险草案
  -> 信息不足时按需检索相关记忆
  -> 带新增证据进入下一轮理解
  -> 收敛、无进展或达到轮次上限后交给 ControlPolicy
```

理解循环最多四轮，但不是固定跑满四轮。模型首轮已明确时可以立即收敛；连续两轮没有获得新信息时提前停止；存在悬空指代且上下文无法解析时由确定性护栏要求用户补充。

模型输出的是认知候选，不是最终控制命令。即使模型声称已经理解，规则层仍会检查缺失信息、能力可用性和安全状态。

### 4.2 确定性决策

`ControlPolicy` 在模型候选之上产生有限动作：

| 动作 | 含义 |
|------|------|
| `ASK_USER` | 关键信息不足或存在无法解析的引用，需要用户补充 |
| `RETRIEVE_MORE` | 本轮仍有明确检索方向且理解预算未耗尽 |
| `PLAN_LOCAL` | 本地回答或构建受控工具计划 |
| `REQUEST_CLOUD` | 进入云端咨询准备与授权流程 |
| `REFUSE` | 请求触发不可执行的危险边界 |

云端准入与本地就绪是两套独立判断。本地信息不完整不必然禁止云端咨询；模型建议上云也不必然获得许可。

### 4.3 本地工具执行

```text
能力选择
  -> 工具草案
  -> 工具名与参数闭集校验
  -> TaskPlanner 构建 ExecutionPlan
  -> preflight 检查路径、目标状态和动态风险
  -> 必要时请求用户确认
  -> GuardedToolExecutor
  -> ToolBackend
  -> ExecutionRecord
  -> 确定性展示或只读结果回流
```

关键约束：

- 能力与工具关系由工具作者声明，模型不能临时创造工具。
- 参数必须符合注册表中的 JSON Schema 子集，缺参进入追问，非法参数不会执行。
- 文件工具只能访问配置的工作区根目录，并在执行前复检路径状态。
- `file.write` 的新建和覆盖都需要用户确认。
- 只读、无网络、无副作用的工具结果可交给本地模型重新组织；执行失败不会生成“已完成”叙述。
- 所有执行结果形成结构化记录，回复中的完成性事实必须能追溯到该记录。

### 4.4 云端协同

```text
ConsultationProposal 或 /cloud ask
  -> 确定性准入
  -> 构建 TaskBrief 与候选上下文
  -> PrivacyPolicy 分类、脱敏和去重
  -> 展示实际外发内容
  -> 用户授权或低风险策略授权
  -> CloudBoundary 最终复核
  -> SideEffectGateway 唯一网络出口
  -> CloudAdvisoryBackend
  -> 响应复核
  -> 本地模型整合建议
  -> 最终回答；如涉及执行则重新进入本地确认链
```

本地模型可以根据任务复杂度、预期收益和自身不足提出升级建议；用户也可用 `/cloud ask` 明确要求咨询云端。强制上云只绕过本地模型的就绪度和建议条件，不能绕过用户禁云、危险请求、Provider 不可用、隐私复核和授权边界。

云端只接收获准的任务包。秘密内容先由确定性扫描器识别并替换为占位符；敏感内容在所有隐私模式下都需要用户明确确认。云端返回始终是不可信建议，不能直接生成或批准本地执行计划。

### 4.5 项目、话题与记忆

```text
用户输入
  -> TopicTracker 判断同话题、新话题或带引用切换
  -> ProjectStore 解析项目归属
  -> MemoryBackend 按 session / project / topic 过滤
  -> 关键词检索 + 可选向量检索
  -> RetentionPolicy 决定全文、摘要或丢弃
  -> ContextAssembler 放入有界上下文
```

| 层级 | 内容 | 默认生命周期 |
|------|------|--------------|
| 回合记忆 | 用户输入、最终回答、工具结果摘要 | 当前进程 |
| 会话摘要 | 当前目标、约束、决定和未解决事项 | 当前进程 |
| 项目状态 | 项目目标、长期约束、摘要和话题标签 | 当前进程 |

默认配置使用 `InMemoryMemoryBackend`，关闭终端后清除。SQLite 模式可跨进程保留回合、摘要、项目记录和向量索引，但当前仍缺少面向普通用户的会话列表、单会话删除和项目摘要重建界面，因此不作为默认交付模式。

### 4.6 可观测性与评估

Core 通过 `RuntimeEventSink` 发出结构化事件，CLI 可选择简洁状态或 trace 显示，JSONL sink 可供场景评估和问题归因使用。

事件只包含动作、原因、计数、风险级别、授权状态和脱敏诊断，不记录隐藏推理、密钥、完整提示词或完整工具返回值。场景运行器复用真实应用装配，用对照变体验证渐进理解、云端升级、安全边界、工具路由和结果回流。

---

## 五、模块职责

### 5.1 Core

| 模块 | 职责 |
|------|------|
| `App` | 编排单轮请求、确认恢复、云端咨询和会话生命周期 |
| `InputNormalizer` | 统一输入事件和基础校验 |
| `ContextAssembler` | 组装当前输入、项目状态、记忆和能力目录 |
| `IntentResolver` | 渐进式理解、按需检索和云端咨询建议 |
| `ControlPolicy` | 以确定性规则选择下一动作 |
| `TaskPlanner` | 将通过校验的工具草案转换为执行计划 |
| `ResponseBuilder` | 生成用户可见的确定性执行结果 |
| `ResultReflow` | 将合格的只读工具结果交给本地模型总结 |

### 5.2 Memory

| 模块 | 职责 |
|------|------|
| `MemoryBackend` | 回合、摘要、检索和项目记录接口 |
| `InMemoryMemoryBackend` | 默认临时记忆 |
| `SQLiteMemoryBackend` | 可选持久化、范围过滤和向量接线 |
| `ProjectStore` | 项目状态和自动摘要 |
| `TopicTracker` | 当前会话的话题关系 |
| `RetentionPolicy` | 根据相关性选择全文、摘要或丢弃 |
| `VectorIndex` | 向量写入、范围过滤和近邻搜索 |

### 5.3 Safety

| 模块 | 职责 |
|------|------|
| `SafetyPolicy` | 本地风险规则和安全检查 |
| `GuardedToolExecutor` | 工具执行、审计和结果记录的唯一出口 |
| `PrivacyPolicy` | 云端候选内容分类、脱敏、去重和请求包构建 |
| `AuthorizationManager` | grant 签发、预算、冷却、过期和撤销 |
| `CloudBoundary` | 云端请求和响应的最终复核 |
| `SideEffectGateway` | 云端网络访问的唯一出口 |

### 5.4 Tools 与 Adapters

| 接口或组件 | 当前实现 |
|------------|----------|
| `ModelBackend` | Mock、Ollama |
| `CloudAdvisoryBackend` | Noop、DeepSeek、GLM、Custom OpenAI-compatible |
| `MemoryBackend` | InMemory、SQLite |
| `EmbeddingBackend` | None、Ollama Embedding |
| `ToolBackend` | Builtin、Composite、MCP Provider |
| 本地工具 | 文件读写、文件搜索、文档读取、时间、天气及基础系统工具 |
| 文档解析 | 纯文本、PDF、DOCX 等按可用解析器接入 |
| 运行事件 | Noop、CLI、JSONL、Composite sink |

### 5.5 CLI 与 Evaluation

CLI 负责输入、命令、显示和会话结束通知，不承担意图判断或安全裁决。场景运行器负责加载场景、切换配置变体、捕获事件并生成可比较结果；两者都复用同一个 `App` 和工厂装配路径。

---

## 六、组件替换与扩展

### 6.1 替换原则

新增实现应满足对应 Protocol，并在工厂或 Provider loader 中注册；Core 不应通过类型判断识别某个具体后端。

| 替换目标 | 所需工作 | 不应改动 |
|----------|----------|----------|
| Ollama 更换为其他本地推理服务 | 新增 `ModelBackend` 适配器并声明能力 | `IntentResolver`、`ControlPolicy`、主循环 |
| DeepSeek 更换为其他云端平台 | 增加 OpenAI-compatible profile 或专用 adapter | 授权、隐私、`SideEffectGateway` |
| InMemory 更换为其他数据库 | 实现 `MemoryBackend` 和项目记录接口 | 话题逻辑、上下文组装策略 |
| Ollama Embedding 更换为其他向量服务 | 实现 `EmbeddingBackend`，处理模型 ID 与维度版本 | 检索融合和项目边界 |
| 新增内置工具 | 注册 `ToolDef`、能力关系、handler 和风险信息 | 模型提示词格式、执行安全出口 |
| 新增外部工具平台 | 实现受限 `ToolBackend` 或 MCP Provider | 工具闭集、参数校验、审计流程 |
| CLI 更换为 GUI 或 API | 消费 `RuntimeEvent` 并调用公开应用入口 | Core 决策和安全流程 |

### 6.2 扩展约束

- 新组件必须在启动时完成配置和能力校验，未知配置不得静默忽略。
- 新工具必须声明参数、风险、所属能力和审计策略。
- 新网络 Provider 必须经过既有隐私、授权和出站边界。
- 新记忆后端必须保持项目、会话和话题隔离语义。
- 新显示层不得依赖模型隐藏推理，也不得自行推断执行成功。

---

## 七、关键数据结构

| 结构 | 用途 |
|------|------|
| `InputEvent` | 规范化用户输入 |
| `MinimalContext` | 单次模型调用的有界上下文 |
| `IntentCandidate` | 模型产生的理解、风险和工具候选 |
| `ConsultationProposal` | 本地模型提出的云端升级建议 |
| `CloudControlState` | 本轮云端开关、预算和确定性状态 |
| `NextAction` | 规则层决定的下一动作 |
| `ExecutionPlan` | 有序、可审计的工具步骤 |
| `ToolDef` / `ToolCapability` | 工具与能力运行时闭集 |
| `PreflightReport` | 执行前动态风险与目标快照 |
| `CloudRequestPackage` | 已脱敏且获授权的云端任务包 |
| `AuthorizationGrant` | 任务级有限授权 |
| `AdvisoryResult` | 不可信的云端建议 |
| `ExecutionRecord` | 工具执行事实 |
| `RuntimeEvent` | 脱敏运行事件 |

精确字段、异常码和边界条件以 `specs/modules/00-core-interfaces.md`、`00-error-contract.md` 及对应模块契约为准。

---

## 八、工程结构

```text
localmind/
├── README.md             # 安装、配置和使用说明
├── requirements.md       # 产品需求与边界
├── project-report.md     # 架构、成果与现状
├── src/
│   ├── core/             # 主循环、理解、决策和结果整合
│   ├── memory/           # 回合、项目、话题和检索
│   ├── safety/           # 风险、授权、隐私和副作用出口
│   ├── tools/            # 内置工具、能力声明和 Provider
│   ├── models/           # 本地模型后端
│   ├── adapters/         # 云端与第三方适配器
│   └── cli/              # 交互式终端
├── config/               # 示例配置
├── tests/                # 自动化测试
├── scripts/              # 评估和维护脚本
├── scenarios/            # 真实文本场景与对照变体
├── specs/modules/        # 模块契约和实现边界
└── data/                 # 本地运行数据，不进入版本控制
```

---

## 九、阶段成果

| 阶段 | 主要成果 | 状态 |
|:---:|----------|:---:|
| P0 | Mock 核心闭环、基础接口与错误模型 | 完成 |
| P1 | Ollama 本地模型与真实推理接入 | 完成 |
| P2 | SQLite 记忆、摘要和差异化留存 | 完成 |
| P3 | 工具执行安全边界、确认与审计 | 完成 |
| P4 | 隐私分类、有限授权和受控云端协同 | 完成 |
| P5 | 项目/话题记忆、混合检索和 Embedding | 完成 |
| P6 | 交互式 CLI、运行事件、场景评估和多云 Provider | 完成 |
| P7a | 能力路由、参数续接和天气工具 | 完成 |
| P7b | MCP stdio 工具生态接入底座 | 完成 |
| P7c | 本地文档读取、工作区搜索和结果回流 | 完成 |

这些阶段不是彼此独立的功能堆叠，而是逐步加固同一条主循环：先保证理解和决策可运行，再加入真实模型、记忆、安全、云端、评估和工具生态。

---

## 十、当前能力与边界

### 10.1 已具备能力

- 通过 Ollama 使用本地模型进行多轮文本对话。
- 在信息不足时追问，在有检索方向时补充记忆后重新理解。
- 由本地模型建议或用户明确要求启动受控云端推理。
- 在外发前展示最终任务包，并对秘密和敏感内容执行脱敏或授权。
- 在工作区边界内读写文件、搜索文件和读取常见文档。
- 调用天气、时间等已注册信息工具。
- 通过 MCP stdio 接入满足白名单和协议约束的外部只读工具。
- 使用项目、话题、关键词检索和可选向量检索组织上下文。
- 通过 `/status`、`/why` 和 trace 事件观察关键决策。

### 10.2 当前边界

- 默认 CLI 不能直接上传附件，文档工具通过工作区内路径访问文件。
- 尚未内置通用网页搜索；可在后续接入搜索 API 或自建 SearXNG Provider。
- 默认记忆随终端关闭清除；持久记忆缺少面向用户的完整管理界面。
- 当前主要交互形态是 CLI，尚无 GUI、会话侧栏和可视化项目管理。
- MCP 已提供接入底座，但第三方工具能否使用取决于本地配置、白名单和服务实现。
- 多专家模型调度尚未进入当前运行主链。

### 10.3 后续优先方向

1. 增加会话和项目的可视化管理，包括列表、切换、删除和持久化策略。
2. 基于真实使用记录继续调优渐进式理解与自主上云判定。
3. 按需要接入通用搜索 Provider，并保持来源、超时、隐私和引用边界。
4. 扩充经过风险建模的日常工具，同时保持能力声明与执行实现分离。
5. 在不改变 Core 控制权的前提下提供 GUI 或 HTTP API。

---

## 十一、配置与运行原则

- 本机配置由示例 TOML 复制生成，不提交 `config/local.toml`。
- 默认模型后端为 Ollama，默认记忆后端为 InMemory。
- 每次只启用一个云端 Provider，API Key 从 Provider 专属环境变量读取。
- `tools.workspace_root` 是文件工具允许访问的唯一根目录。
- 能力、工具、Provider 和配置键集在启动时校验，未知值直接报错。
- 生产入口为 `python -m src.cli --config config\local.toml`。
- 完整安装和配置步骤见 `README.md`，模块级实现约束见 `specs/modules/`。
