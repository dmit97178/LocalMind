# 00-project-scaffold — 工程初始化规范

> 状态：✅ 待实现
> 性质：编码第一步。定义项目工程基础设施，必须在任何 src/ 代码编写前完成。
> 目标：P0a  Mock 核心闭环可运行、可测试、可检查代码质量。

---

## 1. Git 初始化

```bash
git init
```

- 分支：`main`（不设 master）
- 初始化后立即做首次 commit："项目初始化——工程脚手架"
- 后续每个 P0a 模块完成后单独 commit

---

## 2. 目录结构

以下目录必须**一次性创建**（含 `__init__.py`）：

```
localmind/                          # 项目根目录
├── .gitignore
├── .env.example
├── pyproject.toml
├── CLAUDE.md                       # 已存在，不动
├── README.md                       # 新建，写项目名 + 一句话定位
├── specs/                          # 已存在，不动
├── config/
│   └── default.toml                # P0a 默认配置（tomllib 加载，零依赖）
├── src/
│   ├── __init__.py
│   ├── main.py                     # 入口，P0a 最后实现
│   ├── core/
│   │   ├── __init__.py
│   │   ├── interfaces.py           # 6 个抽象接口
│   │   ├── schemas.py              # 所有数据结构
│   │   ├── input_normalizer.py
│   │   ├── intent_resolver.py
│   │   ├── context_assembler.py
│   │   ├── control_policy.py
│   │   ├── task_planner.py
│   │   ├── response_builder.py
│   │   └── reflection_recorder.py
│   ├── safety/
│   │   ├── __init__.py
│   │   ├── policy.py               # SafetyPolicy（依赖 SafetyBackend 接口）
│   │   ├── guarded_executor.py     # GuardedToolExecutor
│   │   ├── cloud_boundary.py
│   │   ├── identity.py
│   │   └── rule_only_backend.py    # RuleOnlySafetyBackend
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── in_memory_backend.py    # InMemoryMemoryBackend（P0 默认）
│   │   ├── sqlite_backend.py       # SQLiteMemoryBackend（P2）
│   │   ├── project_store.py
│   │   └── retrieval.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── mock_backend.py         # MockModelBackend（P0 默认）
│   │   └── ollama_backend.py       # OllamaModelBackend（P1）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                 # ToolDef, ToolBackend 接口重导出
│   │   ├── registry.py             # 工具注册表 + 白名单
│   │   ├── builtin_backend.py      # BuiltinToolBackend（P0 默认）
│   │   ├── composite_backend.py    # P7b 内置/外部工具聚合后端
│   │   ├── provider_declarations.py # P7b provider argv、准入与能力声明
│   │   ├── file_tools.py
│   │   ├── system_tools.py
│   │   └── cloud_advisory.py
│   ├── evolution/
│   │   ├── __init__.py
│   │   ├── noop_backend.py         # NoopEvolutionBackend（P0 默认）
│   │   └── skill_lifecycle.py
│   ├── observability/              # P6a 运行事件 sink
│   │   ├── __init__.py
│   │   └── sinks.py
│   ├── cli/                        # P6a 交互式终端入口
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── commands.py
│   │   ├── loop.py
│   │   └── sink.py
│   └── adapters/
│       ├── __init__.py
│       ├── qwenpaw_adapter.py      # P7 后续；P7b 仅提供标准接入点
│       ├── everos_adapter.py       # P8
│       └── mcp_adapter.py          # P7b MCP stdio provider
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # 共享 fixtures
│   ├── test_schemas.py
│   ├── test_interfaces.py
│   ├── test_intent_resolver.py
│   ├── test_control_policy.py
│   ├── test_safety_policy.py
│   ├── test_guarded_executor.py
│   └── test_context_assembler.py
├── data/                           # 运行时数据目录（gitignore）
└── scripts/                        # 开发用脚本
    ├── run_p0a.py                  # P0a 演示脚本
    └── mcp_demo_server.py          # P7b stdlib-only MCP 演示/故障替身
```

**约束**：
- 每个目录必须有 `__init__.py`（空文件即可）
- 目录一次性创建完成后再开始写代码
- `data/` 目录加入 .gitignore，但保留目录占位（放一个 `.gitkeep`）

---

## 3. pyproject.toml

```toml
[project]
name = "localmind"
version = "0.1.0"
description = "本地优先的个人办公智能体"
requires-python = ">=3.11"
readme = "README.md"
license = { text = "MIT" }

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.9",
    "mypy>=1.14",
]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501", # line too long — handled by formatter
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false

[tool.ruff.lint.isort]
known-first-party = ["src"]

[tool.mypy]
python_version = "3.11"
strict = false
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
exclude = ["tests/"]

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "-v --tb=short"
```

**说明**：
- P0a 核心依赖为零——`project.dependencies` 故意留空。核心闭环不需要任何第三方库。
- `PyYAML` 用于 config 加载，属于标准工程实践，在 Core 的 main.py 中使用（不属于 Core 模块依赖）。如果 ruff 报 `import yaml` 未找到，在 P0a 阶段配置可以先用 Python 原生 dict 硬编码，P1 再加 pyyaml。
- mypy 标记为 `optional`——P0a 不强制通过 mypy，但提供配置供开发者自查。
- ruff 的 `I` 规则（isort）自动排序 import。

---

## 4. .gitignore

```gitignore
# Python
__pycache__/
*.py[cod]
*.so
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
.env

# IDE
.vscode/
.idea/
*.swp
*.swo

# Project data
data/*
!data/.gitkeep

# Environment
.env
.env.local

# OS
.DS_Store
Thumbs.db
```

---

## 5. .env.example

```bash
# LocalMind 环境变量配置
# 复制此文件为 .env 后修改

# 模型后端：mock | ollama | turbo_llm
LOCALMIND_MODEL_BACKEND=mock

# Ollama 配置（model_backend=ollama 时生效）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b-q4_K_M

# 记忆后端：in_memory | sqlite | everos
LOCALMIND_MEMORY_BACKEND=in_memory

# 安全后端：rule_only | qwenpaw
LOCALMIND_SAFETY_BACKEND=rule_only

# 配置文件路径（覆盖默认 config/default.toml）
LOCALMIND_CONFIG_PATH=config/default.toml
```

---

## 6. config/default.toml（P0a 默认配置，tomllib 零依赖加载）

```toml
# LocalMind P0a 默认配置
# 目标：零外部依赖，Mock 核心闭环
# 格式：TOML（Python 3.11+ stdlib tomllib）

[model_backend]
type = "mock"                         # P0a: mock, P1: ollama

[model_backend.config]
model = "mock-model"

[memory_backend]
type = "in_memory"                    # P0a: in_memory, P2: sqlite

[memory_backend.config]
# in_memory 模式无需持久化路径

[tool_backend]
type = "builtin_only"                 # P0a: builtin_only, P6: qwenpaw

[tool_backend.config]
whitelist = [
    "system.echo",
    "system.get_time",
    "file.read",
    "file.list_dir",
]

[safety]
backend = "rule_only"                 # P0a: rule_only, P3: qwenpaw
l2_enabled = false                    # P3 启用，P0a 关闭

[safety.l1_rules]
forbidden_commands = [
    "rm -rf /",
    "dd if=",
    "mkfs.",
    ":(){ :|:& };:",                 # fork bomb
]
forbidden_paths = [
    "/etc/passwd",
    "/etc/shadow",
    "C:\\Windows\\System32",
    "~/.ssh",
]
sensitive_patterns = [
    "\\b(password|passwd|secret|token|api_key)\\s*=\\s*\\S+",
]

[safety.passphrase]
hash_file = "./data/.passphrase"
lockout_attempts = 5
lockout_minutes = 10

[cloud_advisory]
enabled = false                       # P4 启用
backend = "noop"

[evolution]
enabled = false                       # P8 启用
backend = "noop"

[execution]
intent_max_rounds = 4
expert_scheduler_enabled = false      # P7 启用
```

---

## 7. 测试规范

### 框架
- **pytest** 8.0+
- 不使用 `unittest` 模块
- 不使用 pytest-asyncio（P0a 全部同步代码）

### 命名
- 测试文件：`test_<模块名>.py`
- 测试函数：`test_<场景描述>`
- 测试类：`Test<被测类名>`（仅在需要共享 setup 时使用）

### conftest.py 最小内容

```python
# tests/conftest.py
import pytest
from src.core.interfaces import (
    ModelBackend, MemoryBackend, ToolBackend,
    SafetyBackend, CloudAdvisoryBackend, EvolutionBackend,
)
from src.models.mock_backend import MockModelBackend
from src.memory.in_memory_backend import InMemoryMemoryBackend
from src.tools.builtin_backend import BuiltinToolBackend
from src.safety.rule_only_backend import RuleOnlySafetyBackend
from src.evolution.noop_backend import NoopEvolutionBackend


@pytest.fixture
def mock_model() -> ModelBackend:
    return MockModelBackend()


@pytest.fixture
def in_memory_memory() -> MemoryBackend:
    return InMemoryMemoryBackend()


@pytest.fixture
def builtin_tools() -> ToolBackend:
    return BuiltinToolBackend()


@pytest.fixture
def rule_only_safety() -> SafetyBackend:
    return RuleOnlySafetyBackend()


@pytest.fixture
def noop_evolution() -> EvolutionBackend:
    return NoopEvolutionBackend()
```

### 测试要求
- **每个 Core 模块必须有对应的 test 文件**
- P0a 验收标准：`pytest` 全部通过，且测试覆盖核心闭环的每个步骤
- 不需要测 Adapter（P0a 还没有真实 Adapter）
- 不需要覆盖率报告，但关键路径必须有一条 happy-path 测试

---

## 8. 代码规范

### ruff
- **强制**：非空实现代码提交前 `ruff check` 零错误
- **格式化**：`ruff format` 统一风格
- 行宽 100，双引号

### mypy（可选，推荐自查）
- P0a 不强制 mypy 零错误
- 接口文件 (`interfaces.py`) 和 schemas (`schemas.py`) 建议通过 mypy
- 规则：`strict=false`，`ignore_missing_imports=true`

### 命名
| 对象 | 风格 | 示例 |
|------|------|------|
| 模块/文件 | snake_case | `intent_resolver.py` |
| 类（含 ABC/Protocol/dataclass） | PascalCase | `IntentResolver` |
| 函数/方法 | snake_case | `resolve_intent()` |
| 私有方法 | _leading_underscore | `_transition_state()` |
| 常量 | UPPER_SNAKE | `MAX_ROUNDS = 4` |
| 变量 | snake_case | `intent_candidate` |

### import 风格
- 标准库 → 第三方 → 本地（ruff isort 自动处理）
- **绝对禁止** Core 模块 import 具体后端：`src/core/` 下任何文件不得出现 `from src.models.ollama_backend import ...`
- Core 只 import：`src.core.interfaces`、`src.core.schemas`、标准库

---

## 9. P0a 默认后端组合

| 接口 | P0a 实现 | 来源文件 | 说明 |
|------|---------|---------|------|
| ModelBackend | `MockModelBackend` | `src/models/mock_backend.py` | 返回预设 JSON，不调 Ollama |
| MemoryBackend | `InMemoryMemoryBackend` | `src/memory/in_memory_backend.py` | 内存 dict 存储，重启丢失 |
| ToolBackend | `BuiltinToolBackend` | `src/tools/builtin_backend.py` | 白名单本地工具：echo、get_time、read、list_dir、stat、write |
| SafetyBackend | `RuleOnlySafetyBackend` | `src/safety/rule_only_backend.py` | 只用 L1 硬规则，无 LLM |
| CloudAdvisoryBackend | `NoopCloudAdvisoryBackend` | `src/tools/cloud_advisory.py` | advise() 返回 "云端未启用" |
| EvolutionBackend | `NoopEvolutionBackend` | `src/evolution/noop_backend.py` | reflect() 返回空列表 |

---

## 10. 初始化步骤（按顺序执行）

```
Step 1  创建目录结构（src/ 下全部目录 + tests/ + config/ + data/ + scripts/）
Step 2  写入 pyproject.toml
Step 3  写入 .gitignore + .env.example
Step 4  写入 config/default.toml（使用 tomllib，零依赖）
Step 5  创建所有 __init__.py（空文件）
Step 6  写入 tests/conftest.py（此时因缺少实现模块会 import 失败，预期行为）
Step 7  写入 data/.gitkeep
Step 8  写入 README.md（一句话即可）
Step 9  git init → git add -A → git commit -m "项目初始化——工程脚手架"
Step 10 运行 ruff check（脚手架阶段仅验证工具链可执行；空壳通过不代表代码质量）
```

**验收标准**：
- [ ] `python -c "import src"` 不报错
- [ ] `ruff check` 可执行；如已有非空实现代码则零错误
- [ ] `git log` 有且仅有一个 commit
- [ ] 目录结构与本文档第 2 节完全一致

---

## 变更记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-07-06 | 初始版本 | Codex 建议 → Claude 编写 |
