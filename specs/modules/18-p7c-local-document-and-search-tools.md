# 18-p7c-local-document-and-search-tools — P7c 本地文档读取、工作区搜索与只读结果回流契约

> 状态：🔧 实现中（2026-09-28 实现审查未通过，待修；审查见 `specs/reviews/18-p7c-implementation-review.md`）
> 性质：P7c 编码前必读。
> 上游：`15`（工具定义 / 参数校验 / 路径安全）、`16`（能力路由 / 注册期不变式）、`17`（外部工具权威归属 / 子进程纪律 / 外部文本零进提示词）、`07`（可观测性 / 显示净化的唯一实现点）、`00-error-contract`、`00-adapter-factory`。
> **2026-09-27 老板审查后重写**：本文件的前一版把 P7c 的目标写成「提取并显示文档原文」，四个阻塞项见 §0.4。**本版是修订版**，四项全部采纳（含一项改为必须实现）。

---

## 0. 裁决摘要

### 0.1 本阶段做三件事

| # | 事项 | 类型 |
|:---:|------|------|
| 1 | `document.read`：读取工作区内**一份**文档（PDF / DOCX / XLSX / PPTX / TXT / Markdown），返回**带来源定位**的有界结构化文本 | 只读工具 |
| 2 | `file.search`：在工作区内按**文件名**或**文本内容**搜索，返回匹配位置与有限上下文 | 只读工具 |
| 3 | **只读工具结果回流层**（§1）：由**本地模型**基于「原始用户请求 + 有界工具结果」生成最终回答 | 编排层新增一段 |

**第 3 项是本版新增的、也是本阶段真正的难点。** 没有它，前两项只是「把文档原文打印到终端」：工具结果经 `ResponseBuilder.build()` 以**固定 4096 字符**截断后**直接作为用户可见回复**返回，**模型全程看不到工具结果**（现状证据见 §1.1）。因此「总结这份 PDF」「根据文档回答问题」在结构上不可能完成——`max_returned_chars = 40000` 也失去意义。**老板裁决：做回流层**（§0.4 第 1 项）。

### 0.2 明确不做（七项）

| 不做 | 理由 / 上游依据 |
|------|----------------|
| 通用 `web.search`（Tavily / SearXNG / 任何搜索 provider 与 API Key） | `16` §11 第 2 项：搜索是**独立能力**，不能由「云端大模型」冒充。本阶段**不引入任何联网搜索**，配置侧不得出现搜索 provider 键 |
| 任意 URL `web.fetch` / 网页抓取 | `16` §11 第 1 项 |
| OCR、扫描型 PDF 的文字识别 | 需模型权重与第二条重依赖链，与 NFR1（16GB 内存）冲突；本阶段**照实告知不可读**（§4.6 行 5） |
| 文档编辑 / 写入 / 格式转换 | 与 `file.write` 侧副作用面重叠 |
| 内容索引 / 向量化 / 增量索引 | `03`（P2 记忆）已拥有检索面；引入第二套索引会造成「同一份内容两处留存」 |
| 旧格式 `.doc` / `.xls` / `.ppt` | 需另一套（OLE2）解析库；本阶段**明确拒绝**并告知（§4.6 行 6） |
| **回流层扩展到副作用工具 / 外发工具** | §1.3 的 RD2/RD3 把它变成**注册期不可达**，不是策略 |

**另有一项刻意不改**：**不修改 `weather.current` 的任何行为**（`ToolDef`、`provider`、出站三级校验、`16` §5.5 全部逐字不变）。特别地，它 `egress=True` ⇒ 按 RD3 **永久不进回流**（§1.3）。

### 0.3 必须照实说的事（八条，不得宣称已覆盖）

1. **「支持 PDF/DOCX/XLSX/PPTX」的成立范围受依赖安装状态约束**。本版已按老板裁决把四个解析库列为**正常依赖**（§6）；`parser_unavailable` 分支**仍然保留**，但它覆盖的是**安装损坏 / 部分安装 / 打包剥离**，不是「我们设计成可选所以常见」。报告不得把「工具已注册」写成「这些格式已支持」。
2. **无 OCR ⇒ 扫描型 PDF 是覆盖率天花板**，不是 bug。必须计为**未覆盖**。
3. **回流层是概率缓解 + 结构约束的混合体，不是「注入已解决」**。结构性成立的是「**注入不能产生动作**」（§1.5）；**注入能改变用户读到的文字**这一点无法结构消除，登记为残余（§14 第 12 项）。**不得**表述为「文档内容已安全」。
4. **回流的输入预算是字符预算，是对 token 预算的粗略代理**（§1.4）。模型上下文不足时会发生什么，取决于模型自身；本契约只保证「我们发出去的数据不超过 `[reflow].max_chars`」。
5. **`file.search` 的内容搜索在两引擎之间只保证「候选发现」不同、「结果产出」相同**（§5.5），且**逐字节相同**只对 UTF-8 文本夹具成立（§12.3 F7）。
6. **回流没有独立的延迟上界（2026-09-27 二轮新增，据实登记）**：回流**沿用模型后端自身的超时**（§1.6），默认 120 s 是**后端构造值**，不是回流为"总结一份文档"设定的预算。因此本契约**不承诺**任何单次回流的耗时上限，也**不得**在报告里把它写成"有超时保护"。缩短它需要一次 `ModelBackend` 接口变更（§14 第 21 项），**不得**用线程等待事后放弃来伪造。
7. **确认路径的回流输入「验证过」的范围只到它的可观测后果（2026-09-27 三轮新增）**：评估场景跑真实本地模型，能观测的只有**事件**与**输出文本**——提示词是发给模型的**私有输入**，既不进事件也不进持久面（否则会绕过 P4 的"确认回合不留存原文"）。因此 **S20 通过证明的是**「确认口令没有出现在用户可见输出里」，**不是**「回流提示里装的是原始读请求」；后者只由 **R16**（替身模型捕获提示）覆盖。**不得**把"S20 通过"写成"确认路径的回流输入已在真实 run 里验证过"。
8. **单元验收全绿不等于生产装配已接线（2026-09-27 四轮新增，据实登记）**：`App.__init__` 的 `reflow` 是**带默认值的追加参数**，而 R1–R18 都可以用"**直接构造 `App(reflow=替身)`**"满足 ⇒ **R1–R18 全绿与"生产环境启用了回流"之间没有蕴含关系**。这条蕴含关系只由 **R19**（走 `bootstrap()`）承担。因此**不得**把"回流层验收通过"写成"文档总结功能在生产配置下可用"——除非 R19 同时为绿。这也是一条**通用纪律**：凡新增的是带默认值的可注入组件，"接口加了参数"与"装配处传了参数"必须分别验收（§13.3 第 1 步完成判据）。

### 0.4 老板审查的四个阻塞项与处置（2026-09-27）

| # | 阻塞项 | 处置 |
|:---:|------|------|
| 1 | **文档结果不会回流给模型** ⇒ 只能"打印一截结构化文本" | **采纳，实现回流层**（§1）。同步改「App 零变更」的结论（§11）、主流程（§1.2）与验收矩阵（§12.2，本轮为 R1–R12，**后经第二至五轮扩至 R1–R21**） |
| 2 | **`--no-ignore` + 「禁止把忽略交给引擎」自相矛盾** ⇒ ripgrep 会扫完 `.venv` 才过滤；且隐藏文件两引擎默认不一致 ⇒ F7 不可达 | **采纳**：忽略策略拆成**裁剪**与**权威过滤**两段（§5.2）；**两个引擎都跳过隐藏条目**（§5.3） |
| 3 | **软链接规则与 F11 自相矛盾**：不跟随 ⇒ 不会有候选供复检，`skipped.outside` 恒为 0 | **采纳**：拆成两条测试（§12.3 F11a/F11b）；复检明确降级为**纵深防御**并靠**注入**验证 |
| 4 | **字符上限被错误记为段数上限** | **采纳**：闭集增加 `max_extracted_chars`；`chars_extracted` 明确为"实际已提取"（**不新增 `chars_total`**，理由见 §4.2）；「至少返回一段」限定在 `extraction="ok"`（§4.2/§4.3） |
| 附 | 逐格式提取范围未钉死；OOXML 无展开上限；依赖策略推导不成立 | **全部采纳**（§4.4 / §4.5 / §6） |

### 0.5 第二轮审查的四个阻塞项与两处文字订正（2026-09-27，全部经源码核实成立）

**共同形态**：这四个问题都**不是方向性的，而是"契约写下了一个在现有代码上兑现不了的东西"**——纸上自洽、落地不成立。因此处置都是**先回到源码核对，再改契约**。

| # | 阻塞项 | 处置 |
|:---:|------|------|
| 1 | **[严重] `reflow.timeout_ms` 无法实现**——`ModelBackend.generate()` 没有调用级超时参数，Ollama 超时在构造期固定，回流拿到同一个模型引用后限不住本次调用 | **删除 `[reflow].timeout_ms`**（§1.6），回流**沿用后端自身超时**；**明文禁止**用线程/定时器"等 N 秒后放弃"（不取消底层请求 ⇒ 线程泄漏伪装成超时），以零 `threading`/`Timer`/`concurrent.futures` 导入作源级断言（R15）。调用级超时扩展登记为 §14 第 21 项 |
| 2 | **[中等] `result_delivery` 没有载体到达执行事件**——`_record_tool_events(records)` 只收记录列表，`ExecutionRecord` 无该字段；契约只说"回流要在记录事件前完成"，没说状态怎么传 | **`ExecutionRecord` 追加尾部可选字段 `result_delivery: str \| None = None`**（**本阶段第二处接口签名变更**）；回流返回 `Mapping[int, str]`（**第三轮已改为 `ReflowOutcome`，见 §0.6**），由 `_execution_records(plan, results, deliveries)` 按 **step_index** 回填。**不得按工具名**（同一计划可多次调用同名工具，R14），**不得**用列表下标当 step_index（记录列表经 `continue` 过滤，§1.2） |
| 3 | **[中等·安全边界] 回流输出净化的描述与真实链路不符**——契约称回流输出仍经 `ResponseBuilder.build()`，**实际是 `reflow()` 产出文本后直接返回** ⇒ 模型输出的净化与长度上限**从未钉死** | 把 `_sanitize_display_string` 提升为**公开 `sanitize_display_text()`**、`_DISPLAY_LIMIT` 提升为**公开 `DISPLAY_LIMIT`**；回流**输入与模型输出都**过前者、输出另截到后者（§1.4/§1.5）；**实测**替身模型返回 ANSI/`Cc`/`Cf` 字符时 CLI 捕获输出**不含**这些码点（R13） |
| 4 | **[中等·场景不可达] S20 不会实际执行 `document.read`**——该工具 `sensitive` + 需确认，而场景只有"读并总结"一步 ⇒ 首轮只停在等待确认，`tool_any` 与回流事件**永远不会出现** | 改为**四步**（identity + workspace_file → 读请求断言 `confirmation_required=true` → 「确认 <口令>」断言 `tool_any` + `result_delivery_any` → `/quit`），口径对齐 S14（§12.5）。S21 无需 identity，其首轮 `tool_any` 即"免确认"的断言 |
| 文字① | "`max_returned_chars=40000` 服务于执行记录的可审计留存"**与代码不符**——`ExecutionRecord` 只存字段名摘要，`_execution_summary` 明确 "without retaining any returned value" | 删除该说法，照实写明：**原始工具结果不持久化**、它是**执行期内存上限**、回流只消费受 `[reflow].max_chars` 限制的部分、默认口径下大部分内容随回合结束丢弃（§1.4） |
| 文字② | 契约末尾称"3 项待老板拍板"却**没有编号条目** | 补齐**带编号的 §15.1 决策表**；第 1–3 项按老板意见**当场定稿**（保持"`document.read` 需确认 / `file.search` 免确认"、当前默认上限可接受、**本阶段授权修改 `pyproject.toml`** 把四个解析库列为正常依赖），第 4/5 项开放且**不阻塞开工** |

### 0.6 第三轮审查的四个阻塞项与处置（2026-09-27，全部经源码核实成立）

**共同形态**：第一轮暴露的是"漏了东西"，第二轮暴露的是"写了兑不了现的东西"，这一轮暴露的是**契约自身的**两类缺陷——**状态在链路中丢失**（阻塞点 1）与**返回类型承载不了要求的信息**（阻塞点 2），外加一处**测试构造不出来**（阻塞点 3）和一处**上一轮的残留没清干净**（阻塞点 4）。

| # | 阻塞项 | 处置 |
|:---:|------|------|
| 1 | **[严重·状态丢失] 确认执行后拿不到原始用户请求**——`self._pending_*` 九个字段（`src/main.py:223-241`）**没有一个是原始请求**；`_handle_confirmation(passphrase, session_id)`（`src/main.py:792`）**签名里拿不到请求**；该回合的 `current_input` **就是确认口令**；而 `_record_turn("[身份确认，原文不留存]", …)`（`src/main.py:893`）是 P4 **有意**不保留原文。⇒ 确认路径回流喂给模型的会是**口令字符串** | **新增冻结载体 `App._pending_user_request`**（§1.2.3）：进入等待确认时冻结，**八条路径**经既有 `_clear_pending()` 统一清除（清理点**只有那一处**）；**必须在 `execute()` 之前**先取到局部变量——`_clear_pending()` 在 `src/main.py:881` 先于执行发生。**红线**：冻结值只作回流输入，**不得**进 episode / 记忆 / 事件 / 审计 / 云端；`_record_turn` 的占位文案**保持不变**（不放松 P4）。R16 断言"提示含读请求原文、不含口令"；S20 承担可观测侧的反面断言（口令字面量不得出现在任何用户可见输出里，`output_not_contains`） |
| 2 | **[严重·返回类型不足] `reflow()` 只返回 `Mapping[int, str]`，装不下最终回复**——`App.handle()` 需要的是**一句回复文本**，而映射只带"哪些 step 走了模型摘要" | 定义 `ReflowOutcome(display: str, deliveries: Mapping[int, str])`（§1.2.1），**失败回落返回同一个结构**；两个调用点因此可以**零分支**写成 `outcome = self._reflow(...)` → `return outcome.display`（§1.2）。`display` 三态口径：无可回流 ⇒ **逐字节等于** `output.display`；成功 ⇒ 消毒+截断后的模型输出；失败 ⇒ 确定性回落文本 |
| 3 | **[中等·测试构造不出来] R14 的原夹具不可能存在**——`result_delivery` 是 **ToolDef 级**的固定声明，同名工具的两个 step **声明必然相同** ⇒ 构造不出"两个同名 step 声明不同"的计划 | **先钉死多 step 策略**（§1.2.2：**每回合至多一次**回流模型调用，覆盖全部 `model_summary` 成功步骤 ⇒ 覆盖集内取值必然相同），据此**改写 R14**：直接对 `_execution_records(plan, results, {1: "model_summary"})` **注入映射**，构造**两个同名 `document.read` step**，断言 **step_index=1 有值、step_index=0 为 `None`**（并含越界/被过滤臂）。这把断言对象从"计划能否构造"改成"**回填会不会按工具名串写**"，与实现无关地可证伪 |
| 4 | **[中等·残留] `00-adapter-factory.md` 仍把 `timeout_ms` 列为 `[reflow]` 合法键**——第二轮删了 `18` 的键、漏了工程契约镜像 | 该处改为**仅 `enabled` / `max_chars`**，并写明"**没有 `timeout_ms`**"及其理由（模型接口无调用级超时），与 §9.1 / §1.9 三处一致 |

### 0.7 第四轮审查的一个阻塞项与处置（2026-09-27，**接线遗漏，经源码核实成立**）

**形态**：前三轮修的分别是"漏了东西""写了兑不了现的东西""状态与类型承载不了要求"，这一轮是**契约内部两处规定互相不接**——一处说"`App` 增加 `reflow` 参数"，另一处（示范的 `bootstrap()` 代码）**既不构造它、也不传它**。

| # | 阻塞项 | 处置 |
|:---:|------|------|
| 1 | **[严重·接线遗漏] `bootstrap()` 示范代码没有构造与注入 `ResultReflow`**——`00-adapter-factory.md` 的 bootstrap 示例在 `response = ResponseBuilder()` 之后直接 `return App(...)`，`App(...)` 的参数里**没有** `reflow=`。而 `App.__init__` 的新参数带默认值 `None` ⇒ **实现照此写就能通过所有类型检查并正常启动，但生产路径上回流永不发生**：白名单里的 `document.read` 声明了 `model_summary`，却只能"打印一截结构化文本"，「总结这份文档」仍然不可用（§1.1 的缺口原样复现）。**更危险的是它不易被发现**：单元测试通常**直接构造 `App(reflow=替身)`**，于是 R1–R18 全绿，缺陷只存在于真实装配路径上 | ①`00-adapter-factory.md` §3 的 bootstrap 示例**新增 2.5 段**：`normalize_reflow_config(config.get("reflow", {}))` → 构造 `ResultReflow(backend=model_backend, enabled=…, max_chars=…)` → 作为 `reflow=` 传入 `App`（**该构造的实参在第五轮补入 `tool_defs`，以 §1.2.4 为准**）；②`App.__init__` 的签名块补上 `reflow`（**追加置尾 + 默认值**，与 `event_sink` / `run_id` 同法）；③口径订正：**"`bootstrap()` 步骤零新增"作废**，准确表述是"**签名零变更，但装配步骤有新增**"（§11.1 / §13.1 / §13.2 / §16 同步）；④**新增 R19**——**必须走 `bootstrap()`** 断言返回的 `App` 实际持有一个**启用**的回流组件、且端到端（读请求 → 确认 → 执行）**替身模型确实被调用**。**探针 = 删掉构造与传参 ⇒ R19 红，而其余 R 条目仍可能全绿**（这正是本条存在的理由）；⑤`[reflow]` 的键集闭集与默认值**只有一处实现**（`normalize_reflow_config()`，住 `src/main.py` 配置解析区），工具后端侧判定跨表不变式时调用**同一个函数**，不得各写一份默认值 |

**这一轮的方法论教训（写进 §13.3 的完成判据）**：**"接口加了一个参数"与"装配处传了这个参数"是两件事**。凡新增的是**带默认值的可注入组件**，都必须同时钉住**构造点**与**注入点**，并给一条**只走真实装配路径**的验收条目——否则默认值会把缺失伪装成可选项。

### 0.8 第五轮：Codex 在 RED 阶段提出的两个契约级输入缺口（2026-09-27，**经源码核实成立**）

**形态**：前五轮的驱动方都是老板审查；这一轮是**实现方在写第一条测试之前**撞到的——契约给出的 `self._reflow(plan, results, original_request)` **缺少两项必需输入**，而这两项都**无法从实参里推出来**。

| # | 缺口 | 源码事实 | 处置 |
|:---:|------|------|------|
| 1 | **判不出哪些 step 声明了 `model_summary`** | `ExecutionStep`（`src/core/schemas.py:471-482`）只有 `tool_name`/`action`/`params`/`risk_level`/`intent_type`/`entities`/`user_input`/`gate23_passed`/`approval_profile`——**没有 `result_delivery`**；声明在 **`ToolDef` 级**（注册期固定），而 `plan` 与 `results` 里都不带 `ToolDef` | **`ResultReflow` 构造期冻结工具目录**（§1.2.4）：`tool_defs=tool_backend.list_tools()`。**不得**给 `ExecutionStep` 加字段（那会变成第三处签名变更，且要求计划构造方也拿到目录——把注册期事实复制进每一条步骤） |
| 2 | **产不出"无可回流/回流失败"时的确定性回复** | 两态都要求 `display` **逐字节等于** `ResponseBuilder.build().display`（§1.2.1），而该值**只有调用点手里有**（`output.display`），回流组件无从取得 | `__call__` 增参 **`fallback_display`**（本回合数据，**调用时传入**）：`self._reflow(plan, results, original_request, fallback_display=output.display)`。⇒ 回流层**永不合成**回落文本，两态共用同一份字节，二者仅由 `deliveries` 区分（§1.2.1） |

**顺带核实出的一处契约措辞错误（同样是实现会撞到的）**：多轮文本里的覆盖集判据写作"`outcome == "success"` 且声明 `model_summary` 的 step"，但 **`GuardedToolExecutor.execute()` 在任何失败上都 `raise`**（`src/safety/guarded_executor.py:67-266`：未注册 / 参数被拒 / `dangerous` / `high_impact` / 敏感未确认 / 策略拒绝 / 工具返回错误，七条路径全部抛错），`results` 里**只会有成功步骤**——`_execution_records` 里的 `outcome="success"` 是**硬编码**（`src/main.py:1825`）。⇒ **"成功"是构造性事实，不是运行时判据**；实现者若去找"成功标志"会**找不到**（结果 dict 里没有该字段）。全部相关表述已改为"`results` 中出现的 step"，并据此修正 R17 臂③（§1.2.2 / §12.2）。

**新增两条验收**：**R20**（同一回合的 `result_delivery` 在**事件面**与 **episode 面**取值一致——`_execution_records` 在本回合有**三个**调用点：`src/main.py:885`、**`:893`**、`1020`，前版契约只说"两个调用点"，`:893` 是漏掉的那个）、**R21**（执行抛错 ⇒ **零回流、零 `result_delivery` 键**；部分成功的中间结果**不得**被事后回流——它连 `output` 都没构造）。

---

## 1. 只读工具结果回流层（本版新增）

### 1.1 现状证据（为什么这是一个真缺口，不是优化）

`src/main.py:1013-1021`（直连路径）与 `src/main.py:882-886`（确认后消费路径）：

```python
results = self.executor.execute(plan, task_id=task_id, intent_id=intent_id)
output = self.response.build(plan, results)
self._latest_narrative_reply = output.narrative_reply   # ← 常量字符串
return output.display                                    # ← 直接作为用户可见回复
```

`src/core/response_builder.py`：

```python
_DISPLAY_LIMIT = 4096          # ← 本阶段要求提升为公开 DISPLAY_LIMIT（§1.4/§1.5）
...
return ResponseOutput(
    display="\n".join(lines),
    narrative_reply=f"执行结果 {len(results)} 条，已以结构化记录留存。",   # ← 无模型调用
)
```

**结论（结构性事实，不是观感）**：

- 工具结果**只经 `ResponseBuilder` 文本化 → 截断 4096 字符 → 返回**；整条路径上**没有任何一次模型调用**。
- 模型看不到工具结果 ⇒ 无法总结、无法基于文档回答、无法把搜索结果组织成答案。
- 写入类工具的这个形态是**正确**的（执行成功与否不能由模型改写）——但把它无差别地用在**只读大结果**上，等于交付一个**没有 Agent 的文档能力**。

### 1.2 唯一实现点与两个调用点（钉死）

**新增 `src/core/result_reflow.py`，且回流只有这一个实现点。** `main.py` 的**两个** `self.response.build(plan, results)` 调用点（`src/main.py:884` 与 `src/main.py:1018`）**都必须走同一个共享函数**——否则「确认后消费」与「直连」两条路径的行为会分叉（`15` §6.3 的三路径对齐纪律对回流同样成立）。

**顺序要求（钉死，实现细节但影响可观测性）**：

```
execute() → response.build() → **reflow()** → _record_tool_events() → return
```

回流必须在 `_record_tool_events()` **之前**完成，使 `result_delivery` 能落在**同一条** `tool_execution` 记录上（§10.1）。两个调用点都要按此顺序调整。

> **别把两个"调用点计数"搞混（第五轮明确）**：**`response.build` 是两个调用点**（`src/main.py:884`、`1018`），**而 `_execution_records` 是三个**（`:885`、**`:893`（episode 用）**、`1020`）——确认路径上一次执行写了两份记录（事件面 + episode 面）。`outcome.deliveries` 必须传给**本回合的每一个** `_execution_records` 调用点（R20），否则会出现"事件说回流了、会话记录里却是空的"这种同一事实两处不一致。

**状态载体（钉死，2026-09-27 审查后补充）**：前版只说"顺序要对"，**没说状态怎么传过去**——而现有 `_record_tool_events(records: list[ExecutionRecord])` 只收记录列表，`ExecutionRecord` 上**没有** `result_delivery` 字段（`src/core/schemas.py:501-509`；`00-adapter-factory.md:755` 同步）。**必须按 step_index 关联，不得按工具名关联**——同一计划可以**多次调用同名工具**（例如一次计划里两个 `document.read`），按名字关联会把两条记录写成同一个状态。钉死为：

| 环节 | 形态 |
|------|------|
| 1. `reflow(...)` | 返回 **`ReflowOutcome`**（见下），其中 `deliveries: Mapping[int, str]` 是 **step_index → `"model_summary"` / `"model_summary_failed"`**。**未参与回流的 step 不出现在映射里**（不是填 `"deterministic"`） |
| 2. `ExecutionRecord` | 新增**尾部可选字段** `result_delivery: str \| None = None`（追加式 + 默认值 ⇒ 既有构造调用零改动，与 `ToolDef.egress` 同法）。**属接口签名变更，已同步 `00-core-interfaces.md` 与 `00-adapter-factory.md`** |
| 3. `_execution_records(plan, results, deliveries)` | 构造每条记录时按 **step_index** 取 `deliveries.get(step_index)` 写入该字段（函数**新增一个参数**） |
| 4. `_record_tool_events(records)` | **签名不变**：读 `record.result_delivery`，**`None` ⇒ 不发该键**（§10.1 的条件键语义） |

**为什么不把 `deliveries` 直接传进 `_record_tool_events()`（钉死）**：`records` 是 `list`，而 `_execution_records` 内有 `if not 0 <= step_index < len(plan.steps): continue`（`src/main.py:1818-1819`）的过滤 ⇒ **列表下标与 step_index 不保证相等**，用 `enumerate` 去对齐是一个**隐式假设**。把状态写在记录上，则"每条记录自带它的投递状态"，与步骤一一对应是**构造性事实**——这正是 `15` 反复采用的"让错误状态不存在"的手法。

#### 1.2.1 `reflow()` 的返回形态：`ReflowOutcome`（**本轮订正，回应阻塞点 2**）

> **前版的缺陷**：契约一边要求 `reflow()` 只返回 `Mapping[int, str]`，一边要求"它的模型输出**直接作为最终显示文本**返回"。**实现者无法知道显示文本从哪来**——这两个要求不可能同时由一个映射满足。

```python
# src/core/result_reflow.py
@dataclass(frozen=True)
class ReflowOutcome:
    display: str                      # 本回合**用户可见的最终文本**（已消毒、已按上限截断）
    deliveries: Mapping[int, str]     # step_index -> "model_summary" | "model_summary_failed"
                                      # 未参与回流的 step **不出现**在该映射里
```

| 情形 | `display` | `deliveries` |
|------|------|------|
| **本回合没有可回流的结果**（无 `model_summary` step，或 `results` 为空） | **逐字节等于** `fallback_display`（即 `output.display`：`ResponseBuilder.build()` 的产出**原样返回**，不再消毒、不再截断——它已经过那两道，重复施加只是幂等操作，但**照实写成"原样"更不容易被实现者加料**） | `{}` |
| **回流成功** | 回流模型的输出，经 `sanitize_display_text()` 消毒 + 截到 `DISPLAY_LIMIT`（§1.5） | 覆盖集内每个 step ⇒ `"model_summary"` |
| **回流失败**（异常 / 后端超时 / 空输出，§1.6） | 同第一行（回落到确定性 display） | 覆盖集内每个 step ⇒ `"model_summary_failed"` |

**两态共用同一份字节（本轮钉死）**：第一行与第三行的 `display` **都是实参 `fallback_display`**（即 `output.display` 原样）。差别**只在 `deliveries`**：第一行是 `{}`，第三行是覆盖集内每个 step ⇒ `"model_summary_failed"`。因此**回流层没有任何一处自己拼接回落文本**——它要么交出模型输出（成功），要么原样交出调用点给的字符串（无可回流 / 失败）。这让"回流失败的用户可见后果 = 与没有回流层时逐字节相同"成为**构造性事实**，而不是靠实现自觉。

**两个调用点的代码形状因此完全一致、零分支**：

```python
outcome = self._reflow(plan, results, original_request, fallback_display=output.display)
self._latest_execution_records = _execution_records(plan, results, outcome.deliveries)
self._record_tool_events(self._latest_execution_records)
return outcome.display
```

> **`fallback_display` 是本轮新增的必需实参（§0.8 / §1.2.4）**：`output.display` 是"无可回流"与"回流失败"两态要**逐字节保留**的文本，而回流组件**拿不到它**——不传就只能自己合成一段回落文本，那是**第二份确定性显示实现**，会让两条路径的输出分叉。**回流层永不合成回落文本**因此成为可断言的性质。

**为什么不做成"有覆盖集才调用"的分支**：那会把"是否需要回流"的判断**散到两个调用点**，而判据必须只有一处（`ToolDef.result_delivery`，§1.3）。函数自己判断、调用点无条件调用，"两条路径行为一致"因此是**构造性事实**。

#### 1.2.2 多 step 的回流策略（**本轮钉死，回应阻塞点 3 的前半**）

| 项 | 钉死 |
|------|------|
| **覆盖集** | `results` **里出现的每个 step**（键即 `step_index`）中，其 `plan.steps[step_index].tool_name` 在**冻结目录**里声明了 `result_delivery == "model_summary"` 的那些。**"成功"不是判据而是构造性事实**（§0.8：`GuardedToolExecutor.execute()` 在任何失败上都 `raise`，`results` 只含成功步骤；`_execution_records` 里的 `outcome="success"` 是硬编码）——**实现不得去找"成功标志"，结果 dict 里没有该字段** |
| **调用次数** | **每回合至多一次**回流模型调用，**覆盖集内所有 step 共享这一次调用**。**不逐 step 调用** |
| **取值一致性** | 一次调用只有成功或失败两种结局 ⇒ **同一回合内所有被覆盖 step 的 `result_delivery` 取值必然相同**。这不是简化，是事实 |
| **多份结果的组装** | 按 **step_index 升序**依次拼接各 step 的事实头 + 有界正文，共享同一个 `[reflow].max_chars` 预算（§1.4） |

**为什么不是逐 step 调用**：一次回合只有**一个**用户可见回复；逐 step 会产出 N 个候选回复，取哪一个都是**任意选择**，且成本随步骤数线性放大。**探针（R17）**：改成逐 step 调用 ⇒ 替身模型的调用计数等于覆盖集大小 ⇒ R17 红。

**由此 R14 必须改写**：`ToolDef.result_delivery` 是**工具级固定声明**，同一个工具不可能"这一次声明回流、那一次不声明" ⇒ 前版"一次计划里两个 `document.read`，其中一个声明回流"这一臂**构造不出来**。R14 改为**直接对 `_execution_records` 注入按 step_index 的映射**（§12.2）。

#### 1.2.3 确认路径的必需载体：冻结的原始请求（**本轮新增，回应阻塞点 1**）

> **前版的缺陷（严重）**：契约要求回流输入含"本回合用户请求"，但**确认路径上取不到它**。

**事实（源码核对）**：

- 确认链只保存 `plan` / `preflight` / `session_id` / `task_id` / `intent_id` / `topic` / `candidate`（`src/main.py:223-241` 的 `_pending_*`）——**没有任何字段保存原始用户请求**。
- 确认回合**刻意不留存原文**：`_record_turn("[身份确认，原文不留存]", ...)`（`src/main.py:889`）。
- `_handle_confirmation(passphrase, session_id)`（`src/main.py:792`）**拿不到**原始请求。

**后果**：若回流取本回合的 `current_input`，模型看到的请求是「**确认 eval-pass-0000**」——回流退化成"把工具结果贴给模型看，却不说要它做什么"，而**S20 想验证的"总结这份文档"在确认路径上恰恰不成立**（直连路径没这个问题：那里 `current_input` **就是**原始请求）。

**裁决（钉死）**：

1. **在计划进入等待确认时冻结原始请求**：`App` 新增私有字段 `_pending_user_request: str | None`（与 `_pending_plan` 同处赋值）。
2. **生命周期 = 既有 `_clear_pending()`**（`src/main.py:1530-1537`）⇒ 取消 / 拒绝 / 会话不匹配 / 口令错误 / 锁定 / 预检失败 / TOCTOU 变化 / **执行完成** 八条路径**全部自动清除**。**清理点只有一处**：在 `_clear_pending()` 内**加一行**（它当前恰好清 7 个字段，不含本字段）。这正是"让状态不存在"：清理不是八处都要记得写，而是**只有一处存在**——**不得**在各分支里各自清理。
3. **取值次序（实现必须做对）**：确认成功分支在 `execute()` **之前**就调用了 `_clear_pending()`（`src/main.py:881`）⇒ 冻结值**必须先取出到局部变量**（与 `pending_plan` / `pending_preflight` 同法，`src/main.py:856-861`），否则回流拿到 `None`。
4. **回流输入取该冻结值**（确认路径）或 `current_input`（直连路径）——两条路径语义一致：都是"**发起这次操作的那句原始请求**"。实现上统一为一个局部变量 `original_request`，两个调用点各自传对。
5. **红线：冻结值只用于回流输入**。它**不得**进入 episode / 记忆 / 事件 / 审计 / 云端材料；`_record_turn("[身份确认，原文不留存]", ...)` 的写法**保持不变**（P4 的"确认回合不留存原文"是既有安全口径，本轮**不放松**）。冻结范围是**单进程内存 + 计划存续期**，不落盘。
6. **本项目没有待确认计划的 TTL**（不存在超时清理路径）⇒ 生命周期由"下一次 `_clear_pending()`"终止。**若将来加入 TTL，冻结值必须一并清除**——登记为 §14 第 23 项。

**断言**：**R16**（单元层，替身模型捕获提示）：确认路径的回流提示**含原始读请求**、**不含确认口令**；探针 = 把 `current_input` 直接传给回流 ⇒ 红。**S20 的半句（"提示包含原始读取请求"）在场景层无法断言**——真实 run 用的是真实模型，场景只能观测事件与输出。场景层承担的是另一半可确定断言：**确认口令不得出现在任何用户可见输出里**（新增 `output_not_contains`，§12.5）。**不得**把"S20 通过"读成"回流提示词内容已在真实 run 里验证过"。

#### 1.2.4 `ResultReflow` 的构造与调用签名（**本轮钉死，回应 §0.8 的两个输入缺口**）

```python
# src/core/result_reflow.py
class ResultReflow:
    def __init__(
        self,
        backend: ModelBackend,
        tool_defs: Sequence[ToolDef],     # 构造期冻结：只提取 name -> result_delivery
        enabled: bool = True,
        max_chars: int = 4000,
    ) -> None: ...

    def __call__(
        self,
        plan: ExecutionPlan,
        results: dict[int, dict[str, object]],
        original_request: str,
        fallback_display: str,            # 本回合数据，必须由调用点传入
    ) -> ReflowOutcome: ...
```

| # | 钉死 | 理由 / 探针 |
|:---:|------|------|
| 1 | **`tool_defs` 的来源是 `tool_backend.list_tools()`**——即**活跃集**，**与 `GuardedToolExecutor.execute()` 内部构造 `registered_tools` 的来源完全同一个**（`src/safety/guarded_executor.py:60-63`） | 执行器只执行该集合内的工具 ⇒ 冻结集是**可执行工具集的超集**，查得到是必然 |
| 2 | **构造期冻结成 `Mapping[str, str]`（name → `result_delivery`），且回流层只读这一个字段** | `ToolDef` 其余字段（`risk_level` / `parameters` / `description` / `approval_profile`…）在回流层**没有任何用途**——准入与风控已由注册期与执行器负责。回流层若读它们再判一次，就是**第二份准入真源**（§1.5 结构性边界） |
| 3 | **查不到的 `tool_name` ⇒ 视为 `deterministic`（未覆盖），不抛错** | 该分支**不可达**（冻结源 = 执行器源，且 `17` 钉死只收紧不放松、不热插拔 ⇒ 冻结集只会是超集）。即便触发，回流是**呈现层**，"少一个声明"不该让一个**已经成功执行**的回合失败——**工具结果永不因回流失败而丢失**（§1.5 既有口径） |
| 4 | **`fallback_display` 是本回合数据，走调用实参**（`output.display`）；**配置期数据（`enabled` / `max_chars` / `tool_defs`）走构造期** | 二者生命周期不同：目录在 bootstrap 后固定（`17`：不热插拔），而确定性 display 每回合都不同。**不得**把 `fallback_display` 塞进构造期（那会让 `App` 需要每回合重建组件），也**不得**把目录做成调用实参（那会在每个调用点重复取目录） |
| 5 | **关态的唯一实现点是 `App._reflow()` 这一个薄包装**：`self._reflow is None ⇒` 直接返回 `ReflowOutcome(display=fallback_display, deliveries={})`；`enabled=False` 由 `ResultReflow` 内部短路（同样返回该结构） | 两个调用点因此仍写成**零分支的一行**（§1.2 的代码形状不变）。**"关态"有两种来源**（未注入 / 显式关闭），二者必须**行为等价**：`display` 逐字节等于 `fallback_display`、`deliveries == {}` |
| 6 | **`result_reflow.py` 不得导入 `src/tools/` 的任何执行或校验符号**（只消费 `ToolDef` 这个**数据类型**，它来自 `src/core/schemas.py`） | 与 R9/R10 同类：回流层是**呈现层**，它读声明、不判准入（源级断言并入 R9） |

### 1.3 判据是注册期声明，不是工具名（钉死）

新增 `ToolDef` 字段：

```python
# src/core/schemas.py —— ToolDef 的**最后一个**字段（追加式，默认值保证既有构造调用零改动）
result_delivery: str = "deterministic"      # 闭集："deterministic" | "model_summary"
```

语义：`deterministic` = 沿用现状（`ResponseBuilder.build()` 的产出即回复）；`model_summary` = 执行成功后由本地模型基于「本回合用户请求 + 有界工具结果」生成回复。

**这是一处接口签名变更（新增字段），由 Claude 主导并已同步 `00-core-interfaces.md`。**

**三条注册期不变式（fail-loud，`CONFIG_ERROR` / `details.reason="result_delivery_invalid"`）**：

| # | 不变式 | 为什么靠这个结构成立 |
|:---:|------|------|
| **RD1** | `result_delivery ∈ {"deterministic", "model_summary"}` | 闭集，取值非法即启动失败 |
| **RD2** | `result_delivery == "model_summary"` ⟹ 该工具**不在** `LOCAL_SIDE_EFFECT_TOOLS` 内 | **老板要求「写入类工具继续使用确定性结果」不是靠 App 里的 if，而是靠注册期让「让模型改写写入结果」这一状态不存在。** 未来的写工具即使误声明 `model_summary` 也起不来 |
| **RD3** | `result_delivery == "model_summary"` ⟹ `egress == False` | 回流把**工具结果送进提示词**。`egress=True` 的工具结果是**外部来源的文本**，回流会绕开 `17` 的「**外部文本零进提示词**」边界。`weather.current`（`egress=True`）因此**永久不进回流** |

**默认值 `"deterministic"` 的效果**：`file.read` / `file.list_dir` / `file.stat` / `file.write` / `system.get_time` / `weather.current` / `system.echo` 及全部外部工具的**行为逐字不变** ⇒ S01–S19 零回归、`16` §9.1 的非干扰性锚点原样成立（§12.1 N1）。P7c 只让**两个新工具**声明 `model_summary`。

### 1.4 回流输入的组装（钉死）

**输入 = 「发起本次操作的那句原始请求」 + 工具结果的结构化文本**，且**只此两项**：

- **不带**记忆检索结果、项目摘要、会话历史、云端材料、其他工具的结果（与 `15`/`10` 的最小化纪律一致）；
- 请求取**原文**（不是改写版、不是意图结论），**且必须取对来源（本轮订正，回应阻塞点 1）**：

| 路径 | 请求来源 | 为什么 |
|------|------|------|
| **直连路径**（无确认） | 本回合 `current_input` | 它**就是**那次操作的原始请求 |
| **确认后消费路径** | **冻结的原始请求 `_pending_user_request`**（§1.2.3） | 本回合 `current_input` 是「**确认 <口令>**」——用它等于**告诉模型去总结一句口令** |

两条路径在实现上收敛为**同一个局部变量 `original_request`**，各调用点各自传对；**不得**在 `result_reflow.py` 内部再去读 `App` 的字段或 `current_input`（回流模块零 App 依赖，R9/R10 的源级断言同源）。

**工具结果的组装顺序（钉死）**：

```
① 事实头（不受截断影响，整体置于正文之前）：
   tool_name、step_index、truncated / truncation_reason / segments_total
   / chars_extracted / notice、计数类字段
② 有界正文：按 max_chars 截断的 segments / results
```

**多 step 时的组装（本轮钉死，回应阻塞点 3）**：覆盖集内**每个 step 各出一组「事实头 + 正文」**，按 **step_index 升序**依次排列；每组以 `tool_name` + `step_index` 明确标注归属（同名工具两次调用因此**可区分**）。**总预算仍是 `[reflow].max_chars` 一个数**——它是**整次输入**的预算，不是每个 step 各一份；超预算时**从后往前**截断后续 step 的正文，并在事实头里写明哪些 step 被截断。**不得**平均分配、**不得**按 step 各给一份预算（那会让预算随步骤数线性膨胀，与 §1.9 的单值语义冲突）。**探针**：给每个 step 各分配一份 `max_chars` ⇒ R6/R18 红。

**为什么事实头必须在正文之前且不受截断**（这是"诚实"的结构保证）：§4.2 的 `notice` 与计数是**「我们没读全」这一事实的唯一载体**。若它被排在正文之后、又被 `max_chars` 截掉，模型就会在**不知道有未读部分**的情况下生成总结——那正是「静默丢失关键内容」在回流层的复现。**探针**：把 `notice` 移到正文之后并参与截断 ⇒ R6 必须变红。

**正文截断必须显式标注**：截断处写入固定标记，并在事实头里写明「正文已按 N 字符截断」。**不得**让模型以为它看到的是全部。

**字符预算 `[reflow].max_chars`（默认 4000）**，理由照实写明：本地模型上下文默认 4096 token（`src/models/ollama_backend.py:21`），模板本身要占一部分，因此数据预算必须**显著小于**工具自身的返回预算（`max_returned_chars`）。**字符预算是 token 预算的粗略代理**，按 token 精确切分登记为遗留项（§14 第 2 项）。

**`max_returned_chars = 40000` 的真实作用域（据实订正，2026-09-27 审查）**：

> **前版写**「`max_returned_chars` 服务于 ①执行记录的可审计留存（`_latest_execution_records` → 审计/episode）②回落显示」，**这与现有代码不符**：
> - `ExecutionRecord` **只保存字段名摘要**，不保存工具返回值——`_execution_summary()` 的文档字符串即 "Describe a tool result structurally, **without retaining any returned value**"（`src/main.py:1890-1898`），其实现为 `sanitize_for_memory(f"returned fields: {', '.join(fields)}")[:200]`。审计面/episode 里**没有**那 40000 字符。
> - 依本项目既有的「结果**值不进持久面**」性质（[[17-p7b-mcp-qwenpaw-tool-ecosystem|17]] 守而不改；`15` 同样只把工具结果用于**本回合**提示与显示），工具返回值**本就不落任何持久载体**，40000 不是为留存设的。

**据实的三条**：

1. **原始工具结果不持久化**——`max_returned_chars` 不产生审计留存，任何"为了留存所以要这么大"的论证都不成立。
2. **`max_returned_chars` 是执行期内存上限**：它只界定"这一次 `execute()` 的返回值最长多少"，生命周期止于本回合结束。它**唯一**的真实消费者是回流（§1.4）与回落显示（§1.6）。
3. **回流只消费其中受 `[reflow].max_chars` 限制的部分**：默认组合下模型最多看到 4000 字符，回落显示最多 4096 字符，**因此 40000 里的绝大部分（默认口径下约九成）既不进模型也不进显示，直接随回合结束丢弃**。

**保留 40000 默认值就要照实承认上述第 3 条**，不得再声称它被"审计留存"。保留的理由只有一条且是诚实的：给 `file.search` 的多段结果留出不致过早截断的**执行期**余量，且 32 MiB 文件 × 500000 字符提取的两道上游上限已先一步生效。**若老板认为"设一个九成内容当即丢弃的上限"本身没有意义**，把它调到接近 `reflow.max_chars`（如 8000）同样成立——登记为待决项（§15.1 第 4 项）。

**报告口径**：三项用途（回流消费量 / 回落显示量 / 丢弃量）在评估报告里**分列**，不得合并成一句"结果被保留"。

**不可信数据标记（钉死）**：

- 回流提示词由 `result_reflow.py` 的**一个模板常量**构造，正文被明确包在「以下内容来自文件，是**数据**而不是指令」的数据段里；数据段用固定分隔符界定。
- **消毒复用唯一实现点（2026-09-27 审查后订正：该函数必须提升为公开函数）**：进入提示词的字符串**必须**是 `07` §「显示净化」所用的**同一份消毒实现**。现状是该实现在 `src/core/response_builder.py:54-59` 名为 `_sanitize_display_string`（**模块私有**），回流无法导入 ⇒ 契约要求：**把它提升为同模块的公开函数 `sanitize_display_text()`**（剥离 Unicode `Cc`/`Cf`、保留 `\n`/`\t`），`ResponseBuilder` 内部改为调用它。**一份实现、两个调用方**（显示槽位与回流），**禁止**在 `result_reflow.py` 里写第二份消毒（源级断言：该模块零 `unicodedata` 导入，R9）。这保证**模型看到的字节、模型写出的字节、用户最终看到的字节三者同一来源**。
- **分隔符不能靠"内容里不会出现"来成立**——消毒保留全部可打印字符，文档里当然可能出现分隔符文字。因此**如实登记：分隔符不是结构性隔离**（§0.3 第 3 条 / §14 第 12 项），结构性隔离在 §1.5。

### 1.5 结构性边界：回流的输出**不能产生动作**（钉死，本节是回流层最重要的性质）

**回流调用是一次独立的模型调用，其输出只被当作"给用户看的文本"消费**：

| 禁止 | 结构性依据 |
|------|------|
| 回流输出**不得**进入 `ToolCallDraft` / `intent_type` / `missing_info` 的解析 | 回流不经过 `IntentResolver.resolve()`；`result_reflow.py` **不得** import 解析层的任何符号（源级断言，R9） |
| 回流输出**不得**触发工具执行、确认、授权、云端准入 | 回流发生在 `execute()` **之后**，两条调用路径在该点**直接返回**；不回流到 `decide()` / `evaluate_cloud_admission()` |
| 回流输出**不得**成为云端材料 | 同上一行；且 `result_reflow.py` **不得** import `src/cloud/` 或 `PrivacyPolicy` / `TaskBrief` 任何构造点（源级断言，R10） |
| 回流输出**不得**绕过显示净化 | **据实订正（2026-09-27 审查）**：回流成功时 `reflow()` 产生最终文本后**直接返回**，它**不会**再次进入 `ResponseBuilder.build()`——前版写"仍经 `build()` 的净化槽位"**与真实链路不符**。因此净化必须由**回流自己调用同一份公开消毒实现**（`sanitize_display_text()`，§1.4），并**对其输出施加确定的长度上限**。见下 |

**回流输出的两条落地约束（钉死，2026-09-27 审查后新增——它们补上"回流输出不进入 `build()`"留下的口子）**：

1. **消毒**：回流模型产出的文本在返回前**必须**过 `sanitize_display_text()`（§1.4 的同一份公开实现）。**为什么这仍是一条安全边界**：模型输出**可能**原样复述工具结果里的字节，而工具结果来自任意文档 ⇒ 文档里的 ANSI 转义序列有机会经"模型复述"这条路径直接落到终端。这是 `17` 已就外部工具结果立过的同一类威胁（终端注入），**不得**因为"中间隔了一次模型调用"就认为它消失了。
   **探针**：替身模型返回 `"\x1b[2J\x1b[31mFake\x1b[0m"`、`"\x07"`（BEL）、`"​"`（Cf）⇒ CLI 捕获的输出里**不得**出现这些码点；把消毒调用删掉 ⇒ R13 变红。
2. **长度上限**：回流输出**必须**施加**确定的**长度上限，取值 = **显示上限常量本身**（`ResponseBuilder` 的 `_DISPLAY_LIMIT = 4096`）。**要求把它一并提升为公开常量 `DISPLAY_LIMIT`**，使"用户可见文本的上限"在**整个项目里只有一个数**——回流成功与回流失败回落（走 `build()`）因此**上限一致**，不会出现"同样的请求，回流成功时更长、回落时更短"的不确定行为。**不得**为回流新造一个独立的上限配置。
   **探针**：替身模型返回超过 4096 字符 ⇒ 输出被截断到 `DISPLAY_LIMIT`；把上限改成不设或另一个数 ⇒ R13 变红。

**因此本契约对提示词注入的准确承诺是**：**注入最多改变用户读到的一段文字，不能产生动作、不能外发数据、不能越出工作区**。这不是"注入已解决"，是"注入的后果上界被结构压到只剩观感"（§0.3 第 3 条）。

### 1.6 失败语义（钉死）

| 情形 | 行为 |
|------|------|
| 回流模型调用失败（`ModelError` 任意形态，**含后端自身超时**）、输出为空或纯空白 | **不回退为错误**：`result_delivery="model_summary_failed"`，回复回落为 `ResponseBuilder.build()` 的**确定性 display**（截断 4096） |
| 同上，但该工具的结果为空 | 同上（回落显示仍然是有效的） |
| `[reflow].enabled = false` | 见 §1.9 的不变式（该状态与 `model_summary` 工具**不能共存**） |

**超时：不设调用级超时，沿用模型后端自身的超时（钉死，2026-09-27 审查后订正）**。

- **事实**：`ModelBackend.generate(prompt, response_schema=None) -> dict` **没有单次调用超时参数**（`src/core/interfaces.py:50-56`）；Ollama 后端的超时在**构造时**固定（默认 120 s）。
- **后果**：回流组件拿到的是同一个模型引用，**在现有接口下无法把本次调用限制为 10 秒**。前版契约的 `[reflow].timeout_ms` 是一个**无法兑现的配置项**。
- **裁决：删除 `[reflow].timeout_ms`**（推荐方案）。回流与主循环的每一次本地模型调用走**同一条超时路径**——**不新增第二套超时语义**。若将来确实需要调用级超时，那是一次 `ModelBackend` 接口变更（须同步全部后端与替身），**不在本阶段**（登记 §14 第 21 项，触发条件：出现"回流调用把回合拖长到不可接受"的真实证据）。
- **明确禁止的替代做法（钉死）**：**不得**用「线程里跑 `generate()`、主线程等 N 秒后放弃」实现调用级超时。理由照实写明：放弃等待**不会取消底层的 HTTP 请求**，它会继续跑完并把结果丢掉；在多次回流后这会**累积后台线程**（`17` 对子进程用的是"超时即终止进程"，线程没有等价的终止手段）。

**三条硬约束**：

1. **工具结果永不因回流失败而丢失**——回落路径就是现状路径，逐字可用。
2. **不得发 `degradation` 事件**（`07` 对工具失败同法）：回流失败不是记忆/检索降级，混入 `degradation` 会污染既有观测口径。
3. **不得静默**：失败必须落在 `result_delivery="model_summary_failed"` 上（§10.2），报告必须分列。

### 1.7 不进入云端（结构性论证）

- 回流发生在 `execute()` 之后，而两条调用路径在该点**直接 return**，**云端准入判定（`10` P6d 的 `evaluate_cloud_admission`）在时间线上已经过去** ⇒ **不存在"回流结果触发升级"的路径**。
- `result_reflow.py` 零 cloud import（R10）⇒ 回流数据**没有**进入 `TaskBrief` / `PrivacyPolicy` 的构造点。
- **`17` 的「外部工具结果不得作为云端咨询材料」边界不变**，且 RD3 保证回流工具本身都是 `egress=False`。

### 1.8 轮次账（诚实计数，钉死）

回流是一次模型调用，但**不计入 `rounds_used`**——`rounds_used` 是**意图理解轮次**的账（`16` §3.4），回流发生在执行之后、不参与意图收敛。

**但不得因此让它不可见**：`result_delivery`（§10.2）是它的观测位。**报告硬性行**：报告里的「本批模型调用数」必须能由 `rounds_used` 与 `Σ(result_delivery == "model_summary")` **两个来源分别还原并分列**，**不得**把回流调用混进意图轮次计数（§12.5 第 4 条）。

### 1.9 配置与不变式

```toml
[reflow]
enabled = true        # 与 model_summary 工具同生同死，见下
max_chars = 4000
# 无 timeout_ms：回流沿用模型后端自身的超时（§1.6 的裁决与理由）
```

**不变式（fail-loud，`CONFIG_ERROR` / `details.reason="reflow_disabled_with_model_summary_tools"`）**：存在任一**在白名单内**且 `result_delivery == "model_summary"` 的工具时，`[reflow].enabled` **必须**为 `true`。

与 `17` E3（`[tool_providers]` 非空 ⇒ 能力层必须开启）**同一构造**：关掉回流会让工具的声明变成**空头承诺**，所以「文档工具有开、回流关闭」**不是一个被禁止的配置，而是一个不存在的状态**。**没有** `reflow_off` 评估变体（它构造不出来）；默认的关态是 `docs_off`（两个工具与回流一起不在场）。

---

## 2. 两个工具的 `ToolDef`（钉死）

### 2.1 `document.read`

```python
ToolDef(
    name="document.read",
    description=(
        "读取工作区内一份文档的文本内容并返回带来源定位（页码/段落/表格行/工作表行/幻灯片）的结构化结果。"
        "支持 pdf、docx、xlsx、pptx、txt、md。"
        "范围：DOCX 正文段落与表格（不含页眉页脚）；XLSX 各工作表非空行（公式单元格返回公式文本）；"
        "PPTX 各幻灯片的文本与表格（不含备注）。"
        "不支持 OCR 与扫描型 PDF，不支持 .doc/.xls/.ppt。"
        "结果有长度上限；超过时会在结果中明确说明未返回的部分。"
    ),
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    risk_level="sensitive",
    result_delivery="model_summary",
)
```

**只有 `path` 一个参数，且必填**：**不提供模型可调的读取范围或长度参数**（`pages` / `sheet` / `max_chars` 一律不设）。上限只能来自**配置**，因此「模型放大自己的读取预算」不是被禁止的行为，而是**不存在的状态**（`17` 裁决 6 同一构造）。按范围读取登记为遗留项（§14 第 1 项）。

### 2.2 `file.search`

```python
ToolDef(
    name="file.search",
    description=(
        "在工作区内搜索文件。mode=\"filename\" 按文件名子串匹配，mode=\"content\" 按文件内容做"
        "固定字符串（非正则）搜索。返回匹配文件、行号与有限上下文，结果按路径与行号稳定排序。"
        "只搜索工作区，默认忽略隐藏条目、版本控制目录、缓存目录、虚拟环境与二进制文件。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "mode": {"type": "string"},
            "path": {"type": "string"},
            "glob": {"type": "string"},
        },
        "required": ["query", "mode"],
    },
    risk_level="normal",
    result_delivery="model_summary",
)
```

| 参数 | 必填 | 语义 | 校验位置 |
|------|:---:|------|---------|
| `query` | ✔ | **固定字符串**（非正则）；空 ⇒ §5.6 行 1 | 语义层（preflight） |
| `mode` | ✔ | 闭集 `{"filename", "content"}`；**必填，无默认值** | 语义层（preflight） |
| `path` | ✘ | 搜索根；**缺省等价于 `"."`** | 复用 `resolve_workspace_target`（`15` §6.1） |
| `glob` | ✘ | `fnmatch` 风格过滤器，作用于**相对 posix 路径**；语法约束见 §5.6 行 3 | 语义层（preflight） |

**`mode` 必填**：JSON Schema 子集（`15` §1.1）**不含 `enum`**，闭集只能在语义层判；设默认值会让「模型漏填」与「用户真的要搜文件名」在观测上不可分。

**`mode` 的闭集校验不得实现为 `param_instance_checks`**（钉死）：那是「参数值**整串逐字来源于用户输入**」的谓词（`16` §1.2 / §5.6）。用户说「搜一下 TODO」，`mode` 的值 `"content"` 不来自用户原文，套实例谓词会把每次合法搜索都判红。

`supply_by_echo` 为空、`param_instance_checks` 为空、`egress=False`、`audit_redact_all_params=False`（与既有文件工具一致）。

### 2.3 风险等级、确认语义与只读性的准确口径

| 工具 | `risk_level` | 在 `LOCAL_SIDE_EFFECT_TOOLS`？ | `requires_confirmation` | `result_delivery` |
|------|:---:|:---:|:---:|:---:|
| `document.read` | `sensitive` | **否** | `True`（preflight 显式给出） | `model_summary` |
| `file.search` | `normal` | **否** | `False`（preflight 显式给出） | `model_summary` |

**必须把两件事分开说**（这是对 FR12「不应触发写操作确认」的准确兑现）：

1. **不进入副作用路径（已满足，无保留）**：两者都不在 `LOCAL_SIDE_EFFECT_TOOLS`（`src/tools/capabilities.py:8`）内 ⇒ ①不触发写入确认语义；②不参与 `13` 的 `approval_profile="high_impact"` 只升不降合成与扣留；③不受 `16` §1.5 S1/S2 的独占能力约束。**三重均成立，且是结构性事实**（集合隶属决定，不是承诺）。
2. **内容确认是另一件事，本契约默认对齐 `file.read`**：`file.read` 当前 `sensitive` 且 `preflight_read` 返回 `requires_confirmation=True`（`src/tools/file_tools.py:64`，S14 断言「read→确认」）。`document.read` 是 `file.read` 的**能力超集**，给它 `False` 等于对已有保护做**减法**——那是安全边界的**放宽**，属「安全边界」变更类，本契约**不自行拍板**。

> **✅ 老板已裁决（2026-09-27）：保持本表默认** —— `document.read` 需确认、`file.search` 免确认（§15.1 第 1 项，属安全边界裁决，Codex 不得自行调整）。`file.search` 取 `normal` + `False` 的理由是它只返回**定位线索**与**有界片段**（≤ `max_line_chars` × `max_results`），不含整份文件内容；**但片段确实是内容原文**，这条边界不是无懈可击的——残留风险登记为 §14 第 8 项。Codex 按本表实现；若日后要放宽，改动面仅限本条两行 + §12.3 D3/D4 的期望值。

---

## 3. 路径与工作区边界（**复用，不重定义**）

### 3.1 唯一解析器，零新增

两个工具的路径解析与逃逸防护**完全复用** `src/tools/file_tools.py::resolve_workspace_target`（`15` §6.1 的唯一定义），**不得**复制、包装出第二份实现，也**不得**新增任何路径判据。`_file_error` / `_preflight_target` / `_require_readable_file` / `_require_directory` 同样复用。

既有行为逐字不变：绝对路径 / 盘符 / UNC / `~` / 解析后逃出 `workspace_root` ⇒ `FILE_ERROR`（`details.reason="workspace_escape"`，`recoverable=True`）；preflight 侧由 `_preflight_target` 转成 `PreflightReport(effective_risk="dangerous", requires_confirmation=True)` ⇒ **硬拒**（`15` §6.3 第 3 行）。

### 3.2 符号链接与 TOCTOU（**本版重写，回应阻塞项 3**）

**候选发现阶段：两个引擎都不跟随任何符号链接**（目录与文件一律跳过）。

| 引擎 | 实现 |
|------|------|
| ripgrep | **不传** `-L` / `--follow`（ripgrep 默认即不跟随） |
| Python 降级 | `os.walk(followlinks=False)` **且**显式跳过 `entry.is_symlink()` 的条目 |

**为什么 Python 侧必须显式跳过文件符号链接**（这是前版的漏洞）：`os.walk` 在 `followlinks=False` 下**不跟随目录符号链接，但会把「指向文件的符号链接」放进 `filenames`**，随后 `open()` **会跟随它**读到工作区外。因此「不跟随目录链接」不足以成立「读不到工作区外」——必须**连文件符号链接一起跳过**。

**由此产生的诚实结论（前版 F11 不可达的根因）**：既然两个引擎都不产出符号链接目标的候选，**「结果阶段复检」在常规遍历中是不可达的**。它不是常规路径，而是**纵深防御**。保留它的三条理由（照实写明）：

1. **TOCTOU**：一个普通路径可以在「被遍历到」与「被读取」之间被换成符号链接；复检是结果阶段的最后一跳，能拦住这一窗口。
2. **引擎默认值漂移**：ripgrep 的默认行为由**外部二进制的版本**决定，不受本契约控制；复检是引擎无关的最后一道。
3. **它是两个引擎的共同出口**，因此"结果 ⊆ 工作区"这条性质**不依赖任何引擎的默认值**。

**因为它是纵深防御，它的验收必须靠注入**（§12.3 F11b），且 **F11a（真实符号链接）断言的是「不跟随、零匹配」而不是 `skipped.outside > 0`**。**报告不得宣称「靠结果复检拦住了 N 次越界」**——常规路径下该计数应恒为 0，非零只可能来自 TOCTOU 或引擎漂移。

### 3.3 「模型不能通过搜索参数绕过工作区边界」的结构性论证

| 参数 | 靠什么结构不能造成越界 |
|------|----------------------|
| `path` | 经 `resolve_workspace_target`；逃逸 ⇒ `FILE_ERROR` + preflight `dangerous` + 硬拒 |
| `glob` | **不参与任何路径构造**：只做 `fnmatch` 过滤，且作用在一个**已被限定到工作区内的候选集**上。含 `..` 也不产生越界——但仍在语法层拒绝（§5.6 行 3），理由是防止未来实现改成「把 glob 交给引擎」时静默打开缺口（**结构性预防，当前非必要条件**，照实标注） |
| `query` | 只是匹配字面量；内容模式固定 **literal（`-F` / `str.find`）**，无正则注入面 |
| `mode` | 闭集二值，与控制流一一对应，无路径语义 |
| 遍历本身 | 搜索根经解析限定 + **两引擎都不跟随符号链接**（§3.2）⇒ 候选集永远是工作区内的有限集合；结果复检是纵深防御 |

**因此**：「绕过边界」不是一个被拦截的行为，而是**候选集构造**的推论。

---

## 4. `document.read` 语义

### 4.1 格式分派（扩展名 → 容器形态校验 → 解析器）

| `declared_format` | 容器形态校验（不通过 ⇒ §4.6 行 7） | 解析器 |
|------|------|------|
| `pdf` | 前 5 字节 == `%PDF-` | `pypdf` |
| `docx` | ZIP（`PK\x03\x04`）且含 `word/document.xml` | `python-docx` |
| `xlsx` | ZIP 且含 `xl/workbook.xml` | `openpyxl` |
| `pptx` | ZIP 且含 `ppt/presentation.xml` | `python-pptx` |
| `txt` | **无魔数**：前 8192 字节不含 `\x00` | 内置（UTF-8 解码） |
| `md` | 同 `txt` | 内置 |
| `.doc` / `.xls` / `.ppt` | — | **不分派**：§4.6 行 6 |
| 其余扩展名 | — | **不分派**：§4.6 行 8 |

**ZIP 家族靠必需的内部成员名区分，不靠文件扩展名**——这是「`.docx` 实际是 `.xlsx`」能被判红的唯一结构。三个成员名一个都不匹配 ⇒ §4.6 行 7。

### 4.2 结构化输出契约（钉死）

```python
{
    "path": "docs/report.pdf",          # 相对 posix
    "declared_format": "pdf",
    "format": "pdf",                    # 形态校验后确定；必等于 declared_format
    "size_bytes": 812345,
    "extraction": "ok",                 # 闭集："ok" | "empty" | "no_text_layer"
    "segments": [
        {"locator": {"kind": "page", "index": 3}, "text": "..."},
        {"locator": {"kind": "paragraph", "index": 12}, "text": "..."},
        {"locator": {"kind": "table_row", "index": 2, "row": 5}, "text": "..."},
        {"locator": {"kind": "sheet", "name": "Sheet1", "row": 5}, "text": "..."},
        {"locator": {"kind": "slide", "index": 2}, "text": "..."},
        {"locator": {"kind": "line_range", "start": 1, "end": 200}, "text": "..."},
    ],
    "segments_total": 314,              # int | null，见下
    "segments_returned": 200,
    "chars_extracted": 812345,          # 实际已提取的字符数（下界；见下）
    "chars_returned": 39876,
    "segment_truncated": False,
    "truncated": True,
    "truncation_reason": "max_returned_segments",
    "notice": "文档共 314 个文本段，本次返回前 200 段；剩余 114 段未读取。",
}
```

**`locator.kind` 闭集 = `{"page", "paragraph", "table_row", "sheet", "slide", "line_range"}`**：

| kind | 伴随键 | 来源格式 |
|------|--------|------|
| `page` | `index`（1 起） | `pdf` |
| `paragraph` | `index`（1 起） | `docx` |
| `table_row` | `index`（表在**文档中的序号**，1 起）+ `row`（1 起） | `docx` |
| `sheet` | `name`（工作表名）+ `row`（1 起） | `xlsx` |
| `slide` | `index`（1 起） | `pptx` |
| `line_range` | `start` + `end`（均 1 起，闭区间） | `txt` / `md` |

**定位层级与各格式的原生结构对齐**（钉死，这是为什么 PPTX 的表格**不**单独成段）：PDF 有页、DOCX 有块级流、XLSX 有工作表/行、PPTX 有幻灯片——**幻灯片内的表格属于该幻灯片**，因此并入所属 `slide` 段（行以 `\n` 分隔）；而 DOCX 的表格是**顶层块**，与段落并列，故用 `table_row` 保留定位。`table_row` 因此只由 DOCX 产出。

`line_range` 的 `end - start + 1` ≤ `MAX_SEGMENT_LINES`（实现常量，建议 200）：纯文本按行切段，**不得**把整份 TXT 塞进一个 segment（否则段级上限形同虚设，一段就撑爆字符上限，无法给出有意义的"未返回部分"）。

**`null` 的语义（钉死，沿用 `17` 纪律：不得用 0 或猜测值冒充未知）**：

| 字段 | `int` | `null` |
|------|-------|--------|
| `segments_total` | 提取已完成，**精确值** | 提取**中途停止**，总数未知 |

**`chars_extracted` 的语义（本版订正，回应阻塞项 4）**：它是**实际已提取到的字符数**，**不是**文档总字符数。提取中途停止时它是**下界**（真实总量更大且未知）——**禁止**把它当作总量，也禁止用 `len()` 或估计值填出一个"总量"。**探针**：把 `chars_extracted` 在提取期停止时写成估计值 ⇒ D5 变红。

**刻意不设 `chars_total`（钉死理由）**：它与 `chars_extracted` 的关系只有两种——提取完成时**必然相等**，中途停止时**必然为 `null`**。一个恒等于另一字段或恒为 `null` 的字段**没有信息量**，只会制造"两个总数哪个才对"的歧义。诚实性由三者共同承载：`chars_extracted`（下界）+ `truncation_reason`（是提取期停的还是返回期截的）+ `notice`（未返回量是"已提取 N、返回 M、差 N−M"还是"提取到 N 后停止、总量未知"）。同理，**提取完成时 `segments_total == segments_returned`** 是正常且必须出现的情况（返回期未截断）。

**`truncation_reason` 闭集 = `{"max_extracted_chars", "max_segments_total", "max_returned_segments", "max_returned_chars", null}`**（本版**新增 `max_extracted_chars`**，回应阻塞项 4）。三条不变式（D 矩阵逐条断言）：

1. `truncated == True` ⟺ `truncation_reason is not None`。
2. `truncated == True` ⇒ `notice` 是完整中文句子，**包含未返回的数量**（段数或字符数）；提取期的两个 reason 写「**总数未知**」。
3. `extraction != "ok"` ⇒ `notice` 非空（§4.6 行 4/5）。

### 4.3 三重上限与截断声明（本版订正）

| 上限 | 配置键 | 建议默认 | 作用点 |
|------|--------|:---:|------|
| 文件大小 | `max_file_bytes` | 32 MiB | preflight（`stat().st_size`），超限 ⇒ `FILE_ERROR reason="target_too_large"`，**零解析** |
| 提取字符数 | `max_extracted_chars` | 500 000 | 提取期 |
| 提取段数 | `max_segments_total` | 20 000 | 提取期 |
| **返回段数** | `max_returned_segments` | 200 | 序列化前 |
| **返回字符数** | `max_returned_chars` | 40 000 | 序列化前 |

**两个阶段必须分清**：

- **提取期**（`max_extracted_chars` / `max_segments_total`）命中 ⇒ 我们**没有拿到**后面的内容 ⇒ `segments_total = null`（`chars_extracted` 此时是**下界**）；`truncation_reason` = **先命中者**。
  **判定顺序钉死**：每追加一个段之后，**先检查字符上限，再检查段数上限**。因此单段同时顶破两个上限时，reason 取 `"max_extracted_chars"`（确定性的并列打破规则）。**理由**：若文档只有三段巨型文本，`max_extracted_chars` 才是事实，报 `"max_segments_total"` 会说出「在 20000 段处停止」这种**事实错误**。
- **返回期**（`max_returned_segments` / `max_returned_chars`）命中 ⇒ 我们**拿到了**、只是不返回 ⇒ `segments_total` 与 `chars_extracted` 都是**精确值**（`chars_extracted` 此时**不是**下界）；reason 取**先触发者**；两者同时命中时取 `"max_returned_segments"`（同上，确定性并列打破）。

**返回期截断的三条落地规则**：

1. **只在段边界截断**（segment 是不可分的原子）。
2. **`extraction == "ok"` 且 `segments` 非空时，至少返回 1 个 segment**：若第 1 段自身超过 `max_returned_chars`，则在字符上限处**段内截断**该段、保留 `locator`，并置 `segment_truncated = True` + `truncation_reason = "max_returned_chars"`。
   **本条不适用于 `extraction != "ok"`**（空文档与无文本层 PDF）：此时 `segments == []` 是**正确结果**，**不得**为满足「至少一段」而塞入占位段。
3. `chars_returned` 是**实际返回的字符数**（含段内截断后的长度），不是上限值。

### 4.4 逐格式提取范围（**本版新增，明确钉死，回应"应补充"**）

| 格式 | 提取 | **不提取**（`ToolDef.description` 已写明；登记为 §14 第 10 项） |
|------|------|------|
| `pdf` | 每页的可提取文本，一段一页 | 图片、注释、附件、表单字段（无 OCR ⇒ 扫描页为空） |
| `docx` | **正文段落**（`document.paragraphs`）+ **全部表格**（`document.tables`，**逐行**一个 `table_row` 段，行内单元格以 `\t` 连接） | **页眉 / 页脚 / 脚注 / 尾注 / 批注 / 文本框** |
| `xlsx` | 每个工作表的**非空行**（一段一行，`sheet` + `name` + `row`）；行内单元格以 `\t` 连接、空单元格为空串；**只有至少一个非空单元格的行才成段** | 图表、图片、批注、定义名称、隐藏表的**格式**；空行不成段 |
| `pptx` | 每张幻灯片的文本框文本 + **表格**（行以 `\n` 分隔，并入该幻灯片段） | **备注页**、图片、图表、SmartArt |
| `txt` / `md` | 全文，按 `MAX_SEGMENT_LINES` 切 `line_range` 段 | —（Markdown **不渲染**，原样返回） |

**三条必须写明的实现约束**：

1. **XLSX 用 `openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)`**。
   - `read_only=True`：内存有界（与 NFR1 一致）。
   - **`data_only=False`（返回公式文本）是刻意的，不是疏忽**：`data_only=True` 读的是**缓存值**，而缓存值由 Excel 写入——**一个从未被 Excel 打开过的表格，缓存值为 `None`**，公式单元格会**静默变成空**。这正是「不得静默丢失关键内容」。代价（用户看到 `=SUM(A1:A5)` 而不是结果）登记为 §14 第 11 项。
2. **不提取页眉/页脚/备注/批注是声明式的固定范围，不是"这次没读到"**：它写在 `ToolDef.description` 里（模型可见），因此**不加运行时 `notice`**——加一条恒定出现的提示只会变成噪声。**探针**：D10 断言 `description` 含上述范围词；删掉描述里的范围声明 ⇒ D10 变红。
3. **DOCX 表格为空时**（`document.tables` 为空）不产出 `table_row` 段——**不得**产出零文本的占位段。

### 4.5 压缩炸弹防线（**本版新增，回应"应补充"**）

**OOXML 是 ZIP 容器，一个 10 MB 的文件可以合法地展开成数 GB**。因此**在把路径交给解析器之前**，必须检查 ZIP 中央目录：

| 限制 | 配置键 | 建议默认 | 判定 |
|------|--------|:---:|------|
| ZIP 条目数 | `max_zip_entries` | 2000 | 超出 ⇒ `document_expansion_too_large` |
| Σ 解压后大小（`ZipInfo.file_size` 之和） | `max_uncompressed_bytes` | 256 MiB | 超出 ⇒ 同上 |

**三条落地约束**：

1. **检查使用 `zipfile.ZipFile(...).infolist()`，只读中央目录、不解压任何条目**——在解析器（`python-docx` / `openpyxl` / `python-pptx`，它们内部都会用 `zipfile`）**之前**完成。**探针**：把检查移到解析器之后 ⇒ D15 变红（替身解析器会被调用）。
2. 超出 ⇒ `TOOL_EXEC_ERROR` / `document_expansion_too_large`（**不是** `document_corrupt`——它没损坏，它是**太大**）。
3. **PDF 无同级防线**（PDF 不是 ZIP）：这是本契约**照实登记的残余**（§14 第 13 项），缓解是 `max_file_bytes` 与 `max_extracted_chars` 两个上限；彻底缓解需要 PDF 对象流的展开预算，不在本阶段。

### 4.6 行为真值表（**七种故障面逐一钉死**）

| # | 情形 | 判定 | `code` / `details.reason` | 返回 / 用户可见 |
|:---:|------|------|------|------|
| 1 | **依赖缺失 / 模块缺失** | `importlib.util.find_spec` 在**分派时**检查（**禁止**模块级 import，§4.8） | `TOOL_EXEC_ERROR` / `parser_unavailable`（`details.format`） | 失败。「读取 .pdf 需要的解析组件不可用，请重新安装依赖。」 |
| 2 | **加密文件** | PDF：`pypdf` 的 `is_encrypted`；DOCX/XLSX/PPTX：容器是 OLE2（`\xD0\xCF\x11\xE0`）——**这三个格式的合法形态只能是 ZIP** | `TOOL_EXEC_ERROR` / `document_encrypted` | 失败。「该文件是加密的 Office 文档或旧版二进制格式容器，首版均不支持。」（**照实写两种可能**，不猜） |
| 3 | **损坏文件** | 容器形态校验通过但解析器抛异常，或 ZIP 结构不可读 | `TOOL_EXEC_ERROR` / `document_corrupt` | 失败。「文件已损坏或格式不完整，无法读取。」 |
| 4 | **空文档** | 结构上零文本段（PDF 0 页 / DOCX 无段落且无表格 / XLSX 无工作表或全空 / PPTX 0 幻灯片 / TXT 0 字符） | **成功**（**不是错误**） | `extraction="empty"`，`segments=[]`，`notice`：「该文档不含任何文本内容。」 |
| 5 | **扫描 PDF** | 页数 > 0 且**所有页** `extract_text()` 均为空白 | **成功**（**不是错误**） | `extraction="no_text_layer"`，`segments=[]`，`notice`：「该文档未包含可提取的文本层（可能是扫描件或纯图片文档）；本版本不支持 OCR。」 |
| 6 | **旧格式** `.doc` / `.xls` / `.ppt` | **由扩展名判定，不看内容** | `TOOL_EXEC_ERROR` / `document_unsupported_format` | 失败。「首版不支持 .doc/.xls/.ppt 旧格式，请先转换为 .docx/.xlsx/.pptx。」 |
| 7 | **格式与扩展名不符** | §4.1 形态校验不通过，或 ZIP 家族成员名一个都不匹配 | `TOOL_EXEC_ERROR` / `document_format_mismatch`（`details.declared_format`） | 失败。「文件扩展名（.pdf）与实际格式不符，已按安全策略拒绝解析。」 |
| 8 | 扩展名不在支持集 | 分派表未命中 | `TOOL_EXEC_ERROR` / `document_unsupported_format` | 失败（`user_message` 列出支持的扩展名） |
| 9 | **ZIP 展开超限** | §4.5 | `TOOL_EXEC_ERROR` / `document_expansion_too_large` | 失败。「该文件解压后的体积超出安全上限，已拒绝解析。」 |
| 10 | 其余解析器异常 | 兜底 | `TOOL_EXEC_ERROR` / `document_extract_failed` | 失败（§4.7） |

**第 4/5 行刻意做成成功而非失败**：这两件事**是真的**、且用户需要知道；做成错误会让模型的可用信息退化为"工具坏了"，而正确结论是"这份文档里没有可读文字"。这是"诚实失败"纪律的**另一半**：**该成功的不要伪造成失败**。

**行 7 是 fail-closed，不"猜真格式"**：不提供"按真实格式解析"的降级路径（否则「把 `.exe` 改名 `.pdf`」会进入解析器）。代价登记为 §14 第 6 项。

**行 2 与行 7 在 `.docx` 上的分辨**：`.docx` + ZIP 但缺 `word/document.xml` ⇒ 行 7；`.docx` + OLE2 ⇒ 行 2。**不得**合并成一个 reason。

### 4.7 解析器异常 → 统一错误映射（信息泄漏纪律）

```python
try:
    parsed = parser.extract(path)
except Exception as exc:                      # ← 唯一允许 catch 宽泛异常的一处，且立即转换
    raise _doc_error("document_extract_failed", parser=_PARSER_NAME, exception_type=type(exc).__name__) from exc
```

**四条硬约束**（D8 逐条断言）：

1. 第三方解析器异常**必须**在 `src/tools/document_tools.py` 内转换成 `ToolError`；Core 与主循环**不得**感知 `pypdf.errors.PdfReadError`、`zipfile.BadZipFile` 等任何第三方类型（`00-error-contract` §3）。
2. `user_message` **不得**包含 `str(exc)`、文件路径内容或文档片段。
3. `details` **只允许**三个键：`reason`、`parser`（库名）、`exception_type`（异常**类名**）。**禁止**写入 `str(exc)`。
4. `message`（技术描述）**同样不得**包含 `str(exc)`——只写类名与工具名。理由：解析器异常文本常内嵌文档片段或路径（形态如 `Unexpected token '<html>...' at line 42`）。
   **探针**：用抛出 `RuntimeError("SECRET-DOC-TEXT")` 的替身解析器，断言 `user_message` / `message` / `str(error)` / `details` 序列化结果四处均不含该串，且 `details["exception_type"] == "RuntimeError"`。把 `exception_type` 改成 `str(exc)` ⇒ D8 变红。

### 4.8 依赖检查必须在分派时，不在导入时

**禁止**在 `document_tools.py` 或任何被 bootstrap 链路导入的模块顶部 `import pypdf` / `docx` / `openpyxl` / `pptx`。

结构：一张**格式 → 解析库模块名**的字符串映射；分派时用该字符串 `importlib.util.find_spec(module_name)` → 缺失 ⇒ §4.6 行 1；存在 ⇒ **此时**才导入该库（`importlib.import_module` 或分派分支内的 `from … import …`，两者等价，见 §4.9 的 2026-09-28 修订）。

**探针（本契约最强的结构臂之一）**：把任一解析器的 import 提到模块顶层 ⇒ 在**模拟模块缺失**的解释器里 `bootstrap()` 直接失败 ⇒ D11 变红。D11 的断言不是"返回了 `parser_unavailable`"，而是「**应用仍能启动并正常回答一个与本工具无关的问题**」。

### 4.9 解析器可替换性（对应 FR12 的"未来替换解析库不改主循环"）

**本节的硬约束（三条，2026-09-28 实现审查后按下述口径收敛）**：

1. 解析库**只在分派期惰性导入**（§4.8），模块顶部零解析库导入；
2. **替换一个解析库只需改 `document_tools.py` 一个文件**——`ToolDef`、handler、能力声明、配置、主循环**零改动**；
3. 解析器的差异**收敛在"段列表"这一层**：上层（五类上限、截断、通知、错误映射）是**一份实现**，六种格式共用。

**2026-09-28 修订（据实）**：前一版把上述**目标**写成了一种**实现形状**——强制 `DocumentParser` 内部协议 + 模块级 `PARSERS: Mapping[str, DocumentParser]` 描述符表（每项含 `extensions` 与 `extract()`），并要求 `ExtractionResult` 为独立类型。已交付实现采用了等价的另一形状：`_MODULES`（格式 → 解析库**模块名**字符串）+ `_ZIP_MEMBER`（格式 → ZIP 成员名）+ 分派期 `if/elif` 分支，段列表在 `_Extraction` 上累积。**该形状满足上面三条硬约束**（替换 pypdf 只需改 `_MODULES` 的一项与对应分支），因此**描述符表不再是强制要求**，协议名与类型名也不再钉死。

**为什么改而不是要求重构**：本节的目的是「可替换性」与「让 D8/D15 能在**解析器之前**与**解析器内部**插入替身」，不是固定的类结构。而 D8/D15 需要的注入点**已经存在**——两个库都在分派分支内导入，测试可向 `sys.modules` 注入替身模块（令 `PdfReader` 抛错 / 计数），**无需**描述符表。为测试的便利做无收益的重构不值得；契约把实现形状写死才是缺陷。

**D8 / D15 的探针按此改述**（条目内容不变，只改"替身从哪来"）：用 `sys.modules` 注入一个抛 `RuntimeError`（D8）或带调用计数（D15）的替身模块，再调用工具。

---

## 5. `file.search` 语义

### 5.1 两种模式与引擎分工（钉死）

| `mode` | 匹配对象 | 引擎 | 理由 |
|------|------|------|------|
| `filename` | **文件名（basename）子串**，`casefold` 后比较（大小写不敏感，**literal**） | **只有 Python**（`os.walk`） | 文件名匹配不需读文件内容，`os.walk` + 忽略集 + 时间上限已是最简且**引擎无关**的实现。第二引擎只会带来"两引擎对文件名匹配的语义漂移"（大小写/Unicode 归一化/隐藏文件），**收益为零** |
| `content` | 文件**内容**中的固定字符串（`-F` / `str.find`，**非正则**） | **ripgrep 优先**，缺失或启动失败 ⇒ Python 降级 | 「包装成熟搜索能力」的真实适用面在这里（大目录遍历 + 编码处理 + 二进制跳过） |

`engine` 值域 = `{"ripgrep", "python"}`（`filename` 模式恒为 `"python"`）。

**正则搜索登记为遗留项**（§14 第 4 项）：`query` 是模型产出的文本，正则引入 ReDoS 与"匹配语义不受本契约约束"两个问题；固定字符串是"搜索参数不构成攻击面"的最简兑现。

### 5.2 忽略集：单一真源 + **裁剪与权威过滤两段**（**本版重写，回应阻塞项 2**）

前版把「不把忽略交给引擎」写成一条绝对禁令，**与 `--no-ignore` 直接矛盾**，后果是 ripgrep 会**实际遍历** `.git` / `.venv` / `node_modules` 才过滤——大项目上先超时，内置忽略集**失去性能意义**。本版改为**两段式**，并钉死两段的关系：

```
① 裁剪段（candidate pruning，性能用途）：
   ripgrep：把内置忽略策略**编译为排除参数**（--glob '!<dir>/**'、--glob '!*.pyc' …），
           使引擎**不下探**这些目录；同时保留 --no-ignore（关闭 .gitignore 等外部来源）
   Python：os.walk 时原地剪枝（修改 dirnames）
② 权威过滤段（authoritative filter，语义用途）：
   两引擎**共用同一个过滤函数**，对候选逐条复核；它是结果的唯一语义来源
```

**两段的关系（钉死，这是本版的关键）**：

- **裁剪必须是保守的**：裁剪集**不得**裁掉权威过滤会保留的任何东西。裁剪是**优化**，语义上应当是恒等变换。
- **权威过滤仍然是唯一权威**：裁剪段若过度裁剪，是**实现缺陷**，由 §12.3 F7（跨引擎逐字段相等）暴露。
- 因此前版的措辞「禁止把任何一项交给引擎的等价开关」**作废**，替换为：**禁止把「结果语义」交给引擎**（排序、行截断、上下文、每文件上限、全局限量、计数、`notice` 全部由我们自己的实现完成）；**允许把「候选发现范围」交给引擎**（剪枝），因为它的偏差会被公平性验收捕获。

**内置忽略集（单一常量，两段共用同一份真源）**：

- **目录**：`.git`、`.hg`、`.svn`、`__pycache__`、`.venv`、`venv`、`env`、`node_modules`、`.mypy_cache`、`.pytest_cache`、`.ruff_cache`、`.tox`、`build`、`dist`、`.idea`、`.vscode`、`.eggs`、`*.egg-info`
- **二进制扩展名**（**仅内容模式**生效）：`.pyc`、`.pyo`、`.so`、`.dll`、`.dylib`、`.exe`、`.bin`、`.o`、`.a`、`.zip`、`.gz`、`.tar`、`.7z`、`.rar`、`.png`、`.jpg`、`.jpeg`、`.gif`、`.bmp`、`.ico`、`.webp`、`.mp3`、`.mp4`、`.avi`、`.mov`、`.wav`、`.pdf`、`.docx`、`.xlsx`、`.pptx`、`.doc`、`.xls`、`.ppt`、`.sqlite`、`.db`、`.woff`、`.woff2`、`.ttf`、`.otf`

**文件名模式不按扩展名忽略**（钉死）：搜索 `report.pdf` 是合法需求，忽略它会让工具在用户最需要的一类查询上给出错误的"没有找到"。因此文件名模式只应用**目录忽略集**。

**内容模式的两道二进制防线**（缺一不可，扩展名不可信）：①扩展名在二进制集内 ⇒ 跳过；②扩展名不在集内但**前 8192 字节含 `\x00`** ⇒ 跳过。第二道是**唯一**能覆盖"`.txt` 里其实是二进制"的判据。

**配置只能追加，不得豁免内置项**：`effective_ignore = BUILTIN ∪ config`，**不做差集运算** ⇒「操作员把 `.venv` 从忽略集里去掉」**不是一个被禁止的行为，而是一个不存在的状态**（`17` 收紧方向纪律同源）。

**`--no-ignore` 仍然必需**（钉死，理由写进代码注释）：ripgrep 默认尊重 `.gitignore` / `.ignore` / 全局 ignore / 父目录 ignore。若保留默认：①「搜不到」的原因**不可归因**（是忽略集？还是某层 ignore 文件？）且**不可复现**（取决于 repo 状态）；②本项目 `data/` 是 gitignore 的，而 **`data/workspace` 正是搜索根**——保留它会让**整个工作区搜不到任何东西**。**因此 `--no-ignore`（关掉外部来源）+ 显式排除参数（自己剪枝）两者必须同时存在**：前者去掉不可归因的来源，后者提供性能。
**探针**：①删掉 `--no-ignore` ⇒ 在 `data/` 被 gitignore 的仓库里 F4 变红；②删掉排除参数 ⇒ F4b（断言 ripgrep 路径下 `.venv` 内的匹配**零产出且 `skipped` 不因遍历它而膨胀**）变红。

### 5.3 隐藏文件：两引擎必须一致（**本版新增，回应阻塞项 2**）

**前版漏洞**：ripgrep **默认跳过**隐藏条目，而 `os.walk` **不跳过**普通隐藏文件 ⇒ **F7 的逐字段相等不可达**（Python 引擎会多出一批 `.foo` 文件的匹配）。

**钉死**：**两个引擎都跳过隐藏条目**，定义 = 条目名以 `.` 开头（目录与文件一律跳过，任意层级）。

| 引擎 | 实现 |
|------|------|
| ripgrep | 默认行为即跳过隐藏 ⇒ **不传 `--hidden`**（并禁止将来为"多搜点东西"加上它） |
| Python | 显式跳过 `name.startswith(".")` 的目录项与文件项 |

**照实登记**：这条规则使 `.github/workflows` 一类路径**搜不到**——这是**刻意的覆盖边界**，登记为 §14 第 7 项（触发条件：需要搜隐藏路径）。

### 5.4 结果形状与稳定排序

```python
{
    "mode": "content",
    "root": "sub/dir",                  # 相对 posix 的搜索根（缺省 path ⇒ "."）
    "query": "TODO",
    "engine": "ripgrep",
    "fallback_reason": None,            # null | "ripgrep_missing" | "ripgrep_failed"
    "results": [
        {"path": "src/a.py",
         "matches": [{"line_number": 12,
                      "line": "def f():  # TODO",
                      "context_before": ["..."],
                      "context_after": ["..."]}]}
    ],
    "result_count": 7,
    "file_count": 3,
    "results_truncated": False,
    "skipped": {"binary": 41, "too_large": 2, "unreadable": 0, "outside": 0},
    "notice": None,
    "elapsed_ms": 84,
}
```

**`filename` 模式的 `results` 项形状**：`{"path": "docs/report.pdf", "name": "report.pdf"}` —— **无 `matches` 键**（不得用空列表冒充"没有匹配行"）。

**排序规则（钉死）**：`results` 按 **`path`（相对 posix，Python 默认字符串序 = 码点序）**升序；内容模式下 `matches` 按 `line_number` 升序；**在收集完成后由我们排序，不得透传引擎产出顺序**（ripgrep 输出顺序不受保证，取决于并行度与遍历顺序）；**不用 locale collation**。
**探针**：去掉 `sorted(...)` ⇒ F8 变红。注意单次 run 很可能仍是绿的——**所以 F8 必须用"交换引擎"这一臂**。

### 5.5 ripgrep 包装与降级

| 类别 | 项 | 理由 |
|------|------|------|
| 必须 | `--json` | 结构化产出，不解析人类可读输出 |
| 必须 | `--no-ignore` | §5.2（关掉不可归因的外部 ignore 来源） |
| 必须 | **排除参数**（内置忽略策略编译而成） | §5.2（性能；不得下探 `.venv` 等） |
| 必须 | `--fixed-strings`（`-F`） | §5.1 literal 语义 |
| 必须 | `--no-config` | **拒绝外部 ripgrep 配置文件影响结果**（`RIPGREP_CONFIG_PATH` 可改变行为）⇒ 可复现 |
| 必须 | `--max-filesize=<max_file_bytes>` | 与降级引擎同一上限 |
| 必须 | **绝对路径**的已解析搜索根作为遍历目标 | 遍历根即被限定集 |
| 禁止 | `--follow` / `-L` | §3.2 |
| 禁止 | `--hidden` | §5.3 |
| 禁止 | `--text` / `-a`、`-U` / `--multiline` | `--text` 会让二进制文件产出匹配，与 `skipped.binary` 计数语义冲突 |
| 环境 | **复用 `17` 的子进程环境白名单构造器** | 一致性；且 `RIPGREP_CONFIG_PATH` 因此**结构上不可能**出现 |
| 超时 | 到 `timeout_ms` ⇒ **终止进程**（不用 `subprocess.run(timeout=)` 后继续读 stdout） | `17`「超时即作废协议流」同一纪律 |

**定位方式**：`shutil.which("rg")` 在**代码里**解析，**配置不得提供可执行文件路径**（`17` 裁决 6 同源）。`[tools.search]` 因此**没有**任何可执行文件相关的键（§9）。

| 触发 | `fallback_reason` | 行为 |
|------|:---:|------|
| `shutil.which("rg")` 返回 `None` | `"ripgrep_missing"` | 走 Python 引擎，`engine="python"` |
| 启动失败（`OSError`）或退出码 ≥ 3 | `"ripgrep_failed"` | 走 Python 引擎，`engine="python"` |
| 退出码 0（有匹配）/ 1（无匹配） | `None` | 正常 |
| **退出码 2 且零结果** | `"ripgrep_failed"` | 走 Python 引擎。**2026-09-28 澄清**：rc=2 时「真的没有匹配」与「文件全都读不了」**不可区分**，接受它会产出一个与 §5.6 行 7 无法区分的空结果 ⇒ 必须降级（降级路径还能给出真实的 `unreadable` 计数） |
| **退出码 2 且有结果** | `None` | **接受已产出的结果**；`skipped.unreadable` **必须为 `null`**（见下） |
| 超时 | — | **不降级**：`search_timeout`，**零结果返回**（§5.6 行 5） |

**两个引擎的差异只允许存在于「候选发现」阶段，不允许存在于「结果产出」阶段**（钉死，本节承重句）。因此以下**全部由我们自己的实现**统一完成，两引擎**共用同一份代码**：权威过滤（§5.2 ②）、边界复检（§3.2）、行截断、上下文截取、每文件上限、全局限量、排序、计数、`notice`。

**`skipped` 计数的诚实规则**（沿用 `17`：不得用 0 冒充未知）：引擎能提供的填整数；不能提供的填 `null`。`binary` / `too_large` 由我们自己的统计得出（跳过判定在我们这一层）⇒ 恒为整数；`skipped.unreadable` 在 ripgrep 路径下若无法从 `--json` 的 per-file 错误项可靠提取，**必须填 `null`**。**2026-09-28 澄清（据实）**：本实现只解析 `--json` 的 `type == "match"` 项、**不**提取 per-file 错误项，且 `stderr` 送 `DEVNULL` ⇒ 该值在 ripgrep 路径下**不可知**，**一律填 `null`**（`engine="ripgrep"` 时；Python 引擎与降级路径保持整数计数）。**用 `0` 冒充 ⇒ F12 红。**

**降级的可见性**：`engine` / `fallback_reason` 出现在结果 dict 里，**不强制写入 `notice`**——降级不改变结果集，用户无需知情（刻意的选择，与 §10.2 的可观测性无关）。

### 5.6 确定性行为真值表

| # | 情形 | 行为 | 为什么 |
|:---:|------|------|------|
| 1 | `query` 为 `""` 或纯空白 | **失败**：`TOOL_EXEC_ERROR` / `query_invalid`（`recoverable=True`），零结果 | **不得**返回空结果集：返回空集会让模型**如实说出错误的结论**（「工作区里没有 X」），而真相是"没有搜" |
| 2 | `mode` 不在闭集 | **失败**：`query_invalid`（`details.param="mode"`） | 无默认值（§2.2）；闭集只能在这一层判 |
| 3 | `glob` 非法（**七条子判据**） | **失败**：`glob_invalid` | ①空串；②含 `\x00`；③含 `\`；④以 `/` 开头或含盘符；⑤含 `..` 段；⑥长度 > 256；⑦含控制字符（**2026-09-28 澄清**：判据⑦**不得**导入 `unicodedata`——用码位区间 `ord(ch) < 32 or 127 <= ord(ch) < 160`（即 Cc）实现，以使 D9 的源级断言"三个新模块零 `unicodedata` 导入"可落地；D9 的本意是"禁止第二份净化实现与第二个上限数"，不是禁止字符分类，但**断言口径保持绝对**以免出现解释空间）。④⑤是 §3.3 的结构性预防，照实标注为"当前非必要" |
| 4 | 文件不可读（权限 / IO 错误） | **跳过并计数**（`skipped.unreadable`），**不失败整次搜索** | 个别文件读不了是常态；整次失败会掩盖其余可用结果。计数使"有东西没读成"**可见** |
| 5 | 超时（`timeout_ms`） | **失败**：`search_timeout`，**零结果返回**，`user_message` 含实际上限值与缩小范围的建议 | **不返回超时前的部分结果**：部分结果取决于超时**发生在哪一毫秒**，与「结果可复现」直接冲突 |
| 6 | 结果超限 | **成功** + `results_truncated=True` + `notice`（含未返回数量），`result_count` 是**实际返回数** | 与 §4.3 同一纪律 |
| 7 | 无匹配 | **成功**，`results=[]`、`result_count=0`、`notice=None` | 这是**真实的"没有"**，与行 1（没有搜）必须区分开 |
| 8 | `path` 逃逸工作区 | `FILE_ERROR` / `workspace_escape` ⇒ preflight `dangerous` ⇒ **硬拒** | §3.1 |
| 9 | 搜索根不存在 / 不是目录 | `FILE_ERROR` / `target_missing` 或 `not_a_directory` | §3.1 |
| 10 | 结果路径复检越界（纵深防御） | **丢弃该条** + `skipped.outside` 计数 + `notice` | §3.2 |

**`max_results` / `max_results_per_file` 的作用顺序（钉死）**：先按文件内的 `line_number` 取前 `max_results_per_file` 项，再做全局排序，最后取前 `max_results` 项。**不得**反过来——那会让结果依赖文件遍历顺序。

### 5.7 行截断与上下文

- 单行长度 > `max_line_chars` ⇒ 在**字符**上限处截断并追加固定标记 `…[已截断]`（标记本身**计入** `max_line_chars`）。截断后行长**恰好** ≤ `max_line_chars`（F 矩阵断言这个等式，不是"大约"）。
- `context_before` / `context_after` 各取 `context_lines` 行，**同样逐行过 `max_line_chars`**。
- 行号从 **1** 开始；上下文在文件首尾处**截短**（不补空串、不补 `null`）。
- **读文件的编码固定为 UTF-8 + `errors="replace"`**（降级引擎）：**不得**抛解码异常，因此"读某个文件时抛 `UnicodeDecodeError`"这条路径在结构上不存在。代价登记为 §14 第 5 项。

### 5.8 结果净化

两个工具的结果都经 `17` §「显示净化」的**同一份实现**：确定性显示路径经 `ResponseBuilder.build()`，回流路径（输入**与**模型输出，§1.4/§1.5）经**同一模块**提升出的公开 `sanitize_display_text()`，长度上限同为公开 `DISPLAY_LIMIT`。**不得**在新工具或回流模块里写第二份净化、也不得另造第二个上限数——**新增净化实现或新上限数即为违例**（D9 / R9 断言：三个新模块内零 `unicodedata` 导入；R13 断言：回流模块从 `response_builder` **导入**该函数与常量，而不是自带）。

---

## 6. 依赖策略（**本版重写，回应阻塞项附条**）

**四个解析库列为正常依赖**（老板 2026-09-27 裁决）：

```toml
[project]
dependencies = [
    "pypdf>=4.0",
    "python-docx>=1.1",
    "openpyxl>=3.1",
    "python-pptx>=0.6.23",
]
```

**前版的推导作废**。前版写「因为要求明确依赖缺失时的行为，所以依赖必须是 optional extra」——**该推导不成立**：即使列为正常依赖，**安装损坏 / 部分安装 / 打包剥离 / 虚拟环境不完整**仍会产生"模块不存在"这一事实，`parser_unavailable` 分支照样需要。老板的判断更准确：P7c 是**默认启用的日常能力**，"支持 PDF/DOCX"却让首次使用普遍得到 `parser_unavailable`，是**产品缺陷**而不是诚实。

因此本版的分工是：

| 事实 | 处置 |
|------|------|
| 正常安装 ⇒ 四个模块**必然存在** | 首次使用的常见路径**不再失败** |
| 异常安装（损坏/剥离）⇒ 某模块不存在 | `parser_unavailable` 的**诚实失败**（§4.6 行 1），逐格式独立判定，且不影响应用启动（§4.8） |
| `TXT` / `Markdown` | 内置 UTF-8 解码，**零依赖**，任何情况下可用 |
| `ripgrep` | **不是** Python 依赖，**不写入** `pyproject.toml`；缺失走降级（§5.5） |

**§0.3 第 1 条的相应修订**：报告不得把「工具已注册」写成「这些格式已支持」，但**也不得**再把它写成「默认安装普遍失败」——正常安装下它们是可用的。

**`pyproject.toml` 写入授权：老板已批准（2026-09-27，§15.1 第 3 项）**——`CLAUDE.md` 规定该文件只在工程初始化阶段可写，因此这是一次**阶段外的显式授权**：本阶段允许把四个解析库写入 `[project.dependencies]`，**授权范围仅限这四个依赖**（不改 `[project.optional-dependencies]` 结构、不改 pytest/ruff/mypy 配置）。Codex 在 §13.3 第 7 步执行。

---

## 7. 错误映射（错误契约的新增值）

### 7.1 `TOOL_EXEC_ERROR.details.reason`：13 → 24（新增十一值）

| reason | 触发 | `recoverable` |
|------|------|:---:|
| `parser_unavailable` | 该格式的模块不存在（§4.6 行 1） | `True` |
| `document_encrypted` | §4.6 行 2 | `False` |
| `document_corrupt` | §4.6 行 3 | `False` |
| `document_unsupported_format` | §4.6 行 6/8 | `False` |
| `document_format_mismatch` | §4.6 行 7 | `False` |
| `document_expansion_too_large` | §4.6 行 9（ZIP 展开超限，§4.5） | `False` |
| `document_extract_failed` | §4.7 兜底 | `True` |
| `query_invalid` | §5.6 行 1/2 | `True` |
| `glob_invalid` | §5.6 行 3 | `True` |
| `search_timeout` | §5.6 行 5 | `True` |
| `search_engine_error` | 两引擎均失败（§5.5） | `True` |

`document_encrypted` / `document_corrupt` / `document_unsupported_format` / `document_format_mismatch` / `document_expansion_too_large` 定 `recoverable=False`：**重试同一个文件不会成功**（用户需换文件或换格式）。`parser_unavailable` 定 `True`：**修好安装就成功**。`document_extract_failed` 定 `True`：无法预判，重试可能不同（例如文件正在被写入）。

### 7.2 `FILE_ERROR.details.reason`：闭集化 + 新增 `target_too_large`

`00-error-contract` §4 目前只举例（"区分 `workspace_escape` / `target_state_changed` 等原因"），未成闭集；实现里实际存在**十个**值。P7c 借本次机会**把它变成显式闭集**（不改任何行为，只把既有事实写实），并新增一个：

| reason | 来源 |
|------|------|
| `workspace_escape` / `path_type` / `target_missing` / `not_a_directory` / `content_too_large` / `content_type` / `read_failed` / `list_failed` / `stat_failed` | 既有实现（`src/tools/file_tools.py`） |
| `target_state_changed` | 既有实现，但**产出点在 `src/main.py:1011`**（App 侧 TOCTOU 复检），不在 `file_tools.py` 内——闭集化时必须算进来，否则会把一个**正在被使用**的值判成越界 |
| **`target_too_large`** | **P7c 新增**：`document.read` 的目标文件超过 `max_file_bytes`（§4.3） |

### 7.3 新增两个 `CONFIG_ERROR.details.reason`

| reason | 触发 |
|------|------|
| `tool_config_invalid` | `[tools.documents]` / `[tools.search]` / `[reflow]` 的**键集越界**或**取值非法**（非正整数、超区间、`context_lines > 3`）。通用、可复用、fail-loud、判本地作者错误。**`[tools.search]` 出现可执行文件相关键（如 `ripgrep_path`）⇒ 本值**（与 `[tool_providers.<id>]` 出现 `command` 同一构造）。**`[reflow]` 的键集闭集不含 `timeout_ms`（2026-09-27 二轮，§1.6）**——写进去即本值：该键不是"暂未实现"，而是**按现有模型接口无法实现**（无调用级超时参数），回流沿用后端自身超时；R15 以此为探针 |
| `result_delivery_invalid` | RD1 / RD2 / RD3 任一不成立（§1.3）。**跨表不变式 `reflow_disabled_with_model_summary_tools` 同用本值**（§1.9：白名单内存在 `model_summary` 工具而 `[reflow].enabled=false`），与 `17` E3 同一构造 |

**不新增错误码**：P7c 不引入新的 `code`。`TOOL_PARAM_ERROR` 仍只由 `validate_tool_call()` 产出（`15` §1.2）。

---

## 8. 能力声明与注册期不变式

### 8.1 能力目录变更（`src/tools/capabilities.py`）

```python
BUILTIN_CAPABILITIES = (
    ToolCapability("weather.current", "查询指定地点的当前天气与当日预报（需联网）", ("weather.current",)),
    ToolCapability("files.read", "读取或列出工作区内的本地文件", ("file.read", "file.list_dir", "document.read")),  # ← 追加一项
    ToolCapability("files.info", "查看工作区内文件或目录的属性", ("file.stat",)),
    ToolCapability("files.write", "在工作区内新建或覆盖一个文本文件", ("file.write",)),
    ToolCapability("files.search", "在工作区内按文件名或内容搜索", ("file.search",)),                              # ← 新增能力
    ToolCapability("system.time", "获取当前本地时间", ("system.get_time",)),
)
```

- **`document.read` 并入 `files.read`**：其 summary「读取或列出工作区内的本地文件」**已覆盖**「读一份文档」，并入**不使 summary 失真**。
- **`file.search` 不得并入 `files.read`**（钉死）：那会让 summary 变成「读取或列出或搜索工作区内的文件」——一个什么都覆盖的摘要会让**阶段一的能力选择失去区分度**，直接损害 `16` §2 的路由质量。单立是为了让模型能区分「读一个文件」与「找一个文件」。

### 8.2 其余不变式

- **R3**（每个 active 工具至少被一个能力服务）：按 `self._active` 全量重算后仍成立；`capability_coverage_missing` 不得出现。
- **R4**（≤8 能力 / ≤2048 字节）：6 个能力，远低于上限。报告须记录新增后的实际能力数与字节数（`16` §9.5）。
- **S1 / S2**：两个新工具都不是副作用工具，不触发。
- **E11 / E12**（egress）：两者 `egress=False`，不触发。
- **RD1–RD3**：新增（§1.3）。`validate_capabilities()` 必须在 `enabled` 门之前跑这三条（与既有 S1/S2/egress 检查同处），否则关态下声明错误会被静默吞掉。
- **`16` §1.5 的生产覆盖表**更新为八项。

**注意 `document.read` 并入 `files.read` 的后果**：能力层**不区分**「读 txt」与「读 pdf」，因此当某格式的模块不存在时，模型选 `files.read` 后**由工具层**给出 `parser_unavailable`。这是**刻意的分工**——能力层回答"需要哪一类能力"，可用性不由能力层表达（`16` §1.2 的"可用性分离"）。**不得**为了"提前告知 pdf 不可用"而在能力层增加格式可用性标注。

---

## 9. 配置契约

### 9.1 三个新表（**键集闭集**，多一键即 `CONFIG_ERROR` / `tool_config_invalid`）

```toml
# ---- P7c 新增（2026-09-27，18 §9.1）----
[tools.documents]
max_file_bytes = 33554432          # 32 MiB
max_extracted_chars = 500000
max_segments_total = 20000
max_returned_segments = 200
max_returned_chars = 40000
max_zip_entries = 2000             # §4.5
max_uncompressed_bytes = 268435456 # 256 MiB，§4.5

[tools.search]
max_results = 50                   # 匹配项总数上限（filename 模式下 = 文件数上限）
max_results_per_file = 5
max_line_chars = 500
context_lines = 1                  # 允许区间 [0, 3]
timeout_ms = 5000
max_file_bytes = 2097152           # 2 MiB（内容扫描单文件上限）
ignore = []                        # 只能追加，不得豁免内置集（§5.2）

[reflow]                           # §1.9，通用（不专属本阶段两个工具）
enabled = true
max_chars = 4000                   # 无 timeout_ms：沿用模型后端自身超时（§1.6）
```

**取值校验（fail-loud，全部 `tool_config_invalid`）**：数值键必须是**正整数**；`max_returned_chars ≤ max_extracted_chars`；`max_returned_segments ≤ max_segments_total`；`context_lines ∈ [0, 3]`；**`max_line_chars ≥ 6`（2026-09-28 新增下限）**——截断标记 `…[已截断]` 本身 6 个字符且**计入**上限（§5.7 的"截断后行长**恰好** ≤ 上限"是一条等式断言），上限小于标记长度时该等式**不可能成立** ⇒ 让这个状态不存在，而不是让实现各自决定丢标记还是超限；`ignore` 必须是字符串数组，每项非空、不含 NUL / `\` / `..` 段（与 §5.6 行 3 同一语法约束）。**表缺席 ⇒ 用默认值，不报错**（`config/ollama.example.toml` 等既有配置**不必**新增这三个表，D12 断言这一点）。

**§1.9 的跨表不变式**（`reflow_disabled_with_model_summary_tools`）在这三个表的校验之后跑。

### 9.2 白名单

`config/default.toml` 的 `[tool_backend.config].whitelist` 追加 `"document.read"` 与 `"file.search"`：

```toml
whitelist = ["system.get_time", "file.read", "file.list_dir", "file.stat", "file.write", "weather.current", "document.read", "file.search"]
```

**`config/eval.example.toml` 改用占位符**：

```toml
whitelist = ["system.get_time", "file.read", "file.list_dir", "file.stat", "file.write", "weather.current"{{DOC_TOOLS}}]
```

`src/evaluation/config.py` 的渲染逻辑追加：

```python
if "{{DOC_TOOLS}}" not in text and variant in {"docs_on", "docs_off"}:
    raise ValueError("evaluation template is missing the doc tools placeholder")
text = text.replace("{{DOC_TOOLS}}", ', "document.read", "file.search"' if variant == "docs_on" else "")
```

并沿用既有的**渲染后校验**（`src/evaluation/config.py:64-68` 的模式）：`docs_on` 渲染后白名单必须含两个新工具，`docs_off` 必须不含——否则 `ValueError`。**2026-09-28 订正**：前版末句写「`{{DOC_TOOLS}}` 自动受 `if "{{" in text` 的未解析占位符守卫覆盖」，**该说法不成立**——末尾的 `if "{{" in text` 只挡**已存在但未替换**的占位符；模板里**根本没有**这个占位符时，它会静默渲染出一个"两个新工具都不在白名单"的配置，`docs_on` 变体于是**静默失效**（S20 在真实 run 上会以一个无法归因的方式判红）。⇒ **上面第 1 段的占位符存在性检查是必需的，不是冗余的**；两处都必须实现。

**`docs_off` 与 `[reflow]` 的关系**：`docs_off` 时两个 `model_summary` 工具不在白名单 ⇒ §1.9 的不变式不触发 ⇒ 无需在模板里改 `[reflow]`。**没有** `reflow_off` 变体（它构造不出来，§1.9）。

**`config/ollama.example.toml` / 其余示例配置：不新增两个工具**，D12 断言它们**在没有三个新配置表的情况下**能正常 bootstrap。

**副作用提醒（Codex 必读）**：`config/default.toml` 的生产目录由 6 项变 8 项，因此任何**硬断言工具总数或目录字节数**的既有测试会变红。**正确处置**：改为「用自带白名单构造基线目录」（与 `16` §9.1 第 5 条对 `system.echo` 的处置同一手法），**不得**为了让测试变绿而把两个新工具从 `default.toml` 白名单里拿掉——那会让 P7c 在生产配置上**不可用**，而 D12 会照样通过。

---

## 10. 可观测性

### 10.1 事件类型零新增，**键集有一次封闭集扩展**（本版订正）

前版声称「事件闭集零扩展」。**加了回流层之后该结论不再成立**：回流必须可观测，否则 §1.6 的失败语义与 §1.8 的轮次账都无法验证。

- **不新增事件类型**（`16` §8.4 的纪律保持）。
- **新增一个持久化键 `result_delivery`**，落在既有的 `tool_execution` 记录上。**它是条件键**——**仅当被执行工具的 `ToolDef.result_delivery == "model_summary"` 时出现**，闭集二值：

| 值 | 含义 |
|------|------|
| `"model_summary"` | 回流成功，回复由本地模型基于工具结果生成 |
| `"model_summary_failed"` | 声明了回流但回流失败/超时/空输出 ⇒ 已回落确定性显示（§1.6） |

- **为什么做成条件键（钉死，这是刻意的取舍）**：若恒发此键，全部既有工具的 `tool_execution` 键集都会多一个键，`17` 的「关态与 P7a 关态事件流逐字段相等」与 `16` §9.1 的「键集相等」两条锚点**当场失效**。做成条件键后，**未声明回流的工具（含 `file.write` 与全部既有工具）的 `tool_execution` 键集与引入前逐字段相等**。「出现条件」先于「取值域」写死，是 `07` §3 段 2026-09-23 点② 已立的纪律。
- **工具执行本身失败**的回合不发此键（没有结果可回流）。
- **两份白名单必须一起改**（`07` §6.2 纪律）：`src/main.py::_sanitize_event_data` 与 `src/observability/sinks.py::_PERSISTED_KEYS`。**只改一处 ⇒ N4 变红**。
- `reply_provenance` **语义不变**：回流是**呈现层**，工具**确实执行了** ⇒ 仍是 `"executed"`。**不得**因为回复是模型写的就把它改成 `"answered"`（那会让"工具是否真的执行"这一事实丢失）。
- 回流调用**不计入 `rounds_used`**（§1.8）。

### 10.2 派生谓词与报告侧

- 报告新增派生量：`Σ(result_delivery == "model_summary")`（回流成功次数）与 `Σ(result_delivery == "model_summary_failed")`（回落次数）。**两者必须与 `rounds_used` 分列**（§1.8）。
- `scripts/p6_report.py` 与周报按 §12.5 的硬性行输出。

---

## 11. 工厂装配与变更影响清单（**替代前版「三项零变更」**）

### 11.1 变更影响清单（**本版据实重写**）

回流层使前版的「三项零变更 + 零必要变更」**不再成立**。逐项照实：

| 对象 | 变更 | 必要性 |
|------|------|------|
| `src/core/interfaces.py`（全部 ABC） | **零变更** | 回流不需要新抽象方法 |
| `src/core/result_reflow.py`（**新模块**） | 新增组件与**值类型 `ReflowOutcome`**（§1.2.1） | 它是回流层的唯一实现点；值类型与它的唯一生产者同处（`ExecutionRecord` 记在接口文档、代码落 `schemas.py` 是同一条先例） |
| `src/core/schemas.py` 的 `ToolContext` / `PreflightReport` | **零变更** | — |
| `src/core/schemas.py` 的 `ToolDef` | **新增字段** `result_delivery: str = "deterministic"`（追加式，最后一字段，默认值保证既有构造调用零改动） | §1.3：判据必须是**注册期声明**而不是 App 里的工具名特判；默认值保证既有工具行为逐字不变 |
| `ToolHandler` 签名 `Callable[[dict, ToolContext], dict]` | **零变更** | — |
| `src/main.py` 的两个 `response.build` 调用点 | **各插入一次共享的 `reflow()` 调用，并把它排到 `_record_tool_events()` 之前**（§1.2） | 无回流则文档能力不成立 |
| `src/main.py` 的 `App.__init__` / `_finish_bootstrap` | **新增一个注入项**（回流组件：模板 + `max_chars` 预算 + 模型后端引用 + **构造期冻结的工具目录 `tool_defs`**（§1.2.4）；**无超时参数**，§1.6） | 与 `response` / `executor` 同法注入，保持可测试（单测注入替身）。**每回合的 `fallback_display` 不进构造，走调用实参**——二者生命周期不同（§1.2.4 第 4 条） |
| `src/main.py` 的 `App` **状态** | **新增私有字段 `_pending_user_request: str \| None`**（§1.2.3）：进入等待确认时冻结原始请求；`_clear_pending()` **加一行**清它（**唯一**清理点）；确认成功分支**在 `execute()` 之前**取出到局部变量 | 无此载体则确认路径的回流输入**只能是口令**，「总结这份文档」在该路径上不成立（**老板第三轮阻塞点 1**） |
| `bootstrap()` **签名** | **零变更**（`model_backend` 已在入参里） | — |
| `bootstrap()` **装配步骤** | **新增一步**（§13.2）：`normalize_reflow_config(config["reflow"])` → 构造 `ResultReflow` → 作为 `reflow=` 传入 `App` | **只改 `App.__init__` 签名而不在这里构造，生产环境不会启用回流**，`model_summary` 工具退化为"打印一截结构化文本"（§1.1 缺口复现）。前版的"步骤零新增"**作废** |
| `00-error-contract` | +11 `TOOL_EXEC_ERROR` 值、`FILE_ERROR` 闭集化 +1 值、+2 `CONFIG_ERROR` 值 | §7 |
| 事件键集 | **+1 持久化键**（两份白名单） | §10.1 |

**未变的仍然是重要的**：`ToolBackend` 抽象、`ToolProvider`、`16` 的 R1–R8/S1/S2、`capability_relevance()` 集合隶属权威、路径安全实现、净化实现、云端准入与授权链、`weather.current` 行为。

### 11.2 handler 如何拿到上限与预算（钉死，复用 `16` §5.3 的闭包工厂先例）

`ToolContext` 只有 `{workspace_root, tool_def}`，**没有**配置通道；`16` §5.3 已就 `weather.current` 钉死了正确解法——**闭包工厂 + 实例级 active registry**，**不得**做成模块级全局变量。P7c 照此办理：

```python
# src/tools/document_tools.py
def make_document_tool(settings: dict) -> RegisteredTool: ...   # handler / preflight 闭包在内部
# src/tools/search_tools.py
def make_search_tool(settings: dict) -> RegisteredTool: ...
```

**2026-09-28 修订（据实登记）**：前版钉死的名字是 `make_document_read_handler(limits: DocumentLimits)` / `make_search_handler(limits: SearchLimits)` 与 `BUILTIN_IGNORE_DIRS`。已交付实现为 **`make_document_tool(settings: dict)` / `make_search_tool(settings: dict)`**（返回 `RegisteredTool`，把 handler 与 preflight 一起闭包进去）与私有 `_IGNORED_DIRS`；limits 是**裸 `dict`**（由 `main.py` 的三个 `normalize_*_config()` 校验后传入），**没有** `DocumentLimits` / `SearchLimits` 类型。**命名与是否使用 dataclass 都不承载契约价值** ⇒ 口径按实情登记，**不要求改名**；契约在意的只有「上限经闭包工厂注入、不得做成模块级全局」（已满足，且与 `weather.current` 同法）。

**两个 `ToolDef` 住在哪里**（2026-09-28 修订）：

- **定义**是静态事实（与配置无关）⇒ 模块级常量；前版钉死写成 `registry.py` 的 `CONFIGURABLE_TOOL_DEFS: Mapping[str, ToolDef]`，**实际采用**与 `WEATHER_TOOL_DEF` 同一先例：`DOCUMENT_TOOL_DEF` / `SEARCH_TOOL_DEF` 各自住在**工具模块内**，由 `registry.product_tool_definitions()` 惰性 import 后追加。**该形状满足「定义与配置无关」这一目的**，故契约按实情登记（`CONFIGURABLE_TOOL_DEFS` 不再是强制名）。
- **不进 `BUILTIN_TOOLS`**。后者的语义是「**已完整绑定**（`ToolDef` + handler，零配置依赖）的注册项」，而这两个工具的 handler 需要 limits ⇒ 塞进去必然出现「一个绑了默认值的 handler 和一个在装配期被换掉的 handler」两条路径。**保持 `BUILTIN_TOOLS` 的每一项都是零配置依赖**，新工具**只经 `self._active` 进入运行期目录**（与 `weather.current` 完全相同）。
- **R2 的已知工具名全集** = `BUILTIN_TOOLS` 键 ∪ `product_tool_definitions()` 键 ∪ 已准入的外部工具规范名。这是**代码里的确定性事实**，**不得**由配置或目录内容反推。
- **N5 的字面量禁令不变**：装配处（`src/tools/builtin_backend.py`）**必须**用 `DOCUMENT_TOOL_DEF.name` / `SEARCH_TOOL_DEF.name`，**不得**写 `registered["document.read"] = …` 这类字面量。

### 11.3 bootstrap 接线顺序

在既有十四步（`17` §9.2）**不变**的前提下，工具目录装配步骤内按此顺序：

1. 解析 `[tools]` → `workspace_root`（既有）。
2. 解析 `[tools.documents]` / `[tools.search]` / `[reflow]`，**缺席用默认**，非法 ⇒ `CONFIG_ERROR`（**在任何工具被注册之前**）。
3. 构造 limits、handlers、回流组件。
4. `self._active` = 白名单过滤的 `BUILTIN_TOOLS` ∪ （天气，若 provider 可用）∪ （两个新工具，若在白名单内）。
5. **跑 §1.9 的跨表不变式**（`reflow_disabled_with_model_summary_tools`）——它需要 `self._active`，故必须在此处而非第 2 步。
6. `validate_capabilities(...)` 按 `self._active` 跑 R1–R8 / S1 / S2 / E11 / E12 / **RD1–RD3**（既有 + 新增）。

**零新增 bootstrap 步骤**：第 2–5 步是既有"解析 `[tools]`"步骤的扩展。

### 11.4 `App.shutdown()`

不变（`17` §2.4）。两个工具不持有任何进程或文件句柄（文件用 `with` 或读完即关），回流的模型调用是同步的、无长期资源 ⇒ `BuiltinToolBackend` 继续用默认 `close()`。

---

## 12. 验收矩阵

> **每一条都必须带"探针"**（把机制删掉后该条必须变红）。没有探针的行不算验收项。
> **零真实网络**：本阶段的两个工具都不联网；回流的模型调用一律用**脚本化替身模型**（`ModelBackend` 替身）。

### 12.1 非干扰性（单列）

| # | 断言 | 探针 |
|:---:|------|------|
| N1 | 白名单**不含**两个新工具时，`list_tools()`、能力目录、全部既有工具的行为与 P7b 基线**逐字段相等**；`capability_any` 分布不变 | 把两个新工具无条件并入 `self._active`（忽略白名单）⇒ N1 红 |
| N2 | 两个新工具与 `weather.current` **互不影响**：天气的 `ToolDef`、出站三级校验、`16` §5.4 的八值 reason 集**零改动**（源码级比对）；且因 RD3，天气**永不**进回流 | 把 `weather.current` 声明为 `result_delivery="model_summary"` ⇒ N2 红（`CONFIG_ERROR` / `result_delivery_invalid`） |
| N3 | 两个新工具**不在** `LOCAL_SIDE_EFFECT_TOOLS`，不参与 `high_impact` 合成；`file.write` 的确认链与 S14 期望**零变化** | 把 `document.read` 加进 `LOCAL_SIDE_EFFECT_TOOLS` ⇒ N3 红（`files.read` 含副作用工具且工具数 != 1 ⇒ S1 触发） |
| N4 | 事件**类型**未新增；两份白名单**同步**增加了且仅增加了 `result_delivery`；**且该键是条件键**——既有工具的 `tool_execution` 键集与引入前**逐字段相等** | 只改 `_sanitize_event_data` 不改 `_PERSISTED_KEYS` ⇒ N4 红；新增第二个键 ⇒ N4 红；把条件键改成恒发 ⇒ N4 红（既有工具键集多一键） |
| N5 | `composite_backend.py` / `builtin_backend.py` / `main.py` / `control_policy.py` / `task_planner.py` / `guarded_executor.py` 内**零** `document.read` / `file.search` 字面量 | 在 `main.py` 加一个 `if tool_name == "document.read"` 分支 ⇒ N5 红（**D1 的源码级孪生断言**） |
| N6 | **既有工具的回流行为零变化**：不声明 `result_delivery` 的工具**不发**该键、回复逐字等于 `ResponseBuilder.build().display`，且替身模型的调用计数为 0 | 把 `result_delivery` 的默认值改成 `"model_summary"` ⇒ N6 红（S01–S19 大面积红） |
| **N7** | **确认链的可观测面零变化**（**第三轮新增**）：白名单**不含** `model_summary` 工具时，完整的确认流程（进等待确认 → 口令正确 → 执行完成）产出的 **episode 字节、事件流、用户可见输出**与 P7b 基线**逐字段相等**——新增的冻结载体 `_pending_user_request` **不得在任何输出面留下痕迹**（含日志与审计） | 把冻结值写进 `_record_turn` 的 User 段、或把它塞进事件字段 ⇒ N7 红；在确认回合额外发一个事件 ⇒ N7 红 |

### 12.2 回流层矩阵（R1–R21，**本版新增**；R13–R15 第二轮补，R16–R18 第三轮补，R19 第四轮补，R20–R21 第五轮补）

| # | 断言 | 探针 |
|:---:|------|------|
| R1 | **只读工具会回流**：`document.read` 执行成功后，回复**不是** `ResponseBuilder.build().display`，且替身模型收到的请求里含工具结果的正文 | 把回流调用删掉（直接 `return output.display`）⇒ R1 红 |
| R2 | **零工具名特判**：见 N5；且回流判据只读 `ToolDef.result_delivery` | 把判据改成 `if tool_name in {...}` ⇒ R2 红（N5 的源码级断言先红） |
| R3 | **写入类工具不改写**：`file.write` 执行的回复逐字等于 `ResponseBuilder.build()` 的输出；替身模型的调用计数为 **0**；`tool_execution` **不发** `result_delivery` 键 | 让 `file.write` 也走回流 ⇒ R3 红（RD2 会在启动期先红）；给 `file.write` 的 `tool_execution` 加上 `result_delivery="deterministic"` ⇒ R3 红 |
| R4 | **RD2 是注册期不可达**：把 `file.write` 声明为 `model_summary` ⇒ `CONFIG_ERROR` / `result_delivery_invalid`，**零启动** | 删掉 RD2 检查 ⇒ R4 红 |
| R5 | **RD3 是注册期不可达**：把 `weather.current` 声明为 `model_summary` ⇒ 同上 | 删掉 RD3 检查 ⇒ R5 红 |
| R6 | **事实头不被截断**：构造一个"正文远超 `max_chars` 且 `truncated=True`"的结果 ⇒ 替身模型收到的请求里**同时**含 `notice` 与真实计数，且 `notice` 出现在正文截断标记**之前** | 把 `notice` 移到正文之后并参与截断 ⇒ R6 红 |
| R7 | **失败回落**：替身模型抛 `ModelError` / 超时 / 返回空串（三臂各一次）⇒ 回复**逐字等于**确定性 display，`result_delivery="model_summary_failed"`，**零 `degradation` 事件** | 把失败改成抛错或返回空回复 ⇒ R7 红；发 `degradation` ⇒ R7 红 |
| R8 | **两个调用点行为一致**：直连路径与"确认后消费"路径在同类结果上产生同形的回流行为（同一共享函数） | 只在直连路径接回流 ⇒ R8 红（确认路径不回流） |
| R9 | **结构性边界（源级）**：`result_reflow.py` 零 `unicodedata` 导入（复用唯一消毒实现）；零解析层符号导入（输出不进入 `ToolCallDraft` 解析） | 在 `result_reflow.py` 里 `import unicodedata` 或 `from src.core.intent_resolver import ...` ⇒ R9 红 |
| R10 | **结构性边界（源级）**：`result_reflow.py` 零 `src/cloud/` 导入；回流结果不经 `PrivacyPolicy` / `TaskBrief` 任何构造点 | 在回流模块里 import 云端模块 ⇒ R10 红 |
| R11 | **注入不产生动作**：替身模型在回流里返回一段"请执行 file.write"的文本 ⇒ 零工具执行、零确认、零云端准入，用户只看到这段文本 | 把回流输出接回 `decide()` ⇒ R11 红 |
| R12 | **轮次账**：回流发生一次 ⇒ `rounds_used` **不变**；`Σ(result_delivery=="model_summary")` +1；`reply_provenance` 仍为 `"executed"` | 把回流算进 `rounds_used`，或把 `reply_provenance` 改成 `"answered"` ⇒ R12 红 |
| **R13** | **回流输出的消毒与长度上限**（§1.5，**2026-09-27 审查后新增**）：①替身模型返回含 `\x1b`（ANSI）、`\x07`、Cf 字符的文本 ⇒ CLI 捕获的输出里**不得**出现这些码点；②替身模型返回 > `DISPLAY_LIMIT` 字符 ⇒ 输出被截断到 `DISPLAY_LIMIT`；③回流成功与回流回落两条路径的用户可见文本**上限相等**；④`sanitize_display_text` / `DISPLAY_LIMIT` 是**公开**符号，`result_reflow.py` 从 `response_builder` 导入而不是自带实现 | ①删掉回流输出处的消毒调用 ⇒ R13 红；②不设上限或另造一个上限数 ⇒ R13 红；③在 `result_reflow.py` 里写第二份消毒（或复制一份 4096 字面量）⇒ R13 红 |
| **R14** | **按 step_index 关联，不按工具名**（§1.2；**2026-09-27 第三轮改写——前版"两个同名 step 一个声明回流一个不声明"构造不出来**，因为 `result_delivery` 是**工具级**固定声明）。改为**直接对 `_execution_records` 注入映射**：构造含**两个同名工具 step**（同为 `document.read`）的计划与该计划的 `results`，调用 `_execution_records(plan, results, {1: "model_summary"})` ⇒ 断言 **step_index=1 的记录有值、step_index=0 的同名记录仍为 `None`**（同一 `tool_name` ⇒ 二者不可能靠名字区分）；再构造一个"低 step_index 在 `results` 里但**越界/被过滤**"的臂，断言注入值**不发生位移** | 把实现改成"先按工具名建索引再查" ⇒ R14 红（两条同名记录**同值**，第一条也不为 `None`）；用 `enumerate` 的列表下标当 step_index ⇒ R14 红（过滤臂错位，值落到错误记录上） |
| **R15** | **回流无调用级超时**（§1.6）：①`[reflow]` 的**键集闭集不含** `timeout_ms`（写进去即 `tool_config_invalid`）；②`result_reflow.py` **零** `threading` / `Timer` / `concurrent.futures` 导入（源级断言）——"等 N 秒后放弃"这一实现路径在结构上不存在 | 给 `[reflow]` 加 `timeout_ms` 并接受它 ⇒ R15 红（应判 `tool_config_invalid`）；在 `result_reflow.py` 里 `import threading` 或用 `Timer` 实现超时 ⇒ R15 红 |
| **R16** | **确认路径的回流输入是冻结的原始请求**（§1.2.3，**第三轮新增**）：走确认链（首轮进等待确认 → 第二轮输入口令），替身模型捕获提示 ⇒ ①提示里**含**首轮那句读请求的原文；②提示里**不含**确认口令字面量。另断言 `_pending_user_request` 在**取消 / 拒绝 / 会话不匹配 / 口令错误 / 锁定 / 预检失败 / TOCTOU 变化 / 执行完成**八条路径后均为 `None`（与 `_pending_plan` 同生同死）；并断言冻结值**不出现在** episode / 事件 / 审计任何输出面（`_record_turn` 仍是 `"[身份确认，原文不留存]"`） | 把 `current_input` 直接传给回流（即前版行为）⇒ R16 臂①红（提示里是口令而不是读请求）；在清理时只清 `_pending_plan` 而漏掉冻结值 ⇒ 取消臂红；把冻结值写进 `_record_turn` ⇒ 泄漏臂红 |
| **R17** | **每回合至多一次回流模型调用**（§1.2.2，**第三轮新增**）：构造覆盖集大小为 2 与 3 的计划各一次 ⇒ ①替身模型**调用计数恒为 1**；②该回合所有被覆盖 step 的 `result_delivery` 取值**相同**；③没有覆盖集（无 `model_summary` step，或 `results` 为空）时**调用计数为 0** 且 `display` **逐字节等于** `response.build().display`（**措辞已按 §0.8 订正**：前版写"或全部 `outcome != "success"`"，而 `results` 只含成功步骤、结果 dict 里**没有** `outcome` 字段，"失败步骤"在本层**不存在**——执行失败会整轮抛错） | 改成逐 step 调用 ⇒ 计数等于覆盖集大小 ⇒ R17 红；给每个 step 各分配一份 `max_chars` ⇒ 组装臂红；无覆盖集时仍调用模型 ⇒ R17 红 |
| **R18** | **多 step 输入的归属可区分**（§1.4，**第三轮新增**）：覆盖集含**两个同名工具 step** ⇒ 替身模型收到的提示里两组结果**各带 `step_index` 且可区分**（不得只写 `tool_name`）；两组的正文拼接顺序按 **step_index 升序** | 组装时只写 `tool_name` 不写 `step_index` ⇒ R18 红（同名两组不可区分）；按 `results` 字典迭代顺序拼接 ⇒ R18 红（顺序不稳定） |
| **R19** | **生产装配路径真的启用了回流**（**第四轮补，老板审查后新增**）：用**默认配置**（`[reflow]` 缺席 ⇒ 默认开；白名单含 `document.read`）调用 **`bootstrap()`** ⇒ ①返回的 `App` **实际持有一个 `enabled=True` 的 `ResultReflow`**；②对该 `App` 走一遍"读请求 → 确认 → 执行"，**替身模型的调用计数 ≥ 1**，回复**不是** `ResponseBuilder.build().display`（不再退化成"打印一截结构化文本"）；③`[reflow]` 写未知键（含 `timeout_ms`）⇒ `CONFIG_ERROR` / `tool_config_invalid`，**零启动**。**这一条必须走 `bootstrap()` 而不是直接构造 `App(reflow=替身)`**——后者恰恰会漏掉"装配步骤缺失"这一缺陷形态 | **把 `bootstrap()` 里的 `ResultReflow` 构造与 `reflow=` 传参删掉**（只保留 `App.__init__` 的新参数）⇒ R19 红，而**其余 R 条目仍可能全绿**（单测直接构造 `App` 并注入替身）——这正是本条存在的理由；`normalize_reflow_config` 只做键集闭集而不给默认值 ⇒ R19 臂③红 |
| **R20** | **同一回合的 `result_delivery` 在事件面与 episode 面取值一致**（§0.8，**第五轮新增**）：本回合的 `_execution_records` 有**三个**调用点——`src/main.py:885`（事件用）、**`:893`（episode 用，前版契约漏掉的正是这一个）**、`1020`（直连路径）。走一次确认路径的 `document.read`（替身模型成功回流）⇒ ①`tool_execution` 事件里该 step 的 `result_delivery == "model_summary"`；②**episode 里同一 step 的记录取值相同**（不得一侧有值、一侧为 `None`） | **只在事件侧传 `outcome.deliveries`、`:893` 处仍写成 `_execution_records(plan, results)`** ⇒ R20 臂②红（episode 记录为 `None`），而**其余 R 条目仍可能全绿**——这正是本条的缺陷形态；把 `:893` 改成重新调用一次 `_reflow` ⇒ R20 红（模型调用计数变成 2，同时 R17 红） |
| **R21** | **执行抛错 ⇒ 零回流**（§0.8，**第五轮新增**）：让某 step 的执行抛 `LocalMindError`（例如 `TOOL_EXEC_ERROR`）⇒ ①替身模型**调用计数为 0**；②用户可见回复**就是** `exc.user_message`；③`tool_execution` **不发** `result_delivery` 键。**含"前序 step 已成功"的臂**：多 step 计划里 step 1 失败、step 0 已成功 ⇒ **step 0 的成功结果不得被事后回流**（它连 `output` 都没构造，`fallback_display` 不存在） | 在 `except` 分支里也调用回流 ⇒ R21 红。**这条排除的是一种善意误读**："部分成功也应该总结"——那是**新的产品语义**（部分成功语义），本阶段明确不做 |

**R20/R21 与 §1.2.4 的关系**：R20 断言的是**同一个 `deliveries` 映射必须被本回合所有调用点共用**（数据流一致性），R21 断言的是**回流只在成功路径上发生**（控制流边界）。二者都是"契约自己内部要对齐"的性质，与两个工具的解析行为无关，可用任一 `sensitive` + 需确认的既有工具构造（不依赖 P7c 的新代码）。

### 12.3 `document.read` 矩阵（D1–D16）

> 夹具策略：`.txt` / `.md` **测试时直接写入** tmp 工作区；`.docx` / `.xlsx` / `.pptx` **测试时由对应库写出**；`.pdf` **手写最小合法 PDF**（约 300 字节 ASCII，无需第三方写库），"扫描件"臂 = 手写的"有页无文本层" PDF，"加密"臂 = 手写含 `/Encrypt` 字典的 PDF，"压缩炸弹"臂 = 用 `zipfile` 现造一个高压缩比 ZIP。**禁止**为造夹具而把二进制文件提交进仓库（若某臂手写构造被证明不可行，允许提交 **< 2 KiB** 的夹具并在测试里注明来源）。

| # | 断言 | 探针 |
|:---:|------|------|
| D1 | 两个新工具**零主循环特判**（见 N5） | 见 N5 |
| D2 | **路径边界复用**：`../x.pdf` / `/etc/passwd` / `C:\x.pdf` / `~/x.pdf` 四条各返回 `FILE_ERROR` / `workspace_escape`，preflight 为 `effective_risk="dangerous"` + `requires_confirmation=True` | 自写一份路径检查（不复用 `resolve_workspace_target`）⇒ D2 红；把解析器的 `.resolve()` 去掉 ⇒ D2 红 |
| D3 | **只读性**：任何输入都不产生文件系统写入（前后工作区目录树的 mtime + 文件清单逐一相等） | 在 handler 里加一次 `open(..., "w")` ⇒ D3 红 |
| D4 | **不进副作用路径**：`approval_profile` 合成结果与不引入这两个工具时**逐字段相等**；`file.write` 的 `high_impact` 扣留行为不变 | 把 `document.read` 的 `risk_level` 改成 `dangerous` ⇒ D4 红 |
| D5 | **截断声明三不变式**（§4.2/§4.3）：①`truncated ⟺ reason is not None`；②`truncated ⇒ notice 含未返回数量`（提取期停止 ⇒ 写「总数未知」）；③提取期停止 ⇒ `segments_total is None`；返回期截断 ⇒ `segments_total` 是精确值。另有 `chars_extracted` 是**实际已提取数**、提取期停止时是**下界**、**不得**被当作总量；结果 dict **不含** `chars_total` | ①删 `notice` ⇒ 红；②`segments_total = len(segments)` ⇒ 红；③提取期停止时把 `chars_extracted` 写成估计总量 ⇒ 红；给结果加一个 `chars_total` 键 ⇒ 红 |
| D6 | **四类成功形态**：正常文档 ⇒ `extraction="ok"` + 非空 segments；空文档 ⇒ `"empty"` + **空 segments** + notice；扫描 PDF ⇒ `"no_text_layer"` + **空 segments** + notice；TXT 0 字符 ⇒ `"empty"`。**四者都不是错误** | 把 `"no_text_layer"` 改成抛错 ⇒ D6 红；给空文档塞占位段以满足"至少一段" ⇒ D6 红 |
| D7 | **七种故障面**（§4.6 行 1/2/3/6/7/8/9）：逐夹具断言 `code` + `details.reason` 精确匹配，`user_message` 是完整中文句子 | 把 `document_format_mismatch` 与 `document_encrypted` 合并 ⇒ D7 红（`.docx` 的 OLE2 臂与 ZIP-缺成员臂会同时命中）；把 `document_expansion_too_large` 并入 `document_corrupt` ⇒ D7 红 |
| D8 | **信息泄漏**：替身解析器抛 `RuntimeError("SECRET-DOC-TEXT")` ⇒ 四个位置均不含该串，且 `details["exception_type"] == "RuntimeError"`。**替身来源**（§4.9 的 2026-09-28 修订）：向 `sys.modules` 注入一个 `PdfReader` 会抛错的替身模块 | 把 `exception_type` 改成 `str(exc)` ⇒ D8 红 |
| D9 | **净化不重复实现**：三个新模块（`document_tools` / `search_tools` / `result_reflow`）零 `unicodedata` 导入（**源级扫描**；§5.6 行 3 判据⑦ 已改述为码位区间实现，故搜索工具同样可满足） | 在任一模块加 `unicodedata` ⇒ D9 红（与 R9 同源） |
| D10 | **逐格式提取范围**（§4.4）：六格式各一条 happy path，断言 `locator.kind` 与 `format`；**DOCX 表格产出 `table_row` 段**；**PPTX 表格并入 slide 段的 text 且不产出 `table_row`**；XLSX 公式单元格返回**公式文本**（`=SUM(...)`）而非空；`description` 含页眉/备注/公式的范围声明 | 把 XLSX 改成 `data_only=True` ⇒ D10 红（公式单元格变空）；把 DOCX 表格丢弃 ⇒ D10 红；删掉 `description` 的范围句 ⇒ D10 红 |
| D11 | **模块缺失不阻断启动**：在**模拟某个模块不存在**（`find_spec` 被替换为 `None`）的解释器里 `bootstrap()` 成功，且能正常回答一个无关问题；同一环境里 `.txt` 读取**成功**、该格式返回 `parser_unavailable`（**逐格式独立**） | 把任一解析器的 import 提到模块顶层 ⇒ D11 红 |
| D12 | **配置缺席可用**：无三个新配置表时用默认值并 bootstrap 成功；既有示例配置不改也能跑 | 把缺表改成 `CONFIG_ERROR` ⇒ D12 红 |
| D13 | **配置闭集**：三个表各注入一个未知键 ⇒ `tool_config_invalid`；`context_lines = 5` ⇒ 同；`ignore = [".."]` ⇒ 同；`[tools.search]` 出现 `ripgrep_path` ⇒ 同；`max_returned_chars > max_extracted_chars` ⇒ 同 | 把未知键改成"忽略未知键" ⇒ D13 红 |
| D14 | **文件大小上限**：超 `max_file_bytes` 的文件 ⇒ `FILE_ERROR` / `target_too_large` 且**零解析**（替身解析器调用计数为 0）；1000 段的文档 ⇒ `truncation_reason="max_returned_segments"` 且 notice 含"剩余 800 段" | 把检查挪到解析之后 ⇒ D14 红 |
| D15 | **ZIP 展开上限**（§4.5）：高压缩比 ZIP ⇒ `document_expansion_too_large`，且**替身解析器调用计数为 0**（检查在解析器之前）。**替身来源**同 D8（`sys.modules` 注入带调用计数的替身模块） | 把检查移到解析器之后 ⇒ D15 红 |
| D16 | **段数与字符上限的并列打破**（§4.3）：三段巨型文本，两个提取上限被同一段顶破 ⇒ `truncation_reason == "max_extracted_chars"`（**不得**是 `max_segments_total`） | 把判定顺序改成"先段数后字符" ⇒ D16 红 |

### 12.4 `file.search` 矩阵（F1–F13）

| # | 断言 | 探针 |
|:---:|------|------|
| F1 | **`mode` 闭集**：`"filename"` 零文件内容读取（用替身断言未 `open` 任何文件）、`"content"` 走内容匹配；`mode="regex"` / 缺 `mode` ⇒ `query_invalid` | 给 `mode` 加默认值 ⇒ F1 红 |
| F2 | **空查询**：`query=""` 与 `"   "` ⇒ `query_invalid`，**零结果**（**不是** `results=[]` 的成功） | 改成返回 `results=[]` ⇒ F2 红 |
| F3 | **忽略集方向**：配置含 `ignore = ["foo"]` 时内置项**仍被忽略**（`.git` 里有 `TODO`，断言未搜到） | 把 `effective_ignore` 改成"配置存在则用配置" ⇒ F3 红 |
| F4 | **`--no-ignore`**：在 `data/` 被 gitignore 的仓库里，工作区内的文件**必须**被搜到 | 删掉 `--no-ignore` ⇒ F4 红 |
| **F4b** | **裁剪必须真的省下遍历**（本版新增）：`.venv` 里放 2000 个含 `query` 的文件 ⇒ ripgrep 路径下这些**零产出**，且 `elapsed_ms` 显著低于"无排除参数"的对照运行（同夹具、同机器，比值断言） | 删掉排除参数（只靠权威过滤）⇒ F4b 红（时间比与产出都不符） |
| F5 | **glob 七子判据**（§5.6 行 3）各一例 ⇒ `glob_invalid`；合法 glob（`**/*.py`）正常工作 | 把含 `..` 的 glob 改成放行 ⇒ F5 红 |
| F6 | **二进制两道防线**：`.png`（扩展名）与 `fake.txt`（内容二进制、含 `\x00`）**都**不产出匹配；`skipped.binary` ≥ 2 | 删掉第二道（NUL 探测）⇒ F6 红 |
| F7 | **跨引擎一致性（UTF-8 夹具）**：同一夹具集、同一参数，`engine="ripgrep"` 与 `"python"` 的 `results` **逐项逐字段相等**。**夹具必须包含隐藏文件（`.foo`）与 `.venv` 内的文件**——它们正是前版两引擎分歧的来源 | 让 `os.walk` 不跳过隐藏条目 ⇒ F7 红；让 ripgrep 传 `--hidden` ⇒ F7 红；把任一后置处理挪进引擎专用分支 ⇒ F7 红 |
| F8 | **稳定排序**：按 `(path, line_number)` 升序；**连跑两次 + 交换引擎**结果逐项相等 | 去掉 `sorted(...)` ⇒ F8 红（**必须靠"交换引擎"臂**，单跑很可能绿） |
| F9 | **超时**：`timeout_ms` 极小 + 大目录 ⇒ `search_timeout`，`results` 为空，`user_message` 含实际上限值；**进程已终止**（无残留子进程） | 改成"返回超时前的部分结果" ⇒ F9 红 |
| F10 | **结果超限**：命中数超 `max_results` ⇒ `results_truncated=True` + notice 含未返回数量；`max_results_per_file` 使单文件贡献 ≤ 该值；**先每文件后全局** | 把顺序反过来 ⇒ F10 红（用"一个文件 100 命中 + 30 个文件各 1 命中"的夹具） |
| **F11a** | **不跟随符号链接**（本版拆分）：工作区内放一个指向工作区外的**目录**符号链接与一个指向工作区外文件的**文件**符号链接，其中都含匹配内容 ⇒ **零匹配**，`skipped.outside == 0`（因为从未产生候选） | 让 `os.walk` 跟随目录链接（`followlinks=True`）⇒ F11a 红；**不跳过文件符号链接** ⇒ F11a 红 |
| **F11b** | **结果复检（纵深防御，靠注入验证）**：直接调用结果阶段过滤函数，注入一条 `path` 指向工作区外的伪造候选 ⇒ 该条被丢弃，`skipped.outside` +1，`notice` 非空 | 删掉结果阶段复检 ⇒ F11b 红 |
| F12 | **不可读与无匹配**：不可读文件 ⇒ 跳过 + `skipped.unreadable` 计数（ripgrep 路径下允许 `null`，**不得**为 0 冒充）+ 不失败；无匹配 ⇒ 成功 + `results=[]` + `notice=None` | 把不可读改成整体失败 ⇒ F12 红；未知时填 0 ⇒ F12 红 |
| F13 | **隐藏条目一致**（本版新增）：`.hidden.txt` 与 `.hiddendir/` 内的匹配在两引擎下**都不产出** | 在 ripgrep 路径加 `--hidden` ⇒ F13 红 |

### 12.5 评估场景（S20 / S21）与报告硬性行

**新增两个场景**，各两臂（`docs_on` / `docs_off`），沿用 S19 的变体纪律：

| 场景 | 步骤（摘要） | 关键 `expect` |
|------|------|------|
| **S20_document_read** | setup：`identity`（`eval-pass-0000`）+ `workspace_file`（`notes/notes.md`，测试内容）。①（`docs_on`）「读取 notes/notes.md 的内容并总结一下。」②（`docs_on`）「确认 eval-pass-0000」③（`docs_off`）同一句读请求 ④「/quit」 | ①**`confirmation_required=true` + `tool_none=true`**（`document.read` 为 `sensitive` + 需确认，口径对齐 `file.read`/S14——**前版缺这一步，首轮只会停在等待确认，后两步永远不会发生**）；②`tool_any=["document.read"]` + `capability_any=["routed"]` + **`result_delivery_any=["model_summary"]`** + **`output_not_contains=["eval-pass-0000"]`**；③`tool_none=true` + `capability_any=["unavailable"]` + `cloud_any=false` |
| **S21_workspace_search** | setup：`workspace_file`（`notes/todo.md`，含 `TODO` 行）——**无需 `identity`**（`file.search` 为 `normal` + 免确认）。①（`docs_on`）「在工作区里搜一下 TODO」②（`docs_on`）「搜文件名含 todo 的文件」③（`docs_off`）同一句内容搜索 ④「/quit」 | ①**`tool_any=["file.search"]` + `capability_any=["routed"]` + `result_delivery_any=["model_summary"]`**；②`tool_any=["file.search"]`；③`tool_none=true` + `capability_any=["unavailable"]` |

**三处必须照实写明的场景口径（钉死）**：

1. **S20 的"免确认"与 S21 的"免确认"必须用不同方式断言**（`file.search` 免确认是老板 2026-09-27 裁决的结果，`document.read` 需确认是 S14 口径）：S20 用 `confirmation_required=true` **显式**断言第一轮停在确认；S21 则在**第一轮**直接断言 `tool_any=["file.search"]`——若它需要确认，该轮就只会有等待确认而**零 `tool_execution`**（S14 的 `tool_none=true` 臂已确立这一对应关系）。**因此 S21 的第一轮 `tool_any` 就是"免确认"的断言，不需要新 `_EXPECT_KEYS` 值。**
2. **S20 第②步的 `result_delivery_any=["model_summary"]` 是环境相关断言，不得改判**：评估用的是真实本地模型，若该模型调用失败，该步会落在 `model_summary_failed` 上并**判红**。这**是正确的**——该步要验证的恰恰是"回流真的发生了"。按 §12.5 硬性行②，`model_summary_failed` 的计数**与 `rounds_used` 分列**上报，**不得**为了让场景变绿而把期望放宽成两个值都接受（那会让"回流从未成功"与"回流成功"在验收上不可分）。

**`_EXPECT_KEYS` 新增一值 `result_delivery_any`**（本版新增，用于在真实 run 上断言回流发生过）——**校验形态与 `tool_any` / `capability_any` 同类**：非空字符串列表（`src/evaluation/scenarios.py:351-356` 的现有循环里加一个键名即可，**不得**为它新造一套校验）；`_VARIANTS` 新增 `docs_on` / `docs_off`。**断言语义**：本轮**任一** `tool_execution` 的 `result_delivery` 取值落在该列表中即算命中；**无条件键的回合不参与**（`None` 不是取值）。

**`_EXPECT_KEYS` 另新增一值 `output_not_contains`**（**第三轮新增**，S20 阻塞点 1 的可观测侧）——**校验形态**：非空字符串列表，与上面同一个循环里加键名；**断言语义**：本轮**用户可见输出**（即 `handle()` 的返回值，也就是 §1.2 里 `outcome.display`）**不得包含**列表中任一子串，命中即判红。它是**单串否定断言**，与既有的 `output_contains`（肯定）互为对偶，**不得**扩展成正则或作用域选择器。

**必须照实写明的 S20 断言边界（第三轮新增，钉死）**：老板要求的"**S20 应断言回流提示包含原始读取请求，且不含确认口令**"，**前半在场景层做不到、后半才做得到**：

| 断言 | 归属 | 为什么 |
|------|:---:|------|
| 回流**提示里含读请求原文、不含口令** | **R16（单元测试）** | 场景层用**真实本地模型**跑真实 `App`，能观测到的只有**事件**与**输出文本**；提示词是发给模型的私有输入，**不进事件、不进持久面**（钉死：任何把提示词写进事件的做法都会绕过 P4 的不留原文纪律）。⇒ 只能由**替身模型捕获提示**的单元测试断言 |
| 口令不得出现在**用户可见输出**里 | **S20 第②步 `output_not_contains`** | 这是提示污染的**可观测后果**：若回流误把口令当请求喂进模型，模型倾向于在摘要里复述它 ⇒ 输出必然带口令。这条**在场景层可证伪**，因此 S20 承担它 |

**不得**把 S20 的通过表述为"确认路径的回流输入已验证正确"——已验证的是**它的后果**，不是提示内容本身；后者只有 R16 覆盖。

**另一条照实写明的边界（第四轮新增）**：S20/S21 走**真实 `bootstrap()`**（评估运行器复用真实 App 流程，`requirements.md` FR11），因此它们**确实覆盖了生产装配路径**——这是它们相对单元矩阵的一个真实优势，应当如实写出来。但**仍不得**由"S20 通过"推出"回流在生产配置下可用"：场景跑的是**评估专用配置**（白名单占位符渲染后的 `docs_on` 变体），而**默认生产配置是否接上回流**由 **R19**（默认配置 + `bootstrap()`）承担。两者是**不同配置下的不同断言**，混用即为过度宣称（§0.3 第 8 条 / `requirements.md` 第七条不得宣称）。

**必须照实写明的场景层覆盖上限**：`_SETUP_KINDS` 的 `workspace_file` 只能经 `file.write` 写**文本**（`src/evaluation/child.py:86-89`），因此 **S20/S21 只能用 `.md` / `.txt` 夹具**。PDF/DOCX/XLSX/PPTX 的行为由 §12.3 的**单元矩阵**覆盖，**不由评估场景覆盖**。**不得**把"S20 通过"表述为"文档读取在真实 run 里验证过"。二进制夹具的 setup 扩展登记为 §14 第 3 项。

**`scripts/p6_report.py` / 周报新增硬性行**：

1. 两个工具各自的**规则级通过数 / 失败数**（§12.3 / §12.4）。
2. **回流统计**：`model_summary` / `model_summary_failed` 两个计数**与 `rounds_used` 分列**（§1.8）；**不得**把回流调用混进意图轮次计数。
3. **每个格式模块的存在性**与因此**未执行的臂**数——**不得**把未执行计为通过。
4. 新增后的**工具数 / 能力数 / 目录字节数**（`16` §9.5）。
5. `engine="python"` 的搜索占比（降级是否在真实环境里常态发生——这是**环境事实**而非缺陷，但必须可见）。
6. **回流延迟照实分列**：报告记录每次回流的 `duration_ms`（若有）与回落次数，**不得**把它写成"有超时保护"——回流沿用后端自身超时（§0.3 第 6 条 / §1.6），本阶段不承诺延迟上界。
7. **硬性红线**：`document.read` / `file.search` 出现**任何一次工作区逃逸**即为**失败**；`segments_total` 出现"用猜测值冒充未知"、或 `chars_extracted` 在提取期停止时被当作总量，即为**失败**；出现「`truncated=True` 而回复未提及未返回部分」计为**诚实性失败**（由 `output_contains` 与人工复核共同判定，逐条记录）。

---

## 13. 同步清单

### 13.1 Claude（本轮同步）

| 文件 | 变更 | 状态 |
|------|------|:---:|
| `specs/modules/18-...md` | 本文档（**2026-09-27 第二轮审查后重写**：新增 §1 回流层，重写 §§3.2/5.2/5.3/6/11，订正 §§1.2/1.4/1.5/1.6/4.2/4.3，新增 §§4.4/4.5/15.1/S20-S21 重写；**第三轮审查后**：新增 §0.6 / §1.2.1 `ReflowOutcome` / §1.2.2 多 step 策略 / §1.2.3 冻结原始请求，改写 R14、新增 R16–R18 与 `output_not_contains`，§14 +第 23 项；**第四轮审查后**：新增 §0.7 接线遗漏处置、R19、§15 四条决策行，§0.3 +第 8 条，§11.1/§13.2/§13.3/§16 的 `bootstrap()` 口径订正；**第五轮（Codex 提出）**：新增 §0.8（`tool_defs` 构造期冻结 + `fallback_display` 调用期传入 + "成功是构造性事实"的措辞订正）、§1.2.4 签名块、R20–R21、§15 七条决策行） | 本轮 |
| `specs/requirements.md` | **FR12 重写**（新增回流层要求、四条阻塞项处置、**R1–R15**；**第三轮**：R16–R18、冻结原始请求的安全口径、非宣称项 +第 ⑤ 条；**第四轮**：R19、`bootstrap()` 装配口径订正、非宣称项 +第 ⑦ 条；**第五轮**：新增⑬（目录走构造期、确定性显示走调用期、"成功"是构造性事实、三个调用点、执行抛错零回流）、R20–R21） | 本轮 |
| `specs/modules/00-core-interfaces.md` | **两处接口签名变更**：`ToolDef.result_delivery` + **`ExecutionRecord.result_delivery`**（均追加式、带默认值）；**新增 Core 类型 `ReflowOutcome`** | 本轮 |
| `specs/modules/00-error-contract.md` | `TOOL_EXEC_ERROR` 13 → **24**；`FILE_ERROR` 闭集化（11 值）；`CONFIG_ERROR` +`tool_config_invalid` +`result_delivery_invalid` | 本轮 |
| `specs/modules/07-p6a-observability-cli.md` | 记录新增**条件**持久化键 `result_delivery`（两份白名单同步） | 本轮 |
| `specs/modules/00-adapter-factory.md` | ①**`ExecutionRecord` 字段块 +`result_delivery`**（§1.2 的状态载体）②**示范配置 +3 个表**（`[tools.documents]` / `[tools.search]` / `[reflow]`，只列键名、权威默认值指向 §9.1，**不复制第二份真源**）③**`ReflowOutcome` / `ResultReflow` 块 + `App.__init__` 的 `reflow` 参数 + `App` 状态的 `_pending_user_request`**④**`bootstrap()` 内新增回流层的装配步骤**（`normalize_reflow_config()` + 构造 `ResultReflow` + 传入 `App`）。**ABC 零变更；`bootstrap()` 签名零变更，但**装配步骤有新增**——前版写的"`bootstrap()` 步骤零新增"**作废**（照此实现则生产环境不启用回流，文档总结仍不可用） | 本轮 |
| `specs/modules/16-...md` | §1.5 生产覆盖表 +2 行；§11 第 2 项补 P7c 复核 | 本轮 |
| `specs/project-plan.md` | 路线图 **P7c 行** + 立项说明（含回流层）+ 第二至五轮据实修订段 | 本轮 |
| `CLAUDE.md` | 「关键设计文档」表 +1 行（含四轮审查摘要） | 本轮 |
| `specs/progress-summary.md` | P7c 立项段 + 第二至五轮修订段（第四、五轮为**面向老板的宏观叙述**，不写文件英文名，只讲"用什么方法解决什么问题"） | 本轮 |
| `specs/modules/15-tool-orchestration-hardening.md` | §1.1 增补段：`ToolDef` 新增 `result_delivery` 与 RD1–RD3（与 P7b 的 `egress` 增补同处） | 本轮 |

### 13.2 Codex（工程契约镜像 + 代码 + 测试）

| 文件 | 变更 |
|------|------|
| `src/core/schemas.py` | `ToolDef` 追加 `result_delivery: str = "deterministic"`；**`ExecutionRecord` 追加 `result_delivery: str \| None = None`** |
| `src/core/response_builder.py` | **`_sanitize_display_string` → 公开 `sanitize_display_text()`；`_DISPLAY_LIMIT` → 公开 `DISPLAY_LIMIT`**（调用点同步改名，行为零变化） |
| `src/core/result_reflow.py`（**新**） | **`ResultReflow(backend, tool_defs, enabled=True, max_chars=4000)`**（§1.2.4：构造期把 `tool_defs` 冻结成 **name → `result_delivery`** 的映射，**只读这一个字段**；查不到的工具名按 `deterministic` 处理）与 **`__call__(plan, results, original_request, fallback_display) -> ReflowOutcome`**（`fallback_display` 是**本回合实参**，两态原样返回它、**永不自己合成回落文本**）；模板常量 / 输入组装（事实头 + 有界正文，**多 step 按 step_index 升序、单一共享 `max_chars` 预算**）/ 不可信数据标记 / **每回合至多一次**调用模型 / **输出过 `sanitize_display_text()` + 截到 `DISPLAY_LIMIT`**；**零** `unicodedata`、零解析层、零 cloud、零 `src/tools/` 的执行或校验符号（只消费 `ToolDef` 数据类型）、**零 `threading`/`Timer`/`concurrent.futures`** |
| `src/main.py` | **①新增 `normalize_reflow_config(raw) -> dict`**（`[reflow]` 的**键集闭集 + 默认值唯一实现点**，住配置解析区，与 `normalize_cloud_advisory_config` 同处）；**②`bootstrap()` 新增装配步骤**——调用它、构造 **`ResultReflow(backend=model_backend, tool_defs=tool_backend.list_tools(), enabled=…, max_chars=…)`**（`tool_backend` 在 `_finish_bootstrap` 的入参里、`list_tools()` 已在同函数内被 `validate_tool_catalog` 用过）、作为 `reflow=` 传入 `App`（**只改 `App.__init__` 签名而不构造 = 生产不启用回流**）；③两个 `response.build` 调用点插入共享 `reflow()` 并排到 `_record_tool_events()` 之前（`outcome = self._reflow(plan, results, original_request, fallback_display=output.display)` → `return outcome.display`，**零分支**）；④**`_execution_records(plan, results, deliveries)` 新增第三参数**按 step_index 回填，**本回合的** **三个**调用点（`src/main.py:885` / **`:893`（episode）** / `1020`）**必须传同一份 `outcome.deliveries`**（R20）；⑤`App._run_reflow()` 是**关态的唯一实现点**（`None ⇒ ReflowOutcome(fallback_display, {})`；名从前版的 `App._reflow()` 据实改为 `_run_reflow()`，语义不变），`enabled=False` 由组件内部短路；⑥**失败路径（`except LocalMindError`）零回流**（R21）；⑦`_record_tool_events()` 签名不变、仅在非 `None` 时发键；⑧**新增 `App._pending_user_request`**并在进入等待确认时冻结、在 `execute()` **之前**取出到局部 `original_request`（§1.2.3）；⑨`_clear_pending()` **加一行**清该字段（八条路径共用）；⑩`App.__init__` / `_finish_bootstrap` 注入回流组件（`App._run_reflow` 薄包装 + `enabled` 短路）；⑪`_sanitize_event_data` 白名单 +`result_delivery`，**并同时把它加入该处的条件键跳过集合**——该键只对声明 `model_summary` 的工具发出，恒发会让既有工具的 `tool_execution` 键集多一个 `None` ⇒ N4 红（**2026-09-28 实现审查：只做了 `_PERSISTED_KEYS` 一处，本条整条未兑现，见 `specs/reviews/18-p7c-implementation-review.md` 阻塞 1**） |
| `src/observability/sinks.py` | `_PERSISTED_KEYS` +`result_delivery`（**与上一行同时改**） |
| `src/tools/registry.py` | `product_tool_definitions()` 追加两个 `ToolDef`（**定义住在工具模块内**，见 §11.2；**不进 `BUILTIN_TOOLS`**） |
| `src/tools/document_tools.py`（新） | `DOCUMENT_TOOL_DEF` / `make_document_tool(settings)` / `preflight_document()` / ZIP 检查（§4.5，**在解析器之前**）/ 分派期**惰性 import**（§4.8；内部形状按 §4.9 的 2026-09-28 修订，不强制描述符表） |
| `src/tools/search_tools.py`（新） | `SEARCH_TOOL_DEF` / `make_search_tool(settings)` / `preflight_search()` / `_IGNORED_DIRS` / 忽略策略**编译为排除参数**（§5.2 ①）/ ripgrep 调用（§5.5 必须+禁止两栏）/ Python 降级 / **两引擎共用的权威过滤与后置处理**（结果阶段复检须抽成**可注入的独立函数**以兑现 F11b） |
| `src/core/subprocess_env.py`（新，**2026-09-28 补登**） | `restricted_subprocess_environment()`：`17` 的子进程环境白名单构造器的**搬迁**（逐键逐值不变，仍禁继承 `os.environ`）⇒ `search_tools` 与 `mcp_adapter` **单向复用同一实现** |
| `src/adapters/mcp_adapter.py`（**2026-09-28 补登**） | `_ENV_COPY_ALLOWLIST` 改为 import 上一行；`stderr=DEVNULL` / `shell=False` 行为零变化 |
| `src/tools/capabilities.py` | `BUILTIN_CAPABILITIES` 改一行加一行；**新增 RD1–RD3 检查**（在 `enabled` 门之前）；`LOCAL_SIDE_EFFECT_TOOLS` 不动 |
| `src/tools/builtin_backend.py` | 构造期解析三个新配置表（缺席用默认）+ 跨表不变式 + 闭包工厂 + 并入 `self._active` |
| `src/tools/file_tools.py` | **只允许**跨模块复用既有函数；**路径判据零改动** |
| `src/evaluation/config.py` | `{{DOC_TOOLS}}` 渲染 + `docs_on`/`docs_off` 渲染后校验 |
| `src/evaluation/scenarios.py` | `_VARIANTS` +`docs_on`/`docs_off`；`_EXPECT_KEYS` **+2**：`result_delivery_any` 与 `output_not_contains`（均在既有 `src/evaluation/scenarios.py:351-356` 的循环里加键名，**不新造校验器**） |
| `scenarios/S20_document_read.toml`、`S21_workspace_search.toml`（新） | §12.5（S20 第②步含 `output_not_contains=["eval-pass-0000"]`） |
| `config/default.toml` | 白名单追加两工具 + 三个新配置表 |
| `config/eval.example.toml` | 白名单改占位符 |
| `tests/test_p7c_reflow.py`、`test_p7c_documents.py`、`test_p7c_search.py`（新） | **R1–R21** / D1–D16 / F1–F13，**每条带探针**。其中 R13 必须含"替身模型返回 `\x1b` / `\x07` / Cf 字符"的臂，并用 CLI 捕获输出断言码点未出现；**R14 用注入 `deliveries` 的形态直接测 `_execution_records`**（含两个同名 step）；**R16 用替身模型捕获提示**并覆盖八条清理路径；**R17 断言每回合调用计数恒为 1 / 无覆盖集时为 0**；**R18 断言多 step 归属可区分且按 `step_index` 升序**；**R19 必须走 `bootstrap()`**（不得直接构造 `App` 注入替身），断言默认配置下 `App` 持有启用的回流组件且端到端发生模型调用；**R20 断言事件面与 episode 面（`src/main.py:893` 这个被漏掉的第三个调用点）取值一致**；**R21 断言执行抛错时零回流、零 `result_delivery` 键** |
| `pyproject.toml` | **授权已到位**（§15.1 第 3 项）：四个解析库进 `[project.dependencies]`（**正常依赖，不是 optional extra**） |
| `specs/modules/00-*.md` | 工程契约镜像；**两处新增字段（`ToolDef.result_delivery`、`ExecutionRecord.result_delivery`）属接口签名变更** ⇒ 已由 Claude 在本轮先行写入 `00-core-interfaces.md`（与 `00-adapter-factory.md` 的 `ExecutionRecord` 块），Codex 只做镜像 |

### 13.3 建议实施顺序

1. **回流层骨架 + 两处签名变更 + `ReflowOutcome` + `sanitize_display_text`/`DISPLAY_LIMIT` 公开化 + RD1–RD3 + 事件键 + 两个调用点接线 + `_execution_records` 第三参数 + `_pending_user_request` 冻结载体 + `normalize_reflow_config()` 与 **`bootstrap()` 内的构造/注入步骤****（§1）——**最先做**，因为它是本阶段的能力前提，且它独立于两个工具（可用 `system.get_time` 的替身声明来测 R1–R18）。**R13（输出消毒与长度上限）、R14（按 step_index 关联）、R16（确认路径的冻结原文）、R17（每回合至多一次调用）、R18（多 step 归属可区分）、R20（三个 `_execution_records` 调用点共用同一份 `deliveries`）、R21（执行抛错零回流）必须在本步一并完成**——它们是回流接线的组成部分，不是后续补丁。**R16 需要确认链，可与第 2 步并行**（它不依赖两个新工具，可用任一 `sensitive` + 需确认的既有工具构造）。**本步完成的判据包含一条端到端事实**：`bootstrap()` 的返回值（`App`）**实际持有**一个 `ResultReflow` 且 `enabled=true`（且其 `tool_defs` 来自 `tool_backend.list_tools()`）——**只改签名不构造不算完成**（否则生产路径上回流从不发生，而所有单测仍可能因为直接构造 `App(reflow=替身)` 而全绿）。**另需按 §1.2.4 的顺序接线**：`fallback_display` 在**调用时**传入、目录在**构造时**冻结、`App._reflow` 是关态的唯一实现点、本回合三个 `_execution_records` 调用点共用同一份 `deliveries`。
2. 错误契约落地（§7 的三个 reason 集）。
3. `document_tools.py` 骨架 + `.txt`/`.md` 解析器（零依赖路径）⇒ D11/D12。
4. `search_tools.py` 的 Python 引擎 + 全部权威过滤与后置处理 ⇒ F1–F13（`engine="python"`）。
5. 接 ripgrep 引擎（候选裁剪 + 只替换"候选发现"）⇒ F4b/F7/F8/F13。
6. 能力声明 + `builtin_backend` 装配 + 三个配置表 ⇒ D12/D13。
7. 四格式解析器 + ZIP 检查（**`pyproject.toml` 授权已到位**，§15.1 第 3 项）⇒ D6/D7/D10/D14/D15/D16。
8. 评估侧（`config.py` / `scenarios.py` / S20 / S21）。
9. 扫描 §12.1 N1–N7 与 D1 的源码级断言。

---

## 14. 遗留与明确不做（每项带触发条件）

| # | 项 | 触发条件 |
|:---:|------|------|
| 1 | `document.read` 的**范围参数**（`pages` / `sheet` / `slide` / 字符区间） | 真实 run 出现「要读大文档的指定部分而工具只给开头」≥ 2 次 |
| 2 | 回流预算**按 token 精确切分**（当前按字符代理） | 出现"回流输入被模型截断"的真实证据（模型侧报上下文超限或总结缺失尾部） |
| 3 | 评估侧**二进制夹具**（`_SETUP_KINDS` 新增 `workspace_binary_file`） | 需要在真实 run 里评估 PDF/DOCX 行为 |
| 4 | **正则内容搜索** | 出现明确的模式匹配需求，且同时给出 ReDoS 边界论证 |
| 5 | **非 UTF-8 文本**（UTF-16 / GBK / BOM）的跨引擎一致性与正确解码 | 出现真实的中文 GBK 文档/源码搜索需求 |
| 6 | **格式与扩展名不符时按真实格式解析**（当前 fail-closed） | 出现"后缀写错但我就是想读它"的高频真实需求 |
| 7 | **隐藏文件**（`.` 开头）的搜索 | 需要搜 `.github/workflows` 一类路径 |
| 8 | `file.search` 的**片段内容**是否也需确认链（当前 `normal` + 免确认） | 老板对只读内容工具的确认语义重新拍板（与 §15.1 第 1 项同源；该项已按"保持现状"定稿，本项只在老板**再次**提出时触发） |
| 9 | **模型必须转述 `notice`** 的机制化校验 | 出现"截断未告知用户导致误判"的真实 run 证据（§12.5 报告硬性行第 7 条已把它列为诚实性失败） |
| 10 | DOCX **页眉/页脚/脚注/批注**、PPTX **备注**、PDF 注释/表单字段 | 出现明确的真实需求 |
| 11 | XLSX **缓存值**（`data_only=True`）读取 | 出现"想看公式结果而不是公式文本"的高频需求，且能解决"未被 Excel 打开过的文件缓存值为空"的问题 |
| 12 | **回流层的提示词注入防护**（分隔符以外的隔离手段） | 结构性隔离已由 §1.5 保证「注入不产生动作」；剩余面（注入改变用户读到的文字）需要更强的模型侧手段，单独立项 |
| 13 | **PDF 的展开预算**（对象流/解压炸弹） | 出现真实的恶意或异常 PDF 样本；缓解现状是 `max_file_bytes` + `max_extracted_chars` |
| 14 | OCR / 扫描 PDF | 独立阶段（需模型权重与内存预算论证，NFR1） |
| 15 | 内容索引 / 向量化 / 增量索引 | 独立阶段（与 `03` 记忆的检索面合并设计） |
| 16 | 旧格式 `.doc` / `.xls` / `.ppt` | 出现真实需求 + OLE2 解析库的依赖论证 |
| 17 | 通用 `web.search` / `web.fetch` / OCR / 文档编辑 / 内容索引 | **明确不做**（`16` §11 第 1/2 项；老板已裁决 P7c 不介入联网搜索） |
| 18 | `file.search` 的**文件名模式也包装 ripgrep** | 大目录下文件名搜索被证明是性能瓶颈，且能给出"两引擎逐字节一致"的验收臂 |
| 19 | **回流扩展到 `egress=True` 的工具** | 需要先解决「外部文本零进提示词」（`17`）与回流的冲突，属独立安全问题 |
| 20 | 回流结果的**多轮追问**（"再详细讲讲第二部分"复用上一次工具结果） | 需要把工具结果纳入跨轮状态，涉及记忆留存面，单独立项 |
| 21 | **`ModelBackend.generate()` 的调用级超时**（使回流能独立于后端构造期超时设自己的上限） | 老板阻塞项 1 的备选方案。触发条件：**回流在真实运行中造成可感知的响应迟滞**，且能给出"同步所有实现（含 `ollama_backend` / `mock_backend`）"的签名变更与回归论证。**在此之前不得用线程/定时器事后放弃来实现超时**（§1.6，R15 探针） |
| 22 | **回流输出上限与显示上限解耦**（当前刻意共用一个 `DISPLAY_LIMIT`） | 出现"回流输出被 4096 截断导致答案不完整、而回落显示无需那么长"的真实证据 |
| 23 | **等待确认计划的有效期（TTL）** — 当前 `_pending_*` 与 `App._pending_user_request` **都没有超时**：一个悬挂的确认回合会一直保留冻结的原始请求直到用户下次输入（或 `/quit`） | 老板阻塞点 1 要求"**超时**和执行结束时清除"，而现有链路**没有超时这一条路径**（§1.2.3 照实写明只有七条）。若将来引入 TTL，**冻结的请求必须与 `_pending_plan` 同生同死**（同一处清理），不得单独留一个"已无计划但仍持有原文"的状态 |
| 24 | **回流事实头不含结果来源标识**（**2026-09-28 实现审查后登记**）：§1.4 钉死的事实头字段是 `tool_name` / `step_index` / `truncated` / `truncation_reason` / `segments_total` / `chars_extracted` / `notice` / 计数类字段；工具结果里的 `path`（文档）、`root` / `query` / `mode`（搜索）、`segment_truncated` **都不进提示词** ⇒ 模型总结时**不知道自己在总结哪一份文档、哪一次搜索**（只能从用户原话推断），也无法区分"整段截断"与"段内截断" | 出现「总结没提到文件名 / 搜索范围」的真实用户反馈，或模型把两份同名文档的结论混同的 run 证据。届时把**来源标识字段**加入事实头白名单（仍不参与截断） |

---

## 15. 决策记录

| 日期 | 决策 | 理由 / 取舍 |
|------|------|------|
| 2026-09-27 | **P7c 不介入联网搜索** | 老板裁决；与 `16` §11 第 1/2 项一致 |
| 2026-09-27 | **两个工具都只有最小参数集**；上限只来自配置 | 「模型放大自己的读取预算」成为**不存在的状态**（`17` 裁决 6 同源） |
| 2026-09-27 | **`mode` 必填、无默认值**；**不得实现为 `param_instance_checks`** | Schema 子集不含 `enum`；实例谓词语义不同，套用会把每次合法搜索判红 |
| 2026-09-27 | **`document.read` 并入 `files.read`，`file.search` 单立 `files.search`** | 前者不使 summary 失真；后者若并入会让阶段一的选择失去区分度 |
| 2026-09-27 | **空文档 / 扫描 PDF 是成功，不是失败** | 做成错误会让模型的可用信息退化为"工具坏了"；正确结论是"没有可读文字" |
| 2026-09-27 | **格式与扩展名不符 ⇒ fail-closed** | 防止"把 `.exe` 改名 `.pdf`"进入解析器；代价见 §14 第 6 项 |
| 2026-09-27 | **解析器异常只记类名，不记 `str(exc)`** | 解析器异常文本常内嵌文档片段或路径 |
| 2026-09-27 | **配置只能追加忽略项，不得豁免内置项** | 「把 `.venv` 从忽略集去掉」成为**不存在的状态** |
| 2026-09-27 | **排序在收集后自己做，不透传引擎顺序** | ripgrep 输出顺序不受保证；F8 必须用"交换引擎"臂 |
| 2026-09-27 | **超时不返回部分结果** | 部分结果取决于超时发生在哪一毫秒，与"结果可复现"冲突 |
| 2026-09-27 | **ripgrep 路径由代码在 PATH 解析** | `17` 裁决 6 同源 |
| 2026-09-27 | **文件名模式只用 Python 引擎** | 第二引擎对文件名匹配只带来语义漂移；触发条件见 §14 第 18 项 |
| 2026-09-27 | **`skipped.unreadable` / `segments_total` 未知时填 `null`** | `17` 纪律：不得用 0 或猜测值冒充未知 |
| 2026-09-27 审查后 | **必须实现只读工具结果回流层**（原版把目标降级为"提取并显示"，不成立） | 老板阻塞项 1：现状下模型全程看不到工具结果（§1.1），「总结这份 PDF」结构上不可能 |
| 2026-09-27 审查后 | **回流的判据是 `ToolDef.result_delivery` 声明，不是工具名** | 老板要求「不得按名字特判」；声明 + RD2/RD3 让"让模型改写写入结果"与"外部文本进提示词"成为**注册期不可达** |
| 2026-09-27 审查后 | **回流输出只作文本消费，不进入任何解析/执行/云端路径** | §1.5：这是对提示词注入唯一的结构性承诺（**注入不产生动作**） |
| 2026-09-27 审查后 | **回流失败回落确定性显示，且不发 `degradation`** | 工具结果永不因回流失败而丢失；不污染既有降级口径 |
| 2026-09-27 审查后 | **回流不计入 `rounds_used`，但 `result_delivery` 必须可观测** | 诚实计数：`rounds_used` 是意图轮次的账；回流单独分列（§1.8） |
| 2026-09-27 审查后 | **忽略策略拆成「裁剪」与「权威过滤」两段**；前版「禁止把忽略交给引擎」的绝对禁令**作废** | 老板阻塞项 2：原措辞与 `--no-ignore` 自相矛盾，且让 ripgrep 扫完 `.venv` 才过滤 |
| 2026-09-27 审查后 | **两个引擎都跳过隐藏条目** | 老板阻塞项 2：ripgrep 默认跳过、`os.walk` 不跳 ⇒ 前版 F7 逐字段相等**不可达** |
| 2026-09-27 审查后 | **两引擎都不跟随任何符号链接（含文件符号链接）**；结果复检降级为**纵深防御**并靠注入验收 | 老板阻塞项 3：原 F11 不可达。`os.walk` 的 `followlinks=False` **不覆盖文件符号链接**，且 `open()` 会跟随它——这是前版的真实漏洞 |
| 2026-09-27 审查后 | **`truncation_reason` 新增 `max_extracted_chars`**；`chars_extracted` 明确为"实际已提取"（下界）；**刻意不设 `chars_total`**（恒等于 `chars_extracted` 或恒为 `null`，无信息量）；「至少返回一段」限定 `extraction="ok"` | 老板阻塞项 4：把字符上限记为段数上限会说出事实错误的话 |
| 2026-09-27 审查后 | **逐格式提取范围写进契约与 `ToolDef.description`** | 不钉死则实现会自行猜测；写入描述使其对模型可见且可被 D10 断言 |
| 2026-09-27 审查后 | **XLSX 用 `data_only=False`（公式文本）** | 缓存值由 Excel 写入，**从未被 Excel 打开过的文件缓存值为空** ⇒ 会**静默丢失关键内容** |
| 2026-09-27 审查后 | **OOXML 增加 ZIP 条目数与展开大小上限，且检查在解析器之前** | 10 MB 的 OOXML 可合法展开成数 GB；检查必须在解析器拿到路径之前 |
| 2026-09-27 审查后 | **四个解析库改为正常依赖**；前版「optional extra」的推导**作废** | 老板裁决：P7c 是默认启用的日常能力，"支持 PDF"却让首用普遍失败是产品缺陷。`parser_unavailable` 保留，覆盖**安装损坏/部分安装/打包剥离** |
| 2026-09-27 | `document_encrypted` / `document_corrupt` / `document_unsupported_format` / `document_format_mismatch` / `document_expansion_too_large` 定 `recoverable=False` | 重试同一文件不会成功；`parser_unavailable` 例外（修好安装即成功） |
| 2026-09-27 第二轮审查后 | **删除 `[reflow].timeout_ms`**，回流沿用模型后端自身的超时（§1.6） | 老板阻塞项 1：`ModelBackend.generate()` 无调用级超时参数，Ollama 超时在构造期固定；独立 `timeout_ms` **无法实现**。调用级超时扩展登记为 §14 第 21 项 |
| 2026-09-27 第二轮审查后 | **显式禁止"线程等待 N 秒后放弃"的回流超时实现**（零 `threading` / `Timer` / `concurrent.futures` 导入，R15 探针） | 放弃等待**不取消**底层 HTTP 请求，请求继续跑完并占用连接；反复发生会累积后台线程。这不是"超时"，是把泄漏伪装成超时 |
| 2026-09-27 第二轮审查后 | **`ExecutionRecord` 追加可选字段 `result_delivery: str \| None = None`**，回流返回 `Mapping[int, str]`（step_index → 值），由 `_execution_records(plan, results, deliveries)` 按 **step_index** 回填 | 老板阻塞项 2：只写"回流要在记录事件前完成"**没有载体**；多步计划不能用全局字符串。**不按工具名关联**——同一计划可多次调用同名工具（R14） |
| 2026-09-27 第二轮审查后 | **`_record_tool_events(records)` 签名不变**，改由 `_execution_records` 承担回填 | `_execution_records` 内有 `if not 0 <= step_index < len(plan.steps): continue`（`src/main.py:1818-1819`）⇒ **列表下标 ≠ step_index**，把映射传进 `_record_tool_events` 再按下标取值会在被过滤的臂上错位 |
| 2026-09-27 第二轮审查后 | **`_sanitize_display_string` 提升为公开 `sanitize_display_text()`；`_DISPLAY_LIMIT` 提升为公开 `DISPLAY_LIMIT`**；回流输入**与回流模型输出**都调用前者，输出另加后者 | 老板阻塞项 3：回流成功时 `reflow()` 的返回值**直接作为最终文本**，**不经过 `ResponseBuilder.build()`**——前版"仍经 `build()` 的净化槽位"**与真实链路不符**，等于模型输出净化与长度上限**都没钉死**（R13） |
| 2026-09-27 第二轮审查后 | **S20 改为「identity + workspace_file + 确认两步」四步场景**（前版首轮即断言 `tool_any`，**不可达**） | 老板阻塞项 4：`document.read` 是 `sensitive` + 需确认，首轮只会进等待确认 ⇒ 前版 S20 的 `tool_any` 与回流事件**永远不会出现**。改后口径对齐 S14 |
| 2026-09-27 第二轮审查后 | **删除"`max_returned_chars` 服务于执行记录的可审计留存"的说法** | 与代码不符：`ExecutionRecord` 只存字段名摘要（`_execution_summary` 明确 "without retaining any returned value"），工具返回值**不进持久面**。40000 是**执行期内存上限**（§1.4 据实订正） |
| 2026-09-27 第三轮审查后 | **确认路径新增冻结载体 `App._pending_user_request`**，生命周期完全挂在既有 `_clear_pending()` 上（八条路径共用**唯一**清理点）；**必须在 `execute()` 之前取出到局部变量** | 老板阻塞点 1：`_pending_*` 九字段**没有一个存原始请求**，`_handle_confirmation()` 签名拿不到它，确认回合的 `current_input` **就是口令** ⇒ 确认路径的回流输入**必然是口令**，"总结这份文档"在该路径上**结构性不成立**（§1.2.3） |
| 2026-09-27 第三轮审查后 | **冻结值只作回流输入**，不进 episode / 记忆 / 事件 / 审计 / 云端；`_record_turn("[身份确认，原文不留存]", …)` **保持不变** | P4 的"确认回合不留存原文"是既有安全口径，**回流需要原文 ≠ 可以留存原文**。把"为了回流而留存"做成先例，会让 P4 纪律从一处口子开始失效（§1.2.3 第 5 条） |
| 2026-09-27 第三轮审查后 | **`reflow()` 返回 `ReflowOutcome(display, deliveries)`**，失败回落返回同一结构 | 老板阻塞点 2：调用方需要的是**一句回复文本**，`Mapping[int, str]` 只带"哪些 step 走了模型摘要"，**装不下回复**；同结构回落让两个调用点**零分支**、失败路径不产生特例（§1.2.1） |
| 2026-09-27 第三轮审查后 | **多 step 回流 = 每回合至多一次模型调用，覆盖全部 `model_summary` 成功步骤**；覆盖集内取值必然相同 | 老板阻塞点 3 的前半。**先钉策略再改测试**：逐 step 调用会产生 N 个互相独立的候选文本，而一个回合只有一句回复；且成本随 step 数线性增长，与"每回合至多一次"的预算口径冲突（§1.2.2） |
| 2026-09-27 第三轮审查后 | **R14 改为直接对 `_execution_records` 注入 step_index 映射**（同名 `document.read` 两步 + `{1: "model_summary"}`） | 老板阻塞点 3：`result_delivery` 是 **ToolDef 级**声明 ⇒ **两个同名 step 声明必然相同**，原夹具**构造不出来**。改写后断言的是"**回填会不会按工具名串写**"，与计划能否构造无关（§12.2 R14） |
| 2026-09-27 第三轮审查后 | **S20 第②步增加 `output_not_contains=["eval-pass-0000"]`**；并**照实登记**"提示含原始请求"这半句**在场景层无法断言**，归于 R16 | 老板阻塞点 1 的断言要求分两半：**提示内容**只有替身模型捕获提示的单元测试能断言（提示词是私有输入、不进事件、不进持久面）；**可观测后果**（口令出现在用户可见输出里）才在场景层可证伪（§12.5） |
| 2026-09-27 第三轮审查后 | **`00-adapter-factory.md` 的 `[reflow]` 键列改为仅 `enabled` / `max_chars`** | 老板阻塞点 4：第二轮删了 `18` 的 `timeout_ms`、**漏了工程契约镜像**——同一事实在两处不一致就是缺陷本身 |
| 2026-09-27 第四轮审查后 | **`bootstrap()` 示范代码必须构造并注入 `ResultReflow`**（`00-adapter-factory.md` §3 新增 2.5 段）；`App.__init__` 签名块补上 `reflow`（**追加置尾 + 默认值**） | 老板阻塞项：**"接口加了参数"与"装配处传了参数"是两件事**。带默认值的注入口最容易被漏——类型检查通过、进程正常启动、单元测试（直接构造 `App(reflow=替身)`）全绿，**缺陷只存在于真实装配路径** |
| 2026-09-27 第四轮审查后 | **"`bootstrap()` 步骤零新增"作废**，改为"**签名零变更，但装配步骤有新增**" | 同一个函数"签名不变"与"内部做了什么不变"是两件事。前版口径会让实现者以为 bootstrap 无需改动，**而这正是生产环境回流永不发生的直接原因**（§11.1 / §13.1 / §13.2 / §16 同步订正） |
| 2026-09-27 第四轮审查后 | **新增 R19：必须走 `bootstrap()`**，断言返回的 `App` 实际持有**启用**的回流组件、且端到端替身模型确实被调用 | 老板阻塞项的验收缺口：**R1–R18 都可以用"直接构造 `App(reflow=替身)`"来满足**，因此**全绿也不能证明生产装配接线了**。R19 的探针（删掉构造与传参 ⇒ 只有 R19 变红）正是为此存在 |
| 2026-09-27 第四轮审查后 | **`[reflow]` 键集闭集与默认值只有一处实现 `normalize_reflow_config()`**（住 `src/main.py` 配置解析区，与 `normalize_cloud_advisory_config` 同处）；工具后端侧判定跨表不变式调用**同一个函数** | 若 bootstrap 与工具后端各写一份默认值/键集，就出现**第二份真源**：改一处忘一处正是本轮缺陷的同型复发 |
| 2026-09-27 第五轮（Codex 在 RED 阶段提出，核实成立） | **`ResultReflow` 构造期冻结工具目录**：`tool_defs=tool_backend.list_tools()`，内部只提取 **name → `result_delivery`**（§1.2.4） | `ExecutionStep`（`src/core/schemas.py:471-482`）**没有 `result_delivery`**，声明在 `ToolDef` 级，`plan`/`results` 都不带目录 ⇒ 判据**无法从实参推出**。**不给 `ExecutionStep` 加字段**：那会变成第三处签名变更，并把注册期事实复制进每一条步骤 |
| 2026-09-27 第五轮 | **`__call__` 增参 `fallback_display`**（本回合数据，调用时传入 `output.display`）；回流层**永不自己合成回落文本** | "无可回流"与"回流失败"两态都要求 `display` **逐字节等于** `output.display`，而该值只有调用点手里有 ⇒ 不传就只能**再造一份确定性显示**，两条路径的输出会分叉 |
| 2026-09-27 第五轮 | **目录在构造期冻结、`fallback_display` 在调用期传入**——**按生命周期分流**，不得互换 | 目录在 bootstrap 后固定（`17`：不热插拔、不自动重启、只收紧），而确定性 display 每回合都不同。互换的后果：组件要每回合重建，或每个调用点重复取目录 |
| 2026-09-27 第五轮 | **冻结目录里查不到的 `tool_name` ⇒ 按 `deterministic`（未覆盖）处理，不抛错** | 该分支**不可达**（冻结源与执行器的 `registered_tools` 同源；执行器只执行目录内工具）。即便触发，回流是**呈现层**——"少一个声明"不该让一个**已成功执行**的回合失败（"工具结果永不因回流失败而丢失"，§1.5） |
| **2026-09-28 实现审查后** | **§4.9 解除 `DocumentParser` / `PARSERS` 描述符表的强制**，只保留三条硬约束（分派期惰性导入 / 换库只改 `document_tools.py` / 解析器差异收敛在段列表这一层）；D8/D15 的替身改述为 **`sys.modules` 注入** | 契约把「可替换性」这个**目标**写成了一种**实现形状**。已交付实现用 `_MODULES`（模块名字符串）+ 分派分支达成了同一目标，而 D8/D15 需要的注入点**本就存在** ⇒ 为测试便利要求一次无行为收益的重构，是把实现形状当成契约（见审查 §六 表 1） |
| **2026-09-28 实现审查后** | **§5.5 澄清**：rc=2 且**零结果** ⇒ `ripgrep_failed` + 降级；rc=2 且**有结果** ⇒ 接受，且 `skipped.unreadable` **必须为 `null`**（ripgrep 路径下一律 `null`，因 `--json` 的 per-file 错误项未被提取、`stderr` 已送 `DEVNULL`） | 原表「非零退出码且零结果」与「退出码 2」两行在"rc=2 且零结果"这一格**互相冲突**；rc=2 时"真的没有"与"文件全读不了"不可区分 ⇒ 接受它会产出一个与真实"没有"无法区分的空结果，与 §5.6 行 7 的诚实性要求冲突 |
| **2026-09-28 实现审查后** | **§5.6 判据⑦ / D9 明确**：控制字符判据**不得导入 `unicodedata`**，用码位区间 `ord(ch) < 32 or 127 <= ord(ch) < 160` 实现；**§9.1 新增 `max_line_chars ≥ 6` 下限**；**§9.2 订正**「`{{` 守卫自动覆盖 `{{DOC_TOOLS}}`」这一不成立的说法 | 前者：源级断言「三个新模块零 `unicodedata`」必须可落地，而"禁止第二份净化实现"的本意不等于禁止字符分类，故**保持断言绝对、改实现手段**。中者：截断标记本身 6 字符且**计入**上限，上限小于标记长度时 §5.7 的等式断言**不可能成立** ⇒ 让该状态不存在。后者：**缺占位符**与**占位符未替换**是两件事，前版把前者误记为已被覆盖 |
| **2026-09-28 实现审查后** | **§11.2 / §13.2 按实情登记**：工厂名 `make_document_tool` / `make_search_tool`（返回 `RegisteredTool`）、忽略集 `_IGNORED_DIRS`、limits 为裸 `dict`（无 `DocumentLimits` / `SearchLimits`）、`ToolDef` 住工具模块内并由 `product_tool_definitions()` 追加（无 `CONFIGURABLE_TOOL_DEFS`）、`App._reflow()` → **`App._run_reflow()`**；**补登** `src/core/subprocess_env.py` 的搬迁与 `mcp_adapter.py` 的 import 改向 | 命名、是否用 dataclass、映射常量叫什么，**都不承载契约价值**（契约在意的是"上限经闭包工厂注入"与"不进 `BUILTIN_TOOLS`"，两者均已满足）⇒ 按实情登记优于改名 churn。**但 N5 的字面量禁令保留**：`builtin_backend.py` 必须用 `*_TOOL_DEF.name`，不得写 `"document.read"` |
| **2026-09-28 实现审查后** | **§14 新增第 24 项**：回流事实头**不含来源标识**（`path` / `root` / `query` / `mode` / `segment_truncated`）⇒ 模型不知道自己在总结哪一份文档 | 照实登记，不改本阶段范围。触发条件写成"出现总结没提到文件名/搜索范围的真实反馈"（§1.4 钉死的事实头字段清单本身不需要改） |
| 2026-09-27 第五轮 | **`App._reflow()` 是关态的唯一实现点**（`None ⇒ ReflowOutcome(fallback_display, {})`）；`enabled=False` 由组件内部短路 | 关态有**两种来源**（未注入 / 显式关闭），必须**行为等价**，且两个调用点仍写成**零分支一行**（§1.2 的代码形状不变） |
| 2026-09-27 第五轮 | **本回合的三个 `_execution_records` 调用点共用同一份 `deliveries`**（新增 **R20**） | `src/main.py:893`（episode 用）是前版契约**漏掉的第三个调用点**：只给事件侧传值会让 episode 记录退化成 `None`，同一事实在两处不一致——正是本轮要修的那类缺陷 |
| 2026-09-27 第五轮 | **"成功"是构造性事实，不是运行时判据**（新增 **R21**；订正 R17 臂③措辞） | `GuardedToolExecutor.execute()` 在**七条失败路径上全部 `raise`**（`src/safety/guarded_executor.py:67-266`），`results` 只含成功步骤；`_execution_records` 的 `outcome="success"` 是**硬编码**（`src/main.py:1825`）⇒ 结果 dict 里**没有** `outcome` 字段，前版"`outcome == "success"`"的判据**实现者会找不到**。同时明确**部分成功不做事后回流** |

### 15.1 待老板决策（编号表）

> 前版末尾写"需老板拍板 3 项"却没有编号条目——**这是文档缺陷，本节补齐**。老板 2026-09-27 已就其中三项给出书面建议，因此表中**照实记录为"已裁决（老板建议，待确认落笔）"**，Codex **可以据此开工**；第 4/5 项为开放项（第 5 项已登记 §14 第 2 项），**不阻塞开工**。

| # | 待决事项 | 本契约的默认方案 | 老板 2026-09-27 意见 | 状态 |
|:---:|------|------|------|------|
| 1 | **`document.read` 是否需要确认** vs **`file.search` 是否免确认** | `document.read` = `sensitive` + `requires_confirmation=True`（对齐 `file.read`/S14）；`file.search` = `normal` + 免确认（§2.3） | **保持**：前者需确认、后者免确认 | **已裁决**（依此定稿，S20/S21 场景按此写） |
| 2 | **三个配置表的默认上限**（`max_extracted_chars` 500000 / `max_returned_chars` 40000 / `max_returned_segments` 200 / `[reflow].max_chars` 4000 等） | 见 §9.1 | **当前默认值可以接受** | **已裁决**（不阻塞开工） |
| 3 | **本阶段是否允许修改 `pyproject.toml`**，把四个解析库加入**正常依赖** | §6：允许，且是"正常依赖"不是 optional extra | **允许** | **已裁决**（Codex 第 7 步开工前提已解除） |
| 4 | **`max_returned_chars = 40000` 是否过大**：默认口径下约九成内容既不进模型也不进显示，随回合结束丢弃（§1.4 据实订正） | 暂留 40000，理由仅"给 `file.search` 多段结果留执行期余量" | 未表态 | **开放**（若要收紧，候选值 ≈ 8000；不收紧不阻塞开工，但**报告不得称其结果被留存**） |
| 5 | **回流预算按字符代理 token**（§1.9 `[reflow].max_chars`） | 暂按字符（本地模型默认上下文 4096 token） | 未表态 | **开放 → 已登记 §14 第 2 项**（触发条件：出现回流输入被模型截断的真实证据） |

**除第 4/5 项外，本契约无待决事项。** 第 1–3 项按老板意见定稿后，Codex 可全量开工。

---

## 16. 契约状态

- **接口签名变更：两处**（**均为追加式、带默认值，既有构造调用零改动**）：
  1. `ToolDef` 新增字段 `result_delivery: str = "deterministic"`；
  2. `ExecutionRecord` 新增字段 `result_delivery: str | None = None`（§1.2）。
  已同步 `00-core-interfaces.md`。
- **新增 Core 类型：一处** —— `ReflowOutcome`（`display: str` + `deliveries: Mapping[int, str]`，§1.2.1）。**文件位置与文档位置分开说**：代码落 `src/core/result_reflow.py`（与它的**唯一生产者**同处，`00-core-interfaces.md` 的既有先例是 `ExecutionRecord` 记在接口文档里而代码落 `src/core/schemas.py`）；文档面同步进 `00-core-interfaces.md` 与 `00-adapter-factory.md`。这是**新类型的引入**而非既有签名变更，但它出现在 `App` 与回流组件之间，**同属 Claude 主导的接口面**。
- **附带的两处"私有 → 公开"提升**（不属于接口签名变更，但主流程依赖）：`ResponseBuilder._sanitize_display_string` → 公开 `sanitize_display_text()`；`_DISPLAY_LIMIT` → 公开 `DISPLAY_LIMIT`（§1.4/§1.5）。
- **主流程变更：三处** —— ①两个 `response.build` 调用点插入共享 `reflow()` 并排到 `_record_tool_events()` 之前，调用形态**零分支**（`outcome = self._reflow(...)` → `return outcome.display`）；②`_execution_records(plan, results, deliveries)` 新增第三个参数（**内部方法，非接口**），**本回合的三个调用点（`src/main.py:885` / `893`（episode）/ `1020`）必须传同一份映射**（R20）；③`App` 新增一个注入口（`reflow`，追加式带默认值）、一个私有状态字段 `_pending_user_request`（§1.2.3）与一个关态薄包装 `_reflow()`（§1.2.4 第 5 条）。**回流的调用实参含 `fallback_display=output.display`**（§1.2.4），失败路径（`except LocalMindError`）**零回流**（R21）。**`bootstrap()` 签名不变，但新增一步内部装配**（`normalize_reflow_config()` + 构造 `ResultReflow` + 传入 `App`）——**只改签名不构造，生产环境不会启用回流**，`model_summary` 工具会退化成"打印一截结构化文本"（§1.1 的缺口原样复现）；前版的"`bootstrap()` 步骤零新增"**作废**（见 `00-adapter-factory.md` §3 的 2.5 段与 §3.1 增补第 2 条）。
- **验收矩阵规模**：非干扰性 **N1–N7**（N7 第三轮新增）+ 回流层 **R1–R21**（R16–R18 第三轮新增，**R19 第四轮新增：走 `bootstrap()` 断言装配真的接线**，**R20–R21 第五轮新增：三个 `_execution_records` 调用点共用同一份 `deliveries` / 执行抛错零回流**）+ D1–D16 + F1–F13 + S20/S21（S20 四步，第②步含 `output_not_contains`）。**每条含探针**。
- **错误契约变更：有**（`TOOL_EXEC_ERROR` +11、`FILE_ERROR` 闭集化 +1、`CONFIG_ERROR` +2）——已同步 `00-error-contract.md`。
- **可观测性变更：一处封闭集扩展** —— 新增持久化键 `result_delivery`（**条件键**，仅声明 `model_summary` 的工具发出；两份白名单同时改）。**不新增事件类型**。
- **配置契约变更：有**（三个新闭集表 + 白名单 + 评估模板占位符 + `_VARIANTS` +2 + `_EXPECT_KEYS` **+2**：`result_delivery_any` 与 `output_not_contains`）。`[reflow]` **键集闭集且不含 `timeout_ms`**（§1.6），镜像处 `00-adapter-factory.md` 同步为仅 `enabled` / `max_chars`。
- **需老板拍板：0 项阻塞**（§15.1：第 1–3 项已按老板意见定稿；第 4/5 项为开放项，不阻塞开工）。
- **实现状态（2026-09-28）：已交付，审查未通过——待修**。Codex 已完成实现（`pytest 828 passed` / `ruff` / `mypy` 通过、默认配置暴露 8 个工具、回流组件已启用，均由 Codex 报告，本轮未复跑）。**实现审查结论见 `specs/reviews/18-p7c-implementation-review.md`：1 项【阻塞】+ 7 项【重要】+ 9 项【次要】**，另有验收矩阵大面积未落地（R1–R21 仅 6 条有可证伪探针、D1–D16 仅 1 条完整、F1–F13 仅 3 条完整）——**按 §12 的规则，没有探针的行不算验收项，故「测试全绿」不等于 P7c 通过**。
- **本次审查同时落地了四处契约侧修订（Claude 侧，见 §13.2 / §4.9 / §5.5 / §5.6 / §9.1 / §9.2 / §11.2 / §14）**：①§4.9 的 `DocumentParser`/`PARSERS` 描述符表**解除强制**（保留三条硬约束，D8/D15 探针改述为 `sys.modules` 替身）；②§5.5 澄清「rc=2 且零结果 ⇒ 降级」与「ripgrep 路径下 `skipped.unreadable` 必须为 `null`」；③§5.6 判据⑦ / D9 明确**不得导入 `unicodedata`**；④§11.2 / §13.2 的**工厂名、`ToolDef` 住处、`CONFIGURABLE_TOOL_DEFS`、`App._run_reflow()`** 按实情登记，并**补登** `src/core/subprocess_env.py` 的搬迁；⑤§9.1 新增 `max_line_chars ≥ 6` 下限；⑥§9.2 订正「`{{` 守卫会自动覆盖 `{{DOC_TOOLS}}`」这一**不成立**的说法；⑦§14 新增第 24 项（事实头不含来源标识）。**这些是"实现暴露的文档不精确"，不是架构不稳**（`CLAUDE.md` 的反馈循环）。
- **修复顺序建议**（详见审查文件 §八）：事件面 `result_delivery`（阻塞）→ R14/R20/R21/R19①③ → 三条【重要】工具缺陷 → 评估侧两处 → 安全与诚实性臂（D2/D3/D8/D15/D16/F9/F11b/F12/F3）→ 其余。
