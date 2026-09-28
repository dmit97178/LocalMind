# 06-p5-project-memory — 项目记忆与语义检索模块契约

> 状态：✔️ 完成（2026-09-10 终验通过：基础层四轮审查 + 接线阶段 R4-1/R4-2/R4-3 全部落地，E1-E12 验收场景 12/12 自动化，270 passed；见 specs/reviews/06-p5-project-memory-review.md）
> 阶段：P5（项目记忆：Project–Conversation 两层持久化、话题切换接入主循环、混合语义检索）
> 性质：编码前必读。本契约定义 P5 全部新增/演进组件的行为边界。
> 前序依赖：`00-core-interfaces.md`（MemoryBackend 现有签名）、`00-error-contract.md`、`00-adapter-factory.md`、P2 SQLiteMemoryBackend 现状（本契约为**演进而非重写**）。

---

## 0. 范围与不变量

**目标**：落地 FR6 全量——项目摘要、话题切换检测接入主循环、Project–Conversation 两层持久化、语义检索（关键词 + 向量混合），并把 P3 遗留清单第 1 项（敏感执行结果留存规则）一并钉死。

**演进声明（不做推倒重来）**：
- P2 的 `episodes` / `summaries` 表、`schema_version` 迁移框架、`max_search_episodes` 上限**全部保留**。
- `MemoryBackend` 的 `store_episode` / `get_summary` / `save_summary` / `detect_topic_relation` 四个方法**签名不变**。
- `detect_topic_relation` 的确定性启发式实现（`retrieval.py`）保留为默认实现，P5 只接线不重写。
- `project_store.py` 占位文件由本契约填充为正式组件。

**铁律（沿用并扩展 project-plan §3.1 / NFR4）**：
1. `src/core/**` 绝不 `import sqlite3`、不 import numpy/faiss/任何向量库；向量存储与余弦计算用 stdlib（`struct` + `math`）在本模块内实现。**零新增运行时依赖**。
2. `EmbeddingBackend` 是 Core 接口（注入边界，定义在 `core/interfaces.py`）；`VectorIndex` 是 adapter 内部组件（`src/memory/vector_index.py`），**永不出现在 Core 可见签名中**。
3. 所有敏感防线在**写入路径**强制执行（后端写入方法内部消毒，见 §4.1），不依赖调用方自觉，不在读取路径补救。
4. 不一次性加载完整历史：检索永远受 `max_search_episodes`（扫描上限）、`top_k`、`max_context_bytes`（字节预算）三重上限约束；项目摘要与会话摘要各有长度上限。
5. `ambiguous` 关系**永不**自动把旧话题内容注入当前任务（见 §2.2 路由表）。

**范围包含**：
- `src/core/interfaces.py` — 新增 `EmbeddingBackend` ABC、`ProjectRecordStore` Protocol（签名变更，Claude 所有，见 §5.1）
- `src/core/schemas.py` — 新增 `ProjectState`、`TopicDecision`；`MemoryChunk` 扩展字段（见 §5.2）
- `src/core/topic_tracker.py` — TopicTracker（话题切换状态机，新）
- `src/core/memory_hygiene.py` — 记忆消毒纯函数（新）
- `src/core/retention.py` — 阈值语义更新（见 §3.6，supersede P2 数值）
- `src/core/context_assembler.py` — 话题感知装配 + 字节预算
- `src/memory/project_store.py` — ProjectStore（所有权规则、人工覆盖，替换占位）
- `src/memory/sqlite_backend.py` — v2 迁移（episode_vectors / projects / memory_meta 表）、混合检索、写入消毒、ProjectRecordStore 实现
- `src/memory/vector_index.py` — SQLiteVectorIndex（adapter 内部）
- `src/memory/retrieval.py` — 融合/去重/重排纯函数
- `src/memory/in_memory_backend.py` — 同管线对等实现（写入消毒 + 可选注入 embedding）；接受与 SQLite 相同的 retrieval/embedding 配置（默认值一致），其向量索引为进程内 dict、不持久化
- `src/models/ollama_embedding.py` — OllamaEmbeddingBackend（loopback 强约束，复用 P1 transport 模式）
- `src/main.py` — 接线：TopicTracker / ProjectStore / 字节预算 / 工厂 embedding 分支
- `config/default.toml`、`config/p5_semantic.example.toml` — 配置（见 §7）
- `scripts/run_p5.py` — 演示脚本；`scripts/backfill_embeddings.py` — 向量回填
- `tests/test_topic_tracker.py`、`tests/test_project_store.py`、`tests/test_memory_hygiene.py`、`tests/test_retrieval_fusion.py`、`tests/test_embedding_backend.py`、扩展 `tests/test_sqlite_backend.py` / `tests/test_context_assembler.py` / `tests/test_main.py`、`tests/test_p5_scenarios.py`（端到端）

**范围排除**：GUI/TUI、MCP、专家调度、自进化接入、追溯归属历史 episode 到项目、远程 embedding、向量库（faiss/hnswlib 等）。

---

## 1. Project–Conversation 两层数据模型

### 1.1 数据归属与生命周期

| 数据 | 存储 | 创建者/唯一写入者 | 生命周期 |
|---|---|---|---|
| RawEpisode（原始对话） | `episodes` 表（P2 既有） | App `_record_turn` 每轮写入 | P5 不做自动删除；带 topic / session_id / project_id 三重归属 |
| 会话摘要 | `summaries` 表 scope="conversation"（P2 既有） | TopicTracker 触发、App 执行写入 | 滚动覆盖（同 session_id）；topic 收尾/会话结束时更新 |
| ProjectState（项目摘要） | `projects` 表（新，state_json 整体 JSON） | **仅** ProjectStore | active → paused → done → archived；人工可改；永不自动删除 |
| 向量 | `episode_vectors` 表（新） | SQLiteMemoryBackend 写入时尽力 + 回填脚本 | 绑定 (model_id, dim)；模型变更即整体失效（视为 absent，不删除） |

**不变量**：`projects` 表的唯一写入者是 ProjectStore；App 与其他组件一律通过 ProjectStore 读写项目状态。`episode_vectors` 永不直接暴露给 Core。

### 1.2 ProjectState 字段

```python
@dataclass(frozen=True)
class ProjectState:
    project_id: str                    # 归一化后 ^[a-z0-9][a-z0-9_-]{0,63}$
    title: str                         # ≤80 字符
    goal: str                          # ≤500 字符；项目目标
    constraints: tuple[str, ...]       # ≤10 条，每条 ≤200 字符；硬约束
    status: str                        # "active" | "paused" | "done" | "archived"
    summary: str                       # ≤2000 字符（summary_max_chars）；自动更新
    topic_tags: tuple[str, ...]        # ≤32 个；自动累积 + 人工清理
    manual_overrides: frozenset[str]   # ⊆ {"title","goal","constraints","status","summary","topic_tags"}
    created_at: str
    updated_at: str
```

字段超限、`project_id` 不匹配格式、`status` 非法值、`manual_overrides` 越界 → ProjectStore 抛 `MEMORY_ERROR`（recoverable=True）。

### 1.3 所有权与人工覆盖边界

| 字段 | 自动更新 | 人工更新 | 覆盖语义 |
|---|---|---|---|
| title / goal / constraints / status | **永不**（自动路径完全不碰） | ✅ | 进入 manual_overrides 后自动更新跳过 |
| summary | ✅（每轮 task 结束后刷新） | ✅ | 进入 manual_overrides 后自动更新跳过 |
| topic_tags | ✅（只增不减，自动） | ✅（可清理） | 进入 manual_overrides 后自动更新跳过 |

- **人工覆盖入口**：ProjectStore 提供 `set_manual(project_id, field, value)` / `clear_manual(project_id, field)`；CLI 指令格式（如何从对话触发）属工程契约细节，由 Codex 在实现时定义。
- **自动更新来源**：summary 由本地模型生成本轮任务后的项目级更新提案——生成物是不可信文本，写入前过写入消毒（§4.1）+ 长度截断；topic_tags 从 episode.topic 确定性累积。
- **人工优先铁律**：`manual_overrides` 集合非空成员的字段，任何自动更新路径直接跳过，不存在"人工值与自动值合并"。
- **`summary` 的事实身份与来源（2026-09-24 新增，`05` §2.5 规则 9）**：`summary` 是**推断**，不是事实。事实权威只有用户逐字陈述（本轮输入与 episode 逐字文本）。外发到云端时，`summary` **不得**以「已知事实」身份出现——它必须走 `brief_project_note` label，并按来源加**确定性固定前缀**：`"summary" not in manual_overrides`（自动生成）→ 前缀标明「本地模型推断、未经用户确认」；`"summary" in manual_overrides`（`set_manual` 写入）→ 前缀标明「用户手写」。来源判定**只读 `manual_overrides`**（本地持久化状态，模型不可写）⇒ 确定性；前缀是本地固定字面量、不由模型生成、且幂等。`brief_facts` 因此**不再承载 `summary`**（该 section 收窄为「用户逐字陈述」，见 `05` §2.5 规则 9）。
- **摘要生成提示词收窄（2026-09-24）**：项目摘要（本节）与会话摘要（§2.3）的生成提示词必须包含「只允许复述用户已陈述的内容与本轮实际发生的动作；不得推断结论、不得把未验证的推测写成事实；不确定的内容写成未解决事项」的固定文本。提示词加固**不改变**「生成物是不可信文本」的既有前提，也不替代 §4.1 的写入消毒。

### 1.4 project_id 解析（App 每轮，确定性，不经模型）

按顺序：
1. **显式**：`InputEvent.project_id` 非空 → 归一化（小写、空白转 `-`、去非法字符）后使用。
2. **提及匹配**：显式为空时，ProjectStore.resolve(input) 用输入分词与已知项目的 title/topic_tags 分词求交集；**唯一命中**才归属，多命中或零命中 → None（防误绑）。
3. 均无 → project_id=None，episode 归入"未归属"池（topic/session 仍在），**v1 不做追溯归属**。

### 1.5 新项目 / 未知项目 / 项目切换 / 跨项目检索

- **新项目**：解析出 project_id 但 `projects` 表无记录 → `ProjectStore.ensure(project_id)` 创建骨架（status="active"，summary=""，title=project_id 原值），受配置 `projects.auto_create` 控制（false 时返回 None，episode 仍以该 project_id 存储但无项目摘要加载）。
- **未知项目**：用户提到未解析出任何已知项目的名称 → 不创建、不阻塞，正常走 None 路径。
- **项目切换**：本轮解析出的 project_id ≠ 上轮（含 None→X、X→None）→ 判定切换。切换时：加载新项目摘要；旧项目上下文**不注入**本轮；TopicTracker 当前 topic 重置为新输入派生。切换是确定性事件，不经模型确认。
- **跨项目检索**：普通检索（无 topic_hints）范围 = **当前项目 ∪ 未归属池**（project_id IS NULL），不做全库扫描——这是项目边界的默认隔离；定向检索（topic_hints 非空，仅 shift_with_reference 触发）范围 = 全库但必须命中 hints。用户引用其他项目走 §1.4 项目解析（mention 命中旧项目 → 项目切换 + 加载其摘要），不经检索越界。`same_project_boost` 用于当前项目与未归属池之间、以及定向检索中的同项目优先（§3.5）。

---

## 2. 话题切换接入主循环

### 2.1 TopicTracker（src/core/topic_tracker.py）

**按 session 隔离**的内存状态机（不持久化）：内部为 `dict[session_id, _SessionTopicState]`，每个 session 独立持有 `current_topic` 与 `current_project_id`——两个会话交替输入互不串话题、互不串引用。会话结束（EOF）时 App 调用 `end_session(session_id)` 清除该 session 状态。

公开契约：

```python
class TopicTracker:
    def current_topic(self, session_id: str) -> str: ...
    """未知 session 返回 ""（首轮）。"""

    def current_project_id(self, session_id: str) -> str | None: ...
    """未知 session 返回 None。"""

    def on_turn(
        self, session_id: str, input_text: str, *,
        relation: str, project_id: str | None,
    ) -> TopicDecision: ...
    """
    relation 由 App 先经 memory.detect_topic_relation(input_text, tracker.current_topic(session_id))
    求得后传入；project_id 为 ProjectStore.resolve 的归一化结果。
    project_switched 由 tracker 内部判定：project_id != current_project_id(session_id)（含 None↔X）。
    """

    def end_session(self, session_id: str) -> None: ...
```

```python
@dataclass(frozen=True)
class TopicDecision:
    session_id: str
    relation: str                  # same_topic | new_topic | shift_with_reference | ambiguous
    topic_label: str               # 本轮生效的 topic 标签
    referenced_topic: str | None   # 仅 shift_with_reference 非空，= 切换前 topic
    project_id: str | None         # 本轮生效项目（归一化后），episode metadata 以此回写
    project_switched: bool         # 本轮是否发生项目切换
```

- **首轮规则**：`current_topic(session_id) == ""`（会话首轮）时，relation 视为 `new_topic`（App 无需调用 detect_topic_relation，或调用结果被覆盖）——既有启发式对空 topic 返回 ambiguous，若照搬将得到空 topic 使 store_episode 的必填 topic 校验失败。首轮 topic 标签 = 首输入派生。
- **topic 标签派生**（确定性）：`same_topic` / `ambiguous` 延续当前标签；`new_topic` / `shift_with_reference` 的新标签 = 当前输入分词后前 3 个词干以 `-` 连接（可复现、可测试）。v1 **不用模型生成 topic 标签**。

### 2.2 四类关系路由表（钉死，逐格可测试）

| 关系 | 项目摘要加载 | 会话摘要 | chunk 检索 | 本轮 topic | 写入 |
|---|---|---|---|---|---|
| **same_topic** | project_switched 时换载新项目摘要，否则复用 | 正常加载 | 常规 top_k | 不变 | episode.topic = 当前 topic |
| **new_topic** | 仅 project_switched 时换载新项目摘要 | 旧 topic 收尾更新一次 | 常规 top_k（不带旧 topic 过滤） | 新派生 topic | 先更新会话摘要（旧 topic 收尾），episode.topic = 新 topic |
| **shift_with_reference** | 复用 | 旧 topic 收尾更新一次（同 new_topic 行） | **定向检索**：query = 整句输入，`topic_hints=(当前 topic,)`，允许跨项目 | 新派生 topic | episode.topic = 新 topic，metadata.referenced_topic = 旧 topic |
| **ambiguous** | project_switched 时换载新项目摘要，否则复用 | 复用（不重读） | 常规 top_k；**禁止**按旧 topic 定向检索、禁止旧 topic 命中加权置顶 | **不变**（不强行切换） | episode.topic = 当前 topic |

**不变量**：
1. `ambiguous` 时 TopicDecision.referenced_topic 必须为 None；ContextAssembler 不得因 ambiguous 传入 topic_hints。
2. `shift_with_reference` 的引用锚点**只有当前 topic**（最近一个开启的话题）——不猜测"用户指的是哪个更早的话题"；引用更早话题由用户显式给出项目或关键词承担。
3. 项目切换（project_switched）独立于话题关系生效：即使 relation=same_topic，project_id 变化仍换载项目摘要。
4. 加权排序中的 `same_project_boost`（§3.5）是**项目维度**加分，不违反不变量 1（话题 ≠ 项目）。
5. 会话首轮（current_topic 为空）一律按 **new_topic 行**执行（§2.1 首轮规则），不落 ambiguous 行——保证 store_episode 的必填 topic 永非空。
6. 所有状态按 session_id 隔离（§2.1）；跨 session 不存在共享的 topic/project 状态。

### 2.3 会话摘要更新时机

- **语义定为「整个会话的滚动摘要」**：summaries 表主键是 (scope, scope_id)，scope_id=session_id 每会话只有一行；按话题分片存储会与该主键冲突（第二个话题覆盖第一个，且加载时无法判定摘要归属哪个话题）。话题收尾只是**更新触发点**——把刚收尾话题的要点并入滚动摘要后整行覆盖。
- 更新时机仅两处：topic 收尾（new_topic / shift_with_reference 触发，并入旧 topic 要点）+ 会话结束（EOF，最终覆盖）。
- 生成：本地模型生成（输入 = 当前滚动摘要 + 旧 topic 内 episode），长度上限 300 字符（不可信文本 → 写入消毒兜底）；模型失败或超时 3 秒 → **确定性降级**（滚动摘要保留，追加该 topic 的 topic 标签 + 轮次计数一行），**不阻塞主循环**。
- 写入：`save_summary(scope="conversation", scope_id=session_id, summary=...)`，结构 `{"summary": str, "last_updated": str}`；读取策略 = ContextAssembler 仅加载**当前 session_id** 的滚动摘要，跨会话细节一律走 chunk 检索（FR6），不加载历史会话摘要行。
- **摘要行的事实身份（2026-09-24 新增，`05` §2.5 规则 9）**：会话摘要与项目摘要同属**模型推断**，注入上下文时必须带「本地模型推断、未经用户确认」同族固定前缀（与逐字检索片段的前缀不同，见 §2.4），且与 `relevant_history` 中的逐字 episode 片段**可区分**。生成提示词按 §1.3 的固定文本收窄——收窄不改变「生成物是不可信文本」前提，也不替代 §4.1 写入消毒。

### 2.4 主循环接线顺序（App.handle 每轮）

```
normalize（InputEvent.project_id 保留用户原值，仅作 resolve 输入）
→ relation = memory.detect_topic_relation(text, tracker.current_topic(session_id))   # 首轮跳过
→ decision = tracker.on_turn(session_id, text, relation=relation,
                             project_id=projects.resolve(text, input_event.project_id))
→ decision.project_id 非空时 projects.ensure(decision.project_id)
→ ContextAssembler.assemble(input_event, topic=decision,
                            project_state=projects.load(decision.project_id))
→ …（意图解析 / 调度 / 执行，不变）
→ _record_turn(raw_text, decision, candidate, narrative_reply, execution_records)
      （store_episode 的 metadata.project_id = decision.project_id——归一化解析后的值，
        不回写 InputEvent.project_id 原值；写入消毒在后端内强制，§4.1）
→ 会话 EOF 时：tracker.end_session(session_id) + 会话摘要最终覆盖
```

- **project_id 回写规则**：episode 的 project_id 与 projects 表主键处于同一命名空间（归一化后）。`InputEvent.project_id` 原值可能是未归一化字符串，只允许作为 resolve 的显式输入，不得直接落 episode metadata 或与 ProjectState.project_id 比较。
- **ExecutionRecord 来源**：execution_records 由 App 从工具执行链收集（GuardedToolExecutor 的执行/拒绝结果，§4.2 字段），`_record_turn` 的签名随之扩展为接收结构化执行结果列表，见 §4.2。

ContextAssembler 职责变化（00 契约定稿签名）：`assemble(input_event, topic, project_state)`——**App 负责加载** ProjectState 并传入（App 持有 ProjectStore），ContextAssembler 不 import ProjectStore 或任何 memory adapter；向 retrieve 透传 `project_id=decision.project_id` 与 `topic_hints`（§5.1）；将 `project_id` 写入 MinimalContext（IntentResolver 多轮检索的唯一来源，§5.2）；组装完成后按构造器注入的 `max_context_bytes` 对 MinimalContext 相关历史做总字节预算裁剪（从最长条目起丢弃，保证不超限）。

**历史片段的事实身份（2026-09-24 新增，`05` §2.5 规则 9）**：进入 `relevant_history` 的两类行必须**自述来源且彼此可区分**——模型生成的滚动摘要行（§2.3）用「本地模型推断、未经用户确认」同族前缀；检索到的 episode 片段是**逐字局部转录**（经 §4.1 消毒后），用「本地历史片段（逐字）」前缀（具体文案由 Codex 定，但两类前缀必须不同且都非空）。云端因此能区分「用户说过什么」与「本地模型总结/推断过什么」。前缀判据**只看行来源标记**，**不得**引入任何值形态/CJK 判据（该判据已在 `05` §2.3c.3 被删除，理由是它会使中文口令漏检）。

**云端咨询结果写回（2026-09-24 新增；**同日第二轮补钉**，`05` §10.12 W1/W1b/W2/W2b）**：云端咨询的**最终回复**（含 followup 子回合的结果与 `_CLOUD_FALLBACK_REPLY` 兜底）与普通回合走**同一条** `_record_turn` + `_record_tool_events` 链——episode / `recorder.record` / `_topic_records` / `_topic_turn_counts` / `_update_project_memory` 一律照常。五条口径：
1. **每任务恰好一条 episode，且只在终结时写**（第二轮钉死，**同日第三轮把终结形态枚举补全为七种**）：产出授权 preview 的回合**不写**（判据是本回合有 `phase="authorization_required"` 事件，**不用回复文本匹配**）——其四条副作用链一律不推进，因此**临时授权提示永不进入语义记忆、会话滚动摘要或项目摘要**。终结形态全枚举：**成功收敛**（`/cloud allow` 续接回合拿到最终答案）、**fallback 收敛**（云端失败但本地兜底出答复）、**取消**、**授权失效**、**跨会话不匹配**、**被新输入取代**、**云端挂起追问**（云端本轮回复是追问、不是答案）。前两种**各补写唯一一条**，后五种**零条**（第三轮新增第五种：`_suspend_for_followup` 的挂起回合不调用 `_record_turn`，其四条副作用链同样不推进——**理由与首轮抑制一致**：追问文本不是答案、更不是用户说过的内容，写进去会让检索把它当成一条结论）。
2. **User 段 = 原回合用户输入**（不是 `/cloud allow` 这条控制指令），取自 `LocalTaskContext.input_event.text`，使 episode 自洽可检索；`/cloud allow` 作为控制指令不入正文。
3. **Assistant 段带云端来源标记**（固定前缀，本地确定性生成、不由模型产出）：该回复源自本地信任边界之外的模型，本地重解侧已按「不可信引用」处理（`05` §6.2 / §6.4），落盘必须保留同一身份，避免后续检索把云端结论当作用户或本地已证实的陈述。
4. **零新增意图解析调用 + 快照载体唯一说法（第二轮钉死；**第三轮统一载体并补读取时机**）**：`_record_turn` 需要的 `topic_label` / `intent_type` 取进入授权等待时**冻结**的快照；续接回合**不得**为补 `decision` 重跑意图解析——该回合的语义冻结于原回合。载体**只有一种说法**：**由 `LocalTaskContext` 承载**（它是本任务的本地语义容器，其内容不进入 pending/grant/审计；原输入、`project_id`、`session_id` 已在其中）——`PendingCloudAuthorization` **不承载**该快照，**不得**在 pending 结构上加 topic/intent 字段。**实现注意（第三轮从既有代码推出，必须遵守）**：快照必须在**进入 `_consult_cloud` 之前**读取，因为 `_consult_cloud` 会在**成功路径**（`main.py:1239`）与**云端失败路径**（`main.py:1216`）都把 `_local_task_context` 置空；`main.py:1170` 的 `_local_task_context is None` 检查点就是天然的**同点读取位置**。**零签名变更。**
5. **补写调用点必须在 `/cloud allow` 路径上**：该回合在 `main.py:304–306` 提前短路，**不会**自然走到 `main.py:426–433`；**不得**把补写放进 `_consult_cloud` / `_complete_cloud_consultation`（二者与**同回合直连路径**共享出口，放进去会让直连路径出现两条 episode——直连路径本就经 `main.py:426–433` 写入）。
- **两个异常分支（第二轮钉死）**：① `_local_task_context is None`（**状态损坏**，现行状态机下不可达，须用定向测试强制构造）→ 撤销该任务 grant、清空 pending、返回 `_CLOUD_FALLBACK_REPLY`、**不写 episode**、**不新增任何枚举值**；② 正常云端失败但 LocalTaskContext 尚在 → 照常按第 1 条写回（不属异常分支）。
- **挂起回合零 episode 在两条路径上都成立（2026-09-25 修正；原「已登记的不对称」作废）**：第三轮曾登记「同一种挂起形态在**直连路径**上仍会把追问文本写成 Assistant 段」——**该登记不成立，已删除**。追问路径两条路径**共用**（`main.py:1377-1389` 创建 pending 后才写 `phase="authorization_required"`，用的是本回合 `task_id`），而 `main.py:432-435` 的挂起判据（`_pending_cloud is not None and _pending_cloud.task_id == task_id`）对本回合同样成立 ⇒ 直连路径的挂起回合**同样零 episode**。原登记混淆了两件事：`_suspend_for_followup` 里 `create_policy_grant` **成功**的那条分支（`main.py:1376`）确实照常经 `main.py:432` 写入，但它**不是挂起**——它同回合直接咨询、返回的是**云端答案**，写一条 episode 且 Assistant 段是答案，**这正是应有行为**。**现口径**：凡产出授权挂起（`phase="authorization_required"`）的回合零 episode；凡终结回合恰一条 episode（第三轮实现审查，见 `reviews/05-p4-cloud-advisory-review.md` 2026-09-25 节）。
- **代价照实记录（两处）**：① 写回会为该回合触发一次**本地**项目摘要更新调用（`_update_project_memory` → 本地模型 `generate`），与普通回合同价；不新增任何云端调用。② 取消 / 失效 / 不匹配 / 被取代四条路径上，**用户的原始请求文本不进入记忆**（拒绝事实只在事件与审计里）；替代方案是「终结回合写『原输入 + 该回合用户可见的终结回复』」，本轮**不预先实现**，若真实 run 出现「回头追问被取消的任务」的连续性缺口 → 按 `05` §10 立候选，**不得**退回「把临时授权提示写成 Assistant 段」那一版。

**retrieve 直调点全量清单（新增调用必须过范围裁剪，不许默认 None 绕过）**：
1. `context_assembler.py` 主检索——透传 `decision.project_id` + hints（§2.4）。
2. `intent_resolver.py::_retrieve_for_candidate` 多轮认知检索——透传 `context.project_id`（MinimalContext 新字段）。
3. `main.py::_followup_candidates`（P4 云端 memory_evidence）——透传 `local.project_id`（LocalTaskContext 新字段，云端任务创建时从 TopicDecision 记入）。

---

## 3. 语义检索

### 3.1 EmbeddingBackend（新 Core ABC，签名归 00-core-interfaces §同步清单）

```python
class EmbeddingBackend(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> Result[list[list[float]]]:
        """批量嵌入文档文本。失败返回 Result.err(EMBEDDING_ERROR)，不抛异常。"""

    @abstractmethod
    def embed_query(self, text: str) -> Result[list[float]]:
        """嵌入查询文本（非对称模型时与文档嵌入分开）。失败返回 Result.err(EMBEDDING_ERROR)。"""

    @abstractmethod
    def dimensions(self) -> int:
        """向量维度；0 = 未知（探测失败），检索端视为不可用。"""

    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def health_check(self) -> bool: ...
```

### 3.2 OllamaEmbeddingBackend（默认本地实现，src/models/ollama_embedding.py）

- 走 Ollama `/api/embed`，复用 P1 `_UrllibOllamaTransport` 的零依赖模式与 `_loopback_url` 校验。
- **远程 embedding 默认拒绝**：构造期校验 base_url 必须为 loopback（localhost/127.0.0.1/[::1]），否则 `CONFIG_ERROR`（recoverable=False）。**无任何绕过开关**——未来若要支持远程 embedding，属安全边界变更，须新契约条款并经 Claude 审查。
- `dimensions()`：配置 `dim > 0` 时用配置值；否则构造期探测（嵌入一条探测文本）。探测失败 → dimensions()=0、构造**成功**（不让 bootstrap 失败），检索端视为不可用走降级。
- 输入边界：只有已经写入消毒的文本会进入 embed（顺序钉死：消毒 → 存储 → 嵌入，见 §4.1）；输出边界：向量只写本地 SQLite，不进审计、不进日志、不外发。

### 3.3 VectorIndex（adapter 内部，src/memory/vector_index.py）

- 协议：`upsert(episode_id, model_id, dim, vector)` / `search(query_vector, model_id, dim, top_n, *, allowed_ids: set[str] | None = None) -> list[tuple[episode_id, score]]` / `count()`。**allowed_ids 语义：`None` = 不限制；空集合 = 无候选，直接返回空列表**（实现判断必须为 `allowed_ids is not None`，禁止用真值判断——否则 hints 零命中时会把空集当"不过滤"，退化为检索全库向量、注入无关内容）。allowed_ids 非空时**在取 top-N 之前过滤**（SQLiteVectorIndex 用 SQL `WHERE episode_id IN (…)` / JOIN episodes 完成下推），不允许"取全局 top-N 后再过滤"——那样正确话题的向量可能已被挤掉。topic_hints → allowed_ids 的换算由检索管线在调用前完成（先按 hints 查出候选 episode_id 集）。
- 默认实现 **SQLiteVectorIndex**：向量以 float32 数组 `struct.pack` 存 BLOB；余弦相似度纯 Python 暴力扫描。规模上限 = `max_search_episodes`（默认 500）× 384 维 ≈ 2×10⁵ 次乘加，远低于性能三档预算。
- **索引版本与失效**：`memory_meta` 表记录 `embedding_model_id` / `embedding_dim`。启动时与配置不一致 → 该批向量整体视为 absent（不删除、不阻塞），检索自动退化为关键词；重建经 `scripts/backfill_embeddings.py` 显式执行。
- Core 永远看不到 VectorIndex 类型（铁律 2）。

### 3.4 SQLite 迁移 v2（`_LATEST_VERSION = 2`）

沿用 P2 `_run_migrations` 框架，v2 事务内执行：

```sql
CREATE TABLE IF NOT EXISTS episode_vectors (
    episode_id TEXT PRIMARY KEY REFERENCES episodes(id) ON DELETE CASCADE,
    model_id   TEXT NOT NULL,
    dim        INTEGER NOT NULL,
    vector     BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

- **只加表，不动旧表旧数据**；v1 库打开即自动升级，升级前旧数据可完整读取。
- `summaries` 中历史 `scope="project"` 行（P2 期间无写入者，理论为空）：迁移时若有，提取已知字段导入 `projects` 表后**删除旧行**（防双真源；无法解析的行保留原样并忽略）。

### 3.5 混合检索管线（retrieval.py 纯函数，两个后端共享）

0. **范围裁剪**（在两侧召回之前）：普通检索（无 topic_hints）→ 候选范围 = `project_id` 参数非空时"当前项目 ∪ 未归属池"（SQL `WHERE project_id = ? OR project_id IS NULL`），`project_id` 为 None 时**仅未归属池**（隔离对称：未归属会话不看到任何项目内容）；定向检索（topic_hints 非空）→ 范围 = 全库但必须命中 hints。`project_id` 由 ContextAssembler 从 TopicDecision.project_id 透传（§5.1）。
1. **关键词候选**：既有 `keyword_score` 在步骤 0 裁剪后的范围内扫描（≤ max_search_episodes）；指定 hints 时仅保留 topic 命中的候选（hint 匹配按分词交集，过滤下推到 SQL WHERE，不允许取回后再过滤）；hints 零命中 → 关键词侧为空。
2. **向量候选**：embedding 健康时 `embed_query(query)` → 先按 hints 换算 allowed_ids（步骤 0/1 同源查询），再 `vector_index.search(..., allowed_ids=…)`，top_n = 3 × top_k；**hints 零命中 → allowed_ids 为空集合 → 向量侧直接为空**（§3.3 语义，不回退全库）；任一步失败（Result.err / dimensions()==0 / index 空）→ 该侧为空，**不抛错**。
3. **归一**：`kw_norm = min(kw_hits / 3, 1.0)`（与 retention 语义对齐）；`vec_norm = max(cosine, 0.0)`。
4. **融合去重**：按 episode_id 合并两侧，`match_source ∈ {"keyword","vector","both"}`；`final = w_kw·kw_norm + w_vec·vec_norm`（默认 **w_kw=0.6、w_vec=0.4**，与 §6.1 配置注释一致）。
5. **降级模式**：向量侧整体不可用时 `final = kw_norm`（关键词单独归一到同一 [0,1] 标尺，retention 阈值在两种模式下语义一致）。
6. **项目加分**：`chunk.project_id == 当前 project_id 且非 None` 时 `final += same_project_boost`（默认 0.1，cap 1.0）——用于当前项目与未归属池之间的优先级，以及定向检索中的同项目优先；不用于绕过步骤 0 的范围裁剪。
7. **重排**：final 降序 → timestamp 降序 → id 升序（确定性全序）。
8. **截断**：先 top_k；再按 `max_context_bytes` 累加 chunk.text UTF-8 字节数，第一条超界的 chunk 被丢弃并**停止**（不做贪心回填）。

### 3.6 similarity_score 语义变更（supersede P2，有意的行为变更）

- `MemoryChunk.similarity_score` 从"关键词命中数（0..n）"改为**融合分（0..1）**；新增字段 `vector_score: float | None = None`、`match_source: str = "keyword"`（见 §5.2）。
- `retention.classify_retention` 阈值更新：`KEEP_FULL ≥ 0.60`、`KEEP_SUMMARY ≥ 0.35`（supersede P2 的 3.0 / 2.0）。两种模式（混合/降级）下阈值语义一致。
- **实现注意**：既有依赖旧语义的测试断言（分数区间、retention 分级）需按新语义重写，这是本契约的有意变更，不是回归。

### 3.7 上下文数量与字节上限汇总

| 位置 | 上限 | 配置 |
|---|---|---|
| 检索扫描 | max_search_episodes 条 | 既有 |
| 检索出口 | top_k 条 + max_context_bytes 字节 | top_k 既有（App 传 3）；bytes 新增，默认 4096 |
| 项目摘要 | 2000 字符 | projects.summary_max_chars |
| 会话摘要 | 300 字符 | 固定（契约值） |
| MinimalContext | 组装后总字节预算 ≤ max_context_bytes | 复用检索配置 |

---

## 4. 安全与隐私

### 4.1 写入路径消毒（唯一真源 = MemoryBackend 写入方法内部）

**规则**：`store_episode` / `save_summary` / `put_project_record`（ProjectRecordStore）在写入前对全部文本内容强制执行 `memory_hygiene.sanitize_for_memory()`。Core 组件（App / TopicTracker / ProjectStore）**不重复消毒**（幂等无害，但依赖单点强制）。第三方 MemoryBackend 实现（未来 EverOS）在接口契约中写明同等义务。

**消毒规则**（`src/core/memory_hygiene.py` 纯函数，**检测模式集与判据的唯一真源 = `src/safety/secret_scan.py`（`05` §2.3c.1）；本模块不再自定义任何正则**，`contains_bare_secret` / `contains_sensitive_value` 退化为该真源的薄包装）：
1. **凭据类命中**（`redact_local`）→ 替换为**统一字面量 `[已脱敏:secret]`**。2026-09-24 起「秘密模式」与「一般敏感值（api_key= / password= 等）」合并为**同一条规则、同一占位符**——此前分别产出 `[已脱敏:secret]` 与 `[已脱敏:sensitive]`，现由 `05` §2.3c.5 统一。**命中条件与作用域以 `05` §2.3c.3 规则 1–3 为唯一真源**（2026-09-24 **第三轮重写**）：命中的触发是**标签闭集成员 + 边界成分**（T1 显式分隔符 / T2 空白 / T3 紧邻非 CJK 非空白字符），**与值无关**；**值区 = 标签之后到本行末尾的连续跨度**（首尾空白 strip、去掉边界成分），标签独占一行时**顺延一次**取下一个非空行；值区为空或 == `[已脱敏:secret]` → **不可命中**，非空 → **可替换**。处置是**整个值区原地替换为一个 `[已脱敏:secret]`**（同一个字面量、同一处实现，**出站与本地逐字一致**）。
2. **本地不存在「拒绝」处置，也不存在任何值形态判据**（2026-09-24 第三轮）：值区非空的命中**一律原地替换**，不再有「不可界定 → 不可界定的最大区间」这类分支——值区上界确定（行末，必要时顺延一行），归属永不是未知。**不得**因值区的形态（是否含 CJK、是否含空白、是否像值）而跳过或缩减替换：该判据已在 `05` §2.3c.3 规则 4 被显式删除，理由是它会使 `密码 青山绿水` 一类中文口令原样落盘。`05` §2.3c.4 第 2 条的**整段拒绝是出站侧行为**（该段脱敏后已无任务语义 ⇒ 拒绝外发比发送更诚实），**本地不适用**——本地无外发泄漏面，销毁用户整条记忆的成本高于收益，故照常落盘替换后的文本。
3. 受保护路径（safety l1_rules.forbidden_paths 配置 + 内置模式如 `~/.ssh`、`/etc/shadow`、`C:\Windows\System32`）→ 替换为 `[已脱敏:path]`。**不是凭据类**，不受第 1 条合并影响。
4. 扫描顺序：先凭据类，后受保护路径。
5. **fail-closed 自检**：消毒后文本若仍命中任一禁入模式 → 该片段整段替换为 `[已脱敏:block]`。`[已脱敏:block]` 自 2026-09-24 起**降级为最后兜底**，预期在生产路径不再触发；测试须断言普通中文语句（含数字陈述、含 `是`/`为` 等分隔词的普通句）**不产生** `[已脱敏:block]`。消毒函数必须幂等（占位符落回「不可命中」态、不再触发任何模式）。

> **有意行为变更（2026-09-24，安全边界）**：凭据占位符由两个字面量合并为一个，且检测面扩到中文自然语言形态（`我的账号密码是123456` 一类）。既有测试若断言 `[已脱敏:sensitive]` 或断言该形态零命中，按新行为重写（与 §3.6 同属有意变更清单）。
>
> **第三轮补充（同日，值区上界确定化 ⇒ 删除全部尾部判据）**：第二轮仍留了两处**值形态判据的尾巴**，它们各自漏掉一个真实口令：`密码 abc123`（裸空格不当作边界 ⇒ **完全不命中**）与 `密码是abc，青山绿水`（终止符之后的 CJK 片段不回收 ⇒ 尾部原样落盘）。修法不是再补一条形态规则，而是**把值区的上界改成确定量**：命中只看「标签 + 边界成分（T1/T2/T3，全部与值无关）」，值区就是**标签之后到本行末**（标签独占一行时顺延一个非空行），**区内不再切分、不再筛形态**。值区上界确定后「归属不明的后续片段」不再存在，「不可界定」态随之**删除**——因此本地只剩**一种处置**（整个值区原地替换为一个 `[已脱敏:secret]`）。**已知代价照实登记**：`token 过期了` / `api_key 读不到` 这类「拉丁标签 + 空白 + 中文技术句」会被整段替换，字符级与 `password 青山绿水`（真中文口令）不可区分 ⇒ 只能按口令处理；代价方向仍是**不对称取舍**（过度脱敏可见、可拒绝、有界；漏检不可见且即泄漏）。**代价的消解方向是提高标签侧选择性，禁止回收值形态判据**。**三条语法边界照实声明（不是形态豁免）**：① 标签与值之间完全没有边界字符的粘写（`密码青山绿水`）——覆盖它会把 `密码学` / `密钥管理` 错认成凭据；② 值在标签之前（`abc123 是我的密码`）；③ 值跨一个以上顺延行。三者由既有的**无标签裸秘密检测层**兜底。
>
> **第二轮补充（同日，安全承诺不得降低；⚠️ 本段的「值区三态 / 片段回收 / 判态顺序」判据已被上一条第三轮补充整体修订作废，实现请以上一条为准——「删除 CJK 豁免」「防误伤靠标签闭集、不靠值形态」「接受过度脱敏为已知代价」三条结论仍然有效）**：**删除**「条款含 CJK ⇒ 非值区形态」的豁免——它使 `密码是青山绿水` 原样落盘；值区三态改判「是否为空 / 是否 == 占位符字面量 / 是否含内部空白」，**防误伤靠标签闭集、不靠值形态**；新增**跨终止符值形态片段回收**（`密码：abc，123` 的 `123` 一并替换）；**判态在回收之后一次性进行**（`密码是[已脱敏:secret]，123` 的 `123` 不得放走）。**已知代价照实登记**：`改密码是必要的`、`token 是无效的` 一类句子会被命中并替换，该回合进强制用户授权（用户可见、可拒绝、有界；反向取舍会让中文口令漏检，不可接受）——测试**不得**断言这类句子零命中。

由此形成链式保证：**消毒 → 存储 → 嵌入**，embedding 输入、向量索引、检索结果、项目/会话摘要天然不含原值。

> 有意行为变更：P2 起 episodes 直存原文（"User: …\nAssistant: …"），P5 起写入时占位替换。既有测试若断言秘密原值出现在存储/检索结果中，按新行为重写（与 §3.6 同属有意变更清单）。

### 4.2 敏感执行结果留存规则（P3 遗留清单第 1 项落地）

- 工具执行结果**原文永不入记忆**（episodes / 摘要 / 索引 / 检索结果均不含）。仅靠 §4.1 正则消毒**不足以**保证这一点——任意文件内容（如整段 .env）未必命中任何模式，因此必须用结构化切分从源头保证，消毒只作兜底。
- 允许写入的唯一形态 **ExecutionRecord**：
  - 固定字段：`tool_name`、`verdict`（allowed/denied）、`risk_level`、`outcome`（success/failure）、`error_code?`；
  - `sanitized_summary`：≤200 字符，生成规则 = **仅结构化信息**（结果键名/字段名、类型、条目计数等，如 `keys=content,status; type=dict`），**不包含任何工具返回值文本**——结果原文即使不含已知敏感模式也不入任何记忆形态（2026-09-10 澄清修订，见决策表）；非文本/二进制结果 → 固定串 `"（非文本结果，已省略）"`；
  - denied 的执行：只记 tool_name + reason code，**不记 params 原文**（沿用 P3 params_redacted 先例）。
- **App 写入链硬约束**：
  1. `_record_turn` 签名扩展为 `_record_turn(raw_text, decision, candidate, narrative_reply, execution_records)`——接收**结构化执行结果列表**，不再从拼好的 reply 文本间接获得工具输出。
  2. episode 内容 = `User: {raw_text}\nAssistant: {narrative_reply}` + 每条 ExecutionRecord 一行结构化文本（如 `[tool] name=… verdict=… outcome=… risk=… summary=…`）。
  3. **ResponseBuilder 必须分离两种输出形态**：`display`（给用户看，可含工具结果原文）与 `narrative_reply`（给记忆，**不得包含工具返回原文**）。实现形态（双返回值 / 占位标记嵌入）由 Codex 定；`narrative_reply` 中工具结果的位置以占位串表示（如 `[执行结果 N 条，已以结构化记录留存]`）。既有测试若断言 episode 含工具原文，按新行为重写。
  4. 用户对话回复（raw_text 与 narrative_reply 的非工具部分）保留入记忆，经 §4.1 写入消毒兜底。
  5. **口令确认路径（P3 分支）的写入规则**：口令确认会从 handle() 的独立分支提前返回并执行被解锁的计划，该路径**必须**走与普通轮相同的 `_record_turn` 写入链，唯一差异是 User 段替换为固定占位串——episode 内容 = `User: [身份确认，原文不留存]\nAssistant: {narrative_reply}` + 本次执行的 ExecutionRecord 行。**确认文本（口令原值）、confirmation token、P3 内部状态一律不出现在任何写入参数中**——不是靠消毒兜底，而是调用方根本不把它们传进来。确认失败轮**不写 episode**（不留记忆痕迹，仅沿用 P3 既有锁定机制），避免通过记忆侧信道探测口令。

### 4.3 禁入清单总表（任何一处违反即为 P5 验收失败）

| 数据 | 项目摘要 | 会话摘要 | episodes | embedding 输入 | 向量索引 | 检索结果 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 口令（passphrase 及其原文） | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 确认原文（confirmation token / 原文） | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 未脱敏敏感执行结果 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 秘密原值（`api_key=sk-…` 等赋值形式，**及中文自然语言形态如 `我的账号密码是123456`**，`05` §2.3c） | ❌ | ❌ | ❌（占位后可入） | ❌（同左） | ❌（同左） | ❌（同左） |
| 受保护路径原值 | ❌ | ❌ | ❌（占位后可入） | ❌（同左） | ❌（同左） | ❌（同左） |

- 口令与确认原文的"不留存"由 P3 既有裁决保证（IdentityVerifier 哈希文件、确认流程不留存），P5 重申并纳入验收断言。
- "占位后可入"表示经 §4.1 消毒替换为语义占位符后的文本可以进入全部存储与索引。

### 4.4 embedding 本地边界

- 输入边界：只有消毒后文本进入 embed（§3.2 顺序钉死）；EmbeddingBackend 接口文档写明"实现不得将文本发送至非 loopback 端点"。
- 输出边界：向量只落本地 SQLite（episode_vectors）；不进审计事件、不进日志、不外发（P4 TaskBrief 的 memory_evidence 走 retrieve 文本结果，不经向量）。
- 远程 embedding：**默认且唯一行为是拒绝**（构造期 CONFIG_ERROR，无开关，见 §3.2）。

---

## 5. 接口与数据结构（Claude 所有签名；交由 Codex 同步 00-* 工程契约）

### 5.1 core/interfaces.py（→ 00-core-interfaces.md §2 扩展）

1. **新增 `EmbeddingBackend` ABC**（签名见 §3.1）。
2. **新增 `ProjectRecordStore` Protocol**（存储原语，由后端实现；业务规则在 ProjectStore）：

```python
class ProjectRecordStore(Protocol):
    def get_project_record(self, project_id: str) -> dict | None: ...
    def put_project_record(self, record: dict) -> None: ...
    def list_project_ids(self) -> list[str]: ...
```

3. **`MemoryBackend.retrieve` 签名扩展**（向后兼容：既有位置参数不变，新增仅限关键字参数）：

```python
def retrieve(
    self,
    query: str,
    top_k: int = 5,
    *,
    max_bytes: int | None = None,      # None → 用后端配置 retrieval.max_context_bytes
    topic_hints: Sequence[str] = (),   # 非空时仅保留 topic 命中 hints 的候选
    project_id: str | None = None,     # 当前项目（归一化值）；None → 仅未归属池
) -> Result[list[MemoryChunk]]: ...
```

`project_id` 是 §3.5 步骤 0 范围裁剪的输入——后端无法从 query 推断当前项目，必须显式传入；ContextAssembler 从 TopicDecision 取值透传（§2.4），App 与其他调用方不得绕过该参数直接调 retrieve。

4. `store_episode` / `get_summary` / `save_summary` / `detect_topic_relation` 签名不变（但 store/save 的**行为**新增写入消毒义务，写入契约文本）。

### 5.2 core/schemas.py

- 新增 `ProjectState`（§1.2）、`TopicDecision`（§2.1）。
- `MinimalContext` 增字段：`project_id: str | None = None`——由 ContextAssembler 从 TopicDecision.project_id 写入；IntentResolver 多轮检索（`_retrieve_for_candidate`）以此透传给 `memory.retrieve(project_id=…)`，否则认知轮次拿不到当前项目、按 None 规则只检索未归属池，项目内记忆在多轮理解中丢失。
- `MemoryChunk` 增字段：`vector_score: float | None = None`、`match_source: str = "keyword"`。
- `similarity_score` 语义变更为融合分 [0,1]（§3.6）。
- `LocalTaskContext`（P4 结构，main.py 内）增字段：`project_id: str | None = None`——云端任务创建时写入 TopicDecision 的归一化 project_id，供 `_followup_candidates` 的 memory_evidence 检索透传（不得用 InputEvent.project_id 原值替代）。此为 05 契约的结构扩展，随 00 同步清单一并提交 Claude 审查。
- `ExecutionRecord` 与 `ResponseOutput`（§4.2 定义的两种结构化形态）：字段定义落在 00-adapter-factory 的 Core 数据结构区（`ResponseOutput{display, narrative_reply}`、`ExecutionRecord{tool_name, verdict, risk_level, outcome, sanitized_summary, error_code?}`），本契约 §4.2 为行为真源；schemas.py 落位时两处须一致。

### 5.3 core/retention.py

- `KEEP_FULL ≥ 0.60`、`KEEP_SUMMARY ≥ 0.35`（supersede 3.0 / 2.0，注释标注 superseded by 06-p5）。

### 5.4 错误码（→ 00-error-contract.md 扩展）

| 错误码 | 语义 | recoverable | user_message |
|---|---|:---:|---|
| `EMBEDDING_ERROR`（新增） | embedding 计算/超时失败（Result.err 返回，检索降级不致命） | true | "语义检索暂不可用，已切换关键词检索。" |
| `MEMORY_ERROR` | 存储/检索/迁移/ProjectState 校验失败 | 按场景 | 沿用现有 |
| `CONFIG_ERROR` | 配置非法、非 loopback embedding、维度不匹配 | false | 沿用现有 |

### 5.5 00-adapter-factory.md 扩展点

- `create_memory_backend` 内部按 `memory_backend.config.embedding.type` 构造 embedding（"none" → None；"ollama" → OllamaEmbeddingBackend）并注入 SQLiteMemoryBackend / InMemoryMemoryBackend；工厂签名不变。
- bootstrap 组装：ProjectStore（持有 SQLiteMemoryBackend 作为 ProjectRecordStore）与 TopicTracker 注入 App。

### 5.6 Core 组件公开契约（新类，非 interfaces.py 抽象）

**ProjectStore**（`src/memory/project_store.py`，持有 ProjectRecordStore + 消毒由后端兜底）：

```python
class ProjectStore:
    def __init__(self, records: ProjectRecordStore, *, auto_create: bool, summary_max_chars: int): ...

    def resolve(self, input_text: str, explicit_project_id: str | None) -> str | None:
        """§1.4 三级解析：显式归一化 → 提及唯一命中 → None。返回归一化后的 project_id。"""

    def ensure(self, project_id: str) -> ProjectState | None:
        """不存在则按 auto_create 建骨架；auto_create=False 且不存在 → None。"""

    def load(self, project_id: str) -> ProjectState | None: ...

    def set_manual(self, project_id: str, field: str, value: object) -> None:
        """field ∈ {"title","goal","constraints","status","summary","topic_tags"}；校验 §1.2 约束后写入并加入 manual_overrides。"""

    def clear_manual(self, project_id: str, field: str) -> None: ...

    def update_auto(self, project_id: str, *, summary: str | None = None,
                    add_topic_tags: Sequence[str] = ()) -> None:
        """自动更新：跳过 manual_overrides 锁定字段；summary 截断至 summary_max_chars；
        消毒由后端 put_project_record 兜底（§4.1）；project_id 不存在时为 no-op（不隐式建项）。"""

    def list_project_ids(self) -> list[str]: ...
```

**TopicTracker**：签名见 §2.1。**TopicDecision**：见 §2.1（dataclass 归 schemas.py）。

**命名空间规则（防混用）**：`ProjectState.project_id`、episode `metadata.project_id`、`TopicDecision.project_id` 三者恒为归一化值；`InputEvent.project_id` 原值只在 `resolve()` 入口出现一次。

---

## 6. 工程与验收

### 6.1 配置（config/default.toml 增段；config/p5_semantic.example.toml 为示例）

```toml
[memory_backend.config.embedding]
type = "none"                # none | ollama；CI 默认 none（纯关键词，不依赖本机 Ollama）
base_url = "http://localhost:11434"
model = "nomic-embed-text"
dim = 0                      # 0 = 构造期探测
timeout_seconds = 5

[memory_backend.config.retrieval]
vector_weight = 0.4          # 与 keyword_weight 之和必须为 1.0（容差 1e-9），各自 ∈ [0,1]；非法 → CONFIG_ERROR
keyword_weight = 0.6         # 和约束保证融合分恒在 [0,1]，retention 阈值不失真；不允许两者同时为 0（被和约束覆盖）
max_context_bytes = 4096
same_project_boost = 0.1

[projects]
auto_create = true
summary_max_chars = 2000
```

> 注意：融合权重默认值以本节为准（keyword_weight=0.6、vector_weight=0.4，与 §3.5 的 w_kw=0.6、w_vec=0.4 一致——本地小库关键词精确命中可靠，向量用于召回关键词漏掉的内容，不反向压制）。

### 6.2 测试替身

| 替身 | 用途 |
|---|---|
| `MockEmbeddingBackend` | 确定性向量：按文本 token 集合哈希映射到固定维度单位向量（共享 token → 向量相近）；可编程 `health_check=False`、`Result.err` 注入故障 |
| `NullEmbeddingBackend` | 恒不可用（降级路径测试） |
| `InMemoryMemoryBackend` 自身 | 实现 ProjectRecordStore Protocol，作为 ProjectStore 测试存储 |
| v1 库 fixture | 预置 P2 schema + 旧数据行，验证迁移兼容 |

### 6.3 性能三档（参考值，归口测试规范）

混合检索 ≤5k episodes：目标 150ms / 最低可接受 800ms / 调试不设限；关键词降级路径沿用 P2 水准（≤50ms / 300ms）。

### 6.4 端到端验收场景（tests/test_p5_scenarios.py，全部必须自动化）

| # | 场景 | 断言要点 |
|---|---|---|
| E1 | 项目切换 | A 项目对话中显式切 project_id=B → B 的 ProjectState 摘要进入 MinimalContext；随后的普通检索不含 A 的 chunk（§1.5 范围裁剪保证，非仅靠加分）；topic 重置；episodes 归属正确（metadata.project_id = 归一化后的 B） |
| E2 | 旧话题引用 | 同会话 shift_with_reference（embedding=none 也必须通过）→ 定向检索召回旧 topic chunk；referenced_topic 落入 metadata |
| E3 | 语义近似但关键词不同 | MockEmbeddingBackend + 共享语义 token → 关键词 0 分的 chunk 经向量召回进入结果且 match_source 含 "vector" |
| E4 | embedding 不可用降级 | NullEmbeddingBackend → 检索 Result.ok 非空（纯关键词）、无异常、retention 阈值语义一致 |
| E5 | 敏感数据不入索引 | 输入含 `api_key=sk-abc123` 与 `~/.ssh/id_rsa` → DB 存储文本无原值、Mock embedding 收到的输入无原值、检索结果无原值、ProjectState.summary 无原值（占位符存在）；**2026-09-24 增补**：中文自然语言形态（`我的账号密码是123456`、`密码：abc 123`）同样零原值，且**不含标签**的普通数字陈述（`计数器是123456`）逐字留存（零误伤，`05` §10.11 C1–C4/C12）。**同日第二轮补充**：`密码是青山绿水` **必须**被替换、「`密码：abc，123`」的回收片段 `123` **必须**被移除、`密码是[已脱敏:secret]，123` 的 `123` **不得**放走（回收后判态），而 `密码是abc，今天天气不错` 的后半句**必须**保留；**反向断言**：`改密码是必要的` 一类句子**不得**被断言零命中（它是已登记的过度脱敏代价）。**同日第三轮（值区到行末，`05` §10.11 C13）**：`密码 abc123`（**裸空格**作边界）、`密码 青山绿水`、`密码abc123`（粘写）、`密码是abc，青山绿水`（**整行到行末**，终止符后的 CJK 片段一并替换）、`密码：` + 换行 + `abc123`（**顺延**）**全部必须**被替换且零原值落盘；`密码学是什么` / `tokenizer` / `今天讨论了api_key的实现方案` **必须**不命中（标签侧条件）；**反向断言**：`token 过期了` / `api_key 读不到` 一类句子**不得**被断言零命中（T2 已登记的过度脱敏代价）；值区为空（标签独占一行且**文本末尾**）**不得**触发任何拒绝或 `[已脱敏:block]` |
| E6 | 迁移兼容 | v1 库 fixture 打开 → 自动升 v2 → 旧 episodes/summaries 完整、检索可用、backfill 后向量可召回 |
| E7 | ambiguous 不注入 | ambiguous 轮的 MinimalContext 不含按旧 topic 定向召回的内容；referenced_topic 为 None |
| E8 | 字节预算 | 构造超预算 chunk 集合 → 检索结果 UTF-8 字节总量 ≤ max_context_bytes |
| E9 | 工具原文不入记忆 | 工具返回一段不含已知敏感模式的文件内容（如普通 .env 全文）→ episode 中无该原文，仅存 ExecutionRecord 结构化行（§4.2 结构化切分保证，非正则兜底）；display 回复不受影响 |
| E10 | 会话隔离 | 两个 session 交替输入（A 谈话题 1、B 谈话题 2）→ 双方 TopicDecision.topic_label 互不污染；A 的 shift_with_reference 不召回 B 的 chunk |
| E11 | 口令确认路径 | 需口令的危险操作确认成功并执行 → episode 存在且 User 段为固定占位串，DB 全文（episodes/summaries/projects/向量索引）不含口令原值与确认原文；ExecutionRecord 行存在；确认失败轮无新 episode |
| E12 | hints 零命中 | shift_with_reference 但 hints 在库中零命中 → 检索 Result.ok([])（空集不回退全库），普通轮次检索不受影响 |
| E13 | 云端咨询结果写回（2026-09-24 新增，§2.4） | 强制云咨询 + fake backend 走到 `/cloud allow` 续接回合 → **存在**新 episode：User 段 = 原回合用户输入（不是 `/cloud allow`），Assistant 段带云端来源标记；`_topic_records` / `_topic_turn_counts` 已计入该轮；同 session 下一轮的短追问（`那再展开一点`）能召回该 episode 的云端结论；`_update_project_memory` 被触发一次且**零新增云端调用**；取消 / 授权失效 / 跨会话不匹配三类控制确认**不产生** episode（§2.4 排除项）。**同日第二轮补充（单条不变式）**：① 整个任务 `memory.store_episode` **恰一次**——产出授权 preview 的那一回合**零** episode（该回合的 `_topic_records` / `_topic_turn_counts` / 项目摘要更新**均不推进**）；② 断言 `recorder.record` / `_topic_records` / `_topic_turn_counts` / `_update_project_memory` 在整个任务上**各恰一次**（不是两次）——这是「授权提示不入记忆、只写完整一条」的直接外部证据；③ 端到端**不**覆盖 `_local_task_context is None`（现行状态机不可达），该分支由**定向测试**（强制置 `None`）断言「撤 grant + 清 pending + 返回 fallback + 零 episode + 无新枚举值」。**同日第三轮补充**：④ **云端挂起追问**（云端本轮回复是追问、`main.py` 调 `_suspend_for_followup`）的回合**零 episode**、四条副作用链均不推进——断言依据是**该回合没有调用 `_record_turn`**，不是回复文本匹配；⑤ 快照载体**只有 `LocalTaskContext`**：断言 `PendingCloudAuthorization` 上不存在 topic/intent 字段；断言快照在**进入 `_consult_cloud` 之前**读取（`main.py:1239` / `1216` 两条路径都会把 `_local_task_context` 置空，晚读必空）；⑥ **挂起回合零 episode 在两条路径上都断言（2026-09-25 修正，原「已登记的不对称」作废）**：直连路径落到创建 pending 的那条分支（`main.py:1377-1389`）时同样零 episode——抑制判据 `_pending_cloud is not None and _pending_cloud.task_id == task_id`（`main.py:432-435`）对本回合在两条路径上同等成立；测试**应**断言该路径零 episode。**反向断言**：`create_policy_grant` **成功**的那条分支（`main.py:1376`）**不是挂起**——它同回合返回云端答案并写**恰一条** episode（Assistant 段是答案），测试**不得**把该分支也断言成零 episode |

### 6.5 单元测试矩阵（要点）

- TopicTracker：四关系路由表逐格断言（§2.2 每格）；topic 标签派生确定性（同输入同标签）；**首轮规则**（空 topic → 按 new_topic，store_episode 必填 topic 不失败）；**session 隔离**（两 session 交替输入状态互不污染）；end_session 清理。
- ProjectStore：字段校验（超限/非法值）、manual_overrides 锁定（自动更新跳过锁定字段）、ensure 骨架创建、auto_create=false 行为、resolve 唯一命中/多命中不归属、update_auto 对不存在 project_id 为 no-op。
- memory_hygiene（2026-09-24 修订；同日**第二轮**补钉；同日**第三轮重写判据**）：**凭据类两类占位合并为一个 `[已脱敏:secret]`**、受保护路径独立、扫描顺序、幂等、fail-closed 自检；**检测模式集零自定义**——断言 `memory_hygiene` 不持有任何正则字面量（唯一真源 = `secret_scan`）；**不含标签**的普通中文语句与数字陈述零误伤；**值区到行末**（`密码是abc，青山绿水` 整行替换）、**顺延一次**（`密码：` 换行后跟 `abc123` ⇒ `abc123` 被替换）、**值区为空不触发任何处置**；**删除态断言**：「不可界定」这一状态分支**不得存在**（本地只剩「原地整体替换」一种处置）；**反向断言**：⚠️「条款含 CJK 即豁免」分支**不得存在**（`密码是青山绿水` 必须被替换）⚠️、`token 过期了` / `api_key 读不到` 一类句子**不得**被断言零命中（T2 已登记的过度脱敏代价）；**标签侧条件断言**：`密码学是什么` / `tokenizer` / `今天讨论了api_key的实现方案` 不命中，**同一分支的正向断言**是 `密码abc123` 命中（CJK 标签紧随非 CJK 非空白字符时 T3 **照常触发**；「CJK 标签下 T3 不触发」只指紧随 **CJK 字符**这一种情形）——断言该分支的**依据是标签侧条件**（拉丁标签右边界 / CJK 标签紧随 CJK 字符），**不得**引入任何值形态断言（`05` §10.11 C12/C13）。
- 事实身份前缀（2026-09-24 新增）：会话摘要行与逐字 episode 片段进入 `relevant_history` 时前缀不同且都非空（§2.3、§2.4、`05` §2.5 规则 9）；`brief_facts` 不再承载 `summary`；项目摘要前缀按 `manual_overrides` 二值确定（自动 / 用户手写），同输入两次生成前缀相同（幂等）。
- 云端写回链（2026-09-24 新增；同日**第二轮**补钉；同日**第三轮**统一载体并补挂起形态）：续接回合走同一 `_record_turn` + `_record_tool_events`；进入授权等待时**冻结** `topic_label` / `intent_type`，**快照载体只有 `LocalTaskContext`**（断言 `PendingCloudAuthorization` 无 topic/intent 字段；断言快照在进入 `_consult_cloud` 之前读取——`main.py:1239` / `1216` 都会置空 `_local_task_context`）；**断言续接回合零意图解析调用**（fake backend 计数 `generate` 调用）；**单条不变式**——整任务 `store_episode` / `recorder.record` / `_topic_records` / `_topic_turn_counts` / `_update_project_memory` **各恰一次**，产出授权 preview 的回合**零** episode（抑制判据 = 本回合有 `phase="authorization_required"` 事件，**不得**用回复文本匹配）；取消 / 失效 / 跨会话 / 被取代四类零 episode；**云端挂起追问**回合零 episode（断言未调用 `_record_turn`）；`_local_task_context is None` 由**定向测试**（强制置 `None`）覆盖：撤 grant + 清 pending + 返回 `_CLOUD_FALLBACK_REPLY` + 零 episode + 无新枚举值；**挂起回合零 episode 在两条路径上都成立**（2026-09-25 修正：原「直连路径挂起回合会写 episode」的不对称登记**作废**——抑制判据对两条路径同等成立；`create_policy_grant` **成功**的分支是「写恰一条、Assistant 段 = 云端答案」，与「挂起」是两回事）。
- 融合管线：去重（match_source=both）、归一与降级标尺一致、same_project_boost、重排确定性全序；**范围裁剪**（普通检索仅当前项目 ∪ 未归属池；hints 定向检索全库）；**过滤下推**（allowed_ids 在向量 top-N 前生效——构造被挤掉场景验证）。
- 写入消毒义务：InMemory 与 SQLite 两后端共形（同一组消毒断言跑两实现）。
- ExecutionRecord 接入：_record_turn 持久化 narrative_reply + 结构化记录行，episode 不含工具原文；ResponseBuilder display/narrative 分离；**口令确认路径**（成功轮 User 段占位、失败轮不写、写入参数不含口令/token）。
- VectorIndex allowed_ids 语义：`is not None` 判断（空集合返回空列表）、None 不限制；hints 零命中 → 向量侧空且不回退。
- retrieve 直调透传：IntentResolver 多轮检索用 MinimalContext.project_id、_followup_candidates 用 LocalTaskContext.project_id——断言项目内 chunk 在认知轮次与云端 evidence 检索中可召回（而非只落未归属池）。
- 会话摘要：滚动覆盖（第二次话题收尾不丢第一话题要点）、降级路径、读取仅当前 session。
- 迁移：v1→v2、旧 scope="project" 行导入、新库直接 v2。

---

## 7. 决策表

| 日期 | 裁决 | 理由 |
|---|---|---|
| 2026-09-09 | ProjectState 独立 `projects` 表而非复用 summaries(scope="project") | 结构化字段 + 所有权 + 覆盖语义需要 schema 化存储；自由 JSON 摘要表无法表达 manual_overrides |
| 2026-09-09 | 消毒唯一真源放在 MemoryBackend 写入方法内部，而非各 Core 组件 | 单点强制，防未来新写入路径遗漏；组件侧不依赖自觉 |
| 2026-09-09 | 降级模式 final = kw_norm（关键词单独归一 [0,1]） | 保证 retention 阈值在混合/降级两模式下语义一致，否则降级即全部 KEEP_SUMMARY 以下 |
| 2026-09-09 | 向量索引为 adapter 内部组件，Core 只见 EmbeddingBackend | 铁律 2（Core 不依赖具体实现）；向量库选型属 adapter 细节 |
| 2026-09-09 | 远程 embedding 无绕过开关，构造期 CONFIG_ERROR | embedding 输入=本地对话内容，外发即上下文泄漏；放开属安全边界变更需新契约 |
| 2026-09-09 | ambiguous 不切换 topic、不定向检索、不加权 | 用户明确要求：不得因 ambiguous 把旧话题强行注入新任务 |
| 2026-09-09 | shift_with_reference 引用锚点仅当前 topic | 不猜"用户指哪个旧话题"；更早话题由用户显式指定项目/关键词承担 |
| 2026-09-09 | v1 不做 episode 追溯归属项目 | 归属修正需要人工确认语义，超出 P5 范围；未归属池检索可达，不丢数据 |
| 2026-09-09 | similarity_score 语义变更为 [0,1] 融合分 | 单标尺承载混合/降级两模式；配套 retention 阈值 supersede（有意变更清单 §3.6） |
| 2026-09-09 | topic 标签派生不用模型 | 确定性可测；模型标签不可信（P3/P4 同一课），且启发式已存在 |
| 2026-09-09 | 会话摘要模型生成失败 → 确定性降级、不阻塞主循环 | 记忆写入是旁路职责，失败不得影响响应主路径（与 _record_turn 异常吞并策略一致） |
| 2026-09-09 | default.toml 融合权重 vector 0.4 / keyword 0.6 | 本地小库关键词精确命中可靠；向量用于召回关键词漏掉的内容，不反向压制 |
| 2026-09-09 | 自审修正 5 处：路由表 same_topic/ambiguous 行与不变量 3 对齐（project_switched 独立生效）；§3.5 权重默认值顺序与 §6.1 统一为 (w_kw=0.6, w_vec=0.4)；topic_hints 过滤明确覆盖向量候选；InMemory 配置与向量索引形态钉死；episodes 占位替换列入有意变更清单 | 对抗演练发现的自相矛盾与过滤缺口，见正文对应节 |
| 2026-09-09 | 外部审查修订 6+2 项：① TopicTracker 按 session_id 隔离状态 + end_session；② 首轮空 topic 强制按 new_topic（防 store_episode 必填校验失败）；③ 会话摘要定为整会话滚动摘要（summaries 主键 (scope, scope_id) 决定，话题收尾仅为更新触发点）；④ 普通检索范围 = 当前项目 ∪ 未归属池，定向检索全库须命中 hints（修复与 E1 的矛盾，对齐 FR6 项目边界）；⑤ VectorIndex.search 增 allowed_ids 且过滤下推到 SQL（防正确话题向量被挤掉）；⑥ 工具原文不入记忆改为结构化保证——ResponseBuilder 分离 display/narrative，_record_turn 接收 ExecutionRecord 列表（正则消毒不足以拦截任意文件内容）；⑦ 融合权重和恒为 1.0；⑧ TopicTracker/ProjectStore 公开契约补全 + episode project_id 统一用归一化值 | 六条实质问题均成立：并发会话串状态、首轮写失败、主键覆盖、E1 矛盾、过滤时机、正则消毒的根本局限 |
| 2026-09-09 | 外部审查修订第二轮 3 项：① retrieve() 增 `project_id` 关键字参数（后端无从推断当前项目，ContextAssembler 透传 TopicDecision.project_id；None → 仅未归属池）；② allowed_ids 语义钉死为 None=不限制、空集=返回空（实现必须 `is not None` 判断，防 hints 零命中退化为全库检索，配 E12）；③ 口令确认路径写入规则钉死——成功轮 User 段固定占位 + ExecutionRecord 照常、确认文本/token 不进写入参数（结构保证而非消毒兜底）、失败轮不写 episode（防记忆侧信道探测口令），配 E11 | 三条均为实现时无法安全猜测的缺口：接口缺裁剪输入、空集语义二义、P3 提前返回分支绕过写入链 |
| 2026-09-09 | 外部审查修订第三轮 1 项：MinimalContext 增 `project_id` 字段（ContextAssembler 从 TopicDecision 写入），IntentResolver 多轮检索透传——否则认知轮次 retrieve 默认 None 只落未归属池，项目内记忆丢失。同类排查发现第三处直调点 `_followup_candidates`（P4 云端 evidence）：LocalTaskContext 增 `project_id` 字段（任务创建时从 TopicDecision 记入归一化值），一并钉死；契约新增 retrieve 直调点全量清单（§2.4），后续新增调用必须过范围裁剪 | 接口贯通缺口：范围裁剪参数只接入了主检索一处，认知轮次与云端路径会静默退化 |
| 2026-09-10 | §2.2 路由表 shift_with_reference 行「会话摘要」列由「正常加载」修订为「旧 topic 收尾更新一次（同 new_topic 行）」 | 实现审查发现的契约疏漏：topic 标签更换即意味着该标签的 `_topic_records` 累积清算（否则记录永不清算、滚动摘要漏掉该话题内容），new_topic 与 shift_with_reference 同为换标签路由，收尾语义必须一致；§1.5 项目切换重置 topic 同理 |
| 2026-09-10 | §4.2 `sanitized_summary` 生成规则由「结果文本截前 200 字符 → 消毒」修订为「仅结构化信息（键名/类型/计数），零返回值文本」 | Codex 端到端实现证实：不含敏感模式的任意文件内容（如普通 .env 行）会经旧规则漏入 episode，违反本节「工具执行结果原文永不入记忆」——正则兜底对任意文本不充分，确认采纳更强的结构化实现；E9 断言不变，ResponseBuilder display 侧不受影响 |
| 2026-09-24 | §4.1 消毒规则 1/2 合并：凭据类**单一占位符 `[已脱敏:secret]`**，检测模式集零自定义（唯一真源 = `src/safety/secret_scan.py`，`05` §2.3c.1），`contains_bare_secret` / `contains_sensitive_value` 退化为薄包装 | 同一判据此前有四处正则副本 + 七份 TOML 副本，且都锚在英文赋值形态——中文自然语言凭据（`我的账号密码是123456`）全链路零命中（clarifications 2026-09-24 安全阻塞项）。多实现即多漏点；单一真源是唯一可验收的形态 |
| 2026-09-24 | 不可界定命中（值区含内部空白）在**本地落盘**走最大区间替换，**不得**整段 `[已脱敏:block]`；`[已脱敏:block]` 降级为最后兜底 | 本地无外发泄漏面，销毁用户整条记忆的成本高于收益；检测面扩大后此类命中会显著增多。出站侧仍 fail-closed（`05` §2.3c.4），两侧处置不同是**有意的面差异**，不是不一致。⚠️**（本行「不可界定」态已被同日第三轮删除——值区上界改为行末后归属永不确定，本地只剩「整个值区原地替换」一种处置；本行的结论「不得整段 `[已脱敏:block]`」与「`[已脱敏:block]` 仅作兜底」仍然有效）** |
| 2026-09-24 | 会话摘要与项目摘要注入上下文时带「本地模型推断、未经用户确认」同族固定前缀，与逐字 episode 片段前缀**必须不同**；生成提示词固定收窄为「只复述用户已陈述内容与本轮实际动作，不得把推测写成事实」 | 摘要进入云端 TaskBrief 时曾被当「已知事实」，出现把用户原话（「没有明显故障」）强化为结论（「验证无故障」）的事实扩张。前缀是确定性的来源自述，不依赖模型自觉；提示词收窄是加固而非信任——生成物仍按不可信文本消毒 |
| 2026-09-24 | 云端咨询最终回复与普通回合走**同一条** `_record_turn` + `_record_tool_events` 链；User 段 = 原回合输入、Assistant 段带云端来源标记；进入授权等待时**冻结** `topic_label` / `intent_type`；取消/失效/跨会话三类控制确认不写 episode | 原 `/cloud allow` 续接分支提前返回、绕过写入链（`main.py:303-312`），导致云端结论不入 episode、下一轮短追问召回不到——连续性断裂。原输入与 `project_id`/`session_id` 已在 `LocalTaskContext`，只需补冻两个派生字段；冻结换来「续接回合零额外意图解析调用」 |
| 2026-09-24 | **第二轮**：⚠️**（本行「值区三态 / 片段回收」的判据已被下一行（同日第三轮）整体修订作废，实现请以第三轮为准；「删除 CJK 豁免」「禁止任何形态判据」「接受过度脱敏为已知代价」三处结论仍有效）** **删除**「条款含 CJK ⇒ 非值区形态」豁免；值区三态改判「空 / == 占位符字面量 / 含内部空白」；新增跨终止符**值形态片段回收**（判态在回收之后）；接受「部分中文句式过度脱敏」为**已知代价**并**禁止**任何形态/语法豁免 | 原判据使 `密码是青山绿水` **原样落盘并外发**、`密码：abc，123` 残留 `123`——与「原值永不进入 payload/记忆」的承诺直接冲突，不能作为观察项长期挂着。反向取舍（CJK 豁免）的失败模式是真实中文口令泄漏，代价方向**不对称**：过度脱敏可见、可拒绝、有界，漏检不可见且即泄漏。`系统密码是…` / `数据库密码是…` 说明语法豁免会把合法标签一并放走，故**不允许任何形态判据**回归 |
| 2026-09-24 | **第三轮（本轮）**：值区判据重写为**命中 = 标签闭集成员 + 边界成分（T1 显式分隔符 / T2 空白 / T3 紧邻非 CJK 非空白字符，全部与值无关）；值区 = 标签之后到本行末（标签独占一行时顺延一个非空行）**，区内不切分、不筛形态；**删除「终止符 / 片段回收 / 不可界定」三项判据**，本地只剩**一种处置**（整个值区原地替换为一个 `[已脱敏:secret]`，出站同源）；`05` §2.3c.4 第 2 条的**整段拒绝是出站侧**行为，本地不适用；**契约新增三条语法边界（非形态豁免）**：无边界字符的粘写（`密码青山绿水`）、值在标签之前、值跨一个以上顺延行——由既有**无标签裸秘密检测层**兜底 | 第二轮残留的两处**值形态判据的尾巴**各自漏掉一个真实口令：`密码 abc123`（裸空格不当作边界 ⇒ 完全不命中，原样落盘并外发）、`密码是abc，青山绿水`（终止符后的 CJK 片段不回收 ⇒ 尾部原样落盘）——与「原值永不进入 payload/记忆」直接冲突；而「禁止任何形态豁免」与「CJK 后缀不回收」本身互相矛盾。修法不是再补一条形态规则（那只会把尾巴挪个位置），而是**把值区上界改成确定量（行末）**：上界确定后「归属不明的后续片段」不存在，「不可界定」态随之删除，本地处置从两种收敛为一种。代价照实登记：`token 过期了` / `api_key 读不到` 这类「拉丁标签 + 空白 + 中文技术句」被整段替换，与 `password 青山绿水`（真口令）字符级不可区分——**消解方向是提高标签侧选择性，禁止回收值形态判据** |
| 2026-09-24 | **第三轮**：云端写回**快照载体只有 `LocalTaskContext`**（`PendingCloudAuthorization` 不承载 topic/intent），且快照必须在**进入 `_consult_cloud` 之前**读取（`main.py:1239` 成功路径与 `main.py:1216` 云端失败路径都会把 `_local_task_context` 置空；读取点取 `main.py:1170` 的同一处）；终结形态枚举补全为**七种**——成功收敛 / fallback 收敛（各写唯一一条）、取消 / 授权失效 / 跨会话不匹配 / 被新输入取代 / **云端挂起追问**（零条）；**零签名变更** | 前一种说法（W2 写「`PendingCloudAuthorization` 冻结 topic/intent」）与规范正文和实现清单的「由 `LocalTaskContext` 承载」互相矛盾，实现者无法同时满足——统一为后者（它已是本任务的本地语义容器，内容不进 pending/grant/审计）。补全终结枚举是因为**挂起追问**与首轮授权提示的抑制理由**完全一致**（追问既不是用户的输入、也不是系统的结论，写进去会被检索当成一条结论），不补就会出现「挂起回合写一条、终结再写一条」的双条回归。读取时机不是文字问题而是实现约束：晚读必空。**已登记的不对称照实记录、本轮不修**：直连路径（`create_policy_grant` 分支）的挂起回合仍会把追问写成 Assistant 段，修它要动直连路径写入时机，超出本轮范围，若真实 run 出现影响按 `05` §10 立候选（**该登记于 2026-09-25 作废**：挂起判据对两条路径同等成立，挂起回合零 episode 是共有不变式；`create_policy_grant` **成功**的分支不是挂起，它写恰一条、Assistant 段 = 云端答案） |
| 2026-09-24 | **第二轮**：云端任务**每任务恰好一条 episode、只在终结时写**——产出授权 preview 的回合**零** episode（判据 = 本回合有 `phase="authorization_required"` 事件），`/cloud allow` 续接回合补写唯一一条；取消/失效/不匹配/被取代**零条**；`_local_task_context is None`（不可达的状态损坏分支）不写回、不新增枚举值 | 首轮写 `User: 原输入 / Assistant: 授权提示`、终结再写一条同 User 的 episode，会让同一输入留两条记录，且**临时授权提示会作为上下文参与检索**——记忆里出现一段用户从未获得、也不代表系统结论的「Assistant 回复」。抑制首轮 + 只在终结补一条，使「用户说过什么 / 系统答了什么」恒为一一对应。与 P3 口令确认路径保留两条的选择**有意不同**：那里的确认回合 User 段是占位文本，原请求只存在于第一条，丢则失忆；这里终结 episode 的 User 段就是原输入，故只留一条 |
