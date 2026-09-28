# 02-p1-ollama-backend — OllamaModelBackend 模块契约

> 状态：✔️ 完成
> 阶段：P1（接入 Ollama，实现真实本地模型对话）
> 性质：编码前必读。本契约定义 `OllamaModelBackend` 的行为边界。
> 前序依赖：`00-core-interfaces.md`（ModelBackend 签名，**不得改动**）、`00-error-contract.md`（错误码）、`00-adapter-factory.md`（工厂与配置注入）。

---

## 0. 范围与不变量

**目标**：用真实本地 Ollama 替换 MockModelBackend，跑通"用户输入 → 真实模型理解 → 决策 → 工具执行 → 中文回复"的完整闭环。

**接口不变**：`OllamaModelBackend` 实现 `core/interfaces.py::ModelBackend` 的现有 6 个方法，签名一字不改。P1 不新增、不修改任何 Core 接口签名——只做 Adapter 实现。

**铁律（沿用 project-plan §3.1 / NFR4）**：
1. `src/core/**` 绝不 `import ollama`、不 import `src.models.ollama_backend`；只有 `src/main.py` 的工厂 `create_model_backend()` 可 import 本类。
2. 所有第三方/传输层异常（连接失败、超时、HTTP 错误、JSON 解析失败）**必须**在本类内捕获并转换为 `ModelError`（`00-error-contract.md §3`）。Core 永远看不到 `ConnectionError` / `TimeoutError` / `ollama.ResponseError` 这类原始异常。
3. 返回值只含纯 Python 类型（`dict` / `str`）——不得把 Ollama 的响应对象、迭代器等泄漏给 Core。

**位置**：`src/models/ollama_backend.py`（当前为占位文件，仅一行 docstring）。

---

## 1. 连接方式

Ollama 通过本机 HTTP REST 服务暴露能力，默认 `http://localhost:11434`。本类用到的端点：

| 用途 | 方法 + 路径 | 说明 |
|------|-------------|------|
| 文本 / 结构化生成 | `POST /api/generate` | body `{model, prompt, stream, format?, keep_alive?, options?}` |
| 流式生成 | `POST /api/generate`（`stream=true`） | 响应为 NDJSON，每行一个 `{"response": "...", "done": bool}` |
| 健康探测 / 模型清单 | `GET /api/tags` | 返回本地已拉取模型列表 |
| 预热 / 卸载 | `POST /api/generate`（空 prompt + `keep_alive`） | 把模型页入/逐出内存 |

**传输实现（Codex 工程决策，Claude 审查）**：可用官方 `ollama` Python 客户端，或 stdlib `urllib.request`（零新增依赖，推荐优先评估），或 `httpx`。约束：
- 若引入新运行时依赖，须在 `pyproject.toml` 的 `[project.dependencies]` 声明，并在对话中同步给 Claude 审查。
- **所有 HTTP 调用必须收敛到一个可注入的传输接缝**（见 §6 测试替身），使单元测试无需真实 Ollama。

**建议的内部接缝形状**（非强制，Codex 可等价替换）：

```python
class OllamaTransport(Protocol):
    def get_json(self, path: str) -> dict: ...
    def post_json(self, path: str, payload: dict) -> dict: ...            # stream=false
    def post_ndjson(self, path: str, payload: dict) -> Iterator[dict]: ... # stream=true，逐行 yield 已解析的 dict

class OllamaModelBackend(ModelBackend):
    def __init__(self, config: dict, transport: OllamaTransport | None = None) -> None: ...
    # transport=None 时用默认实现（连真实 base_url）；测试注入 fake
```

---

## 2. 模型配置

工厂按 `00-adapter-factory.md §1` 传入 `config["model_backend"]["config"]`：

```python
# create_model_backend() 新增分支
elif backend_type == "ollama":
    from src.models.ollama_backend import OllamaModelBackend
    return OllamaModelBackend(config["model_backend"]["config"])
```

`[model_backend.config]` 读取的键：

| 键 | 必填 | 默认 | 含义 |
|----|:---:|------|------|
| `model` | ✅ | — | Ollama 模型名，如 `qwen3:4b-q4_K_M` |
| `base_url` | — | `http://localhost:11434` | Ollama 服务地址；**仅允许 loopback 主机**（见 §2.1） |
| `keep_alive` | — | `30m` | 模型驻留内存时长 |
| `request_timeout_seconds` | — | `120` | 单次请求读超时（对齐 NFR2 最低可接受档） |
| `num_ctx` | — | 模型默认 | 上下文窗口；填入 `options.num_ctx`，并作为 `get_capabilities().max_context_tokens` |
| `options` | — | `{}` | 透传给 Ollama 的 `options`（temperature、top_p 等） |

- **`config/default.toml` 保持 `type = "mock"`**（离线 CI/pytest 不依赖真实 Ollama）。P1 另提供切换到 Ollama 的示例配置（`config/ollama.example.toml` 或在 `default.toml` 加注释示例，文件布局由 Codex 定）+ `scripts/run_p1.py` 演示脚本。

### 2.1 构造期配置校验（全部字段，非法一律 CONFIG_ERROR）

**架构立场（High 级审查采纳）**：`OllamaModelBackend` 声明 `local_only=True`，因此 P1 **只允许连接本机 loopback 的 Ollama**。远端地址会在"本地模型"名义下把上下文外发，绕过 `CloudBoundary`，违反本地优先与云端受控边界（requirements FR1 / project-plan §1.4）。远端推理若将来确有需要，必须作为**独立的、经 CloudBoundary 管控的**后端另立契约，不得借本类混入。

构造函数 `__init__(config, transport=None)` 必须在**返回前**逐字段校验，任一不满足即抛
`LocalMindError(code="CONFIG_ERROR", recoverable=False, user_message="系统配置有误，请检查 model_backend.config。", details={...})`，
**绝不**让非法配置在后续请求时以 `TypeError` / `ValueError` 等原始异常泄漏：

| 字段 | 校验规则 |
|------|---------|
| `model` | 非空字符串 |
| `base_url` | 合法 http/https URL，且**主机为 loopback**：`localhost` / `127.0.0.0/8` 内的 IPv4 / `::1`。非 loopback → CONFIG_ERROR（`user_message` 提示"当前仅支持本机 Ollama"） |
| `keep_alive` | 字符串（Ollama 时长格式，如 `30m`）或 ≥0 的数值 |
| `request_timeout_seconds` | 数值且 > 0 |
| `num_ctx` | 缺省或正整数 |
| `options` | 缺省或 `dict` |

- `local_only=True` 仅在上述 loopback 约束成立时才被声明——两者绑定，不再出现"本地名义、远端实连"的空档。

---

## 3. generate() 行为

```python
def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
```

沿用 `00-core-interfaces.md §1` 语义，非流式请求（`stream=false`）：

**A. 不带 schema（`response_schema is None`）**
- 请求 `POST /api/generate`，`format` 不传。
- 返回 `{"text": <完整 response 字符串>}`。

**推理包裹剥离（P6a 期补记，A/B 两路径共用）**：`response` 文本先经 `_strip_thinking()` 处理——剥离 `<think>…</think>` 整块、孤立 `</think>` 前的残留、以及无闭合的 `<think>` 起始段——再做 JSON 解析（B）或作为可见文本返回（A）。真实 Qwen 系模型的输出常带推理包裹，会把结构化解析与 CLI 可读回复一起打坏；剥离只按标签结构处理，不改其余文本（`tests/test_ollama_backend.py` 两个用例钉死）。

**B. 带 schema（结构化输出，IntentResolver 每轮都依赖此路径）**
- Ollama 的 `response` 字段是一段 **JSON 字符串**，需 `json.loads(response["response"])` 解析为 dict 后返回。
- **返回解析后的 dict 本身**（不是 `{"text": ...}`）——`intent_resolver._candidate_from_model_output()` 直接消费该 dict。
- 解析失败、`response` 字段缺失/非字符串、或解析结果非 dict → `ModelError(code="MODEL_PARSE_ERROR", recoverable=True, user_message="模型返回格式异常，正在重试。")`。

**结构化机制：确定性写死（Med 级审查采纳，不留版本悬念）**

核心闭环强依赖结构化输出，其能否跑通**不得**取决于未声明的本机 Ollama 版本。因此 P1 规定：

1. **必须实现 `format="json"` 基线回退**：请求携带 `format="json"`，并在 prompt 内嵌"仅输出符合以下 JSON Schema 的对象"及该 schema。`format="json"` 是 Ollama 长期支持的 JSON 模式，保证在任意现代版本上都能拿到**合法 JSON**。schema 一致性由 `_candidate_from_model_output()` 的防御式解析兜底（缺字段填默认、非法 state 归 VAGUE），故基线足以让 P1 跑通。
2. **可选增强 `format=<schema>`**：`load()` 时探测 `GET /api/version`，≥0.5.0 则优先用 `format = response_schema`（Ollama 结构化输出，schema 强约束）；探测/使用失败时**自动落回**基线 (1)。
3. 无论走 (1) 还是 (2)，`generate(schema)` 返回契约一致：解析后的 dict，或 `MODEL_PARSE_ERROR`。生效模式同时决定 `get_capabilities().supports_structured_output`（见 §6）：走 (2) 为 `True`，走 (1) 基线为 `False`。

> 即"基线保底、增强可选"：P1 是否能跑通只依赖基线 (1)，与本机版本无关；(2) 仅在支持时提升 schema 约束强度。

---

## 4. stream() 行为

```python
def stream(self, prompt: str) -> Iterator[str]:
```

- 请求 `POST /api/generate`，`stream=true`，`format` 不传（流式仅用于 CLI 文本实时输出，不用于结构化）。
- 逐行读取 NDJSON。对每条记录：取 `record.get("response", "")`，非空则 `yield`；`done` 缺失视为 `False`，`done` 为布尔 `True` 时结束（`done` 存在但非布尔的处理见下）。
- 生成器惰性执行：首个 `next()` 之前不发请求；调用方提前关闭生成器不应报错。
- 传输错误在迭代过程中转换为 `ModelError` 抛出（见 §5）。

**畸形 NDJSON 的错误契约（Med 级审查采纳）**——逐行解析必须防御，下列一律转 `ModelError(code="MODEL_PARSE_ERROR", recoverable=True, user_message="模型返回格式异常，正在重试。")`，**不得**冒出 `JSONDecodeError` / `KeyError`：
- 某行无法 `json.loads`（畸形 JSON）；
- 解析结果不是 JSON 对象（dict）；
- 存在 `response` 但其值非字符串；
- 存在 `done` 但其值**非布尔**（如 `"true"` / `1`）——不得静默当作未结束（Minor 级审查采纳）。

**容忍项（不算错误，避免误伤正常流）**：
- `response` 字段缺失 → 视为空串（跳过，不 yield）；
- `done` 字段**缺失** → 视为 `False`（注意：仅"缺失"容忍；"存在但非布尔"按上面畸形处理）；
- 末条"仅统计"记录（`{"done": true, ...}` 无文本 `response`）是 Ollama 正常收尾，**必须正常终止而非报错**。

---

## 5. 错误与降级行为

**错误映射（传输/HTTP → ModelError，全部在本类内完成）：**

| 情形 | code | recoverable | user_message |
|------|------|:---:|------|
| 连接被拒 / 服务不可达 / socket 错误 | `MODEL_UNAVAILABLE` | `True` | "本地模型尚未就绪，请稍候。" |
| 读超时 | `MODEL_TIMEOUT` | `True` | "模型响应超时，请稍后重试。" |
| 非 2xx 或 Ollama 错误体（含运行期"模型不存在"） | `MODEL_UNAVAILABLE` | `False` | "本地模型不可用，请检查 Ollama 与模型是否就绪。" |
| 结构化输出 JSON 解析失败 | `MODEL_PARSE_ERROR` | `True` | "模型返回格式异常，正在重试。" |
| 构造期配置非法（缺 model 等） | `CONFIG_ERROR` | `False` | "系统配置有误，请检查 model_backend.config。" |

- `message`（技术描述）与 `details`（如 `{"base_url", "model", "status"}`）供日志；**绝不**把 `Connection refused`、stack trace 等泄漏进 `user_message`（`00-error-contract.md §5`）。
- **可选**内部有界重试：对 `MODEL_TIMEOUT` / 连接类错误可重试 1 次（配置 `max_retries`，默认 `0`），仍失败则按上表抛出。是否实现由 Codex 定；不实现也符合契约。

**降级（P1 无云端、无备用模型）**：
- 本类只负责"正确抛 `ModelError`"。上层 `App.handle()` 已用 try/except 兜底，把 `LocalMindError.user_message` 返回给用户、不抛 traceback（`01-p0a-main-loop.md §9`）。
- `IntentResolver.resolve()` 逐轮调用 `generate()`；某轮抛 `ModelError` 会中断认知循环并冒泡到 `App.handle()` → 返回 `user_message`。P1 不要求 resolver 内部吞错重试。

---

## 6. 生命周期：load / unload / health_check

| 方法 | 契约 |
|------|------|
| `load()` | **幂等**。首次调用做一次预热（`POST /api/generate` 空/极短 prompt + `keep_alive`），把模型页入内存、提前暴露"服务不可达 / 模型未拉取"。服务不可达或模型缺失 → 抛 `ModelError(MODEL_UNAVAILABLE)`（服务不可达 `recoverable=True`；模型缺失 `recoverable=False`，提示用户先 `ollama pull`）。已成功 load 后再次调用为 no-op。|
| `unload()` | **幂等**、**绝不抛异常**。尽力发 `keep_alive=0` 请求逐出模型；任何失败静默吞掉。未 load 时直接返回。|
| `health_check()` | **绝不抛异常**。`GET /api/tags`，可达且配置的 `model` 在清单中返回 `True`；任何异常/不满足返回 `False`。|
| `get_capabilities()` | **要求已加载**（见 §6.1）。返回 `ModelCapabilities(supports_structured_output=<见下>, max_context_tokens=<num_ctx 或默认 4096>, local_only=True)`。`local_only=True` 由 §2.1 的 loopback 约束保证成立。|

**`supports_structured_output` 必须如实反映生效模式（Med 级审查采纳）**：该字段在 `00-core-interfaces.md` 中语义为"支持 **JSON Schema 约束**"，而 `format="json"` 基线只保证合法 JSON、不保证 schema 一致。因此：
- `load()` 探测确认走 `format=<schema>`（增强模式）→ `supports_structured_output=True`；
- 走 `format="json"` 基线回退 → `supports_structured_output=False`。

P1 的 `IntentResolver` 不受影响——无论该字段真假，`generate(schema)` 都由后端兼容处理并返回 dict；此字段仅供 P2+（如 ContextAssembler 决策是否走强约束路径）参考，避免被误导。

### 6.1 已加载状态门禁（Med 级审查采纳）

本类以 `_loaded` 布尔显式跟踪加载状态（与 `MockModelBackend._ensure_loaded` 一致），并作为唯一权威：

- **仅 `load()` 置 `_loaded=True`；仅 `unload()` 置 `_loaded=False`。**
- `generate()`、`stream()`、`get_capabilities()` 在 `_loaded is False` 时**直接抛** `ModelError(code="MODEL_UNAVAILABLE", recoverable=True, user_message="本地模型尚未就绪，请稍候。")`，**不得**向 Ollama 发请求触发其服务端隐式自动重载。
- 理由：P7 多专家阶段依赖 `unload()` 真正释放内存做资源调度；若 `generate()` 能在已 unload 后隐式重载，调度记账将失效。把"是否可推理"的权威留在本类，而非 Ollama 的 keep_alive 行为。

**bootstrap 交互（已由 `00-adapter-factory.md §3` 固定，本类需与之吻合）**：
`create_model_backend()` → `model_backend.load()` → `if not health_check(): raise MODEL_UNAVAILABLE`。因此 `load()` 负责硬失败（配置/模型缺失）早抛，`health_check()` 负责可达性布尔探测。

---

## 7. 测试替身（离线可测）

**硬约束**：单元测试**不得**依赖真实 Ollama 进程；默认 `pytest` 全绿必须在无 Ollama 环境成立。实现方式 = §1 的可注入传输接缝：测试注入 fake `OllamaTransport`，喂预置响应。

**必须覆盖的单元测试**（fake transport）：
- generate 无 schema → 返回 `{"text": ...}`。
- generate 带 schema → 返回 `json.loads` 后的 dict（非 `{"text":...}`）。
- 结构化响应非法 JSON → `MODEL_PARSE_ERROR`。
- stream → 按 NDJSON 顺序 yield 增量、`done` 处停止。
- 连接错误 → `MODEL_UNAVAILABLE`；读超时 → `MODEL_TIMEOUT`。
- health_check：模型在 tags → `True`；传输抛错 → `False`（不冒泡）。
- load 幂等；模型缺失 → `MODEL_UNAVAILABLE(recoverable=False)`。
- unload 幂等且吞错（传输抛错时不抛）。
- get_capabilities：字段正确、须先 load。
- 构造期缺 `model` → `CONFIG_ERROR`。
- **配置校验（§2.1）**：非 loopback 的 `base_url`（如 `http://10.0.0.5:11434`）→ `CONFIG_ERROR`；`request_timeout_seconds` 为字符串、`num_ctx` 非正整数、`options` 非 dict、`keep_alive` 非法 → 均 `CONFIG_ERROR`（不冒 `TypeError`）。
- **已加载门禁（§6.1）**：未 load 即调用、以及 `unload()` 之后再调用 `generate`/`stream`/`get_capabilities` → `MODEL_UNAVAILABLE(recoverable=True)`，且**不触发任何传输请求**（fake transport 记录零调用）。
- **结构化基线（§3）**：`format="json"` 回退路径喂合法 JSON → 返回解析后的 dict；喂合法 JSON 但缺字段 → resolver 防御式解析不崩（可在 resolver 层或本层验证返回 dict）。
- **能力反映模式（§6）**：探测版本 ≥0.5.0（走 `format=<schema>`）→ `get_capabilities().supports_structured_output is True`；探测为旧版本/回退基线 → `is False`。
- **畸形流（§4）**：某行畸形 JSON / 非对象记录 / `response` 非字符串 / `done` 非布尔（`"true"`、`1`）→ `MODEL_PARSE_ERROR`；`done` 缺失按未结束容忍；末条"仅 `done:true`"记录 → 正常终止不报错。

**可选联调冒烟**：`@pytest.mark.integration`，仅当环境变量 `LOCALMIND_OLLAMA_LIVE=1` 时运行，默认套件跳过；连真实 Ollama 验证一次 generate + stream。

---

## 8. 验收标准（P1 Done 定义）

1. Ollama 运行且模型已拉取时，`python scripts/run_p1.py` 驱动 `App.handle()` 走**真实** `generate()`，返回可读中文回复（端到端闭环打通）。
2. 默认离线 `python -m pytest` 全绿（OllamaModelBackend 走 fake transport；`config/default.toml` 仍为 mock）。
3. `ruff check .` 通过；`OllamaModelBackend` 通过 mypy（若纳入检查范围）。
4. `src/core/**` 无对 ollama / 本后端的 import（可用 grep 校验铁律 §0.1）。

**性能观测（NFR2，记录即可，不作硬门槛）**：冷启动预热 5–15s（最低 30s）；热推理 ≥10 tok/s（最低 5 tok/s）。

---

## 9. 实现清单

| 项 | 位置 | 说明 |
|----|------|------|
| `OllamaModelBackend` | `src/models/ollama_backend.py` | 实现 ModelBackend + 传输接缝 |
| 默认传输实现 | 同上或 `src/adapters/`（Codex 定） | stdlib/官方客户端；异常包装 |
| 工厂分支 | `src/main.py::create_model_backend` | 新增 `elif "ollama"`，不改 Core |
| Ollama 示例配置 | `config/`（Codex 定文件名） | 演示用；`default.toml` 保持 mock |
| 演示脚本 | `scripts/run_p1.py` | 连真实 Ollama 的端到端 demo |
| 单元测试 | `tests/test_ollama_backend.py` | fake transport，覆盖 §7 |
| 依赖声明（如需） | `pyproject.toml` | 新增运行时依赖须同步 Claude 审查 |

---

## 10. 与后续阶段的接口预留（不在 P1 实现）

- `supports_structured_output` 已由 Capabilities 暴露，P2+ ContextAssembler 可据此决定是否走 schema 约束路径。
- `max_context_tokens` 供后续上下文预算裁剪使用；P1 只需如实上报。
- 多专家（P7）会新增其他 ModelBackend 实现并按需加载/卸载——本类的 `load()`/`unload()` 幂等语义为其打基础，P1 不实现调度。

---

## 11. 审查修订记录

| 日期 | 级别 | 审查发现（Codex） | 处理 |
|------|:---:|------|------|
| 2026-07-13 | 高 | `base_url` 可指任意远端，却无条件 `local_only=True` | 采纳：§2.1 限 loopback，非 loopback → CONFIG_ERROR；`local_only=True` 与该约束绑定；远端推理须另立经 CloudBoundary 管控的后端 |
| 2026-07-13 | 中 | 未规定未 load/已 unload 后 generate/stream 行为 | 采纳：§6.1 三方法均要求已加载，否则 `MODEL_UNAVAILABLE(recoverable=True)` 且不发请求；仅 load/unload 改状态 |
| 2026-07-13 | 中 | 结构化回退"可选"，但核心强依赖 | 采纳：§3 写死——`format="json"` 基线**必须**实现，`format=<schema>` 为可选增强；P1 可跑通不依赖本机版本 |
| 2026-07-13 | 中 | 仅校验 `model`，其余配置可能泄漏原始异常 | 采纳：§2.1 构造期校验全部字段，非法一律 CONFIG_ERROR |
| 2026-07-13 | 中 | 流式畸形 NDJSON 无错误契约 | 采纳：§4 畸形/非对象/`response` 非串 → `MODEL_PARSE_ERROR`；末条仅 `done` 记录容忍终止；§7 加测 |
| 2026-07-13 | 中 | 能力声明 `supports_structured_output=True` 与 JSON 回退语义矛盾 | 采纳：§6 该字段如实反映生效模式——`format=<schema>` 为 True，`format="json"` 基线为 False；§3 挂钩、§7 加测。IntentResolver 不受影响 |
| 2026-07-13 | 轻微 | `done` 存在但非布尔被静默当未结束 | 采纳：§4 `done` 缺失容忍为 False，存在但非布尔 → `MODEL_PARSE_ERROR`；§7 加测 |
