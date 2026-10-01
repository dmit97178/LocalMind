# 15-tool-orchestration-hardening — 工具编排加固契约（统一工具定义、草案化工具调用、完成性陈述溯源）

> **状态：✅ 待实现**（2026-09-18 立项，Claude 裁决，Codex 实现）
> **依赖**：`00-core-interfaces.md`（工具接口）、`04-p3-safety-hardening.md`（三关、确认恢复、防线分层）、`07-p6a-observability-cli.md`（事件流、`file.write` 工作区写入）、`08-p6b-evaluation-loop.md`（S14 与验收口径）、`12-risk-draft-closed-set.md`（解析层唯一归一化）、`13-approval-profile-high-impact.md`（批准档只升不降）
> **上游**：`clarifications.md` 开放项「工具名/参数键」（2026-09-17 Codex 提出）+ S14 连续 4 次真实 run 失败（`data/evals/run_5ae664c8e1e7/6c2a80df5189/cc29f8613d98/ec9196e10f27`）
>
> 本契约**不新增**模型能力、**不新增**安全机制、**不改变**任何既有安全不变量：模型只能提议工具调用草案，执行权仍在 ControlPolicy / SafetyPolicy / preflight / 身份确认 / GuardedToolExecutor；所有副作用仍只经 GuardedToolExecutor；云端建议**不得**直接产生或执行本地工具调用；不引入 LangChain、专家模型、自进化。**不为 `file.write` 打补丁**——加固的是编排链路本身。

---

## 0. 裁决摘要

### 0.1 六个漏洞的核定与四条附加发现

上游六条事实**全部成立**（证据见 §0.2 表）。核对中另发现四条上游未列缺陷，F7 与上游第 5 条同源（是它的代码落点）：

> **2026-09-18 Codex 复审修正**：初稿把 F7 写成了「**策略要求的确认被 App 吞掉**」（依据是空计划早返回排在 `:821` 的 `requires_user_confirmation` 检查**之前**）。该论断**已撤回**，理由见 §5.2：确认语义是 **step-scoped** 的——没有 step 就没有可确认的操作，空计划轮次根本不该进入确认链；真正被吞掉的不是确认，是**「本轮本该有工具」这个事实**（早返回不区分两种空计划）。F7 措辞已按此改写，F7 的价值（定位了自由文本的产生点）不变。

| # | 缺陷 | 证据 | 归属 |
|:---:|---|---|---|
| **F7** | **空计划分支回落到模型自由文本**：`_handle_action` 在 `src/main.py:792-800` 直接 `return self._build_local_reply(...)`，**没有区分「本回合确实不需要工具」与「本该有工具但没能建立」**——这正是 S14 那句「文件不存在 / 已创建 / 已覆盖」的产生位置（上游第 5 条的代码落点） | `src/main.py:792-800`；唯一防线是提示词里一句 `Do not claim that a tool was executed.` | 本契约 §5（I2 + `reply_provenance` 分流） |
| **F8** | 即插即用违规**第二处**：`BuiltinToolBackend` 对 `file.write` 有两处名称分支（handler `:59-61`、preflight `:76-87`） | `src/tools/builtin_backend.py` | 本契约 §1.3 |
| **F9** | 同一事实存三份（`ToolDef.parameters` 扁平写法 / `RegisteredTool.required_params` / `_missing_params`），且参数**类型**校验全链路不存在；`00-core-interfaces.md:193`「JSON Schema」、`07 §6.1` `{"path":{"type":"string"}}`、代码扁平写法**三方不一致** | `src/tools/registry.py`、`src/tools/builtin_backend.py`、`src/safety/guarded_executor.py`（无参数校验） | 本契约 §1.1/§3 |
| **F10** | P6b 场景替身通道绕过 `GuardedToolExecutor`，观测到的「已执行」有一处断点 | `src/evaluation/child.py:87` | **记录在案，本契约不动**（§11） |

### 0.2 六条上游事实的证据表

| # | 事实 | 证据 |
|:---:|---|---|
| 1 | 提示词只给工具名 + 短描述 | `src/core/context_assembler.py:139-140`（`f"{tool.name}: {tool.description}"`） |
| 2 | `suggested_tools` 是任意字符串数组，不受 `list_tools()` 约束 | `src/core/intent_resolver.py:38`（静态 schema，无 `enum`） |
| 3 | `entities` 与工具参数无显式绑定 | `src/core/task_planner.py:14`（`params=dict(candidate.entities)`） |
| 4 | 只取 `suggested_tools[0]` | `src/core/task_planner.py:12-15` |
| 5 | 缺工具时退化为自然语言回答 | `src/main.py:792-800`；唯一防线是提示词一句 `Do not claim that a tool was executed.`（`_build_local_reply`） |
| 6 | `file.read` 无工作区边界 | `src/tools/file_tools.py:66-68`（`_required_path` = `Path(str(raw_path))`，无解析无校验） |

### 0.3 三条必须照实说的事

1. **残余风险不可消除**：模型可以谎报「本回合不需要本地动作」（`tool_intent="none"`）继而在自由文本里声称完成。在不扫回复文本、不穷举输入关键词的前提下，这在本阶段**结构上不可证伪**。处置见 §5.5。
2. **迁移期的行为变更只有一处**：`suggested_tools` 不再参与任何判定（§2.5）。既有 fixture 只要不构造草案，行为与今日**逐字相同**（§7.4）。
3. **模型合作度不由本契约保证**：本契约保证「模型给出草案时链路可靠、模型不给时系统不伪造」。真实 `qwen3:4b` 是否产出草案由 P6b 证据回答（§9.12）。

---

## 1. 统一工具定义：`list_tools()` 是运行时闭集的唯一来源

### 1.1 `ToolDef.parameters` 的格式钉死（F9）

`parameters` **就是 JSON Schema 的 object schema 子集**，不再是「键 → 类型名」的扁平简写：

```python
ToolDef(
    name="file.read",
    description="读取工作区内某个文本文件的内容。",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    risk_level="sensitive",
    approval_profile="...",
)
```

- **支持的键闭集 = 实际会被校验的键**：只有 `type`、`properties`、`required`。**其它键在注册期直接拒绝**（`CONFIG_ERROR`，不进入主循环）——**不是「忽略」**。「工具作者写下的约束被系统静默忽略」与本次要修的「静默退化」是同一类问题：作者写了 `minimum` 会以为它生效，模型照着提示词里的约束产出，而系统从头到尾没看过这个键。
- 类型闭集：`object` / `string` / `integer` / `number` / `boolean` / `array`，**浅层判定**（`array` 只判是否 list，不校验元素类型）。
- 无参数工具写 `{"type": "object", "properties": {}, "required": []}`。
- **注册期不变式（bootstrap 失败，不进入主循环）**：① 根节点必须是 `{"type": "object", ...}` 形态（含 `properties`）；② `properties` 必须是映射，每个值必须是 dict 且 `type` ∈ 上述闭集；③ `required` 必须是字符串列表，每个名字必须出现在 `properties` 中；④ 工具名非空，且**全目录唯一**；⑤ 出现上述闭集之外的任何键 → 拒绝。违例一律 `CONFIG_ERROR` + `details.reason`。
- **不与 §2.2 层 A 的 `enum` 混淆**：响应 schema 里注入的**工具名 `enum`** 是**编排层自己构造**的（§2.2 层 A），不是工具作者写的 `parameters`，不受本条限制。本条约束的只是 `ToolDef.parameters`。
- **`RegisteredTool.required_params` 删除**：必填的唯一来源是 `definition.parameters["required"]`。第三份实现 `builtin_backend._missing_params` 随之删除（§3.1）。
- 迁移：`registry.py` 现有 5 个工具的扁平写法改为上表形态。`07 §6.1` 的块引用已是目标形态，**不需修改**；`00-core-interfaces.md:193` 的注释改为「JSON Schema 子集（见 15 §1.1）」（Codex 镜像）。
- **2026-09-25 P7b 增补（`17` §2.3）**：`ToolDef` 新增 `egress: bool = False`（**出站工具标记**：参数值会离开 Agent 进程）。**本条（§1.1）确立的 parameters 格式与注册期不变式对出站工具同样成立**，并且新增两条**通用**注册期不变式（`17` §3 E11/E12，fail-loud）：`egress=True` ⇒ ①`set(properties) ⊆ set(supply_by_echo) ⊆ set(param_instance_checks)`、②`audit_redact_all_params=True`。**首批受影响者**：`weather.current` **必须回填** `egress=True`（它已满足①②，回填只是把 `16` §11 第 22 项的源码级断言换成通用不变式——回填后 `16` §9.4 的 C15 必须全绿）；`file.stat` 为 `False`（不离开进程）。**`egress` 不进提示词**（渲染白名单排除，与 `audit_redact_all_params` 同处断言）。**本节 §1.1 的类型闭集（含 `integer` 等）不受 P7b 影响**——限制到 `string` 的规则是**只对外部工具**的准入门槛（`17` E9），不是对 `ToolDef.parameters` 的全局收窄。
- **2026-09-27 P7c 增补（`18` §1.3）**：`ToolDef` 新增 `result_delivery: str = "deterministic"`（尾部带默认值，**追加式 ⇒ 既有构造调用零改动**；**同样不进提示词**——渲染白名单排除，与 `egress` / `audit_redact_all_params` 同处断言）。**语义**：`deterministic` = 沿用现状（`ResponseBuilder.build()` 的产出即回复）；`model_summary` = 执行成功后由本地模型基于「本回合用户请求 + 有界工具结果」生成回复（只读工具结果回流层）。**关键纪律（与本节 §3.3 的「无工具名分支的通用 TaskPlanner」同源）**：本字段的存在意义正是**避免**在 `main.py` 里写 `if tool_name in {...}`——运行期模块（`main.py` / `control_policy.py` / `task_planner.py` / `guarded_executor.py` / `composite_backend.py` / `builtin_backend.py`）**零工具名字面量**（`18` §12.1 N5 的源码级断言）。**三条通用注册期不变式**（fail-loud，`CONFIG_ERROR` / `result_delivery_invalid`，`18` §1.3）：RD1 闭集；**RD2 `model_summary` ⇒ 工具不在 `LOCAL_SIDE_EFFECT_TOOLS`**（写入类工具继续确定性结果 ⇒「让模型改写是否写入成功」成为**注册期不可达**，与 `13` 的批准档合成一致）；**RD3 `model_summary` ⇒ `egress == False`**（回流把工具结果送进提示词，egress 工具的结果是外部来源文本 ⇒ 不绕开 `17` 的「外部文本零进提示词」边界；`weather.current` 因此**永不进回流**）。RD1–RD3 与 `validate_capabilities()` 的既有 S1/S2/E11/E12 检查同处、**在 `enabled` 门之前**执行。**同一轮的第二处签名变更（`ExecutionRecord.result_delivery: str | None = None`，`18` §1.2）**：回流状态须落在**同一条** `tool_execution` 记录上，而 `_record_tool_events(records)` 只收记录列表 ⇒ 状态**写在记录上**，由 `_execution_records(plan, results, deliveries)` 按 **step_index** 回填（**不得按工具名**——同一计划可多次调用同名工具；**不得用列表下标**——记录列表经过 `continue` 过滤，下标与 step_index 不保证相等）。这是本契约「执行记录是执行事实的唯一载体」的同一手法：让错配状态**不存在**，而不是事后检查。

### 1.2 值的来源与流动（单源）

- 工具闭集**只用** `ToolBackend.list_tools()` 产出。`Core` 任何模块**不得** import `src.tools.registry.BUILTIN_TOOLS`（当前唯一合法使用者在 `builtin_backend.py` 内部；源码级断言见 A8）。
- 流向单向：`list_tools()` → `ContextAssembler` → `MinimalContext.tool_defs` → `IntentResolver`（提示词 + 响应 schema）/ `ControlPolicy` / `TaskPlanner`。逐轮现取，不缓存、不在构造期快照（新注册的工具当轮可见，§4.4）。
- **工具数上界 `32`：两层检查**。①**主防线 —— `bootstrap()`**：`len(list_tools()) > 32` → 启动期失败（`CONFIG_ERROR`）；②**冗余防线 —— `ContextAssembler` 每轮**：因为第 1 条明确「逐轮现取、新注册工具当轮可见」，bootstrap 的检查**不能**保证后续仍 ≤ 32，所以每轮装配时重查数量、名字唯一性与 §1.1 的 schema 合法性，超限/违例 → **明确失败**（`CONFIG_ERROR` + `details.reason`，回合以 `error` 终结），**禁止截断**（截断=静默丢工具，不可接受）。两层是 `04 §4.7` 防线分层在本维度的同构：主防线在装配入口，冗余防线在持有者。
  - **口径随之修正**：工具目录长度**不是**编译期常量，而是**每轮被显式校验的有界量**。这不是「提示词长度有界」这个结论的退让——拒绝截断、拒绝静默，超限就是故障，必须响。
- **工具目录序列化后的 UTF-8 总字节上界 `8192`**（2026-09-18 二轮复审补钉）：数量上界 `32` **不足以**保证目录有界——`description`、工具名、属性数量与属性名**都没有长度上限**，一个工具仍可携带极大目录。加一条**定值**约束，不做预算系统、不做按比例分配：把目录按 `IntentResolver` 实际渲染的形态（§6.4 的完整目录，含 name / description / parameters / required / risk_level）序列化后取 UTF-8 字节数，超限即 **`CONFIG_ERROR`**（`details.reason="tool_catalog_too_large"`），**禁止截断**。
  - 检查点与 §1.2 的两层一致：**主防线 `bootstrap()`**（启动期一次）+ **冗余防线 `ContextAssembler` 每轮**（逐轮现取的必然要求）。两处**共用同一个纯函数**（`ToolDef` 序列 → 字节数），不写第二份实现。
  - 这是**可靠性上限，不是性能预算**，因此取定值而非按模型窗口缩放；8192 B ≈ 32 个工具各带一句中文描述与两三个参数的正常量级的两倍余量——正常目录**远达不到**，触发的都是「工具作者写了超长描述」这类真故障。
  - **检查顺序与诊断量（2026-09-19 代码审查补）**：数量上界先判、目录字节上界后判——字节上界只对**已通过数量上界**的目录生效。两条上界共用 `details.reason="tool_catalog_too_large"`，但 `details` **必须**带诊断量（数量超限带 `tool_count`，字节超限带 `catalog_bytes`），供运维区分「加了工具」与「描述太长」这两类成因不同的故障。
  - **与 `context_byte_budget` 相互独立**：该预算治理 `relevant_history`（`00-adapter-factory.md:475-476`），工具目录是**每轮被显式校验的有界量**，既不进该预算，也不从该预算借额度。

### 1.3 Handler / PreflightHook 签名统一（F8：删掉名称分支）

```python
# core/schemas.py
@dataclass(frozen=True)
class ToolContext:
    workspace_root: Path
    tool_def: ToolDef

# tools/registry.py
@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDef
    handler: Callable[[Mapping[str, object], ToolContext], Mapping[str, object]]
    preflight: Callable[[Mapping[str, object], ToolContext], PreflightReport] | None = None
```

- **一律两参**：`handler(params, context)`。`file.write` 的工作区参数改走 `ToolContext.workspace_root`，`write_file` / `preflight_write` 的签名从 `(params, workspace_root)` 改为 `(params, ctx)`。
- **`BuiltinToolBackend.execute` 不得出现任何工具名字面量**：`tool.handler(dict(params), ctx)`。现有的 `if tool_name == "file.write"` 元数分支删除。
- **`BuiltinToolBackend.preflight` 同法**：`hook = tool.preflight`；有 hook 用 hook、无 hook 走 `super().preflight(...)`。**合成规则不变**（`13 §2.3` 只升不降；`effective_risk` 取 max，`approval_profile` 取 max）。现有的 `if tool_name != "file.write"` 分支删除。
- 默认静态 preflight（`interfaces.py:141-169`）保持不变：这是「注册表给出风险下界」的唯一实现。
- **`ToolError` 的抛出仍在 handler 内部**，`execute` 的 `except (OSError, KeyError, TypeError, ValueError)` 集合不变。

### 1.4 明确不做

引入 `$ref` / `allOf` / `oneOf` / `patternProperties` / 格式校验（email、date）——不做；**`enum` / `maxLength` / `items` 的校验——不做，且为此把它们移出了 §1.1 的支持键集**（声明了就必须校验，不校验就不许声明）；参数**默认值**——不做（缺参数必须显式失败，§3.3）；工具版本号 / 依赖声明——不做。

---

## 2. 结构化工具草案 `ToolCallDraft`

### 2.1 结构

```python
# core/schemas.py
@dataclass(frozen=True)
class ToolCallDraft:
    tool_name: str
    arguments: dict[str, object] = field(default_factory=dict)
```

`IntentCandidate` 追加**四个**尾部字段（带默认值，位置构造兼容）：

```python
    tool_intent: str = "none"                 # 闭集：none | local_action
    tool_call: ToolCallDraft | None = None
    tool_call_resolution: str = "absent"      # 闭集见 §2.3；归一化结果随候选携带
    tool_intent_conflict: bool = False        # N4 的判定结果，见 §2.4；同点写入
```

- **`tool_call_resolution` 必须随候选携带**（2026-09-18 Codex 复审补钉）：未知工具、畸形形状、多草案在归一化后**都会变成 `tool_call=None`**，若不把归一化结论一并带出，`ControlPolicy` 与 App 就无法区分 `unknown_tool` / `multiple_proposed` / `invalid_shape` / 真正的 `tool_call_missing`——§3.3 的分支表、A3 与 `intent_final.tool_call_resolution` 全部落不了地。
- **`tool_intent_conflict` 同理，也必须是候选字段**（2026-09-18 二轮复审补钉）：N4 判的是**原始**两个字段，而归一化会改写 `tool_intent`（§2.4 步骤 1–3）、丢弃原始 `tool_call`——判定依据在候选构造完成后**已不可复原**。若不把结论随候选带出，App 只能拿到归一化后的候选，`intent_final.tool_intent_conflict` 无从生成。**禁止**塞进 `IntentResolver.last_*` 旁路（如 `last_resolution_exhausted` 那样）：那条路是给「与候选无关的回合级事实」用的，本条是**候选级**事实，与本契约刚确立的「归一化结论随候选携带」相冲突。
  - 原始值本身**不携带、不落事件**（原始 `tool_intent` 是模型自由文本），只落一个 bool——符合事件层「不落模型派生原文」的既有纪律。
- 这与 `risk_draft` 的既有做法**完全同法**（`project-plan §4.2`：归一化来源以 `IntentCandidate.risk_draft_resolution` 随候选携带并落 `intent_final`）。同一类事实（模型原始输出 → 归一化结论）只有一种携带方式，不得一处用字段、一处用旁路。

### 2.2 闭集如何进入响应 schema：**双层，后置校验是权威**

- **层 A（提高命中率，非权威）**：`_INTENT_RESPONSE_SCHEMA` 由常量改为函数 `_intent_response_schema(tool_names: Sequence[str]) -> dict`，其中 `tool_call.properties.tool_name.enum = sorted(tool_names)`；`generate(prompt, response_schema=...)` 每轮用 `context.tool_defs` 现算。提示词渲染**完整目录**（渲染契约见 **§6.4**，实现点只有 `IntentResolver` 一处——`ContextAssembler` 不做渲染，§10.2）。
  - 依据：本地弱模型的合作度只能靠"把闭集摆到它眼前"提高；但**任何依赖后端实现 enum 的假设都不成立**（适配器可能忽略未知关键字），所以层 A 只是概率手段。
- **层 B（权威）**：解析层后置校验（§2.3）。**只有层 B 决定 `ToolCallDraft` 是否存在**。两层都不得留下「工具名不在闭集却建出 step」的路径。

### 2.3 归一化：唯一入口（解析层）与 `tool_call_resolution` 闭集

`_tool_call_or_none(raw: object, tool_names: Sequence[str]) -> tuple[ToolCallDraft | None, str]`，返回值第二项是闭集 `tool_call_resolution ∈ {resolved, absent, invalid_shape, unknown_tool, multiple_proposed}`：

| raw `tool_call` 形态 | 归一化结果 |
|---|---|
| 键缺失 / `null` | `None`, `absent` |
| object，`tool_name` 为非空 string，`arguments` 为 object 或缺省 | 成员校验：∈ 闭集 → `ToolCallDraft(name, arguments or {})`, `resolved`；∉ 闭集 → `None`, `unknown_tool` |
| 数组（长度 ≥ 1） | `None`, `multiple_proposed`。**不区分长度**：哪怕只有 1 个元素也不解析（v1 的 `tool_call` 是单数槽位，取元素=替模型做形状修正，且无法断言它是否还想表达更多）；本项是「形状不被 v1 接受」的标记，多工具阶段它将变成合法输入 |
| 其它任意形态（含 `arguments` 非 object） | `None`, `invalid_shape` |

- **`multiple_proposed` 不做「取第一个」**：「挑哪个」没有确定性依据，与本项目「不做字段优先级截取」的既有裁决（boss 32768 裁决）同构。该计数是未来多工具阶段的证据触发器（§11）。
- `arguments` 里的键与值**不在这里判合法**（那是 §3 的事）；解析层只管形状与成员。
- **唯一不变式**：`tool_call_resolution == "resolved"` ⟺ `tool_call is not None`。§3 起的一切分流都读这两个字段，**不得**再由下游重新解释原始 raw（解析层是唯一归一化点）。
- 消费侧用法（**先看 resolution，再验草案**）：`resolution != "resolved"` 时**不要**调用 `validate_tool_call`（它只处理草案），直接按 §3.3 取 reason；只有 `resolved` 才把草案交给校验函数。

### 2.4 `tool_intent` 闭集与归一化（**严格有序**的单一过程，N1–N4）

`tool_intent ∈ {none, local_action}`，语义：**模型对本回合是否需要本地动作的显式声明**。

归一化（**解析层唯一**，其它任何层不得重写这两个字段）**必须是一个有严格顺序的单一过程**，不得写成三条并列规则（2026-09-18 三轮复审补钉：初稿把 N1/N2/N3 平列，对「模型给了合法草案但**省略** `tool_intent`」这一输入，N1 得出 `local_action`、N3 得出 `none`，两条规则同时命中且结论相反——这是契约级歧义，不是实现细节）：

```
步骤 1  原始 tool_intent → 中间 intent（只看 intent 自己，与草案无关）
          · 键存在且 == "local_action"        → "local_action"
          · 键存在且 == "none"                → "none"
          · 键缺失                            → "none"          ← N3 前半（合法缺省，纯分析轮的前提）
          · 键存在但值不在闭集                 → "local_action"  ← N3 后半（未识别值 fail-closed，
                                                                    与 12 §1.3 的 risk_draft 同法）
步骤 2  草案覆盖（**最高优先级**）
          · tool_call_resolution != "absent"  → intent 强制为 "local_action"   ← N1 + N2
步骤 3  仅在草案缺席时保留步骤 1 的结论
          · tool_call_resolution == "absent"  → intent = 步骤 1 的结果
```

- 步骤 2 的依据（N1 与 N2 合并为一条）：模型**确实提交了东西**（合法草案、未知工具、畸形形状、多草案中的任意一种），fail-closed 方向必须是「不谎称已完成」——退化为自由文本正是 S14 的病。因此 `resolution != "absent"` ⟹ `local_action`，**与步骤 1 的结果无关**。
- 步骤 1 的两种缺省语义**不可互换**：**键缺失**是合法缺省（模型没表态，按不动作处理）；**键存在但值不可识别**是 fail-closed（模型表了态但系统读不懂，按要动作处理）。
- **推论（写进真值表，防实现侧只测「正常路径」）**：「省略 `tool_intent` + 给出合法草案」的最终 intent 是 `local_action`（步骤 2 覆盖步骤 1），**不是** `none`。这与 N1 在初稿下的结论一致——**顺序钉死只消除歧义，不改变任何一种输入的结果**。
- **N4（`tool_intent_conflict` 的定义与载体）**：`candidate.tool_intent_conflict == True` ⟺ **原始 `tool_intent` 键存在且其值恰为 `"none"`** **且** **原始 `tool_call` 键存在且其值不为 `null`**（模型自相矛盾：嘴里说不需要动作，手里递了一份草案，被步骤 2 覆盖为 `local_action`）。
  - **判定必须按「键存在 + 值不为 null」，不得用 Python truthiness**：`{}` / `[]` / `""` / `0` 都是「模型明确提交了东西」的畸形草案，`if raw_tool_call:` 会把它们判为假而**漏记冲突**——那恰好是「畸形草案」这一类最该被观测的样本。
  - 显式 `null` **不算**提交（§2.3 表：`null` 与键缺失同归 `absent`）；判定式两边都是「明确性」而非「内容丰富度」。
  - **判定在解析层内部完成，结论落在候选字段上**（`IntentCandidate.tool_intent_conflict`，§2.1）——判定所需的原始值在这一步之后就没了，**必须当场落结论**。App 只做转发（`candidate.tool_intent_conflict` → `intent_final.tool_intent_conflict`），**不重算**。
  - **旧定义作废**：初稿写的是「`tool_intent=="none"` 且 `risk_draft ∈ {sensitive, dangerous}`」——这是**错的**：分析敏感材料完全不需要本地工具，两者同时出现是**完全自洽**的常见形态，把它记成「冲突」会让这个计数失去意义（Codex 复审指出）。
  - **照实承认的观测盲区**：`tool_intent` **键缺失**时**永远不产生冲突标记**（无论模型是否给了草案）——「模型心里想调工具但一个字都没说」在本阶段**无法观测**，不得假装能观测。冲突标记只抓「明确说了 none 又给了草案」这一种自相矛盾。

**归一化真值表（A13 的用例清单，逐行断言四个字段 + `reason`）**：

| # | 原始 `tool_intent` | 原始 `tool_call` | `tool_call_resolution` | 最终 `tool_intent` | `tool_intent_conflict` | 失败 `reason` |
|:---:|---|---|---|---|:---:|---|
| 1 | **缺失** | 合法草案 | `resolved` | `local_action` | `False` | —（正常建 step） |
| 2 | **缺失** | 畸形（字符串 / `{}` / `[]` …） | 按 §2.3 **逐形态**判：非空数组 → `multiple_proposed`；其余畸形（字符串、`arguments` 非 object、**`[]`**）→ `invalid_shape` | `local_action` | `False` | 与 resolution 配对：`multiple_proposed` / `tool_call_invalid_shape` 二选一 |
| 3 | **缺失** | 缺失 / `null` | `absent` | `none` | `False` | —（`answered`） |
| 4 | `"none"` | 合法草案 | `resolved` | `local_action` | **`True`** | —（正常建 step） |
| 5 | `"none"` | 畸形（`[]` / `{}` / 未知工具） | 按 §2.3 **逐形态**判：`[]` → `invalid_shape`、`{}` → `invalid_shape`、未知工具 → `unknown_tool`、非空数组 → `multiple_proposed` | `local_action` | **`True`** | 与 resolution 配对 |
| 6 | `"none"` | 缺失 / `null` | `absent` | `none` | `False` | —（`answered`） |
| 7 | `"local_action"` | 缺失 / `null` | `absent` | `local_action` | `False` | `tool_call_missing` |
| 8 | `"local_action"` | 合法草案 | `resolved` | `local_action` | `False` | —（正常建 step） |
| 9 | 非法值（如 `"maybe"`） | 缺失 / `null` | `absent` | `local_action` | `False` | `tool_call_missing` |
| 10 | **缺失** | 键缺失 | `absent` | `none` | `False` | —（`answered`） |

- 第 2/5/9 行是**本表存在的理由**：它们都是「模型表了态但表达不合法」的形态，任何一条落到自由文本就是 S14 的病复发。
- 第 1 行是三轮复审指出的歧义点：**必须**是 `local_action`，且**不记冲突**（键缺失 ⇒ 无法断言模型自相矛盾）。

### 2.5 `suggested_tools` 的命运：保留、降级为纯观测字段

**裁决：本契约不删除 `suggested_tools`；但它不再是任何判定的输入。**

- 判定源替换（**唯一两处**）：
  - `src/core/control_policy.py:230-231` 的准入否决 `CloudAdmissionDecision(False, "suggested_tools_present")` → 读 `candidate.tool_intent == "local_action"`，reason 改名 **`local_action_proposed`**。
  - `src/core/control_policy.py:264` `_is_conditionally_answerable` 的 `and not candidate.suggested_tools` → `and candidate.tool_intent == "none"`。
  - `src/core/task_planner.py:12-15` 的 `suggested_tools[0]` → `candidate.tool_call`（§4.2）。
- **源码级断言**：除 `src/core/intent_resolver.py`（解析层）与 `src/adapters/openai_compat_adapter.py`（云端建议侧的同名字段，见下）外，`src/` 内**不得**出现对 `candidate.suggested_tools` 的读取。
- 注意区分：`ConsultationProposal.suggested_tools`（`schemas.py:240`）是**云端建议**的字段，`cloud_boundary.py:49` 的可执行标记检查与它相关，**不属于本条**，不动。
- **退役条件（2026-09-18 收紧，Codex 复审指出原条件过松）**：三个条件**同时**满足才由 Claude 出删除裁决：
  1. **正样本存在**：连续 3 次真实 run 中，`suggested_tools_count > 0` 的轮次 **≥ 1**（否则「无样本」被误判成「无差异」——两个字段恒为 false 时逐轮相等恒成立，会误触退役）；
  2. **逐轮一致**：在上述 3 次 run 的**全部**轮次上 `tool_call_present == suggested_tools_present`；
  3. 无 `tool_intent_conflict == True` 的轮次（模型自相矛盾的样本不算「一致」）。
  本契约不删；报告侧保留该计数用于迁移期对比（§8.3）。**两个谓词的定义钉死在 §8.1**（`tool_call_resolution == "resolved"` / `suggested_tools_count > 0`）——不能由实现者自选口径，否则「相等」可以靠口径差异造出来。

---

## 3. 参数校验：一份实现、三层调用

### 3.1 唯一实现

```python
# core/tool_validation.py（或 core/schemas.py 同级，Codex 定位置）
@dataclass(frozen=True)
class ToolCallValidation:
    ok: bool
    reason: str                      # ok | unknown_tool | param_missing | param_type | param_unknown_key
    tool_def: ToolDef | None = None
    missing: tuple[str, ...] = ()
    offending: tuple[str, ...] = ()
    instance_rejected: tuple[str, ...] = ()   # 2026-09-23 新增（`16` §6.3.x）：被实例谓词剔除的键

def validate_tool_call(
    draft: ToolCallDraft,            # 非可选：见下
    tool_defs: Sequence[ToolDef],
) -> ToolCallValidation: ...
```

- **参数不接受 `None`（2026-09-18 Codex 复审补钉）**：`None` 的语义（「本轮没有可用草案」）已经在**解析层**由 `tool_call_resolution` 定完（§2.3），本函数只回答「**这份草案**是否合法」。让它接收 `None` 等于把解析层职责下沉进校验器，且会诱使实现者在函数里再造一套 `unknown_tool`/`multiple_proposed` 的分支。调用方一律**先读 resolution、再验草案**。
- **`instance_rejected`（2026-09-23 新增，`16` §6.3.x 的接口变更）**：与 `missing` / `offending` 并列的**归因位**，默认空元组 ⇒ 既有断言与构造点零改动。本函数内部以 `current_input=None` 调 `16` §6.3.x 的 `rejected_instance_params(arguments, tool_def)`（**唯一实现，不在本函数里复写第二份**），命中的键**同时**进 `missing`（视为未提供）与 `instance_rejected`（记名），`reason` 仍取 `param_missing`——**终态是追问，不是错误**，故本节不新增 reason 值、§5.3 不新增模板。**边界**：`current_input=None` 是**刻意的**——本函数在补参消费路径上被调用时「用户输入」就是那个值本身，「值等于整句」这条通用规则在那里会**误伤正确答案**，故那条规则只在准入级生效（`16` §6.3.x 第 2 条）。

校验内容（浅层、递归到 `properties` 一层）：
1. `tool_name` ∈ `tool_defs`（否则 `unknown_tool`）；
2. `arguments` 的键 ⊆ `parameters["properties"]`（否则 `param_unknown_key`，`offending` 给出键名）；
3. `parameters["required"]` 中的键全部存在**且非空**（`None` / `""` / `[]` / `{}` 视为缺失，否则 `param_missing`）。**被实例谓词剔除的键（本节上面的 `instance_rejected` 条）视为不存在**；
4. 每个值类型匹配 `properties[key]["type"]`（`string`/`integer`/`number`/`boolean`/`array`/`object` 的浅层判定；`bool` 不是 `integer`，Python 的 `isinstance(True, int)` 陷阱必须显式排除，否则 `param_type`，`offending` 给出键名）。

**禁止第二份实现**：`builtin_backend._missing_params` 删除；`GuardedToolExecutor` 与 `TaskPlanner` 一律调用本函数。

### 3.2 三层职责（谁能知道什么，就判什么）

| 层 | 位置 | 判什么 | 失败后果 |
|:---:|---|---|---|
| 1 形状与契约 | `ControlPolicy`（判定）+ `TaskPlanner`（建步） | 成员、必填、类型、未知键（**纯函数，无 IO**） | 见 §3.3 表 |
| 2 语义与事实 | `ToolBackend.preflight`（各后端自己的 hook） | 路径解析与工作区边界、目标存在性、内容长度等**只有后端知道的事实** | 只升不降的 `effective_risk`；`dangerous` → 硬拒；`sensitive` → 确认链；**另有第三类出口（2026-09-19 代码审查补）**：无法用风险档表达的事实类失败（`target_missing` / `path_type` / `not_a_directory`）由 hook 抛 `ToolError` → App `record_denial` + 返回 `exc.user_message`（**构造器产物**，零执行，`reply_provenance=="unfulfilled"`）。**禁止**让原生异常（`ValueError` / `OSError` / `KeyError`）从 hook 逃逸——那会退化成 `INTERNAL_ERROR` 并把「文件事实」误报成「系统故障」 |
| 3 冗余复核 | `GuardedToolExecutor.execute()` | **同规则、同函数**再验一次形状——由 `ExecutionStep` **重建** `ToolCallDraft(tool_name=step.tool_name, arguments=step.params)` 后调用（执行层只持有 step；重建不解释 raw、不推断参数，只是同一份数据再验一次） | 抛既有 `TOOL_PARAM_ERROR`（fail-closed） |

层 3 的定位与 `04 §4.7` 的防线分层一致：主防线在 App/Policy（正确路由、正常响应），冗余防线在持有者（接线错了就抛）。层 2 是**每个后端必须做的必要适配**，不是「加工具要改编排」的违规。

### 3.3 失败分支的确定性行为

**分流顺序是先 resolution、后草案校验**（§2.3 末条）：`resolution != "resolved"` 的行**不调用** `validate_tool_call`。

| 情形 | 处置 | `reason` | 可恢复性 |
|---|---|---|:---:|
| `resolution=="absent"` 且 `tool_intent=="local_action"` | **能力错误回复**（**不** ASK_USER、**不**重解析） | `tool_call_missing` | 本回合否；用户改述即恢复 |
| `resolution=="unknown_tool"` | **能力错误回复**，且 `tool_intent` 已被步骤 2 强制为 `local_action`（§2.4） | `unknown_tool` | 同上 |
| `resolution=="multiple_proposed"` | **能力错误回复** | `multiple_proposed` | 同上 |
| `resolution=="invalid_shape"`（`tool_call` 是数组以外的畸形形态、`arguments` 非 object 等） | **能力错误回复** | `tool_call_invalid_shape`（**2026-09-18 新增的独立 reason**，不与 `param_invalid` 合并：两者的成因与将来的修法不同——一个是「模型把 `tool_call` 写成了字符串/数字」，一个是「模型给了参数但类型不对」，合并会在报告里抹掉这个区别） | 同上 |
| `resolution=="resolved"` + `validate_tool_call` 通过 | 正常建 step（§4.2） | 既有 READY reason 不变 | — |
| `resolution=="resolved"` + 必填参数缺失 | **ASK_USER**（确定性追问，逐条列出 `missing` 键名，**不调模型**；不得编造参数值） | `param_missing` | **是**：用户补一句即恢复（同一 session 连续两轮） |
| `resolution=="resolved"` + 类型错 / 含未声明键 | **能力错误回复**（§5） | `param_invalid` | 否；用户改述即恢复 |
| `resolution=="resolved"` + 工具名不在**本次** `tool_defs`（解析层算闭集之后目录发生了变化） | **能力错误回复** | `unknown_tool` | 同上 |
| `local_action` 且 `tool_defs is None`（App 未提供目录） | **能力错误回复**（fail-closed 到诚实回复，绝不退化成自由文本） | `tool_catalog_absent` | 接线问题，见 §7.2 |
| `resolution=="absent"` 且 `tool_intent=="none"` | **不进本表**——纯分析轮，走 §4.3 第 1 行 | — | — |

> **上游多一层：能力相关性（2026-09-20 P7a，`16-p7-practical-tools-capability-routing.md`）**：本表**逐行不变**，但在能力路由**开启**时（`capability_routing.enabled=true`）它**不再是最先命中的分支**——`_decide_ready()` 顶部先做能力检查（`16` §3.8 ③），早于本节的 `tool_intent == "local_action"` 分支：
>
> - `capability_resolution ∈ {unavailable, unrecognized}` → `capability_unavailable`，走**能力错误模板的「不可用」变体**（§5.3）；`reason` **不是**本表任何值。语义差别是实在的：本表各行是「模型表达的草案不合格」，这一行是「系统**没有**这个能力」——模板文案不得把后者写成前者。
> - `capability_resolution == "routed"` 且无草案 → `tool_call_missing`（与本表第 1 行**同值同义**，故不重复定义）。
> - **关闭时（P7a 默认）本节逐字回到上表**，不新增分支、不新增 reason——这是 `16` §9.1 第 1 条「关态事件流与 `15` 实现逐字段相等」得以断言的前提。
>
> 另有两行**只在能力开启时可达**，均走能力错误模板：`irrelevant_tool`（工具**在**目录内、但不服务所选能力）与 `unrouted_tool`（无可归属能力却有草案），`reason` 分别为 `capability_irrelevant` / `capability_unrouted`（`16` §8.1）。归属判定**先于**参数校验（`16` §9.2 C8）——与本表「先 resolution、后草案校验」同法，理由相同：成因不同则该报的错不同。
>
> **反查映射是红线**：不得用「工具名 → 能力」反查来给一个无归属的草案**补**归属（`16` §2.4）。漏接线的方向必须是**诚实失败**，不是放行。

- **`unknown_tool` 有两个来源，reason 同一个**：①主路径在解析层（模型写的名字不在闭集）；②冗余路径在 `validate_tool_call`（解析层算完闭集后目录被改）。两处都归 `unknown_tool`，因为对用户与报告而言是同一件事；`tool_call_resolution` 保留了这个区别（②的 resolution 仍是 `resolved`）。

「能力错误回复」是**常量模板**（§5.3）：明示「我没能建立本地工具调用，本轮没有执行任何操作」，并给出重述示例（这就是「可恢复路径」——系统状态无污染：无待确认悬挂、无审计副作用、下一轮可正常发起同一请求）。

### 3.4 ControlPolicy 的插入点

`_decide_ready()` 的**第一行**（先于 `_is_conditionally_answerable` 与 `requires_user_confirmation` 的计算）：

```
行 1（新）  candidate.tool_intent == "local_action"
            → tool_defs is None  → reason = tool_catalog_absent
                                   （**必须排在第一位**：目录缺失时下面两条都不可
                                     求值——resolution 的成员判定本就依赖闭集，
                                     validate_tool_call 也不接受 None 目录）
            → 否则读 candidate.tool_call_resolution（唯一归一化结论，§2.3）
              · != "resolved"  → 按 §3.3 取 reason（tool_call_missing /
                                 unknown_tool / multiple_proposed /
                                 tool_call_invalid_shape），不调 validate_tool_call
              · == "resolved"  → validate_tool_call(candidate.tool_call, tool_defs)
                                 · ok     → 不拦截，继续走既有行序（成功路径 reason 不变）
                                 · 失败    → 按 §3.3 取 reason
            → 需要拦截时返回 ASK_USER(param_missing) 或 PLAN_LOCAL(其余 reason，
              App 依 §5 走能力错误回复，不调模型)
行 2..n     既有行序不变
```

- **`tool_defs is None` 判定必须在解引用之前**（2026-09-18 二轮复审补钉）：`tool_defs` 是**带默认值 `None`** 的可选参数，若实现先算 `resolution` / 先调 `validate_tool_call`，在接线遗漏时抛的是 **`TypeError` 之类的原生异常**，而不是本契约定义的确定性失败——用户看到的会是崩溃，`reason` 也落不了 `tool_catalog_absent`。`ControlPolicy.decide()` 侧按 §7.2 接线保障目录非缺省；本行是**持有者侧的兜底**，兜底的产出仍是**合法的契约内失败**。测试锁定见 **A12**。

**为什么在这里**：`tool_intent == "none"` 的回合（纯分析、条件化回答、云端回流）**逐字不变**；只有模型声明了本地动作的回合才进入新分支。VAGUE/PARTIAL/ALMOST 状态仍走既有追问/检索路径——模型不确定时先问，是对的。

**`requires_user_confirmation` 不变**：草案合法时仍按既有风险/置信度规则计算，随后由 App 的 preflight → 确认 → 执行链承接（S14 的正确链路）。

---

## 4. 通用 `TaskPlanner`（无工具名分支）

### 4.1 目标形态

`plan(candidate, context)` 的**签名不变**（`00-adapter-factory.md:526-529`）；工具闭集从 `context.tool_defs` 读（§1.2）。`src/core/task_planner.py` 内**不得出现任何工具名字面量**（源码级断言，A8）。

### 4.2 算法（行序即代码顺序）

```
1. if candidate.tool_call_resolution != "resolved": return ExecutionPlan()
                                                     # 纯分析／无可用草案：空计划
                                                     # 失败形态已由 §3.4 定性，App 依 §5 分流
2. v = validate_tool_call(candidate.tool_call, context.tool_defs)   # 此处 draft 必非 None
3. if not v.ok: return ExecutionPlan()                            # 空计划；失败原因已由 §3.4 给出；
                                                                   #   App 依 §5 不得据此走自由文本
4. d = candidate.tool_call
   return ExecutionPlan(steps=[ExecutionStep(
       tool_name=d.tool_name,
       action=d.tool_name.rsplit(".", maxsplit=1)[-1],
       params=dict(d.arguments),            # ← 唯一参数来源：草案的 arguments
       risk_level=candidate.risk_draft,
       intent_type=candidate.intent_type,
       entities=dict(candidate.entities),   # ← 退化为观测字段，不再是执行输入
       user_input=context.current_input)])
```

**两处语义变更（本契约的核心修复）**：
- `params` **只来自** `draft.arguments`（原 `params=dict(candidate.entities)` 删除）。`entities` 仍是「模型抽取的实体」，只进观测与追问，**不再是参数来源**。
- `suggested_tools[0]` 删除（§2.5）。
- **多工具禁止隐式合并**：任何情况下不得把两个工具塞进一个 step 的 `params`；`ExecutionStep` 保持单工具语义。
- `approval_profile` **不由 planner 设置**：来源仍是 `13 §2.2` 的「注册表 + preflight，只升不降」合成，由执行层负责——同一安全事实不得有两处设置点。

### 4.3 失败必须是显式的

「计划为空」现在有两种截然不同的含义，**必须在事件流里可区分**：

| 空计划成因 | 含义 | App 行为 |
|---|---|---|
| `tool_call_resolution == "absent"` 且 `tool_intent == "none"` | 本回合确实不需要工具 | 走 `answered`（§5.2） |
| `reason ∈ {tool_call_missing, unknown_tool, param_invalid, tool_call_invalid_shape, multiple_proposed, tool_catalog_absent}` | 本该有工具、没能建立 | 走 `unfulfilled` 能力错误（§5.2） |

`TaskPlanner` 内部**不得**自行把失败改写成成功的 `ExecutionPlan`（例如「名字不认识就跳过」）。

### 4.4 扩展性验收（上游第 7 点）

新增工具只需两件事：①在 `ToolDef` 里写清 `parameters`（含 `required`）与 `risk_level`/`approval_profile`；②在 `RegisteredTool` 里给 `handler`（两参）与可选 `preflight`。**`TaskPlanner` / `ControlPolicy` / `GuardedToolExecutor` / `ContextAssembler` / 解析层零改动**（dummy 工具的完整链路验收见 A8）。

---

## 5. 完成性陈述溯源（硬不变式）

### 5.1 五条不变式

| # | 不变式 |
|:---:|---|
| **I1** | 完成性叙事只允许出现在 `executed` 轮，且该叙事由 `ResponseBuilder` / `ToolBackend` 的**真实结果**确定性构造，**不得掺入模型自由文本** |
| **I2** | `tool_intent == "local_action"` 的回合（**无论草案是否成立**）不得以模型自由文本作为可见回复；一律走确定性回复（执行报告 / 能力错误 / ASK_USER / 确认请求 / 拒绝文案） |
| **I3** | `answered` 轮的可见回复必须携带 App 追加的**确定性来源声明**（常量，不得由模型生成）；触发条件见 §5.3 |
| **I4** | 每轮的 `reply_provenance` 由 App 在回合终结处按 §5.2 判据表**确定性判定**，不得由模型或提示词决定；落 `turn_completed.data.reply_provenance` |
| **I5** | 计划非空的失败/拒绝轮不得出现成功叙事（既有 `SafetyDenied.user_message` / `RecordOutcome` 路径已满足，本条把它显式化并纳入验收 A6） |

### 5.2 `reply_provenance ∈ {executed, unfulfilled, answered}`（判据表）

**三值的语义按「本轮是否产生执行」定义，不按「成败」定义**，避免把正常追问读成失败：

| 值 | 语义 |
|---|---|
| `executed` | 本轮产生了至少一条成功执行记录 |
| `unfulfilled` | 本轮**意图是本地执行**（`local_action` 或计划非空），但没有任何成功执行——可见回复必须是确定性构造器产物 |
| `answered` | 本轮**不是执行型回合**；回复是正常交互产物（模型自由文本，或**非执行型**回合的规则层追问/提示，如信息不足时的 ASK_USER 追问、无待确认操作时的提示）。**与 `unfulfilled` 的分界是「本轮意图」而非「回复是不是模板」**：`param_missing`（模型声明了本地动作、只缺参数）属 `unfulfilled`；VAGUE 状态的 `missing_info` 追问属 `answered` |


判定输入**只有三个结构化事实**：`next_action.reason`、`plan.steps` 是否为空、`records[].verdict`，外加一个已随候选携带的**意图标记** `candidate.tool_intent`（**2026-09-19 代码审查补记**：实现按 `tool_intent == "local_action"` 判 `unfulfilled`，与按上表 reason 集合判**逐例等价**——`local_action` 且计划为空时 `reason` 必落在 §3.3 的 7 值内。把这一条写明是为了消除「表里只列三个事实、实现读了第四个」的歧义；两种写法都合规，但**不得**只读对话文本或回复措辞）。**不扫回复文本、不用任何中文词表。**

| 条件（自上而下，首个命中即判定） | `reply_provenance` | 可见回复的构造器 |
|---|---|---|
| 存在 `verdict == "allowed"` 的 `ExecutionRecord` | `executed` | `ResponseBuilder.build()`（无模型调用） |
| 计划非空（`len(steps) ≥ 1`）且**无** allowed 记录 | `unfulfilled` | 既有拒绝/失败路径（无模型调用） |
| 计划为空 且 `reason ∈ {tool_call_missing, unknown_tool, param_invalid, tool_call_invalid_shape, multiple_proposed, tool_catalog_absent}` | `unfulfilled` | **能力错误常量模板**（无模型调用） |
| 计划为空 且 `reason == "param_missing"`（App 出 ASK_USER） | `unfulfilled` | 确定性追问（无模型调用） |
| 其余空计划（纯分析 / 条件化回答 / 云端建议回流 / ASK_USER 的追问 / 无待确认操作时的提示） | `answered` | `_build_local_reply` / `_build_local_advisory_reply`（有模型调用，云端回流受 `05`/`10` 既有约束）/ 规则层追问模板（无模型调用） |

#### `_handle_action` 的权威顺序（F7 的正确修法，2026-09-18 Codex 复审后改正）

初稿写的是「空计划分支**必须先判** `requires_user_confirmation`」。**该写法作废**：照它实现会出现「确认一个空计划」——用户确认完之后没有任何 step 可执行，还要留下一个空的 pending 状态。真正的顺序是：

```
1. plan = planner.plan(candidate, context)
2. if plan.steps 非空:                     # ← 确认语义唯一的适用域
      既有链路逐字不变: preflight → _apply_preflight_risk → dangerous 硬拒
      → high_impact → requires_user_confirmation or preflight.requires_confirmation
      → TOCTOU 复检 → executor.execute()
3. else（空计划）——按 §3.3 的 reason 分流，**不进入确认链**:
   3a. tool_intent == "local_action"（含所有失败形态）
       → 确定性能力错误回复，reply_provenance = "unfulfilled"
   3b. tool_intent == "none"
       → 正常回答，reply_provenance = "answered"（§5.3 的触发条件下追加来源声明）
   3c. **仅 3a** 不得出现模型自由文本（I2）；3b 是 `answered` 轮，
       按 §5.2 末行的正常规则处理（允许模型自由文本）
```

- **3c 的适用范围只有 3a**（2026-09-18 二轮复审补钉）：初稿写成「两条路径都不得出现模型自由文本」，与同表的 3b（`tool_intent=="none"` → 正常回答）和 A9（`answered` 轮允许自由文本）**直接冲突**。I2 的语义本来就是 **`local_action` 轮次专属**（见 I2 原文：「`tool_intent == "local_action"` 的回合…」），不是「空计划轮次」专属。以 I2 为准，3b 不受约束。

- **硬断言（纳入 A11）**：空计划轮次**不得**产生 pending confirmation 状态（无 `awaiting_confirmation`、无待执行 step、无 `_pending_plan` 残留）；也不得出现「确认请求」文案。理由：`requires_user_confirmation` / `high_impact` / `gate23` / TOCTOU 全部是 **step 级**语义，没有 step 就没有可确认、可放行的对象。
- **F7 的原始观察仍然有效，但结论换了**：`src/main.py:792-800` 的危险不是「早返回排在确认检查之前」，而是**它不区分两种空计划**（「本回合确实不需要工具」与「本该有工具、没能建立」），把后者也送进了 `_build_local_reply` 的自由文本。修的是这个分流，不是分支顺序。
- **反向情形（确认不得被吞）仍受保护**：任何**有 step** 的回合都必然经过 `:821` 的确认检查——这才是「策略要求的确认不被吞掉」的真实适用范围，A5 覆盖它。
- 确认轮（`gate23`）同样按本表判定（它有非空计划）。
- 云端回流轮的 text 内容约束仍由 `05 §`/`10 §`/`CloudBoundary` 承担，本契约只记 provenance，不新增文本约束。

### 5.3 `answered` 轮的来源声明与「能力错误模板」

- **来源声明触发条件**：`answered` 且（`requires_user_confirmation == True` 或 `risk_draft ∈ {sensitive, dangerous}`）。纯分析且 normal 的轮次**不加**（避免每轮噪声）。
- 形式：App 追加一行**常量**文本（不含模型输出）明示「本轮未执行任何本地工具操作」。具体文案由 Codex 定稿，但**必须是模块级常量**，可由测试逐字节断言。
- **能力错误模板**（§3.3 第 3–6 行复用它）同样是常量，须包含：①本轮未执行任何操作；②未能建立工具调用的原因类别（`unknown_tool` / `param_invalid` / `tool_call_missing` / `multiple_proposed`）；③一个重述示例（可恢复路径）。**2026-09-20 P7a 增补**：模板须有**「不可用」变体**（`capability_unavailable`，`16` §4.2 复用本节模板），内容为：①本轮未执行任何操作；②**系统当前没有能回答这个请求的能力**（原因类别 = **能力缺失**，不是「模型没给出草案」）；③可恢复路径 = 改述为已有能力能做的事，或由用户自行开启/配置相应能力（`16` §4.1 恢复路径）。**判据**：两个变体都是模块级常量、都是确定性构造器产物，可由测试按同一断言标签机检（`16` §9.2 C5 断言「可见回复逐字节等于不可用变体常量」）。**不得**在本变体里出现完成性叙事，**不得**把地点等入参回显成「我查到了」的语气。

- **不得**把 `ToolError` 的内部 code/reason 直接暴露给用户（`04 §4.7` 的既有约束）。

### 5.4 为什么这是结构化判据（而不是文案检查）

- 判据只读三个字段，全部来自确定性组件（`NextAction` / `ExecutionPlan` / `ExecutionRecord`），与语言、措辞、模型输出无关。
- 机检形式 = **断言标签 + 断言该轮没有模型调用**（用确定性模型替身的调用计数），而不是「回复里不含某中文词」。
- 由 I1/I2 可直接推出：**S14 的「已创建 / 已覆盖 / 文件不存在」在 `local_action` 轮次上结构上不可达**——那些轮次的可达回复构造器里没有模型调用点。

### 5.5 残余风险（照实写）

模型若谎报 `tool_intent="none"` 而自由文本声称完成，本阶段**结构上不可证伪**（扫回复文本、穷举输入关键词两条路都已被排除）。处置：

1. 该轮标 `answered`；若同时 `risk_draft ∈ {sensitive, dangerous}` 或 `requires_user_confirmation`，来源声明会把「未执行」明示给用户——**系统的嘴保持诚实**；
2. 提示词规则要求「用户明确要求本地读/写/列目录时必须产出草案」（§6 的提示词契约）；
3. **这一形态本身无法从事件里认出来**（照实说）：N4 的 `tool_intent_conflict` 抓的是「模型自相矛盾」（说了 `none` 又给了草案），**不是**这一形态——本条恰恰是模型**什么都没给**。可用的近似证据只有交叉聚合：`reply_provenance="answered"` 且 `suggested_tools_count == 0` 且 `risk_draft ∈ {sensitive, dangerous}` 或 `requires_user_confirmation` 的轮次，人工抽检其可见回复；**不得**把它包装成「已可观测」；
4. 更强的下一手段（把 `answered` 轮的可见文本限制为分析类模板、禁止完成态）记录在 §11，**本契约不提前实现**。

---

## 6. 统一文件工具边界

### 6.1 唯一解析器与拒绝集

- **唯一实现** `resolve_workspace_target(raw: object, workspace_root: Path) -> Path`：由 `file_tools` 的私有函数升级为**工具层共享函数**，`file.read` / `file.list_dir` / `file.write` 及其 preflight hook **全部**调用它（现状：只有 `write_file`/`preflight_write` 用，`_required_path` 完全绕过）。
- **拒绝集（三条路径一致）**：绝对路径 / 盘符 / UNC / `~` / 解析后不在 `workspace_root` 内（含 `..` 逃逸）。最后一个条件以 `is_relative_to(workspace_root)` 为准；前缀检查只能作为快速拒绝，**不得**作为唯一防线。
- **拒绝的后果**：`ToolError(code="FILE_ERROR", details={"reason": "workspace_escape"}, recoverable=True)`，且 preflight 的 `effective_risk = "dangerous"`（现状仅 write 如此，扩展到 read/list_dir）→ App 硬拒，**不得**返回任何文件内容或目录项。

### 6.2 `FILE_ERROR` 的 `details.reason` 闭集扩展

现有（`00-error-contract.md:130`）：`workspace_escape` / `target_state_changed`（+ `target_exists` 用于 preflight 升险）。本契约新增：

| `reason` | 触发 |
|---|---|
| `target_missing` | `read` 的目标不存在；`list_dir` 的目标不存在 |
| `not_a_directory` | `list_dir` 的目标存在但不是目录 |
| `path_type` | `path` 参数不是字符串 / 不是**可用路径**：含 NUL 字符、或 `Path.resolve()` 抛 `OSError`/`ValueError` 的畸形路径（**2026-09-19 代码审查补**：必须在 `resolve_workspace_target` 内部当场转成 `FILE_ERROR`，**不得**让异常逃出 preflight——否则 App 只能报 `INTERNAL_ERROR`，把文件事实误报成系统故障） |
| `content_too_large` | `write` 内容超上限（既有 `_MAX_WRITE_CHARS` 的口径统一到此处） |

- `message` 必须与操作一致（现状 `file_tools.py:59` 的 `_file_error` 对读操作也写 `File write rejected`，属缺陷）。
- **禁止**让原生异常逃逸到 App：读不存在必须返回上述 `ToolError`，**不得**抛 `FileNotFoundError`；`handler` 内可保留 `except OSError` 兜底，但必检情形必须显式转成 `ToolError`。

### 6.3 三条路径的行为对齐表

| 情形 | `file.write` | `file.read` | `file.list_dir` |
|---|---|---|---|
| 逃逸（任何形式） | `dangerous` → 硬拒 | 同左 | 同左 |
| 目标不存在 | **`sensitive` → 确认后新建**（2026-09-20 P7a-0 反转；`target_exists=False` 只决定文案为「新建」） | `FILE_ERROR/target_missing` | `FILE_ERROR/target_missing` |
| 目标存在 | `sensitive` → 确认后覆盖（`target_exists=True`，文案含「覆盖」） | 正常返回内容（注册表 `sensitive` → 确认链） | 正常返回条目 |
| 目标类型不符 | `path_type` | `path_type`（是目录时） | `not_a_directory` |

- **注册表风险值**：`file.read` 保持 `sensitive`（S14 step0 的确认链依赖它），`file.list_dir` 保持 `normal`，**`file.write` 由 `normal` 改为 `sensitive`（2026-09-20，P7a-0）**——动态只升不降仍由 preflight 提供，但写操作的基线已不可能是 `normal`。**这张表的三条路径是前置校验/拒绝的形态表，其「允许」列一律不等于「无需确认」**——写操作的确认由注册表基线在 App 侧决定（`07` §6.3），与本表的路径判定正交。
- `file.read` 返回结构增加 `target_missing` 之外的一切保持原样（`{"path", "content"}`）；`list_dir` 保持 `{"path", "entries"}`。

### 6.4 提示词契约（`IntentResolver`）

提示词必须携带（全部由 `context.tool_defs` 渲染，不得硬编码）。**渲染的实现点只有本模块一处**：`ContextAssembler` **不做**目录渲染（只校验并写入 `MinimalContext.tool_defs`，§1.2/§10.2），响应 schema 的 `enum` 注入同样只在本模块（§2.2 层 A）——同一份渲染不得有两处实现：

1. 工具清单：`name` / `description` / **完整 `parameters`** / **`required` 展开** / `risk_level`；
2. **何时该用**：用户明确要求读取、列出、写入工作区内文件（或其它已注册本地副作用）时，必须产出 `tool_call`；用户只要求解释、分析、总结、讨论时**不得**产出；
3. **何时不该用**：纯分析、闲聊、纯知识问答 → `tool_intent="none"` 且 `tool_call=null`；
4. **参数纪律**：`arguments` 的键必须取自该工具的 `parameters.properties`；**缺必填参数时不得编造**（缺什么就不给，由系统追问）；
5. **模型不能标记已批准**：不得输出任何「已执行 / 已批准 / 已确认」语义的字段或措辞（既有 `12 §4.3` 的提示词点检清单同法，本契约新增的检查点：`tool_call` / `tool_intent` 不得由模型赋予批准含义）；
6. 既有软约束保留：`Do not claim that a tool was executed.`（§5.5 的第 2 条处置）。

---

## 7. 接口签名变更（Claude 授权，Codex 落 00-* 与代码）

### 7.1 数据类

| 类型 | 变更 | 位置 |
|---|---|---|
| `ToolCallDraft` | **新增** `{tool_name: str, arguments: dict[str, object]}` | `core/schemas.py` |
| `ToolContext` | **新增** `{workspace_root: Path, tool_def: ToolDef}` | `core/schemas.py` |
| `ToolDef.parameters` | **语义钉死**为 JSON Schema 子集（§1.1）；字段本身不变 | `core/schemas.py:92-100` |
| `IntentCandidate` | 追加**四字段**（尾部 + 默认值）：`tool_intent: str = "none"`、`tool_call: ToolCallDraft \| None = None`、`tool_call_resolution: str = "absent"`、`tool_intent_conflict: bool = False`。**四个字段必须由解析层在同一处一次写完**（§2.1/§2.4 N4）——不得一个进候选字段、一个走 `IntentResolver.last_*` 旁路 | `core/schemas.py:291-304` |
| `MinimalContext` | **新增** `tool_defs: tuple[ToolDef, ...] = ()`；**删除** `tool_summaries: list[str]`（同一事实不得两份载体，渲染在提示词构造处） | `core/schemas.py:330-339` |
| `RegisteredTool` | `handler` 改两参签名；**删除** `required_params`；**新增** `preflight: PreflightHook \| None = None` | `tools/registry.py` |
| `ControlPolicy.decide()` | **新增** keyword-only `tool_defs: Sequence[ToolDef] \| None = None` | `core/control_policy.py` |

### 7.2 `ControlPolicy.decide()` 的新参数：默认值语义

```python
def decide(self, candidate, cloud_state=None, *, resolution_exhausted,
           no_progress=False, reference_guard=None,
           tool_defs: Sequence[ToolDef] | None = None) -> NextAction:
    """tool_defs 由 App 从 context.tool_defs 原样转发（与 cloud_state / reference_guard 同法）。
    None 表示「App 未提供工具目录」：此时任何 tool_intent="local_action" 的回合
    以 reason="tool_catalog_absent" 走能力错误回复（fail-closed 到诚实回复），
    绝不退化为自由文本。tool_intent="none" 的回合不受影响。"""
```

**为什么不设成必传（与 `14 §3.2` 的偏离，理由）**：`14` 把 `resolution_exhausted` 改必传，是因为漏传会**静默退化**成错误动作（`RETRIEVE_MORE`）。本参数的漏传后果是**显式可见**的能力错误（`tool_catalog_absent` 进事件流、回复为常量模板），不会伪装成成功；且全部既有单测调用点不构造草案，行为逐字不变。**复议触发条件**：一旦出现「忘接线」事故，或下一次改动本就要触碰这批调用点，改必传并同步 `00-adapter-factory.md:485-503`。

**运行期口径照实修正（2026-09-19 代码审查补）**：`MinimalContext.tool_defs` 的默认值是**空元组 `()` 而非 `None`**，`ContextAssembler` 每轮必写、App 两处调用点一律原样转发，因此**运行期不存在 `tool_defs is None`**。于是这段「漏传后果」的论证只在**直接调用 `decide()`（A12 第一段的形态）**时成立；真正的「忘接线」在 App 内的表现是**空目录 → `unknown_tool`**（A12 第二段：确定性、不抛原生异常），而 `tool_catalog_absent` 只覆盖**显式 `None`**。

- 本契约**接受**这一归因边界，**不**把 `MinimalContext.tool_defs` 改成可空：空白名单本就是合法运行态（`list_tools()` 可以合法为空），把「空」与「未接线」在类型上分开需要一个本阶段没有证据支持的新状态。
- 代价**必须写进报告纪律**（§8.3）：`unknown_tool` 计数里可能混入接线缺陷 —— 排查 `unknown_tool` 时**先确认 `list_tools()` 非空**，再判断是不是模型写错了名字。

### 7.3 不改变的部分（先钉死，防实现侧顺手放宽）

`ToolBackend` 三方法签名；`ExecutionStep` / `ExecutionPlan` / `ExecutionRecord` / `AuditEvent` 结构；`GuardedToolExecutor.execute()` 的判定顺序（注册 → preflight → 只升不降 → dangerous → high_impact → gate23 → SafetyPolicy → 执行 → 审计）；`_CONFIRM_WORDS` 与确认恢复流程；`SafetyPolicy` / `PrivacyPolicy` / `CloudBoundary` / 授权与预算；`risk_draft` 闭集与 `approval_profile` 合成规则；`ResponseBuilder` 的确定性格式化。**本契约只在上述结构之间加入「参数形状层」，不移动任何既有闸门的位置。**

### 7.4 迁移规则（本契约最重要的一条边界）

- **不引入「缺草案即能力错误」的全局规则**（那会把所有纯分析轮变成能力错误）。fail-closed **只在** `tool_intent == "local_action"` 时生效。
- 既有 fixture / 场景替身（`suggested_tools=[...]` 但无 `tool_call`）归一化后 `tool_intent="none"`、`tool_call=None` → 空计划 → `answered` 自由文本，**与今日行为逐字相同**。
- 显式测「模型提议了本地工具」的用例（准入否决、条件化回答抑制）必须补 `tool_intent="local_action"`；清单由 Codex 按 §10.2 处理。
- 真实模型在提示词更新后仍可能不产出草案 → S14 可能仍失败；**本契约保证链路，不保证模型合作度**（§0.3/§9.12）。

---

## 8. 可观测性

### 8.1 键集变更（封闭集扩展，**两份白名单都要改**）

| 事件 | 变更 | 依据 |
|---|---|---|
| `intent_final` | **+4 键**：`tool_intent`（`none`/`local_action`）、`tool_call_resolution`（**归一化结论，随候选携带**，§2.1/§2.3 闭集）、`tool_intent_conflict`（bool，定义见 §2.4 **N4**；**纯观测，不改变任何行为**）、`suggested_tools_count`（int ≥ 0，**计数不是内容**） | `07 §2.2` 产生者分工：与 `risk_draft` / `risk_draft_resolution` 同 stage（`tool_call_resolution` 与 `risk_draft_resolution` 是**同一类事实**：模型原始输出 → 归一化结论）。`suggested_tools_count` 是 §2.5 退役判据的**唯一载体**——`suggested_tools` 的原文此前不进任何事件，没有这个计数就没有「模型提议了工具但没给出草案」的证据面，退役条件会变成永远无法判定 |
| `dispatch_decision` | `reason` 闭集扩展 **7 值**：`tool_call_missing` / `unknown_tool` / `param_missing` / `param_invalid` / `tool_call_invalid_shape`（§3.3 新增）/ `multiple_proposed` / `tool_catalog_absent`；准入否决 reason 改名 `suggested_tools_present` → `local_action_proposed` | §3.4 / §2.5 |
| `turn_completed` | **+1 键** `reply_provenance ∈ {executed, unfulfilled, answered}`（§5.2）。**不复用** `completion`——后者是回合级异常轴（`normal`/`error`），语义不同 | §5.1 I4 |
| `tool_execution` | **不变** | — |
| 场景 `expect` 键集 | **不扩展**（10 项之外的断言落在单测与报告聚合，与 `14 §9` 第 5 项同法） | §9 |

**两份键白名单必须同时改**：`src/main.py:1440-1486`（`_sanitize_event_data`，白名单外的键被**静默丢弃**）与 `src/observability/sinks.py:14-69`（`_PERSISTED_KEYS`，落盘阶段再过滤一次）。漏改 = 新键形同不存在。

**迁移期两个派生谓词（钉死定义，实现者不得自选口径）**：

| 谓词 | 定义 | 落点 |
|---|---|---|
| `tool_call_present` | `intent_final.tool_call_resolution == "resolved"` | 已有键，派生 |
| `suggested_tools_present` | `intent_final.suggested_tools_count > 0` | 本契约新增键「`suggested_tools_count`」，派生 |

两者都是**逐轮**布尔量，均由既有/新增事件键**确定性派生**，不新增采集面、不引入自由文本。§2.5 的退役条件判的就是这两个量的逐轮相等。

### 8.2 报告侧（P6b）

`scripts/p6_report.py` 增加：`reply_provenance` 计数、`tool_call_resolution` 分布、`unfulfilled` 轮次列表，以及**迁移期对比行**：`tool_call_present` vs `suggested_tools_present`（**定义见 §8.1**，分别由 `tool_call_resolution` 与 `suggested_tools_count` 派生；§2.5 的退役条件需要它）。另：`suggested_tools_count` 的分布（0 / 1 / ≥2）单列——它是「模型确实想调工具但给不出草案」的唯一证据，与 `reply_provenance="unfulfilled"` 交叉后能区分「模型没意图」与「模型有意图但不会表达」。

- **`reason` 不得作为报告输入（2026-09-19 代码审查改正）**：初稿写「`unfulfilled` 轮次列表（**含 reason**）」，但按 `07 §2.2` 的落盘分级，`dispatch_decision.reason` 属**整键不落盘**（`JsonlEventSink._project_data` 显式 `pop`）——报告读的是 JSONL，**拿不到 `reason`**。报告只能由**已落盘**的键派生：`reply_provenance` + `dispatch_decision.action` + `intent_final.tool_call_resolution` + `suggested_tools_count`。
- **可分辨性照实声明**：`(action, tool_call_resolution, reply_provenance) = (PLAN_LOCAL, resolved, unfulfilled)` 这一签名在**运行期实际等价于 `param_invalid`** —— 另两个同签名的成因里，`tool_catalog_absent`（显式 `None`）在 App 内不可达（§7.2），`resolved 但名字不在本次目录` 需要目录在解析与本轮校验之间发生变化（§3.3 冗余路径）。`param_missing` 由 `action=="ASK_USER"` 分辨。若要恢复逐 `reason` 细粒度聚合，必须先在 `07` 立契约（新增落盘键），不在本契约内私加。

### 8.3 不新增的事件类型、不新增的层

不新增事件类型；不引入新的观测通道；`reply_provenance` 不进 `_active_report` 之外的持久层（无新表、无新字段）。

---

## 9. 验收矩阵（A1–A13）

**口径**：A1–A9 用**脚本化模型替身**（确定性输出）+ `tmp_path` 工作区，断言结构化事实与文件系统状态，不做文案关键词断言。真实模型 run 单列为证据（§9.12）。

### A1 — S14 全链（上游第 1 点）

| 段 | 脚本化模型输出 | 断言 |
|:---:|---|---|
| 1 | `tool_intent="local_action"`, `tool_call={file.read, {path:"notes/deploy.md"}}` | `dispatch_decision.requires_user_confirmation == True`；零 `tool_execution`；无文件内容出现在回复中 |
| 2 | （用户）`确认 <passphrase>` | `tool_execution{verdict:"allowed"}` 恰好 1 条；回复由 `ResponseBuilder` 构造；`reply_provenance=="executed"` |
| 3 | `{file.write, {path:"notes/new.md", content:"..."}}`（目标不存在） | 无前置确认（`requires_user_confirmation == False`）；直接执行；`tmp_path` 内文件内容逐字节匹配 |
| 4 | `{file.write, {path:"notes/deploy.md", content:"..."}}`（目标存在） | preflight `effective_risk=="sensitive"`；`requires_user_confirmation == True`；执行前文件内容**未变** |
| 5 | （用户）`确认 <passphrase>` | `allowed` 1 条；文件内容更新；`reply_provenance=="executed"` |

### A2 — 操作型请求但无草案（上游第 2 点）

`tool_intent="local_action"` + `tool_call=null` → 断言五件事：①`tool_call_resolution=="absent"` 且 `reason=="tool_call_missing"`；②`reply_provenance=="unfulfilled"`；③可见回复**逐字节等于能力错误常量**；④**模型替身调用计数与本轮开始时相同**（无模型调用 ⇒ 模型不可能声称成功）；⑤工作区快照无变化，零 `tool_execution`。

### A3 — 未知工具（上游第 3 点）

`tool_call={tool_name:"file.delete", arguments:{...}}` → `tool_call_resolution=="unknown_tool"`；`tool_intent=="local_action"`（§2.4 步骤 2 强制，N1+N2）；`reason=="unknown_tool"`；零 `tool_execution`；零副作用。

### A4 — 参数缺失 / 类型错（上游第 4 点）

- ①缺 `content` → `reason=="param_missing"`、`action=="ASK_USER"`、追问文本包含缺失键名；零执行；**同一 session 紧接一轮补齐参数 → 正常链路成功**（可恢复性）。此项的 `tool_call_resolution` 仍是 **`resolved`**（草案本身形状合法，缺的是参数）——用于锁死「resolution 不是校验结果的替身」。
- ②`{path: 123}` → **事件里** `reason=="param_invalid"`（**不是** `param_type`：校验器的命名空间只到 §3.1 为止，进事件前**必须**在 `ControlPolicy` 边界映射）；`offending==("path",)` **断言在校验器层**（`validate_tool_call` 的返回值——事件只承载 `NextAction` 三字段，`offending` 不进事件）；能力错误模板；零执行。
- ③`{path:"a.md", 未知键:...}` → **同上**（事件 `reason=="param_invalid"`；校验器层 `reason=="param_unknown_key"` 且 `offending` 含该键名，**2026-09-19 代码审查后改正**：初稿把③写成「`param_unknown_key` 同上」，与 §3.3/§8.1 的 `param_invalid` 冲突）。
- ④`{"path": ""}`（空值视为缺失）→ `param_missing`。
- ⑤**形状层（与参数层分开验）**：`tool_call="file.read"`（字符串）→ `tool_call_resolution=="invalid_shape"`、`reason=="tool_call_invalid_shape"`、**未调用** `validate_tool_call`（替身/探针：让该函数抛异常即用例变红）；`{tool_name:"file.read", arguments:"/etc"}`（`arguments` 非 object）→ 同上。
- ⑥`tool_call` 为**单元素数组** `[{tool_name:"file.read",...}]` → `resolution=="multiple_proposed"`、`reason=="multiple_proposed"`、零执行（§2.3：长度 1 也不解析）。

### A5 — 未确认 → 零副作用（上游第 5 点）

敏感草案 + 用户不确认（或发非确认词）→ 零 `allowed` 记录、零 `tool_execution`、**目标文件字节不变**、审计无 allowed 条目、`_pending_plan` 已被清理（既有 `04 §` 行为不回归）。

### A6 — 工具失败 → 无成功叙事（上游第 6 点）

`ToolBackend.execute` 返回 `err`（或抛 `ToolError`）→ `records` 中该 step 非 allowed → `reply_provenance=="unfulfilled"`；断言**构造器来源**（拒绝/失败路径）与标签，不断言文案用词。

### A7 — 工作区逃逸（上游第 7 点）

**三个工具 × 五种路径形态 = 15 组**：`../outside.md`、绝对路径、`~`、UNC、带盘符路径。断言：`FILE_ERROR/workspace_escape`；preflight `effective_risk=="dangerous"`；`verdict=="denied"`；**回复与事件中不含目标文件内容或目录项**。

### A8 — 扩展性（上游第 8 点）

测试内注册 `demo.upper`（`parameters={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}`, `risk_level="normal"`）+ handler + 无 hook → 断言：出现在 `list_tools()`；出现在提示词目录与响应 schema 的 `enum`；完整链路可执行；**源码级断言**：`src/core/task_planner.py` / `src/core/control_policy.py` 中无任何内置工具名字面量，`src/tools/builtin_backend.py` 中无 `== "file.write"` 之类的名称比较。

### A9 — 纯分析仍允许空计划（上游第 9 点）

`tool_intent="none"`, `tool_call=null`, `risk_draft="normal"` → 空计划 + `answered` + 自由文本回复 + **无来源声明**（§5.3 不触发）。

### A10 — 零回归（上游第 10 点）

既有 **569** 例全绿（基线经 `pytest --collect-only -q` 核验，2026-09-18 Codex 二轮复审修正）；S02/S03/S06/S09 口径不变；云端（外发预览、预算、授权、`deny_cloud`）、安全（三关、确认恢复、口令锁定）、记忆（两层持久化、检索）场景零回归；S14 的**风险层**期望不变（step0 仍要求 `confirmation_required`）。

### A11 — 空计划不得进入确认链（F7 的正确修法）

三组：①`tool_intent="local_action"` + 无草案 → 断言**无** `awaiting_confirmation` 文案、无 `_pending_plan` 残留、无待执行 step；②`tool_intent="none"` 纯分析 + 计划为空 → 同上，且走 `answered`；③反向：有 step 且策略要求确认 → 确认检查**必须**生效（断言 `requires_user_confirmation==True` 且文件在执行前未变，与 A1 第 1 段同法）。**探针**：把空计划分支改回「一律进确认链」→ ① 必须变红。

### A12 — 漏接线不得抛原生异常（2026-09-18 二轮复审补）

`decide()` **不传** `tool_defs`（用默认值 `None`）+ `tool_intent="local_action"` + 合法草案 → 断言：①**不抛原生异常**（`TypeError` / `AttributeError` / `NoneType` 之类一律判红——这是本用例的存在理由）；②`reason=="tool_catalog_absent"`；③`reply_provenance=="unfulfilled"`，可见回复等于能力错误常量；④零 `tool_execution`、零副作用；⑤同一 `decide()` 的调用在 `tool_intent="none"` 时**不受影响**（不传 `tool_defs` 也照常 `answered`）。

- **探针**：把 §3.4 的 `tool_defs is None` 判定移到 `validate_tool_call` 之后 → ① 必须变红。用例锁的是**顺序**，不是「有个 if」。
- **附加（同用例内，三轮复审补）**：`context.tool_defs == ()`（**空目录**而非缺省 `None`）+ 合法草案 → `validate_tool_call` 确定性返回 `unknown_tool`；断言**不抛原生异常**且 `reason=="unknown_tool"`。它与 `tool_catalog_absent` 是**两个不同的故障**，不得合并（前者是「解析层算出的闭集里没有这个名字」，后者是「App 根本没给目录」）。
- 本用例只覆盖 `ControlPolicy` 侧的默认参数遗漏。`TaskPlanner` 侧的同类情形**不是**「不走到校验」，而是**空目录进入校验后确定性返回 `unknown_tool`、不抛原生异常**（2026-09-18 三轮复审改正：`resolution` 是**候选**字段，由解析层按 `list_tools()` 算好，与 `context.tool_defs` 是否为空**无关**——目录为空时草案的 resolution 仍可能是 `resolved`，于是 §4.2 第 2 行照常调用 `validate_tool_call(draft, ())`，其产出必须是契约内的 `unknown_tool` 失败，不是崩溃）。

### A13 — 归一化真值表（2026-09-18 三轮复审补）

**逐行**断言 §2.4 真值表的 10 行，每行四个字段（`tool_intent` / `tool_call_resolution` / `tool_intent_conflict` / 最终 `reason`）全部匹配。**必须整表参数化跑，不得只挑「正常路径」**——第 2/5/9 行（畸形与非法值）才是这张表存在的理由。

- **专项锁死两处易错点**：① 第 1 行（**省略** `tool_intent` + 合法草案）必须得到 `local_action` 且 `tool_intent_conflict == False`——这正是初稿 N1/N3 并列时结论相反的输入；② 第 5 行用 `tool_call=[]` 与 `tool_call={}` 各跑一次，`tool_intent_conflict` 必须为 `True`（**真值判定**：若实现写成 `if raw_tool_call:`，两者都是 falsy，本行会红——这就是探针）。
- **源码级断言（防第二种携带方式）**：`tool_intent_conflict` 在 `src/` 内的写入点**只有一处**（解析层），`IntentResolver` 上不得出现 `last_tool_*` 之类的旁路属性。

### 9.12 S14 场景层口径

- `scenarios/S14_file_confirmations.toml` **不改**：其 6 步文本与 6 条 `expect` 在目标形态下全部可满足（read→确认、write → 确认、write 覆盖→preflight 敏感→确认）。**2026-09-20 追注（P7a-0）**：原表述里「write 新建→**直连**」一项已作废——新建现在同样走确认链（`07` §6.1/§6.3）。场景文件本身仍**不改**（步骤与 `expect` 是对**行为**的断言，不依赖新建是否免确认）；口径上**必须区分两层**：`08` §2.6 的 S14 硬性行若断的是 AuditEvent / `requires_confirmation` 的工具层风险，期望值反转；若断的是 `risk_draft` 的意图层取值，仍为 `normal`（`12` §1.2 表注）。
- 真实模型 run 仍是 P6b 证据来源；本契约的通过标准是 A1–A13（脚本化）。A1 通过而 S14 真实 run 仍失败，**不构成契约未完成**——那属于模型合作度（§0.3 第 3 条），按 `08 §7` 的流程另行处理。
- **报告措辞纪律（2026-09-18 Codex 复审后加严）**：**A1–A13 全绿不等于「S14 已解决」**。在实施完成后**复跑真实 S14** 之前，`08` 报告与 `boss-report` 都**不得**出现「S14 已解决 / 已修复」的表述；真实的失败必须**保留为开放问题**（§11 第 10 项），只能写成「工具链层缺口已封闭，模型侧是否产出草案由复跑证据回答」。
- 复跑口径：三次 run，逐轮记录 `tool_call_resolution` / `reply_provenance` / `suggested_tools_count`。**通过标准不是「必须成功执行」**（那是模型合作度），而是**「不出现 `reply_provenance="executed"` 却无 `allowed` 记录的轮次，且不出现 `local_action` 轮次的自由文本回复」**——即：模型可以继续失败，但系统不能再谎报。

---

## 10. 同步清单

### 10.1 Claude（本轮同步）

| 文件 | 内容 |
|---|---|
| `requirements.md` | FR3 增三条子项：工具候选须落在运行时闭集内且参数可校验；完成性陈述只能来源于执行记录；文件类工具共用工作区边界。待澄清项区更新（该开放项已裁决） |
| `project-report.md` | §4.3、§5.1 和 §5.4 概述草案校验、能力/工具闭集与执行记录；§2.1 保留完成性陈述可溯源原则；§九记录阶段成果 |
| `01-p0a-main-loop.md` | `_handle_action` 分支表：空计划按 `reason` 分流 + `reply_provenance` 判定表落点（**2026-09-18 改正**：不是「`requires_user_confirmation` 先于空计划早返回」，而是「空计划不进确认链、有 step 才进」——见 §5.2 权威顺序） |
| `04-p3-safety-hardening.md` | §3.2/§3.4 三层校验表**增第 0 层（参数形状）**并注明唯一实现；§4.7 防线分层补「参数维度的冗余复核」+ 引用本契约；§4.6b 六条硬约束不变 |
| `07-p6a-observability-cli.md` | §2.2 `intent_final` **+4 键**、`turn_completed` **+1 键**、`dispatch_decision` reason 闭集扩展；§6 补 `file.read` / `file.list_dir` 的工作区边界与 `FILE_ERROR` 口径（现状只讲 `file.write`）；§10 决策表加行 |
| `08-p6b-evaluation-loop.md` | §2.3 S14 行补口径（风险层已闭环、工具链由 A1 覆盖、真实 run 单列证据）；§6 报告聚合增 `reply_provenance` 与迁移期对比；§9 决策表加行 |
| `05-p4-cloud-advisory.md` | **连带同步（超出上游 9 份清单，为消除跨契约矛盾）**：§1.3 允许本次问云端的绕过清单、§1.3a 资格条件、§11 验收矩阵第 6/10/11 例的判定源由 `suggested_tools` 改为 `tool_intent`；`:154` 增 2026-09-18 判定源说明 |
| `10-p6d-autonomous-escalation.md` | **连带同步**：§4.3 `proposal_gate_result` 的 `suggested_tools_present` → `local_action_proposed`、`proposal_denied_reason` 的 `none` 列表；§3.3 条件化回答第 4 个条件改为 `tool_intent == "none"` 并重写安全论证（N1 ⇒ 无草案 ⇒ 空计划）与行号引用；§7 测试项 13c/14/15 |
| `14-resolution-exhausted.md` | **连带同步**：`:32` 资格条件列举中的 `suggested_tools_present` → `local_action_proposed` |
| `clarifications.md` | 关闭「仍开放（工具名/参数键）」并保留裁决记录（§2.6 口径） |
| `CLAUDE.md` | 必读文档表增 `15-tool-orchestration-hardening.md` |

### 10.2 Codex（工程契约镜像 + 代码 + 测试）

| 文件 | 内容 |
|---|---|
| `00-core-interfaces.md` | `:193` 注释改为「JSON Schema 子集（见 15 §1.1），支持键仅 `type`/`properties`/`required`」；`§3` 工具接口块增 `ToolContext` / 两参 handler / 可选 `preflight` hook 签名；`:416-417` 的「解析归一化唯一实现」段按 `risk_draft` **同法**补工具**四**字段（`tool_intent` / `tool_call` / `tool_call_resolution` / `tool_intent_conflict` 由解析层**同一处**唯一写入，其它层不得重写，**不得用 `last_*` 旁路**） |
| `00-adapter-factory.md` | `:526-529` `TaskPlanner`（签名不变，补注「工具目录来自 `context.tool_defs`」）；`:485-503` `ControlPolicy.decide()` 增 `tool_defs`；`§3.2` 增 `IntentResolver`（schema 由 `context.tool_defs` 现算）与 `ToolContext` 说明；bootstrap：工具数上界 32 的**主防线**校验 + §1.1 注册期不变式（`CONFIG_ERROR`）；`ContextAssembler` 说明补**每轮冗余校验**（数量/重名/schema 合法性 + §1.2 目录字节上界，超限 fail-loud，**不截断**；且**不承担目录渲染**） |
| `00-error-contract.md` | `:130` `FILE_ERROR` 的 `details.reason` 闭集按 §6.2 扩展；`TOOL_PARAM_ERROR` 的作用域说明补「形状层唯一实现」；`CONFIG_ERROR` 的作用域补「工具目录越界（数量 > 32）/ 重名 / 非法 schema（§1.1）/ 目录序列化后 UTF-8 字节 > 8192（`details.reason="tool_catalog_too_large"`，§1.2）」 |
| `src/core/schemas.py` | `ToolCallDraft` / `ToolContext` 新增；`IntentCandidate` **+4 字段**（`tool_intent` / `tool_call` / `tool_call_resolution` / `tool_intent_conflict`，**同点写入**）；`MinimalContext` 删 `tool_summaries`、加 `tool_defs` |
| `src/core/intent_resolver.py` | `_INTENT_RESPONSE_SCHEMA` → `_intent_response_schema(tool_names)`（`enum` 注入 + `tool_call` / `tool_intent` 属性）；`_tool_call_or_none` + **N1–N4** 归一化，**四个结论字段由本处在同一处一次写完**（含 `tool_intent_conflict`，**不得**走 `last_*` 旁路）；提示词按 §6.4 重写工具段（**本模块是目录渲染的唯一实现**，渲染 `context.tool_defs`） |
| `src/core/context_assembler.py` | `:139-140` **删除** `_format_tool_summaries`（**不做目录渲染**——渲染归 `IntentResolver` 独有，§6.4）；只填 `MinimalContext.tool_defs`；**每轮目录校验**（数量 ≤32 / 无重名 / schema 合法 / §1.2 的目录字节上界，违例 `CONFIG_ERROR` fail-loud，**不截断**） |
| `src/core/control_policy.py` | `:230-231` / `:264` 判定源替换 + reason 改名（§2.5）；`_decide_ready` 第 1 行新分支（§3.4）；`decide()` 新参数（§7.2） |
| `src/core/task_planner.py` | 按 §4.2 重写（约 10 行） |
| `src/core/tool_validation.py`（新） | `validate_tool_call(draft, tool_defs)`（**draft 非可选**）+ `ToolCallValidation`（§3.1，**2026-09-23 起含 `instance_rejected`**）；`reason` 闭集见 §3.1。**2026-09-23 补**：同模块新增 `rejected_instance_params(arguments, tool_def, current_input=None) -> tuple[str, ...]`（上游 `16` §6.3.x 的实现，`validate_tool_call` 内部以 `current_input=None` 调用它）——**实现只有一份**，`intent_resolver` 的准入级调用点也调它 |
| `src/tools/registry.py` | `parameters` 改 JSON Schema 子集；删 `required_params`；`preflight` hook 字段；handler 两参 |
| `src/tools/builtin_backend.py` | 删两处 `file.write` 名称分支（§1.3）；删 `_missing_params`；`ToolContext` 装配；**注册期 schema 校验**（§1.1 五条不变式，违例 `CONFIG_ERROR`） |
| `src/tools/file_tools.py` | `resolve_workspace_target` 共享化；`read_file` / `list_dir` 走解析器；`_file_error` 的 reason/message 统一（§6.2）；`write_file`/`preflight_write` 改收 `ctx` |
| `src/safety/guarded_executor.py` | `execute()` 增层 3 复核（由 `ExecutionStep` 重建 `ToolCallDraft` 后调用同一 `validate_tool_call`，失败抛 `TOOL_PARAM_ERROR`）；判定顺序不变 |
| `src/main.py` | 空计划分支按 `reason` 分流（**§5.2 权威顺序**：空计划不进确认链、有 step 才进）；`tool_call_resolution` / `tool_intent_conflict` **原样转发**进 `intent_final`（**不重算**，§2.4 N4）；`reply_provenance` 判定与 `turn_completed` 落键；能力错误模板与来源声明常量；转发 `tool_defs`；`:1440-1486` 键白名单 **+4**（`intent_final`）/ **+1**（`turn_completed`） |
| `src/observability/sinks.py` | `:25-31` `intent_final` **+4**、`:57-67` `turn_completed` +1（与 `main.py` 是**两份**独立白名单，必须同时改） |
| `src/evaluation/runner.py` | summary 增 `reply_provenance` 计数、`tool_call_resolution` 分布、`suggested_tools_count` 分布、`tool_call_present` / `suggested_tools_present` 对比（谓词定义见 §8.1） |
| `scripts/p6_report.py` | §8.2 的渲染 |
| `tests/` | §9 全矩阵（A1–A13；A13 是**参数化真值表**，10 行必须整表跑，不得只挑正常路径）+ A12 的顺序探针 + §7.4 的用例改写清单（凡断言 `suggested_tools_present` 的用例改 `local_action_proposed`） |
| `scenarios/` | **无改动**（§9.12） |

---

## 11. 遗留与明确不做

| # | 事项 | 本契约的态度 |
|:---:|---|---|
| 1 | 多工具依赖编排（一个回合多个副作用） | **不做**。触发条件：出现「同一回合两个独立副作用」的真实需求，或 `multiple_proposed` 在真实 run 中出现 ≥2 次。届时才引入 `calls: list[ToolCallDraft]` 与执行顺序语义；禁止提前加 `depends_on` / 拓扑排序 / 部分回滚 |
| 2 | 完整 JSON Schema（`$ref`/`allOf`/正则/格式校验），以及 `enum` / `maxLength` / `items` 的参数级校验 | **不做**（§1.4 + 第 11 项）：校验越强，弱模型的落地率越低，而编排层的价值是「给不出就显式失败」。**但「不做校验」不等于「允许声明」**——这几个键已从 §1.1 的支持键集移出，写了就在注册期被拒 |
| 3 | 删除 `suggested_tools` | **本轮不删**（§2.5），退役条件已钉死 |
| 4 | `answered` 轮禁止完成态文本模板（更强手段） | **不做**（§5.5）——需要扫文本或关键词表，与本次的判据纪律冲突；待真实 run 出现「谎报 + 完成叙事」证据后再议 |
| 5 | `tool_defs` 设必传 | **不做**（§7.2）：漏传后果可见（`tool_catalog_absent`），非静默退化 |
| 6 | 参数默认值 / 可选参数带缺省 | **不做**：缺参数必须显式失败（§3.3） |
| 7 | `evaluation/child.py:87` 的替身通道绕过执行器（F10） | **记录在案，本轮不改**：它影响的是 P6b 观测证据的纯度，与 S14 链路无关；改动会横跨评估替身与场景运行器 |
| 8 | 工具目录的字节预算治理 | **已做**（2026-09-18 二轮复审改判，§1.2）——**但只做定值上限，不做预算系统**：初稿以「上界 32 已把提示词长度变成常量」为由不做，**该理由不成立**（Codex 复审指出）：数量有界 ≠ 目录有界，`description` / 工具名 / 属性名都没有长度上限，单个工具仍可携带极大目录。现取**定值 8192 UTF-8 字节**（两层检查、超限 `CONFIG_ERROR`、禁止截断）。**仍不做**的是按模型窗口缩放的多档预算与按工具数配额分配——那需要一个真实的窗口协商机制，本阶段没有证据支持 |
| 9 | LangChain / 专家模型 / 自进化；云端建议产生本地工具调用 | **架构约束，永不做**。云端侧新增一条断言：`ToolCallDraft` 只由解析层的 `raw_candidate` 构造（`ConsultationProposal` 的任何字段不得流入） |
| 10 | **S14 真实 run 复跑**（2026-09-18 Codex 复审补） | **本契约实施完成后必做，且结果照实记录**。A1–A13 是工程链路验收，**不能替代**真实 run 证据。复跑若仍失败：`reply_provenance` / `tool_call_resolution` / `suggested_tools_count` 三个读数定位是「模型有意图但给不出草案」（`suggested_tools_count > 0` 且 `unfulfilled`）还是「模型根本没有工具意图」（全 0 且 `answered`），两者对应完全不同的下一步（提示词工程 vs 需求层重新评估），**不得合并成一句「S14 还是没过」**。在复跑出结果前，`boss-report` 与 `08` 报告只能写「工具链层缺口已封闭」，不得写「S14 已解决」（§9.12） |
| 11 | `enum` / `maxLength` / `items` 的参数级校验 | **不做，且已移出 §1.1 支持键集**（声明了就必须校验）。将来若要支持，走「先加校验、再加进支持键集」的顺序，不得反向 |

---

## 12. 决策记录

| 日期 | 决策 / 发现 | 处理 |
|---|---|---|
| 2026-09-18 | S14 连续 4 次真实 run 失败，`tools.executed = 0` | **立项**：根因是编排链路缺「结构化工具调用」，不是 `file.write` 的缺陷；拒绝打补丁式修法（§0.1） |
| 2026-09-18 | 发现 F7：空计划分支早返回先于 `requires_user_confirmation`（`main.py:792-800`） | **采纳为硬约束**：I1–I5 + 分支顺序重排（§5.2）——这是「策略要求被 App 吞掉」，比「模型漏给工具」更硬 |
| 2026-09-18 | 契约形态 | **采纳**：新增独立薄契约 `15`（改动横跨 5 处，扩写任一既有模块都会让它成为「别处的规范」；沿用 11–14 先例） |
| 2026-09-18 | `ToolCallDraft` 的位置 | **采纳**：落在 `IntentCandidate` 内（下游唯一载体 + 解析层是唯一归一化点 + 与 `ConsultationProposal` 对称）；不新开 Resolver 输出 |
| 2026-09-18 | 参数校验的分工 | **采纳三层/一份实现**：形状层是 Core 纯函数三处调用；语义层留在各后端 preflight（即插即用的必要适配）；执行层做同规则冗余复核，与 `04 §4.7` 的防线分层同构 |
| 2026-09-18 | 操作型请求但无草案 | **不采纳** ASK_USER（缺的是系统能力不是用户信息）与重解析一次（`10 §` 的「对已观测问题零收益的改动不予授权」；S14 4/4 表明多问一次不提高弱模型命中率）。采纳：确定性能力错误 + `unfulfilled` |
| 2026-09-18 | `suggested_tools` | **保留但降级为纯观测字段**（删字段的连带成本高、观测价值真实）；两处判定源替换为 `tool_intent`；源码级断言 + 退役条件钉死 |
| 2026-09-18 | 自审发现：§2.5 的退役条件与 §8.2 的迁移期对比写在**没有任何事件载体**的 `suggested_tools` 上——`src/` 内该字段只进 `IntentCandidate`，从不落任何事件，实现者将被迫自造口径 | **补 `intent_final.suggested_tools_count`（int ≥ 0，计数不是内容）**，并把两个派生谓词（`tool_call_present` / `suggested_tools_present`）的定义钉死在 §8.1。代价是一处键白名单（`main.py` + `sinks.py`）从 +3 变 +4；不补的代价是一条**永远无法判定**的退役条件 | **不做「取第一个」**：无确定性依据，与 boss 的 32768「不做字段优先级截取」裁决同构；一律 `unfulfilled` 并记观测，作为未来立项的证据触发器 |
| 2026-09-18 | 单工具 v1 的兼容空间 | **采纳**：`ExecutionPlan.steps` / 逐 step 执行 / 审计结构一律不动（本就兼容多 step）；禁止隐式合并；多工具语义留到有证据时立项 |
| 2026-09-18 | 完成性陈述的判据 | **采纳结构化三值**（读 `reason` / `steps` / `verdict` 三个确定性事实），明确**不用**中文词表、**不扫**回复文本；机检形式 = 标签断言 + 模型替身调用计数 |
| 2026-09-18 | 模型谎报 `tool_intent="none"` | **照实声明为残余风险**（§5.5）：本阶段结构上不可证伪；处置为「系统的嘴保持诚实」+ 观测 + 记录更强手段，不提前实现 |
| 2026-09-18 | `clarifications.md:58` 的开放项「显式匹配已注册工具且参数齐全时是否必须输出精确工具名与参数键」 | **裁决**：**不要求模型「必须」**（软约束无法强制）；要求的是——模型不产出时**系统必须显式失败**。手段三条：提示词把完整目录摆到模型眼前（概率）、响应 schema 注入 `enum`（概率）、解析层后置校验（权威）。三条合力下，「模型乱写工具名/参数」不再可能产生副作用，也不再可能被自然语言回答掩盖 |
| 2026-09-18 | **Codex 复审阻塞 ①**：`tool_call_resolution` 在归一化后丢失——未知工具/畸形/多草案都变成 `tool_call=None`，下游分不出 `unknown_tool` 与真正的 `tool_call_missing`，§3.3 分支表、A3、`intent_final.tool_call_resolution` 全落不了地 | **采纳**：`IntentCandidate` **+3 字段**，归一化结论随候选携带（与 `risk_draft_resolution` **同法**）；`validate_tool_call` **不再接收 `None`**（那是解析层职责）；`invalid_shape` **独立成新 reason `tool_call_invalid_shape`**（不与 `param_invalid` 合并——成因与将来的修法不同）；消费侧顺序钉死为「先读 resolution、再验草案」 |
| 2026-09-18 | **Codex 复审阻塞 ②**：§1.1 宣称支持 `enum`/`maxLength`/`items`，§3.1 只校验必填/未知键/类型——**声明的约束被系统静默忽略** | **采纳缩小支持集**：v1 支持键 = **实际校验的键**（`type`/`properties`/`required`），**其它键注册期一律拒绝**（`CONFIG_ERROR`，不写「忽略」）。理由：这与本次要修的「静默退化」是同一类问题。补注册期不变式五条（根 object、properties 为映射、required 为字符串列表、工具名非空且全目录唯一、闭集外键拒绝）。**响应 schema 的工具名 `enum` 不受影响**（那是编排层自造，不是工具作者的 `parameters`） |
| 2026-09-18 | **Codex 复审阻塞 ③**：初稿要求「空计划分支**必须先判** `requires_user_confirmation`」，与其后「空计划按 reason 分流」自相矛盾，会产生「确认一个空计划」+ 空 pending 状态 | **撤回初稿论断**（F7 的措辞一并改写）。采纳正确顺序：计划非空才进确认链；空计划按 reason 分流（能力错误 / 正常回答），**不进确认链**，并加硬断言（A11）「空计划轮不得产生 pending confirmation 状态」。**F7 的真命题**是「工具草案失败不得退化成自由文本」+「早返回不区分两种空计划」，不是「空计划也必须进确认」——确认语义本就是 step-scoped |
| 2026-09-18 | **Codex 复审阻塞 ④**：§1.2 一边说「逐轮现取、新注册工具当轮可见」，一边把 32 上界只放在 bootstrap，「提示词长度恒定有界」的论证不成立 | **采纳两层检查**：bootstrap 是**主防线**、`ContextAssembler` 每轮是**冗余防线**（数量/重名/schema 合法性，违例 `CONFIG_ERROR` fail-loud，**禁止截断**），与 `04 §4.7` 防线分层同构。**不采纳「启动后冻结目录」**——那会砍掉 §4.4/A8 的扩展性语义。口径随之照实修正为「每轮被显式校验的有界量」 |
| 2026-09-18 | **Codex 复审建议 ①②**：`tool_intent_conflict` 的初定义（`tool_intent=="none"` 且 `risk_draft ∈ {sensitive,dangerous}`）不是可靠冲突信号（分析敏感材料不需要工具，两者自洽）；退役条件「两字段相等」在**零样本**时恒成立会误触 | **①重定义为 N4**：**原始** `tool_intent=="none"` **且 原始** `tool_call` 非空（模型自相矛盾，被 N1 覆盖）；并照实承认盲区——模型完全省略 `tool_intent` 时**无法观测意图**。**②退役条件收紧**为三条同时满足：正样本 ≥1 轮、全部轮次逐轮一致、无 `tool_intent_conflict` 轮次 |
| 2026-09-18 | **Codex 二轮复审阻塞 ①**：`tool_intent_conflict` **没有数据载体**——N4 判的是原始两个字段，而归一化会改写 `tool_intent`、丢弃原始 `tool_call`，判定依据在候选构造完成后已不可复原；`IntentCandidate` 只加了三个字段，App 拿不到结论 | **采纳**：`IntentCandidate` **+第 4 个尾部字段** `tool_intent_conflict: bool = False`，由解析层与另外三个**同点写入**、App **原样转发不重算**。**明确不采纳** `IntentResolver.last_*` 旁路（Codex 亦反对）：旁路是给「与候选无关的回合级事实」用的，本条是**候选级**事实，会用两种携带方式表达同一类事实 | 
| 2026-09-18 | **Codex 二轮复审阻塞 ②**：`tool_defs=None` 分支未进 §3.4 伪代码——`validate_tool_call(candidate.tool_call, tool_defs)` 会在 `tool_catalog_absent` 之前先抛**原生 `TypeError`**（默认参数允许 `None`）；§3.3 的失败表定义了该 reason，权威伪代码却不可达 | **采纳**：`tool_defs is None` 判定**提到第一位**（resolution 的成员判定与草案校验都依赖目录），并新增 **A12** 锁定「漏接线不得抛原生异常」+ 顺序探针（把判定移后必须变红）。理由：兜底路径的产出必须是**契约内失败**，不是崩溃——这正是本次要修的「静默/意外退化」的近亲 |
| 2026-09-18 | **Codex 二轮复审一致性 ③**：§5.2 的 3c「两条路径都不得出现模型自由文本」与同行 3b「`tool_intent=="none"` → 正常回答」及 A9 直接冲突 | **采纳改正**：3c 收窄为**仅 3a**（`local_action` 路径），3b 按 `answered` 规则允许自由文本。依据是 I2 的原文——它的适用域本来就是 `tool_intent == "local_action"` 的回合，不是「空计划」轮次 |
| 2026-09-18 | **Codex 二轮复审一致性 ④**：目录渲染**双源**——`§10.2` 要求 `ContextAssembler` 把 `_format_tool_summaries` 改成「完整目录渲染」，而 §6.4 规定 `IntentResolver` 渲染；删掉 `tool_summaries` 后渲染产物**没有承载位置** | **采纳改正（渲染归一）**：`ContextAssembler` **删除** `_format_tool_summaries`，只校验并写入 `MinimalContext.tool_defs`；`IntentResolver` 是**唯一**的提示词目录渲染与响应 schema `enum` 注入点。与「同一事实不得两份载体」同一条纪律 |
| 2026-09-18 | **Codex 二轮复审阻塞 ⑤**：§11 第 8 项仍以「上界 32 已把提示词长度变成常量」为由拒绝字节治理——**不成立**（数量有界 ≠ 目录有界，`description`/工具名/属性名无长度上限） | **采纳**：§1.2 增**定值** 8192 UTF-8 字节上界（序列化后计，两层检查、超限 `CONFIG_ERROR`、**禁止截断**），与逐轮 fail-loud 一致；§11 第 8 项由「不做」改判为「已做（定值上限），仍不做预算系统」 |
| 2026-09-18 | **Codex 二轮复审小修 ⑥**：`project-plan §4.2` JSON 示例漏 `"tool_call_resolution": "resolved"`（下方文字已解释但示例未同步）；`08 §2.6` 退役条件仍只写「连续三次逐轮相等」；A7 写「3 工具 × 3 路径 = 9」而实际列了 5 种形态；A10 基线写 568 | **全部采纳**：示例补键；`08 §2.6` 补「≥1 正样本 + 无 `tool_intent_conflict`」；A7 改为 **15 组**；A10 基线改为 **569**（经 `pytest --collect-only -q` 核验） |
| 2026-09-18 | **Codex 三轮复审阻塞**：§2.4 的 N1/N2/N3 是**三条并列规则**，对「给了合法草案但**省略** `tool_intent`」这一输入，N1（草案存在 ⇒ `local_action`）与 N3（键缺失 ⇒ `none`）**同时命中且结论相反**——契约级歧义（未知工具 / 畸形草案同样触发 N2 与 N3 冲突） | **采纳：改为严格有序的单一过程**。步骤 1 只归一化原始 intent（合法值保留 / 缺失 → `none` / 非法值 → `local_action`）；步骤 2 草案覆盖（`resolution != "absent"` ⇒ 强制 `local_action`，即 N1+N2）；步骤 3 仅 `absent` 时保留步骤 1 结论。**顺序钉死只消除歧义、不改变任何输入的结果**（原 N1 对第 1 行的结论就是 `local_action`）。并补 **§2.4 真值表 10 行**与 **A13**（参数化整表断言） |
| 2026-09-18 | **Codex 三轮复审**：N4 的「原始 `tool_call` 非空」用词会被实现成 Python truthiness——`{}` / `[]` / `""` 这些**明确提交了的畸形草案**会被判为假而**漏记冲突**，恰是最该观测的那类样本 | **采纳**：判定式改为「**键存在且值不为 `null`**」两侧都是「明确性」而非「内容丰富度」；显式 `null` 不算提交（§2.3 表：与键缺失同归 `absent`）。A13 第 5 行用 `[]` 与 `{}` 各跑一次作为探针 |
| 2026-09-18 | **Codex 三轮复审小修**：`project-plan` 的 `ControlPolicy` 输入只写「含 `tool_intent`/`tool_call`」；A12 末行说「`context.tool_defs` 缺省时 `resolution != "resolved"`」**不准确**——resolution 是**候选**字段，与 `context` 目录是否为空无关 | **全部采纳**：`project-plan` 补全为四字段并指向 `15` §2；A12 末行改为「**空目录进入校验后确定性返回 `unknown_tool`、不抛原生异常**」，并明确它与 `tool_catalog_absent` 是**两个不同的故障**（解析层算出的闭集里没这个名字 vs App 根本没给目录），不得合并 |
| 2026-09-18 | **Codex 复审建议 ③④**：`project-plan §4.2` 的 `IntentCandidate` 示例未同步；A1–A11 全绿不得被读成「S14 已解决」 | **③已同步** `project-plan §4.2` 示例与字段说明。**④加严**：§9.12 增报告措辞纪律（复跑前不得出现「S14 已解决」）+ 复跑口径（通过标准是「系统不再谎报」而非「模型必须成功」）；§11 新增第 10 项把真实 run 复跑列为必做与开放问题 |
| 2026-09-19 | **Claude 代码审查必改 ①**：`dispatch_decision.reason` **越出闭集**——`ControlPolicy._decide_ready` 把 `validate_tool_call` 的 `param_type` / `param_unknown_key` 原样写进 `NextAction.reason`，`main.py` 再原样落事件，而 §3.3/§8.1 只认 `param_invalid`（该值当时在 `src/`、`tests/` 内**均为 0 处引用** ⇒ A4 ②③ 既无实现也无断言） | **采纳，在 `ControlPolicy` 边界映射**：`param_missing` / `unknown_tool` 保持原样，其余任一失败 → `param_invalid`；**校验器自身的命名空间**（§3.1 的 `param_type` / `param_unknown_key`）不变、**不得**直接进事件；`offending` 的断言落在校验器层（不进事件白名单）。A4 ②③ 随本条改口径并补事件级断言 |
| 2026-09-19 | **Claude 代码审查必改 ②**：`_preflight_target` 只捕 `ToolError`——含 NUL 的路径在 `Path.resolve()` 抛 `ValueError` 逃出 preflight，App 只能退化成 `INTERNAL_ERROR`；同一输入在 `execute()` 里却得到干净的 `FILE_ERROR`（层 2 与层 3 对同一事实给出两种类别，且层 2 那条不可归因） | **采纳，并收进契约**：`resolve_workspace_target` 显式拒 NUL 且把 `resolve()` 包进 `(OSError, ValueError)` → `FILE_ERROR/path_type`；§3.2 层 2 的失败后果补第三类出口（可抛 `ToolError` → `record_denial` + `user_message` 回复、零执行、`unfulfilled`）；§6.2 的 `path_type` 行补「含 NUL / 解析失败的畸形路径」 |
| 2026-09-19 | **Claude 代码审查观察 ③⑤**：`tool_catalog_too_large` 一个 reason 同时承担「数量 > 32」与「字节 > 8192」且无诊断量；`validate_tool_call` 直接下标 `parameters["properties"]`，坏 schema 会抛原生 `KeyError` | **采纳**：`_config_error` 增诊断量（`tool_count` / `catalog_bytes`），§1.2 补「数量先判、字节后判」的顺序说明；`validate_tool_call` 先跑 `_valid_parameters_schema`，坏 schema 归入契约内失败（`param_type` → 边界映射为 `param_invalid`），与 A12「不得抛原生异常」同源 |
| 2026-09-19 | **Claude 代码审查观察 ④**：`MinimalContext.tool_defs` 默认 `()` 而非 `None`，App 每轮必写并原样转发 ⇒ 运行期 `tool_defs is None` **不可达**，「忘接线」表现为空目录 → `unknown_tool`，归因指向模型而非接线 | **采纳「照实写明」而非改接口**：§7.2 补运行期口径（`tool_catalog_absent` 只覆盖显式 `None`；空目录 → `unknown_tool`），并要求报告侧知道 `unknown_tool` 计数可能混入接线缺陷。**不采纳**把 `MinimalContext.tool_defs` 改成可空——空白名单本就是合法运行态，新增状态没有证据支持 |
| 2026-09-19 | **Claude 代码审查自审追加**：§8.2 要求报告出「`unfulfilled` 轮次列表（**含 reason**）」，但 `07 §2.2` 的落盘分级把 `dispatch_decision.reason` 定为**整键不落盘**（`JsonlEventSink._project_data` 显式 `pop`）——报告读 JSONL，**这条要求不可实现**（`runner.py` 也确实没读 `reason`，改读 `action`） | **采纳改正**：§8.2 删「含 reason」，改为由已落盘键派生（`reply_provenance` + `action` + `tool_call_resolution` + `suggested_tools_count`），并**照实声明**可分辨性边界——`(PLAN_LOCAL, resolved, unfulfilled)` 在运行期实际等价于 `param_invalid`。要恢复逐 `reason` 聚合必须先在 `07` 立新落盘键，**不在本契约内私加**（同一纪律：报告不得依赖「约定上不落盘」的字段） |
| 2026-09-20 | **上游增加一层「能力相关性」（P7a，`16-p7-practical-tools-capability-routing.md`）**：老板真实试用暴露两条本契约**结构上管不到**的失败——① 本地无对应能力时既不说「没有这个能力」、也把问题送云端换回编造的实时数据；② 补全参数后调用了 `system.echo`（目录里结构合法、但语义无关）。本契约的判据只有形状/成员/参数，**对「该不该有草案」没有任何判据** | **采纳（分界写清）**：相关性权威归 `16`（注册表的**集合隶属**），本契约**不改判据、不加词表**。落地形态：① §3.3 增「上游多一层」说明——能力开启时 `_decide_ready()` 顶部的能力检查**早于**本节 `tool_intent=="local_action"` 分支，`capability_unavailable` **不在**本节 7 值表内；`irrelevant_tool` / `unrouted_tool` 两行**只在能力开启时可达**；② §5.3 能力错误模板**增「不可用」变体**（原因类别 = **能力缺失**，不是「模型没给出草案」——两者文案不得混同）；③ **反查映射是红线**（`16` §2.4）：不得用「工具名 → 能力」反查给无归属草案补归属，漏接线的方向必须是**诚实失败而非放行**；④ **关闭时本节逐字不变**（`16` §9.1 第 1 条的逐字段相等）。本节 §11 第 1/10 项**继续开放**（多工具编排；S14 真实 run 复跑）——P7a 不改变这两条的触发条件与态度 |
| 2026-09-23 | **上游 `16` 新增「准入级（实例性）」参数校验**（`16` §6.3.x，S18 真实 run 的直接后果：模型把用户整句填进地点参数，而本契约的三层校验**都放行了**——层 1 只判形状/成员/必填/类型，「这个值是不是该参数的有效实例」**不在判据内**） | **采纳（只加一个归因位，不加判据）**：① `ToolCallValidation` **+1 字段** `instance_rejected: tuple[str, ...] = ()`（默认空 ⇒ 既有断言与构造点零改动）；② 本函数内部以 `current_input=None` 调用上游的 `rejected_instance_params(arguments, tool_def)`（**唯一实现住 `16` §6.3.x，本节不复写**，且**不得**在本节引入任何领域词表）；③ 校验内容第 3 项补「被剔除的键视为不存在」；④ **不新增 `reason` 值、§5.3 不新增模板**——该形态的终态是**追问**（`param_missing` 的既有语义），不是失败；⑤ **判据的边界**：本条只做「域谓词 + 视为缺失」，**「值等于用户整句」这条通用规则不在本节生效**（补参消费路径上 `current_input == value`，套它会误伤正确答案——上游 §6.3.x 第 2 条）；⑥ **关闭时本节逐字不变**（能力层不参与 ⇒ 天气工具不注册 ⇒ 谓词不存在） |
