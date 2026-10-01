# 03-p2-sqlite-memory — SQLiteMemoryBackend 模块契约

> 状态：✔️ 完成
> 阶段：P2（SQLite 持久化记忆，替换 P0a 的 InMemoryMemoryBackend）
> 性质：编码前必读。本契约定义 `SQLiteMemoryBackend` 及相关检索/留存模块的行为边界。
> 前序依赖：`00-core-interfaces.md`（MemoryBackend 签名，**不得改动**）、`00-error-contract.md`（错误码）、`00-adapter-factory.md`（工厂与配置注入）、P0a/P1 已完成闭环。

---

## 0. 范围与不变量

**目标**：用持久化 SQLite 替换 P0a 的 `InMemoryMemoryBackend`，实现对话记录跨重启保留、按需检索可用、差异化留存生效。P2 不引入向量库或外部嵌入模型——检索仍基于关键词匹配，与 InMemory 行为一致。

**接口不变**：`SQLiteMemoryBackend` 实现 `core/interfaces.py::MemoryBackend` 的现有 6 个方法，签名一字不改。P2 不新增、不修改任何 Core 接口签名。

**铁律（沿用 project-plan §3.1 / NFR4）**：
1. `src/core/**` 绝不 `import sqlite3`、不 import `src.memory.sqlite_backend`；只有 `src/main.py` 的工厂 `create_memory_backend()` 可 import 本类。
2. 所有 sqlite3 原生异常（`sqlite3.OperationalError`、`sqlite3.IntegrityError` 等）**必须**在本类内捕获并转换为 `LocalMindError(code="MEMORY_ERROR", ...)`。Core 永远看不到 `sqlite3.Error`。
3. 返回值只含纯 Python 类型（`list[MemoryChunk]` / `dict` / `str`）——不得把 `sqlite3.Row`、`sqlite3.Cursor` 等泄漏给 Core。

**零新增运行时依赖**：Python 3.11+ stdlib `sqlite3` 模块。不引入 SQLAlchemy / aiosqlite / peewee 等 ORM。

**范围包含**：
- `src/memory/sqlite_backend.py` — SQLiteMemoryBackend 主实现
- `src/memory/retrieval.py` — 关键词分词与打分（供两个后端共享）
- `src/core/retention.py` — 差异化留存分级策略（纯函数，无后端依赖，Core 自有）
- `src/core/context_assembler.py` — 调用 `retention.classify_retention()` 分级上下文
- `src/main.py` — 工厂 `create_memory_backend()` 新增 `"sqlite"` 分支
- `config/default.toml` — 内存后端配置（保持 in_memory 为 CI 默认，新增 sqlite 示例）
- `tests/test_sqlite_backend.py` — SQLiteBackend 单元测试
- `tests/test_context_assembler.py` — 扩展：差异化留存分级集成测试
- `scripts/run_p2.py` — 演示脚本（连真实 db 文件，端到端验证持久化）

---

## 1. 表结构设计

单文件 SQLite 数据库，路径由配置 `db_path` 指定。以下所有表在 `__init__` 时自动创建（`CREATE TABLE IF NOT EXISTS`）。

### 1.1 schema_version — 迁移版本

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);
```

- 仅一行或无行。首次创建时写入当前最新版本号。
- 迁移时逐版本检查、递增（见 §3）。

### 1.2 episodes — 对话片段

```sql
CREATE TABLE IF NOT EXISTS episodes (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    topic       TEXT NOT NULL DEFAULT '',
    session_id  TEXT NOT NULL,
    project_id  TEXT,
    timestamp   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_episodes_session
    ON episodes(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_episodes_topic
    ON episodes(topic);

CREATE INDEX IF NOT EXISTS idx_episodes_project
    ON episodes(project_id, created_at);
```

| 列 | 类型 | 必填 | 说明 |
|----|------|:---:|------|
| `id` | TEXT | ✅ | 唯一 chunk ID，格式 `"ep_{uuid_hex_short}"`（如 `ep_a1b2c3d4e5f6`） |
| `content` | TEXT | ✅ | 对话文本，如 `"User: ... \nAssistant: ..."` |
| `topic` | TEXT | ✅ | 话题标签，来自 `metadata["topic"]`；默认空串 |
| `session_id` | TEXT | ✅ | 会话 ID，来自 `metadata["session_id"]` |
| `project_id` | TEXT | — | 项目 ID，来自 `metadata.get("project_id")` |
| `timestamp` | TEXT | ✅ | 对话发生时的时间戳，来自 `metadata.get("timestamp", "")` |
| `created_at` | TEXT | ✅ | 数据库插入时间，SQLite `datetime('now')` 自动填充 |

**索引选择理由**：
- `idx_episodes_session` — `retrieve()` 按 session 过滤的常见路径
- `idx_episodes_topic` — 话题切换检测、按 topic 检索
- `idx_episodes_project` — 项目级记忆检索

### 1.3 summaries — 摘要存储

```sql
CREATE TABLE IF NOT EXISTS summaries (
    scope       TEXT NOT NULL,
    scope_id    TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (scope, scope_id)
);
```

| 列 | 类型 | 说明 |
|----|------|------|
| `scope` | TEXT | `"conversation"` 或 `"project"` |
| `scope_id` | TEXT | conversation_id 或 project_id |
| `summary_json` | TEXT | JSON 序列化的摘要 dict |
| `updated_at` | TEXT | 最后更新时间（ISO 8601） |

- `save_summary()` → `INSERT OR REPLACE`
- `get_summary()` → `SELECT summary_json WHERE scope=? AND scope_id=?`，`json.loads()` 后返回 dict
- `summary_json` 解析失败 → `MEMORY_ERROR`（不吞错，数据损坏需暴露）

### 1.4 （预留）chunks_fts — 全文索引

P2 不建此表。P5 引入 FTS5 或向量嵌入时在此处扩展。当前在 `retrieval.py` 中做 Python 侧关键词打分（见 §4）。

---

## 2. 连接与生命周期

### 2.1 构造函数

```python
class SQLiteMemoryBackend(MemoryBackend):
    def __init__(self, config: dict) -> None:
        """
        config 键：
        - db_path: str — SQLite 文件路径（必填）
        - max_search_episodes: int — retrieve() 扫描上限，默认 500
        """
```

**构造期校验（非法一律 CONFIG_ERROR）**：

| 字段 | 校验规则 |
|------|---------|
| `db_path` | 非空字符串。目录部分若不存在则自动创建（`Path(db_path).parent.mkdir(parents=True, exist_ok=True)`）。**路径为 `":memory:"` 时使用内存数据库**（测试用）。 |
| `max_search_episodes` | 缺省或正整数 |

### 2.2 连接管理

- `__init__` 时打开一个 `sqlite3.connect()` 连接，**整个 Backend 生命周期复用同一连接**。
- 连接参数：
  ```python
  sqlite3.connect(
      db_path,
      # check_same_thread 使用默认 True——P2 明确单线程，不引入伪安全声明
      isolation_level=None,     # 手动管理事务
  )
  ```
- 若 `db_path` 为文件路径（非 `:memory:`），开启 WAL 模式（`PRAGMA journal_mode=WAL;`），允许文件级并发读。
- 开启外键约束（`PRAGMA foreign_keys=ON;`）。
- `row_factory = sqlite3.Row`。
- **不在 `__del__` 中依赖自动关闭**（析构时机不确定）。提供显式 `close()` 方法，由 `main.py` 在应用退出时调用。若 `bootstrap()` 阶段失败（如迁移失败），连接在抛异常前关闭。

**为什么不用 `check_same_thread=False`**：WAL 协调的是数据库**文件**级读写（写不阻塞读），不保护单个 `sqlite3.Connection` 对象的内部状态。同一连接跨线程使用仍是未定义行为。P2 明确单线程，用默认值。未来需要多线程时采用"每线程独立连接"或"连接 + 锁"模式，不靠关闭此检查蒙混过关。

### 2.3 close() 行为

```python
def close(self) -> None:
    """关闭数据库连接。幂等——重复调用无副作用。绝不抛异常。"""
```

- 已关闭的连接再次 `close()` 为 no-op。
- close 后调用任何 MemoryBackend 方法 → `MEMORY_ERROR`，`user_message` = `"记忆系统已关闭。"`。

---

## 3. 迁移策略

### 3.1 版本号约定

版本号为递增整数，从 `1` 开始。`SQLiteMemoryBackend._LATEST_VERSION` 常量记录当前代码期望的版本。

### 3.2 迁移流程

`__init__` 末尾执行：

```
1. CREATE TABLE IF NOT EXISTS schema_version（确保表存在）
2. SELECT MAX(version) FROM schema_version → current_version（无行 = 0）
3. 从 current_version+1 到 _LATEST_VERSION，依次执行迁移函数
4. 每个迁移函数在单事务中运行：BEGIN → DDL → INSERT INTO schema_version → COMMIT
5. 任一步骤失败 → 回滚该迁移事务 → 抛 CONFIG_ERROR（不静默继续）
```

### 3.3 迁移函数模板

```python
def _migrate_v1_to_v2(self) -> None:
    """示例：v1 → v2 添加 project_id 列"""
    self._conn.execute("ALTER TABLE episodes ADD COLUMN project_id TEXT;")
    self._conn.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (2, datetime('now'))"
    )
```

### 3.4 P2 初始版本

P2 为 v1。`_LATEST_VERSION = 1`。初始建表即 v1 schema。

**约束**：
- 迁移只增不删列（ADD COLUMN only），不做破坏性变更。
- 若未来需要破坏性变更，增量版本号 + 新建表 + 数据迁移。
- 迁移失败时 `user_message` 包含 `"记忆数据库升级失败，请检查 data/memory.db 是否被占用或损坏。"`。

---

## 4. retrieve() — 检索语义

```python
def retrieve(self, query: str, top_k: int = 5) -> Result[list[MemoryChunk]]:
```

### 4.1 检索流程

```
1. 参数校验：top_k < 1 → Result.err(MEMORY_ERROR)
2. query 分词（复用 in_memory_backend._tokenize 同款分词逻辑，见 §4.3）
3. 若分词结果为空 → Result.ok([])
4. SELECT id, content, topic, session_id, project_id, timestamp
   FROM episodes ORDER BY created_at DESC LIMIT max_search_episodes
5. 对每条 episode，用 retrieval._keyword_score(query_terms, text, metadata) 打分
6. 排序：`similarity_score` 降序 → `id` 升序（同分时确定次序，与 InMemory 的 `(-score, id)` 一致）
7. 取前 top_k → 组装 MemoryChunk
8. 返回 Result.ok([...])
```

### 4.2 分词逻辑

**必须与 `InMemoryMemoryBackend._tokenize` 行为一致**，代码抽取到 `src/memory/retrieval.py` 作为模块级函数，两个后端共享：

```python
# src/memory/retrieval.py
import re

_CJK_RE = re.compile(r"[一-鿿]+")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")

def tokenize(text: str) -> set[str]:
    """中英文混合分词，零依赖。"""
    tokens = {t.lower() for t in _WORD_RE.findall(text)}
    for cjk_run in _CJK_RE.findall(text):
        tokens.add(cjk_run)
        tokens.update(_char_ngrams(cjk_run, size=2))
    return tokens

def _char_ngrams(text: str, size: int) -> set[str]:
    if len(text) <= size:
        return {text}
    return {text[i:i+size] for i in range(len(text) - size + 1)}
```

- `InMemoryMemoryBackend` 重构为从 `retrieval.py` import（不改行为，只消除重复）。
- `SQLiteMemoryBackend.retrieve()` 同样 import。

### 4.3 关键词打分

```python
def keyword_score(query_terms: set[str], text: str, metadata: dict) -> float:
    """与 InMemory 行为一致的匹配分。"""
    text_terms = tokenize(text)
    meta_text = " ".join(str(v) for v in metadata.values())
    meta_terms = tokenize(meta_text)
    return float(len(query_terms & (text_terms | meta_terms)))
```

### 4.4 MemoryChunk 映射

| MemoryChunk 字段 | 来源 |
|------|------|
| `id` | `row["id"]` |
| `text` | `row["content"]` |
| `metadata` | `{"topic": row["topic"], "session_id": row["session_id"], ...}`（所有非 content 列） |
| `similarity_score` | `keyword_score(...)` 返回值 |

### 4.5 未命中

查询无匹配（所有 episode 分数为 0）→ `Result.ok([])`，不报错。

---

## 5. store_episode() — 存储对话片段

```python
def store_episode(self, content: str, metadata: dict) -> str:
```

### 5.1 行为

```
1. content.strip() == "" → 抛 MEMORY_ERROR（与 InMemory 一致）
2. metadata 必须包含非空 topic 和 session_id → 缺或空抛 MEMORY_ERROR
3. project_id 从 metadata.get("project_id") 提取（可为 None）
4. 生成 id = "ep_" + uuid4().hex[:12]
5. INSERT INTO episodes (id, content, topic, session_id, project_id, timestamp)
6. 返回 id
```

### 5.2 INSERT 失败处理

- `sqlite3.IntegrityError`（id 冲突，极罕见）→ 重生成 id 重试一次；再次失败 → `MEMORY_ERROR`
- `sqlite3.OperationalError`（DB 锁定、磁盘满等）→ `MEMORY_ERROR`
- `sqlite3.ProgrammingError`（已 close）→ `MEMORY_ERROR`

---

## 6. get_summary / save_summary — 摘要读写

### 6.1 get_summary

```python
def get_summary(self, scope: str, scope_id: str) -> dict | None:
```

```
1. SELECT summary_json FROM summaries WHERE scope=? AND scope_id=?
2. 无行 → return None
3. json.loads(summary_json) → return dict
4. JSON 解析失败 → MEMORY_ERROR（数据损坏，不吞错）
```

### 6.2 save_summary

```python
def save_summary(self, scope: str, scope_id: str, summary: dict) -> None:
```

```
1. scope.strip() / scope_id.strip() 为空 或 summary 为空 → 抛 MEMORY_ERROR（与 InMemory 一致）
2. summary_json = json.dumps(summary, ensure_ascii=False)
3. INSERT OR REPLACE INTO summaries (scope, scope_id, summary_json, updated_at)
   VALUES (?, ?, ?, datetime('now'))
4. 写入失败 → MEMORY_ERROR
```

**幂等**：同 `(scope, scope_id)` 重复调用覆盖旧值（`INSERT OR REPLACE`）。

### 6.3 与 InMemory 实现的差异

InMemory 返回 summary 的副本（`dict(summary)`）防止调用方意外修改。SQLite 版同理——`json.loads` 每次都产生新 dict。行为一致。

---

## 7. detect_topic_relation() — 话题切换检测

```python
def detect_topic_relation(self, current_input: str, current_topic: str) -> str:
```

### 7.1 行为

**与 InMemory 实现完全一致**——使用相同的关键词表和判断逻辑：

```python
_STRONG_REFERENCE_TERMS = {"previous", "above", "刚才", "继续", "上面", "之前"}
_WEAK_REFERENCE_TERMS = {"it", "that", "this", "那个", "这个"}
_NEW_TOPIC_TERMS = {"换个话题", "新话题", "另外", "另一个", "next topic"}
```

判断流程：
1. 输入包含 "新话题" 类关键词 → `"new_topic"`
2. 输入与当前 topic 有共同 token → `"same_topic"`
3. 输入含 "强引用" 词 + 当前 topic 非空 → `"shift_with_reference"`
4. 输入含 "弱引用" 词 → `"ambiguous"`
5. 其他 → `"ambiguous"`

### 7.2 实现策略

**将 InMemory 的判断逻辑抽取到 `src/memory/retrieval.py`**，两个后端共享同一实现。P2 的 `detect_topic_relation` 不查询数据库——仅基于输入文本判断。

**与 InMemory 的关键差异**：InMemory 的 `current_topic` 来自调用方传入。SQLite 版本行为一致，但在后续 P5 阶段可选地利用 `episodes` 表中最近 topic 记录增强判断（当前不做）。

---

## 8. 差异化留存

需求 FR2 要求：检索结果打分后分为**保留原文 / 保留摘要 / 丢弃**。

### 8.1 负责模块

`src/core/retention.py` — Core 自有模块，纯函数，零后端依赖：

```python
# src/core/retention.py
def classify_retention(
    similarity_score: float,
    *,
    high_threshold: float = 3.0,
    low_threshold: float = 2.0,
) -> str:
    """
    根据匹配分分级：
    - score >= high_threshold → "keep_full"       （保留原文）
    - low_threshold <= score < high_threshold → "keep_summary" （保留摘要）
    - score < low_threshold → "discard"           （丢弃）
    """
```

**为什么在 Core 而非 `src/memory/retrieval.py`**：`classify_retention` 是上下文组装的策略逻辑——它决定"哪些记忆片段进入模型上下文"，不依赖任何存储后端。放在 Core 保持单向依赖：`memory/` 负责存取，`core/` 负责裁剪。

### 8.2 调用方

`ContextAssembler.assemble()` 直接 import `src.core.retention`（同包，合法）：

1. 调用 `self._memory.retrieve(query)` → `list[MemoryChunk]`
2. 对每条 chunk 调用 `classify_retention(chunk.similarity_score)`
3. `keep_full` → 原文加入 `relevant_history`
4. `keep_summary` → 截断前 200 字符作摘要加入上下文（P5 可接入 LLM 精炼）
5. `discard` → 不加入上下文

### 8.3 阈值

阈值在 `src/core/retention.py` 中为模块级常量。P2 默认：`high_threshold=3.0`，`low_threshold=2.0`。

**阈值与检索行为的对齐**：`retrieve()` 仅返回 `keyword_score > 0` 的 chunk（至少 1 个 token 命中），且关键词打分是整数（交集 token 数）。因此：
- score ≥ 3 → 原文（强匹配，3+ token 命中）
- score = 2 → 摘要（中等匹配）
- score = 1 → 丢弃（弱匹配，仅有 1 个 token 命中即噪音）

`low_threshold=1.0` 会使 discard 分支永不触发（score > 0 的 chunk 不会 < 1.0），设为 `2.0` 确保三档都可达。

---

## 9. ProjectStore — 延后至 P5

P2 **不实现** ProjectStore。理由：

1. **信任模型冲突**（[project-report.md §4.5](../../project-report.md)）：ProjectState 定义为"人工维护、可自动加载"。`touch()` 自动写入模型推断的 `intent_type` 会污染受信任的项目状态。
2. **阶段边界**：项目摘要管理（话题统计、跨会话项目状态）是 P5 目标，不是 P2。P2 聚焦持久化 episode 存储与检索。

P2 仅保留基础设施：
- `episodes` 表的 `project_id` 列已存在（被动存储，无自动处理）
- `summaries` 表的 `scope="project"` 可用（人工写入）
- `ContextAssembler` 通过 `memory.get_summary("project", project_id)` 读取项目摘要——由人工预先 `save_summary` 写入，不自动生成

P5 实现 `ProjectStore` 时，可考虑使用独立低信任 scope（如 `"project_activity"`）存储自动统计，与人工维护的 `"project"` scope 隔离。

---

## 10. 错误映射

所有 sqlite3 原生异常在本类内转换为 `LocalMindError(code="MEMORY_ERROR", ...)`：

| 情形 | code | recoverable | user_message |
|------|------|:---:|------|
| 数据库文件无法创建/打开 | `MEMORY_ERROR` | `False` | "记忆系统初始化失败，请检查磁盘空间和权限。" |
| 迁移失败 | `CONFIG_ERROR` | `False` | "记忆数据库升级失败，请检查 data/memory.db 是否被占用或损坏。" |
| 磁盘满（INSERT 失败） | `MEMORY_ERROR` | `False` | "磁盘空间不足，记忆存储失败。" |
| 数据库锁定（SQLITE_BUSY） | `MEMORY_ERROR` | `True` | "记忆系统繁忙，请稍后重试。" |
| content/metadata 非法 | `MEMORY_ERROR` | `True` | 与 InMemory 相同的 user_message |
| 已 close 后调用方法 | `MEMORY_ERROR` | `False` | "记忆系统已关闭。" |
| summary_json 解析失败 | `MEMORY_ERROR` | `False` | "记忆数据损坏，摘要无法读取。" |
| retrieve 参数非法 | `MEMORY_ERROR` | `True` | "记忆检索参数无效。" |

**通用原则（沿用 00-error-contract §5）**：`message` 包含技术描述（含 sqlite3 原始错误信息），`user_message` 是完整中文句子，不泄漏 `sqlite3.OperationalError: database is locked` 等技术栈信息。

---

## 11. 并发边界

### 11.1 单进程模型

P2 **不引入多进程/多线程并发控制**。假设：
- 一个进程内单线程调用 MemoryBackend 方法。
- WAL 模式**为未来扩展预留**，P2 不主动使用多线程。

### 11.2 WAL 模式

开启 WAL（Write-Ahead Logging）：
- 写操作不阻塞读操作。
- 单文件数据库 + `-wal` / `-shm` 临时文件。
- `.gitignore` 中排除 `*.db-wal` / `*.db-shm`。

### 11.3 事务粒度

- `store_episode()`：单行 INSERT，自动提交（`isolation_level=None` + 显式 `conn.execute("COMMIT")` 或依赖自动提交）。
- `save_summary()`：`INSERT OR REPLACE`，同上。
- **不在 Python 层做长事务**——每个方法调用即提交。

### 11.4 不支持的场景（明确排除）

- 多进程同时写同一 db 文件 → 行为未定义，不做保证。
- 网络文件系统（NFS/SMB）上的 db → 不支持。
- 异步并发（asyncio + aiosqlite）→ 不在 P2 范围。

---

## 12. 配置

### 12.1 default.toml（保持 in_memory 为 CI 默认）

```toml
[memory_backend]
type = "in_memory"

[memory_backend.config]
```

### 12.2 P2 运行配置

新增 `config/p2_sqlite.example.toml` 示例，或直接在 `default.toml` 中注释示例：

```toml
# P2 SQLite persistent memory (uncomment and set type to "sqlite" to enable)
# [memory_backend]
# type = "sqlite"
#
# [memory_backend.config]
# db_path = "./data/memory.db"
# max_search_episodes = 500
```

### 12.3 工厂分支

`main.py::create_memory_backend()` 新增：

```python
def create_memory_backend(config: dict) -> MemoryBackend:
    backend_type = _backend_type(config, "memory_backend", "type")
    if backend_type == "in_memory":
        return InMemoryMemoryBackend()
    if backend_type == "sqlite":
        from src.memory.sqlite_backend import SQLiteMemoryBackend
        return SQLiteMemoryBackend(_section(config, "memory_backend").get("config", {}))
    raise _config_error("Unsupported memory backend")
```

**铁律**：`src/core/` 仍无对 `sqlite_backend` 或 `sqlite3` 的引用。

---

## 13. 检索模块合并

`InMemoryMemoryBackend` 当前内嵌了分词 + 关键词打分 + 话题检测逻辑。P2 要求：

1. **分词 + 打分 + 话题检测常量** → 抽取到 `src/memory/retrieval.py` 作为模块级函数
2. **差异化留存分级** → 新文件 `src/core/retention.py`（纯策略，无后端依赖，Core 自有）
3. `InMemoryMemoryBackend` 重构为从 `retrieval.py` import（行为不变，消除重复）
4. `SQLiteMemoryBackend` 同样从 `retrieval.py` import
5. 现有 InMemory 测试继续通过——确保重构不破坏行为

**受影响文件**：
- `src/memory/retrieval.py` — 新增/实现（目前占位）：`tokenize`、`keyword_score`、话题检测常量
- `src/core/retention.py` — 新增：`classify_retention`
- `src/memory/in_memory_backend.py` — 重构 import
- `tests/test_in_memory_backend.py` — 继续全绿

---

## 14. 测试要求

### 14.1 单元测试

大部分测试使用 `:memory:` 模式（快速、隔离）。WAL 相关测试使用临时文件数据库并在 teardown 清理 `.db`、`.db-wal`、`.db-shm`。

**`:memory:` 模式测试**（`tests/test_sqlite_backend.py`）：

- store_episode → 返回 chunk_id、内容可 retrieve 出来
- store_episode 空 content → MEMORY_ERROR
- store_episode 缺 metadata.topic → MEMORY_ERROR
- retrieve 空 query → 返回空列表（不报错）
- retrieve top_k < 1 → MEMORY_ERROR
- retrieve 关键词匹配 → 按 `similarity_score` 降序、`id` 升序返回
- retrieve 多 session → 跨 session 检索均可命中
- get_summary 不存在 → None
- save_summary + get_summary → 读写一致
- save_summary 重复调用 → 覆盖旧值
- save_summary 空 scope → MEMORY_ERROR
- close() 后调用 store_episode → MEMORY_ERROR
- close() 后调用 retrieve → MEMORY_ERROR
- close() 幂等——两次 close 不报错
- **检索逻辑与 InMemory 一致**——同一批数据同一 query，两个后端返回相同结果集（顺序、分数）
- **detect_topic_relation 与 InMemory 一致**——所有 4 种分类相同
- **迁移**——mock 旧 schema → 构造 v1 后端 → 自动迁移到最新版本（P2 为 v1，验证初始建表路径）

**临时文件测试**（独立于 `:memory:` 测试）：

- WAL 模式开启 — 使用临时文件 `sqlite3.connect(tmp_path / "test.db")`，执行后验证 `PRAGMA journal_mode` 返回 `"wal"`；teardown 清理 `.db`、`.db-wal`、`.db-shm`

> 说明：SQLite `:memory:` 数据库的 journal_mode 固定为 `"memory"`，`PRAGMA journal_mode=WAL` 为 no-op。WAL 验证必须走磁盘文件。

### 14.2 差异化留存集成测试

`tests/test_context_assembler.py` 扩展——验证 `classify_retention` 的三个分支在 `assemble()` 中实际生效：

- **keep_full**：注入 retrieval 返回 `similarity_score=5.0` 的 chunk → 断言该 chunk 的完整文本出现在 assembler 输出的 `relevant_history` 中
- **keep_summary**：注入 `similarity_score=2.0` 的 chunk（原文 500 字符）→ 断言仅前 200 字符出现在输出中，且 200 字符后的文本不在输出中
- **discard**：注入 `similarity_score=1.0` 的 chunk → 断言该 chunk 的文本完全不在输出中

测试使用 `InMemoryMemoryBackend`（快速、可控），注入预置 episode 和已知分数。不依赖 SQLite。

### 14.3 重构回归

`tests/test_in_memory_backend.py` 全绿——确认抽取 `retrieval.py` 后行为不变。

### 14.4 联调冒烟

`scripts/run_p2.py`：
1. 创建 SQLiteMemoryBackend（`db_path="./data/p2_demo.db"`）
2. 写入 3-5 条对话
3. retrieve 验证命中
4. 关闭、重启后端 → retrieve 仍命中（持久化验证）
5. 清理 demo db

---

## 15. 验收标准（P2 Done 定义）

1. `python scripts/run_p2.py` 端到端：写入 → 重启 → 检索命中，持久化生效。
2. `python -m pytest` 全绿（含 `test_sqlite_backend.py` + 重构后的 InMemory 测试 + 现有 116 个测试）。
3. `ruff check .` 通过。
4. `src/core/**` 无对 `sqlite3` / `src.memory` 下任何模块（`sqlite_backend`、`retrieval`、`project_store`）的 import。Core 内 `context_assembler` 可 import `src.core.retention`（同包合法）。
5. `InMemoryMemoryBackend` 行为不变（重构不改功能）。
6. 生产配置（`config/default.toml` 改为 `type="in_memory"` 时）与 P0a/P1 行为一致。

---

## 16. 实现清单

| 项 | 位置 | 说明 |
|----|------|------|
| `retrieval.py`（实现） | `src/memory/retrieval.py` | `tokenize`、`keyword_score`、话题检测常量（抽取自 InMemory） |
| `retention.py`（新增） | `src/core/retention.py` | `classify_retention` 纯函数，Core 自有 |
| `SQLiteMemoryBackend` | `src/memory/sqlite_backend.py` | 实现 MemoryBackend 全部 6 方法 + close() |
| `InMemoryMemoryBackend`（重构） | `src/memory/in_memory_backend.py` | 从 retrieval.py import，行为不变 |
| `ContextAssembler`（微调） | `src/core/context_assembler.py` | 调用 `retention.classify_retention()` 分级上下文 |
| 工厂分支 | `src/main.py::create_memory_backend` | 新增 `"sqlite"` 分支 |
| SQLite 示例配置 | `config/`（Codex 定文件名） | 演示用；`default.toml` 保持 `in_memory` |
| 演示脚本 | `scripts/run_p2.py` | 持久化端到端验证 |
| `test_sqlite_backend.py` | `tests/test_sqlite_backend.py` | `:memory:` 模式为主 + WAL 用临时文件，覆盖 §14.1 |
| `test_context_assembler.py`（扩展） | `tests/test_context_assembler.py` | 差异化留存集成测试，覆盖 §14.2 三种分级 |

---

## 17. 与后续阶段的接口预留（不在 P2 实现）

| 预留点 | 当前状态 | 后续阶段 |
|------|------|:---:|
| ProjectStore 自动话题统计 | `episodes.project_id` 被动存储，无自动处理 | **P5**：`ProjectStore` + `touch()` 使用 `"project_activity"` 低信任 scope，与人工维护的 `"project"` 隔离 |
| FTS5 全文索引 | `retrieval.py` 做 Python 侧关键词 | P5 可选接入 SQLite FTS5 |
| 向量嵌入列 | episodes 表无 embedding 列 | P5 新增 `embedding BLOB` 列 + 迁移脚本 |
| 语义检索 | 纯关键词 | P5 混排：关键词 + 向量相似度 |
| 真正摘要精炼 | `keep_summary` 截断前 200 字符 | P5+ 接入本地模型生成 TL;DR |
| 多进程并发 | WAL 模式已就绪 | 需要时开启 |
| 连接池 | 单连接 | 需要时引入 |
| EverOS 适配 | — | P8 `EverOSAdapter` 同时实现 MemoryBackend + EvolutionBackend |

---

## 18. 审查修订记录

| 日期 | 级别 | 审查发现 | 处理 |
|------|:---:|------|------|
| 2026-07-19 | 高 | Core 依赖边界自相矛盾：§8 让 ContextAssembler 调 `retrieval.classify_retention()`，§9 注入 `ProjectStore`，§15 又禁止 `src/core/**` 导入这些模块 | 采纳：`classify_retention` 移至新文件 `src/core/retention.py`（纯策略，Core 自有）；`ProjectStore` 不注入 Core，`ContextAssembler` 继续通过 `memory.get_summary()` 获取项目摘要；§9 移除 ContextAssembler 签名变更 |
| 2026-07-19 | 高 | `:memory:` 模式下验证 WAL 不可实现——SQLite 内存数据库不支持 WAL | 采纳：§14.1 拆分为 `:memory:` 测试（主体）+ 临时文件测试（WAL 验证），teardown 清理 `.db-wal`/`.db-shm` |
| 2026-07-19 | 中 | 检索同分结果没有确定排序规则，不同运行中可能不稳定 | 采纳：§4.1 排序明确为 `similarity_score DESC, id ASC`，与 InMemory 的 `(-score, id)` 双键一致 |
| 2026-07-19 | 高 | ProjectStore.touch() 调用责任矛盾：§5.3 说 Backend 调用、§9.2 说 App 调用、Backend 没有 ProjectStore 实例 | 采纳：删除 §5.3；§9.3 明确 `App._record_turn()` 为唯一触发点并给出完整调用链；`project_id` 经 `handle()` → `_record_turn()` → `metadata` + `touch()`；需同步 `00-adapter-factory.md` App 签名 |
| 2026-07-19 | 中 | `check_same_thread=False` 安全声明不成立——WAL 只协调文件级读写，不保护连接对象内部状态 | 采纳：§2.2 改回默认 `True`，删除 "GIL + WAL 保护" 注释，新增说明段落解释为什么不用 False；§11.1 删除残留引用 |
| 2026-07-19 | 高 | P2 自动写入 ProjectStore 与 project-plan 的 ProjectState "人工维护" 信任模型冲突；项目摘要本应是 P5 目标 | 采纳：§9 整节替换为延后声明；ProjectStore 整体延后到 P5；P2 仅保留 `episodes.project_id` 被动存储；`ContextAssembler` 仅读取人工预先 `save_summary` 写入的项目摘要；P5 使用独立 `"project_activity"` scope 隔离自动统计 |
| 2026-07-19 | 中 | 差异化留存缺少验收测试——规范要求三种分级但无覆盖 | 采纳：新增 §14.2，`test_context_assembler.py` 扩展三个断言：`keep_full` 原文完整出现、`keep_summary` 仅前 200 字符、`discard` 完全不在输出中 |
| 2026-07-19 | 中 | 00-adapter-factory.md App 签名尚未包含 project_store 字段 | 因 ProjectStore 延后到 P5 而自然消除——P2 不再修改 App 构造函数签名 |
| 2026-07-19 | 高 | `low_threshold=1.0` 使 discard 不可达——检索只返回 score>0 的 chunk，而关键词分是整数，discard 所需 score<1 永不出现 | 采纳：`low_threshold` 改为 `2.0`，三档变为 score≥3 原文、score=2 摘要、score=1 丢弃；§8.3 增加行为对齐说明；§14.2 discard 测试 score 改为 1.0 |
| 2026-07-19 | — | 代码审查通过（Claude） | 141/141 测试全绿，ruff 干净，Core 依赖边界干净，所有 §1–§17 要求满足。详见 `specs/reviews/03-p2-sqlite-memory-review.md` |
