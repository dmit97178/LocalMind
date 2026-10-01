# P7b · MCP / QwenPaw 工具生态接入契约

> **状态：🔧 实现中**（上一版 `✅ 待实现`——2026-09-25 立项。2026-09-26 代码已由 Codex 实现并通过自报的 780 passed / ruff / mypy / 真实子进程冒烟，随后完成**代码审查**：4 处必改（1 处协议漏检 `id: bool` + 3 处「契约已明文的断言在测试侧不存在」）、4 处应改、4 处可选，另 5 处文档缺陷已由我在本文件当场修正；详见 `specs/reviews/17-p7b-mcp-qwenpaw-tool-ecosystem-review.md`。**2026-09-26 复审**：必改 1–3、应改 5–8、可选 9–12 已落地，且必改 1 的两条回收路径经**反向验证**（删掉终止/回收 ⇒ 断言变红，还原 ⇒ 变绿，摘要值核对）；**必改 4 的代码修复正确但它的回归探针空转**（演示服务的 `bool_id` 故障臂覆写了**每个**响应的编号，断言分辨不出守卫；收窄为「只污染第一个请求」后即有判别力）⇒ **新增必改 5 退回实现侧**。全量 `pytest` 我实跑 794 passed、ruff/mypy 通过。**必改 5 落地并给出反向验证后**方可标 ✔️）
> **2026-09-26 修订**（老板两轮审查，5 处阻塞 + 2 处措辞，**未写实现代码**）：① **命令改由本地代码签发**（§0.3 裁决 6 / §5.2 / E17/E18）——配置不再是「跑什么」的来源，只留 `enabled` 与两个超时；② **子进程环境白名单**（§5.2）——禁止继承 `os.environ`，凭据结构性不可达；③ **新增进程级生命周期**（§2.2/§2.4/§9.2：`ToolBackend.close()` 默认 no-op + `App.shutdown()` + CLI `finally`），「三项零变更」据实改为**两项零变更 + 一项必要变更**；④ **超时即作废协议流**（§5.3）——握手/调用超时都必须终止进程并标记不可用，禁止复用迟到帧；⑤ **帧结构按方法区分**（§5.4）——`initialize`/`tools/list`/`tools/call` 各自的响应形状、`protocolVersion` 协商、`id` 对应规则、content 类型白名单、确定性转换 `Result[dict]`，并新增**显示净化**（§5.7，防 ANSI/终端注入）；兼容性检查同步加强（§5.6）。措辞修正：「引入零新外发面」改为「不新增网络或文件目标面，新增一个受控的本地进程出站面」；「QwenPaw 接入」据实改为**接入点**（未经真实互操作验证，报告不得宣称已接入）。
>
> **2026-09-26 二次修订（老板复审，指出本轮新引入的一处阻塞性自相矛盾 + 两处清理，**未写实现代码**）**：⑥ **删除 E17 的 shell 元字符禁令**——该禁令由**本轮修订**新加入，与 P10 第 ⑥ 臂（用含 `;`/`|` 的字面参数证明未被 shell 解释）**互相否定**（按 E17 那个 provider 在 bootstrap 期就 CONFIG_ERROR，该臂根本跑不起来）；且它**没有安全收益**（`shell=False` + argv 数组 + argv 由代码签发已结构性消灭 shell 注入），却会误伤合法路径（安装目录含 `&`）。E17 改为**只禁 NUL / CR / LF / 空串**（§3 / §5.2）；`00-error-contract.md` 的对应描述同步删除。⑦ **`ProviderSnapshot.failure_reason` 不再就地列举**（原只列四值，已与 §5.3a/§5.4.1 的新增原因脱节）——权威清单统一到 §8.3，并明确它与 `TOOL_EXEC_ERROR.details.reason` **不是同一份清单**（前者不进事件流，且 `tool_reported_error` / `provider_unsupported_content` 发生时 provider **仍健康**，故**不构成** `failure_reason`）。⑧ **子进程 stderr 钉为 `subprocess.DEVNULL`**——原稿「丢弃或诊断缓冲由 Codex 定」留有实现陷阱：实现成 `PIPE` 却不消费会写满管道、子进程阻塞在 `write()`，表现为「调用超时」（§5.2 / §5.4.5 / P10 第 ⑤ 臂）。
> **2026-09-26 三次修订（实现审查后，`specs/reviews/17-p7b-mcp-qwenpaw-tool-ecosystem-review.md`）**：只改**文档缺陷**，不动接口签名与安全口径——⑨ **§6.3 补第四行**：出站边实现里还有一次「草案重校验」（`validate_tool_call` ⇒ `TOOL_PARAM_ERROR`），原表只写了三行，等于「唯一实现点」漏列一处（兑现 15 号契约「一份实现三层调用」）；⑩ **§8.3 新增 `contract_mismatch_clauses`**——§5.6 明文要求「记失败的那一条编号」，而 §8.3 只列了 `contract_mismatch_count`，**两节互相矛盾**，现按 §8.3 为权威补字段，§5.6 指过去；⑪ **§10.2 P3 的探针改为可实施写法**（原写「`--dump-argv` 臂断言 PID 已不存在」，但 `hang` 臂不会有成功调用、拿不到 PID ⇒ 保留 `Popen` 句柄断 `poll() is not None`）；⑫ **§10.2 P11 ⑥ 补平台边界**（`ignore_sigterm` 依赖 POSIX；Windows 上 `terminate()` = `TerminateProcess`，宽限期不可能触发）；⑬ **§10.2 P10 ① 写明穷尽式断言的判据形式**；⑭ **§10.2 M2 补测试替身要求**（演示服务必须发带哨兵的 `description`/`annotations`，否则该臂无法构造）。以上均为文档与验收口径的收口，不涉接口签名、需求或安全边界。
> **2026-09-26 四次修订（复审后，只改**文档缺陷**，不动接口签名与安全口径）**：⑮ **§8.3 + §5.6 改正 `not_reported` 的语义**——我在三次修订里把它写成「服务端未提供 `input_schema`」，**与实现不符**：实现用它表示**服务端未自报该工具**（候选缺失或**重复**，即绑不到本地声明那一条），而「自报了但 `inputSchema` 缺失/形状不合」落在 ① `schema_shape`（缺失按 `{}` 处理，天然落 ①）。同时补登记「**能唯一绑定**」这一前置条件——原稿四条检查没交代绑定失败这一档，等于 §5.6 有第五种失败形态却只在诊断字段里存在。⑯ **§9.2 步骤 9 据实改写**：原写 `enabled=...` 暗示该值派生自 `capability_routing.enabled`，实现**恒为 `enabled=False`**，覆盖检查（E13/E14）改为下一行 `validate_active_capabilities(...)` **无条件**跑在**准入集**上。这不是偏差而是更正确的分工（E13 问「声明出来的工具都得有能力覆盖」，与「这次运行开不开能力层」是两个问题；按运行态取值会让关态下这条静态完整性检查**静默消失**），故改写文档而非改实现，并写明运行态覆盖的真实位置（`CompositeToolBackend` 构造 + `ContextAssembler`）。⑰ 表格单元格内代码跨度里的裸 `|`（`` `|` ``）按 GFM 规则转义为 `` `\|` ``（3 行 4 处，纯渲染修正）。以上均不涉接口签名、需求或安全边界。
> **上游依据**：老板本轮 10 条边界；`project-report.md` §九 路线图 P7b 行；`16-p7-practical-tools-capability-routing.md`（**直接前置**，§11 第 4 项 / 第 22 项）；`00-adapter-factory.md` §2.1 / §3.4；`13-approval-profile-high-impact.md` §2.4 / 第 134 行；`04-p3-safety-hardening.md` §23 / 第 424 行；`07-p6a-observability-cli.md:361`。
> **本契约的性质**：P7b **不新增任何准入路径、不新增任何执行出口、不新增任何提示词段**。它做的是把 P7a 已经立好的三道门（能力路由 / 风险合成 / 唯一副作用出口）**接到一个可扩展的外部来源底座上**，并把「谁能声明权限」这个问题用代码结构回答死。

---

## 0. 裁决摘要

### 0.1 上游已经把话说死的四件事

| 来源 | 原话（摘要） | 对 P7b 的约束 |
|------|-------------|--------------|
| `16 §11` 第 4 项 | 「MCP 市场 / 插件平台 / QwenPaw Skills 接入 \| **不做**（P7a）。它们要求**能力的动态声明**（运行时注册），而本契约的能力目录是**编译期常量**——动态声明需要先解决「谁能声明能力、声明如何被信任」，那是一个独立的安全问题」 | 本契约的**第一议题**就是回答这个问题；回答不了就不该开工 |
| `16 §11` 第 22 项 | 「出站参数标记的泛化 … P7a 只对唯一的出站工具做源码级断言（`weather.current` 的全部参数必须 ∈ `supply_by_echo`），**不引入**通用的「出站工具」标记。触发条件：出现第二个出站工具时，把该断言升级为注册期不变式」 | **P7b 就是那个触发条件**——本契约必须把源码级断言升级为通用注册期不变式（§2.3） |
| `project-report.md` §九 P7b 行 | 交付物为 MCP stdio 工具生态接入底座；前置条件是 P7a 能力路由和首个真实工具已经验证 | 交付物口径与前置条件都在本契约 §10 / §11 里对齐 |
| `00-adapter-factory.md:217` | 「Adapter 实现（P7 的 MCP 等第三方工具后端）**必须**经 `read_approval_profile()` 归一化，不得自行放宽；`requires_confirmation` 仍只由风险驱动」 | 外部工具的风险/批准档不得来自外部自报（§6.4） |

### 0.2 P7b 要关掉的三个缺口

1. **权威缺位**：外部工具的名字、描述、参数 schema、只读声明，都是**别人说的话**。系统目前没有任何「谁有权让它变成真的」的结构。
2. **出站面扩张**：P7a 只有 `weather.current` 一个出站工具，且它的参数义务是用**源码里一句注释式的断言**维持的。第二个出站工具一出现，这句话就守不住了（`16 §11` 第 22 项）。
3. **新入站面**：外部工具的返回值是**新的一类不可信内容**，它可能含凭据、可能超大、可能是畸形结构。既有实现里「工具结果的**值**不进任何持久面」这条性质必须被守住，而不是被顺手拓宽。

### 0.3 本次拍板的五条

**裁决 1（回答「谁签发」）——权限由本地代码签发，外部自报只是候选人。**
一套外部工具要能被用，必须先在**本地代码**里存在一条**准入声明**（`ExternalToolAdmission`）：它给出规范名、所属能力、风险基线、副作用分类、参数契约（含每个参数的来源约束与实例谓词）。外部服务能提供的只有一件事实：**「这个工具此刻存在」**。它不能提供权限、不能提供风险档、不能提供能力归属、不能提供提示词文本。

形式化一句话：**外部自报只能影响 `available`，永远不能影响 `allowed`。**

**裁决 2——外部文本零进提示词。**
外部服务自报的 `description`、`inputSchema` 的 `description`/`enum`/`default`、`annotations`（含 `readOnlyHint`/`destructiveHint`）**既不渲染、也不进字节账、也不参与任何判据**。进提示词的外部工具，其 `name`/`description`/`parameters` **全部是本地撰写**的文本。理由：这是零成本地消灭一整类提示词注入源，而且它同时解决了字节账（外部内容不改变任何预算上界）。

**裁决 3——动态变化只能朝收紧方向自动生效。**
会话内 `available` 只能从「可用」变「不可用」（崩溃、超时、协议破损），**不能**反向自动恢复；`tools/list_changed` 通知**不改变目录**；不热插拔、不自动重启。放宽方向的任何变化都必须经过一次新的启动（= 一个新的、有人按了回车的时刻）。

**裁决 4——v1 只准入「只读 + 本地 stdio」这一类外部工具。**
- 副作用分类必须声明为 `read_only`；任何其它分类 ⇒ **CONFIG_ERROR fail-loud**（不是忽略、不是降级）。
- transport 只有本地子进程（stdio）一种。远端 transport（HTTP/SSE）**不做**——它需要与 P7a §6 同级的独立出站论证（主机白名单、TLS、重定向、凭据、出站审计），那是另一份工作（§11 第 1 项）。
- 首批外部工具的参数类型只允许 `string`，且必须逐个参数同时具备**来源约束**（`supply_by_echo`）与**实例谓词**（`param_instance_checks`）。
- **`provider` 的可执行文件与固定参数也由本地代码签发**（2026-09-26 增补，见裁决 6）。

**裁决 5——外部工具只在能力层开启时存在。**
`[tool_providers]` 非空 且 `[capability_routing].enabled=false` ⇒ **CONFIG_ERROR fail-loud**。这条把老板第 1 条边界（外部工具不得绕过能力选择）变成**结构性事实**而不是纪律要求：关态下外部工具**不可能**进入提示词，因为那个组合起不来。

**裁决 6——命令由代码签发，配置只控制「跑不跑」（2026-09-26 增补，回答审查第 1 项）。**

原稿让配置给出 `command = [...]`，于是出现一个**自相矛盾**：配置能决定「启动哪个程序」，而那个程序在 `bootstrap` 期、**在 `GuardedToolExecutor` 之前**就已经在跑了。一个配置文件因此可以换来一次任意的本地进程启动——「配置只能控制传输，不能改变权限」与「`GuardedToolExecutor` 是 MCP 副作用的唯一出口」**不能同时为真**。

**裁决**：把 `argv` 移进**本地代码**的 `ProviderDeclaration`（§5.2）。配置 `[tool_providers.<id>]` 的键**闭集**收为 `{enabled, handshake_timeout_ms, call_timeout_ms}`（E18），`command` **不再是配置项**，出现即 `CONFIG_ERROR`（静默忽略会让作者误以为配好了）。

**这条收紧了什么、没收紧什么（必须同时说）**：
- **收紧**：「启动哪个程序」从此**必须过一次代码审查**。权限提升的最短路径从「改一次配置」变成「改一行代码 + 一次 diff 评审」——与裁决 1（权限由代码签发）在**同一个方向上**。
- **没有收紧**：argv 由代码签发**不等于**进程沙箱。被启动的进程仍拿到宿主机权限，仍可在启动时写文件、联网、做任何它想做的事——`GuardedToolExecutor` 约束的是**工具调用**，不是**进程自身的副作用**。因此 §0.4 ① 的残余风险登记照旧成立，并**明确写出**：**FR3（工具生态不得绕过安全边界）对「任意第三方 provider」尚未满足**——v1 只对「本地代码里声明过的 provider」成立，其准确性口径是**「受信任的已安装代码」**，不是「被隔离的不可信代码」（§0.4 ① 末段）。

### 0.4 必须照实写明的四件事

**① 「只读」是一个声明，不是系统可验证的事实。**
外部工具是一个**本机进程**。系统无法约束它能读什么、能连什么。所以 v1 的防线不是「我们证明了它只读」，而是四件可查的事叠加：
- 它**拿不到**任何未被本地声明承认的参数（E9–E11）；
- 它拿到的每个值**必须逐字来自用户原文**（P7a 准入级来源校验）；
- 它拿到的每个值必须**通过本地作者写的整值谓词**（拒绝路径形态 / URL 形态 / 控制字符）；
- 它送回来的东西**值不进任何持久面**（§6.5）。

**照实登记为残余风险**：一个被本地声明为 `read_only` 的外部进程仍可做任何它想做的事。缓解手段是**它只能由本地代码声明、启动期一次、且永远拿不到新权限**；彻底缓解需要进程级沙箱，**不在 P7b**（§11 第 4 项）。**不得在任何面向用户的文档里宣称「MCP 工具是安全的」。**

**一句必须写进文档的话（2026-09-26 增补）**：**外部 provider 是「受信任的已安装代码」，不是「被隔离的不可信代码」。** `GuardedToolExecutor` 与全部准入校验约束的是**工具调用**（参数从哪来、值能不能出、风险怎么算、批准档谁定），**不约束进程自身的行为**——被启动的进程在握手前就可以写文件、连网络、起子进程。因此：

- **FR3（工具生态不得绕过安全边界）在 v1 对「任意第三方 provider」尚未满足。** 它当前成立的形态是：**只对本地代码里显式声明过的 provider 成立**，且成立的部分是「工具调用不可能绕过三道门」。
- 这条**不得**被表述为「P7b 已解决插件安全」。正确的表述是「P7b 把**声明权限**这件事收到了代码里，并把**进程权限**这件事照实登记为未解决」。
- 触发条件（§11 第 4 项）：首个带副作用的动态工具立项时，必须与进程级沙箱（容器/命名空间/seccomp）一并论证。

**② 外部工具没有目标级动态风险评估。**
P7a 的 `file.write` 靠 preflight 判断「目标是否存在、是否工作区外」并据此抬升风险。对一个外部进程，这些**判不了**——它的目标是它内部的事。因此：**外部工具的 preflight 恒为基线（默认实现），准入声明里没有 preflight 字段**。代价照实写明：一个被声明为只读的外部工具可以读任何它能读的东西，`preflight` 不会察觉。

**③ 「QwenPaw Skills 接入」在 v1 的实现形态是「接入点」，不是「适配器」。**
`project-report.md` 将 P7b 的交付物定义为 MCP stdio 工具生态接入底座。据此：
- 一个 QwenPaw 技能若通过 MCP 暴露 ⇒ **v1 的 MCP 路径已经覆盖它**，不需要第二套后端；
- 需要一个**原生** `skills_dir` 适配器（即依赖 QwenPaw 运行时）的部分 ⇒ **v1 不做**（§11 第 2 项），触发条件是拿到 QwenPaw 运行时的执行契约（与 `04 §23` 的 ToolGuard L2 同批）。
- 可替换性由 **`ToolProvider` 接口 + 工厂的单一分支**承载，并由验收矩阵里一个**「第三种 kind」的替身 provider**证明（M6）——不是靠「写了两套」证明。

**必须照实区分「接入点」与「已验证的接入」（2026-09-26 增补，回应措辞修正第 2 条）**：本契约交付的是**接入点**（一条标准路径 + 一个可替换的接口 + 一个能跑通的 MCP 服务端）。**没有任何真实 QwenPaw 运行时或第三方 MCP 服务端参与过互操作验证**——v1 的验证对象是**本仓库自带的 `scripts/mcp_demo_server.py`**，它是按 MCP 帧格式写的**最小实现**，不是合规性证明。

因此：**在完成一次真实 QwenPaw / 第三方 MCP 服务端的互操作测试之前，任何报告、周报、状态行都不得出现「QwenPaw Skills 已接入」「MCP 生态已打通」这类表述**（同 `16 §9.4` 的措辞纪律：真实 run 之前不得宣称天气可用）。该互操作测试登记为 §11 第 12 项，触发条件 = 拿到 QwenPaw 运行时的 MCP 端点或一个可安装的真实 MCP 服务端。

**④ 底座 ≠ 大量工具。**
老板明令「目标不是一次接入大量工具」。因此 v1 **不做「零声明自动接入」**：接入一个新外部工具**必然**伴随一次本地代码变更（一行准入声明）。这是**特性**，不是缺陷——它正是裁决 1 的实现方式。当「声明成本」成为真实瓶颈时再论证（§11 第 3 项），且届时要先解决「自动准入 = 把外部自报当权威」的冲突。

---

## 1. 权威归属：谁能声明什么

### 1.1 三类来源 × 九类事实

| # | 事实 | 权威来源 | 外部自报能否影响 | 判错时的形态 |
|:-:|------|:--------:|:---------------:|-------------|
| 1 | 某外部工具**此刻是否存在** | 外部服务（唯一来源） | ✅ 只能影响这一格 | 不可用（诚实失败） |
| 2 | 外部工具的**规范名** | 本地代码（`provider_id`. + `alias` 派生） | ❌ | CONFIG_ERROR |
| 3 | 外部工具**服务哪个能力** | 本地代码（能力声明的 `tools` 元组） | ❌ | CONFIG_ERROR（R1/R3'） |
| 4 | 外部工具的**风险基线** | 本地代码（准入记录显式字段） | ❌ | CONFIG_ERROR |
| 5 | 外部工具的**批准档** | 本地代码（准入记录显式字段 ∪ `read_approval_profile()` 归一化） | ❌ | CONFIG_ERROR（闭集外） |
| 6 | 外部工具的**副作用分类** | 本地代码（准入记录显式字段） | ❌ | CONFIG_ERROR（v1 只允许 `read_only`） |
| 7 | 外部工具的**参数契约**（有哪些参数、类型、来源约束、实例谓词） | 本地代码（**工具作者撰写**） | ❌（自报 schema 只用于 §5.6 兼容性检查） | CONFIG_ERROR |
| 8 | 进提示词的 `description` / `parameters` **文本** | 本地代码（作者撰写） | ❌ | — |
| 9 | provider 的**启动命令**（可执行文件 + 固定参数） | **本地代码**（`ProviderDeclaration.argv`，§5.2 / 裁决 6） | ❌ | CONFIG_ERROR（`tool_provider_command_missing`，静态可判定） |
| 10 | provider 的**运行开关与超时**（`enabled`、两个 timeout） | 本地配置 | ❌ | CONFIG_ERROR（静态可判定）/ 不可用（动态） |

**这条表的读法**：外部自报只在第 1 行有权力。第 2–9 行全部由本地代码签发；第 10 行由本地配置签发，但**配置里没有一个字段能改变第 2–9 行**。配置只能让一个**已被代码承认**的外部工具「跑起来」或「停下来」，以及给它多少时间。

**第 9 行为什么从配置挪进代码（2026-09-26）**：一个能决定「启动哪个程序」的配置文件，等于一个能在 `bootstrap` 期（`GuardedToolExecutor` 之前）换来任意本地进程的能力——那与第 10 行的「配置只控制跑不跑」以及「唯一副作用出口」两条**不能同时为真**。挪进代码之后，「启动哪个程序」必须过一次代码审查。**注意**：这只把**声明**收进了代码，**不构成**进程沙箱（§0.4 ①）。

### 1.2 为什么能力不能来自配置，更不能来自外部

`16 §0.5` 已经用同一条理由拒绝过「把天气关键词放配置」：**配置承载会让运行期可变、报告不可复现**。能力映射比关键词严重得多——它是**权限**：

- 若能力映射进配置，则 `S1`（有本地副作用的工具必须独占能力）与 `R1–R5` 就变成**数据的属性**，而数据可以被一次编辑放宽。P7a 把这些不变式做成**注册期代码常量上的 fail-loud 校验**，正是为了让「放宽权限」这件事**必须过一次代码审查**。
- 若能力映射来自外部自报，则一个 MCP 服务只要声称「我是只读的、我服务于 `files.read`」，它就直接进了可信能力目录——这正是 `16 §11` 第 4 项说的那件「独立的安全问题」。

**因此 P7b 的外部工具走完全相同的路**：外部能力声明与 `BUILTIN_CAPABILITIES` **合并成同一份目录**，跑**同一套** `validate_capabilities()`（单一入口，禁止两条路径各判一次）。合并是刻意的：`16 §1.1` 明文警告过「同一份声明两条路径不同结论」的形态。

### 1.3 「候选人」的形式化

外部自报在系统里的唯一载体是 `ToolCandidate`（§2.1），它的字段名就写着它不可信：

```python
@dataclass(frozen=True)
class ToolCandidate:
    """外部来源自报的工具条目——**候选人，不是权威**。

    这里出现的一切字符串都可能被外部控制：不得渲染、不得进入任何判据、
    不得写入任何持久面。唯一的合法用途有两个：
      ① 与准入记录的 raw_name 做匹配（决定 available）；
      ② 与准入记录的 parameters 做兼容性检查（决定 available）。
    """
    raw_name: str
    input_schema: Mapping[str, object]   # 自报参数 schema：只查兼容性，不渲染、不进字节账
```

`input_schema` 是**唯一**会进入系统判断的自报内容，而它的作用面被限制在「让一个**已经**被承认的工具从可用变不可用」——即**收紧方向**。这与裁决 3 同源。

### 1.4 显式不读的自报字段

MCP 的工具定义里有 `annotations.readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`，以及 `description`。本契约**明文规定**：

- `annotations`（整个对象）：**不读**。既不映射到 `risk_level`、也不映射到 `approval_profile`、也不映射到 `side_effect_class`、也不进诊断。
- `description`（工具级与参数级）：**不读**。
- `inputSchema` 的 `description` / `enum` / `default` / `examples` / `$schema` 等一切非结构键：**不读**。兼容性检查只允许读 `type` / `properties` / `required` 三者（§5.6）。
- **`initialize` 响应里的 `serverInfo` / `instructions` / `capabilities`（2026-09-26 增补）**：**不读**。`instructions` 是服务端写给我们模型的一段自然语言——**这正是最直接的一段提示词注入载体**，必须与 `description` 同等对待；`capabilities` 声明服务端支持哪些协议特性，v1 不支持任何可选特性，读它无意义且会引入「服务端自报影响行为」的路子。三者一律不进提示词、不进字节账、不进事件、不进诊断（诊断只记 `protocol_version` 与 `serverInfo.name` 的**存在与否**，见 §8.3）。
- **`tools/list` 的 `nextCursor`（2026-09-26 增补）**：**不跟随**。v1 不支持分页；若服务端返回非空 cursor，只使用**本页**工具集（外部事实 ⇒ 收紧方向：少工具而非多工具），诊断计数 `pagination_ignored += 1`（§8.3）。

**验收形态**：一个自报 `readOnlyHint: false` 的服务端，其工具**仍按本地声明为只读**准入；一个自报 `readOnlyHint: true` 的工具，若本地声明为 `local_side_effect`，**仍然 CONFIG_ERROR**（因为 v1 不支持）。自报的 hint 在两臂上都不改变结论。

---

## 2. 数据结构与接口

### 2.1 新增 Core 类型（`src/core/schemas.py`）

```python
@dataclass(frozen=True)
class ToolCandidate:
    """外部来源自报的工具条目（候选人，不是权威）。见 §1.3。"""
    raw_name: str
    input_schema: Mapping[str, object] = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class ProviderSnapshot:
    """一次握手的完整结果：外部来源「此刻存在什么」的快照。

    healthy=False 时 candidates 必须为空（不得「一半健康」）。
    failure_reason 只用于诊断，不落事件流（§8.1）。
    """
    provider_id: str
    healthy: bool
    candidates: tuple[ToolCandidate, ...] = ()
    failure_reason: str | None = None      # 诊断用；**闭集与权威清单见 §8.3**
                                           # （2026-09-26 订正：原稿在此只列四个——
                                           #  unreachable/timeout/protocol/oversize——
                                           #  已与 §5.3a/§5.4.1 的新增原因脱节，
                                           #  故本行不再重复列举，避免第二份清单漂移）


@dataclass(frozen=True)
class ExternalToolAdmission:
    """**本地签发的准入声明**：一个外部工具被允许存在的唯一来源（§1.1 第 2–8 行）。

    刻意不包含的字段（源码级断言，见 M0）：
      capability_id / capabilities  —— 能力归属只能写在 ToolCapability.tools 里
      provider_id_of_origin         —— 不能由外部自报提供
      requires_confirmation         —— 确认只能由风险驱动（13 §2.1）
      preflight                    —— 外部工具没有目标级动态评估（§0.4 ②）
      annotations / hints           —— 不读（§1.4）
    """
    provider_id: str                # 必须 ∈ 代码声明的 provider id 集合（E1）
    raw_name: str                   # 与服务端自报名匹配用；非空、无控制字符、≤128
    alias: str                      # 规范名的第二段；字符集受 E4 约束
    description: str                # **本地撰写**，进提示词
    parameters: Mapping[str, object] = field(hash=False)   # **本地撰写**的 JSON Schema 子集，进提示词
    risk_level: str = ""            # 显式必填（E7），闭集 normal/sensitive/dangerous
    side_effect_class: str = ""     # 显式必填（E7），v1 唯一合法值 "read_only"（E8）
    approval_profile: str = "standard"                     # 闭集 standard/high_impact（E15）
    supply_by_echo: tuple[str, ...] = ()                   # 必须覆盖全部参数（E11）
    param_instance_checks: Mapping[str, ParamInstanceCheck] = field(
        default_factory=dict, hash=False)                  # 必须覆盖全部参数（E11）
```

`ToolDef` **不新增字段来承载上述任何权限**——外部工具最终被构造成一个**普通的 `ToolDef`**，唯一的区别是多了一个标记（§2.3）。

**`ProviderDeclaration`（2026-09-26 新增，回答审查第 1 项）**——住在 **`src/tools/provider_declarations.py`**（与 `EXTERNAL_PROVIDERS` 同处，**不进 Core**：它是本地代码的声明形状，Core 不该知道「provider」这个概念）：

```python
@dataclass(frozen=True)
class ProviderDeclaration:
    """一个外部 provider 的**本地代码**声明。裁决 6 的载体。

    config 里**没有一个字段**能改变这里的任何一项（E18 的键闭集）。
    """
    provider_id: str
    argv: tuple[str, ...]        # 可执行文件 + 固定参数；**不是** shell 字符串（§5.2）
    cwd_from_repo_root: bool = True   # True ⇒ 子进程 cwd = 仓库根；False ⇒ 不指定（继承父进程）
```

**权威边界**：`argv` 决定**启动哪个程序**，因此它是**权限**（裁决 6），与第 2–9 行同权。配置只能决定**跑不跑**（`enabled`）。

**`argv` 里的路径不写占位符**：`sys.executable` 与仓库根由**代码在 bootstrap 期计算**（`Path(__file__)` 上溯），配置侧**没有** `{{PYTHON}}` / `{{PROJECT_ROOT}}` 这类占位符——**这是 2026-09-26 对原稿的一处收回**：那两个占位符之所以存在，只是因为原稿把命令放在配置里；约束挪进代码后它们随之消失（§9.3）。

### 2.2 `ToolProvider`——Core 定义、零平台依赖

```python
class ToolProvider(ABC):
    """动态工具来源的抽象：只负责「此刻存在哪些工具」与「执行」两件事。

    刻意**没有**的方法：list_capabilities() / risk 相关 / 渲染相关。
    一个 provider 拿不到「声明能力」的入口，这是裁决 1 的结构化表达。
    """

    provider_id: str

    @abstractmethod
    def handshake(self) -> ProviderSnapshot:
        """建立连接并返回一次快照。**只能在与前一次调用之间被调用一次**（v1 单次握手）。"""

    @abstractmethod
    def execute(self, raw_name: str, params: Mapping[str, object]) -> Result[dict]:
        """执行一个**已准入**的工具。raw_name 是服务端原始名，不是规范名。"""

    @abstractmethod
    def close(self) -> None:
        """关闭连接与子进程。**幂等；不得抛异常**。

        语义（2026-09-26 补钉，回答审查第 3 项）：
          ① 先请求正常终止（关 stdin → terminate → 宽限期）；
          ② 宽限期内未退出 ⇒ **强杀并回收**（wait），不得留孤儿；
          ③ 调用方必须能在**未握手成功**、**已崩溃**、**已超时**的 provider 上安全调用；
          ④ 关闭超时本身不得抛出——记入诊断（§8.3）后强杀。
        """
```

**位置理由**：住 `src/core/interfaces.py`，与 `ToolBackend` / `ModelBackend` 同级。它跨层（`src/tools/` 的聚合后端消费它，`src/adapters/` 实现它），所以必须由 Core 定义，否则 `src/tools/` 会依赖 `src/adapters/`。这与 P7a 把 `ToolCapability` 从工具层搬回 Core 是**同一条依赖方向的理由**。

**`execute` 拿到的是 `raw_name`**：规范名到原始名的映射是本地的事，适配器不该知道我们给工具起了什么名字。

### 2.3 `ToolDef` 新增一个字段：`egress`（兑现 `16 §11` 第 22 项）

```python
@dataclass(frozen=True)
class ToolDef:
    ...
    egress: bool = False
    """出站工具标记：本工具的参数值会离开 Agent 进程（送交外部进程或网络）。

    语义边界（刻意收窄，防扩张）：
      离开**本进程** ⇒ True。子进程、socket 都算。
      在本进程内被用作路径/键/索引 ⇒ False。file.read/file.write/file.list_dir 均为 False。
    """
```

由此产生**两条通用注册期不变式**（对**所有**工具成立，含内置）：

- **E11（来源 + 实例）**：`egress=True` ⇒ `set(parameters["properties"]) ⊆ set(supply_by_echo) ⊆ set(param_instance_checks.keys())`。
- **E12（审计脱敏）**：`egress=True` ⇒ `audit_redact_all_params=True`。

**回填义务**：`weather.current` 必须回填 `egress=True`（它已满足 E11/E12 的全部要求，回填只是把 P7a 的源码级断言换成通用不变式）。**回填后 P7a §9.4 的 C15 必须仍然全绿**（`egress` 属布尔标记，与 `param_instance_checks` 同族——`C15 ⓐ`「声明前后提示词逐字节相同」对它同样适用，因为渲染白名单不含它）。

**渲染白名单**：`egress` **必须**加入 `render_tool_catalog()` 的排除断言集（与 `audit_redact_all_params` / `param_instance_checks` / `supply_by_echo` 同处）。验收：源码级 + 行为级（渲染前后逐字节比较）。

**外部工具的 `egress` 不由作者填写**：准入管道**强制**把外部工具的 `ToolDef.egress` 置为 `True`（因为参数必然送交子进程）。准入记录里**没有** `egress` 字段——少一个能填错的面，且「外部 = 出站」是分类事实而非选项。

### 2.4 `ToolBackend` 接口：**一处必要变更**（`close()`，2026-09-26）

| 方法 | P7b 的改动 |
|------|-----------|
| `list_tools()` | 零变更。聚合后端返回 = 内置 active ∪ (已准入 ∧ 该 provider 健康) 的外部工具 |
| `execute(tool_name, params)` | 零变更。签名与错误语义不变 |
| `preflight(...)` | 零变更。外部工具走基类默认实现（基线风险，无目标级评估） |
| `list_capabilities()` | 零变更。返回**合并后**的完整声明目录（含不可用能力） |
| **`close()`** | **新增**，`src/core/interfaces.py` 上给**默认实现**（no-op），与既有 `list_capabilities()` / `preflight()` 的默认方法同族 |

```python
class ToolBackend(ABC):
    ...
    def close(self) -> None:
        """Release process-level resources. **幂等；不得抛异常**；默认无资源可放。"""

        return None
```

**为什么必须加这一条（回答审查第 3 项）**：原稿给 `ToolProvider` 加了 `close()`，但**没有任何调用方**——`ToolBackend` 没有 `close()`、`App` 不持有 `ToolProvider`、`end_session()` 只管摘要与话题。结果是 provider 进程启动后**没有确定性的关闭路径**，「不得留孤儿」这条要求**无法实现**。契约里出现一个没人调用的生命周期方法，等于把资源泄漏写进了设计。

**三处落点（缺一不可）**：

| 落点 | 形态 |
|------|------|
| `ToolBackend.close()` | 默认 no-op（上表）；`.builtin_only` 后端**零改动**即满足 |
| `CompositeToolBackend.close()` | 关闭**全部** provider（逐个调用 `ToolProvider.close()`）；幂等；任何单个 provider 关闭失败**不中断**其余，失败记入诊断（§8.3）。**关闭后** `list_tools()` 返回空集、`execute()` 一律 `TOOL_NOT_FOUND` |
| `App.shutdown()` | **新增方法**（不是构造签名变更）：委托 `self.executor.tool_backend.close()`；幂等；**在 `finally` 中安全**（不抛异常）。CLI（`src/cli/loop.py`）与评估运行器子进程、诊断脚本都必须在 `finally` 中调用 |

**`shutdown()` 为什么不复用 `end_session()`**：两条不同的生命周期。`end_session()` 是**会话边界**（写摘要、更新话题），一个进程内可以发生多次（CLI 的 `/quit` 之后再进一次、S16 的两段共享实例）；`shutdown()` 是**进程边界**（释放子进程），一个进程内**恰好一次**。把资源释放挂在会话边界上，会让「关掉一个会话就杀掉还在被另一个会话使用的 provider」，也会让「没有会话时启动的 provider」永远没人关。

**这一步推翻了什么（据实记录）**：原稿 §12 第 14 行主张「事件闭集 / `App` 构造签名 / `ToolBackend` 接口**三项零变更**」。现在据实改为**两项零变更 + 一项必要变更**：事件闭集零扩展 ✅、`App` **构造签名**零变更 ✅（新增的是一个方法，不是构造参数）、`ToolBackend` 接口**新增一个带默认实现的方法**（接口变更，按 CLAUDE.md 属 Claude 主导，本节即该裁决）。

**「Core 不依赖具体平台」仍然成立**：外部工具通过**实现** `ToolBackend` 的聚合后端接入；`close()` 是**资源生命周期**方法，不含任何平台语义（它对内置后端是 no-op，对替身 provider 同样适用）。聚合后端持有一个**具体类型**的 `diagnostics()` 供测试与脚本读取——**不进接口**，因为 Core 不该知道「provider」这个概念。

### 2.5 层归属

| 文件 | 层 | 内容 |
|------|:--:|------|
| `src/core/schemas.py` | Core | `ToolCandidate` / `ProviderSnapshot` / `ExternalToolAdmission`；`ToolDef.egress` |
| `src/core/interfaces.py` | Core | `ToolProvider`（ABC，含 `close()`）；`ToolBackend.close()` **默认实现**（§2.4） |
| `src/tools/provider_declarations.py` | tools（**建议名**，Codex 可改） | `EXTERNAL_PROVIDERS`（`ProviderDeclaration` 元组，含 `argv`）、`EXTERNAL_TOOL_ADMISSIONS`、`EXTERNAL_CAPABILITIES`、E1–E18 的校验实现 |
| `src/tools/composite_backend.py` | tools（**建议名**） | `CompositeToolBackend(ToolBackend)`：内置注册表 + N 个 provider；准入过滤；**出站边**（§6.3）；诊断快照 |
| `src/adapters/mcp_adapter.py` | adapters | `MCPStdioToolProvider(ToolProvider)`：stdio 传输、握手、帧解析、超时、大小上限、关闭 |
| `src/adapters/qwenpaw_adapter.py` | adapters | **保持占位**；文件头补一行注释写明延后理由与触发条件（§11 第 2 项） |
| `scripts/mcp_demo_server.py` | scripts | 首批外部工具的宿主：stdlib-only stdio MCP 服务 + `--fault` 故障注入开关 |

**「底座可替换」的判据**：`src/tools/composite_backend.py` 里不得出现 `mcp` / `qwenpaw` / `jsonrpc` / `subprocess` 字样（M6 源码级断言）。

---

## 3. 注册期不变式 E1–E18（fail-loud）

**统一形态**：`LocalMindError(code="CONFIG_ERROR", details={"reason": ...})`，在 `bootstrap` 内、**任何工具被暴露之前**抛出不捕获。判错对象是**本地代码与本地配置**——不是外部事实（外部事实一律走「不可用」，§7.2）。

| # | 不变式 | reason |
|:-:|--------|--------|
| **E1** | 配置里 `[tool_providers.<id>]` 的 `<id>` 必须 ∈ 代码的 `EXTERNAL_PROVIDERS`。配置**不能**引入新 provider 身份 | `tool_provider_unknown` |
| **E2** | 代码声明的 provider 若配置里没有对应表，或该表 `enabled=false` ⇒ 该 provider 的全部工具**不可用**（**不是错误**；与 `weather.provider="none"` 同形） | — |
| **E3** | `[tool_providers]` 非空（存在任一 `enabled=true` 的表）⇒ `[capability_routing].enabled` 必须为 `true` | `tool_providers_require_capability_routing` |
| **E4** | 规范名 = `f"{provider_id}.{alias}"`，必须匹配 `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`。`provider_id` 与 `alias` 各自不得含 `.` | `external_tool_declaration_invalid` |
| **E5** | 规范名在**全体**（内置 ∪ 外部）内唯一；**不得**覆盖任何内置名 | `external_tool_name_conflict` |
| **E6** | `raw_name` 非空、无控制字符、长度 ≤128，且在同一 provider 内唯一 | `external_tool_declaration_invalid` |
| **E7** | `risk_level` 与 `side_effect_class` **必须显式给出**（不得依赖数据类默认值），且 ∈ 各自闭集 | `external_tool_declaration_invalid` |
| **E8** | `side_effect_class` 必须是 `"read_only"` | `external_side_effect_not_supported` |
| **E9** | `parameters` 只允许 `{"type":"object","properties":{...},"required":[...]}`；每个 property 的 `type` 必须是 `"string"` | `external_tool_declaration_invalid` |
| **E10** | `supply_by_echo` 非空且 ⊆ `properties` ⊆ `required`（外部工具的全部参数都必须来自用户原文） | `external_tool_declaration_invalid` |
| **E11** | `egress=True` ⇒ `set(properties) ⊆ set(supply_by_echo) ⊆ set(param_instance_checks)`（**通用**，含内置与天气） | `egress_contract_invalid` |
| **E12** | `egress=True` ⇒ `audit_redact_all_params=True`（**通用**） | `egress_contract_invalid` |
| **E13** | **R3'（对外部工具的强化）**：每个已准入的外部工具必须被**至少一个**能力声明覆盖——**无论该工具此刻是否可用** | `capability_coverage_missing` |
| **E14** | 合并后的能力目录（内置 ∪ 外部）满足 R1/R4/R5 与 S1/S2 的**全部**既有校验（单一入口 `validate_capabilities()`） | 复用 P7a 的 reason |
| **E15** | `approval_profile` ∈ `APPROVAL_PROFILES`（`src/core/risk_vocabulary.py`）。`read_approval_profile()` 归一化**仍然保留**为接口义务（`00-adapter-factory:217`），但本地声明层面的闭集外值**直接 fail-loud**，不依赖运行期兜底 | `external_tool_declaration_invalid` |
| **E16** | `handshake_timeout_ms` / `call_timeout_ms` 必须是有限正整数且 ≤ 60000 | `tool_provider_invalid` |
| **E17** | **`ProviderDeclaration.argv`（代码）**：非空元组、元素均为非空字符串；首项解析为**存在的绝对路径**（含分隔符 ⇒ 按仓库根解析；裸名 ⇒ `shutil.which()`）。**2026-09-26 二次修订（删除 shell 元字符禁令）**：`;` `\|` `&` `>` `<` 等**是合法字符**，不得拒绝——见下方「为什么删除 shell 元字符禁令」。只禁止**无法安全构成进程参数**的字符：**NUL（`\x00`）、CR / LF（`\r` / `\n`）、空字符串**。**每个 `EXTERNAL_PROVIDERS` 成员都必须通过**（无论配置是否启用它——与 E13 同理，堵住「provider 关着时藏在门后的静态错误」） | `tool_provider_command_missing` / `tool_provider_invalid` |
| **E18** | **配置键闭集**：`[tool_providers.<id>]` 的键必须 ⊆ `{enabled, handshake_timeout_ms, call_timeout_ms}`。**未知键一律 fail-loud**（含原稿的 `command`）——静默忽略会让作者误以为「我配的命令生效了」 | `tool_provider_invalid` |

**E13 为什么比 R3 更强**：R3 只校验 `active` 集。若沿用 R3，则「provider 未配置时启动正常、配置后启动失败」——一个**潜伏的配置错误**会藏在关着的门后面。E13 把校验对象改成**准入集**（代码常量），代价为零，堵住了这个潜伏面。

**为什么删除 shell 元字符禁令（2026-09-26 二次修订，老板审查指出本轮自相矛盾）**：本轮修订的初稿在 E17 里写了「argv 内不得出现 `;` `|` `&` `>` `<` 或换行」，同时又要求 **P10 第 ⑥ 臂**用「含 `;`/`|` 的单项参数**不被解释**」来证明没有经过 shell。**两条规则互相否定**：按 E17，那个 provider 在 bootstrap 期就 `CONFIG_ERROR`，P10 第 ⑥ 臂根本跑不起来。更根本的问题是**这条禁令没有安全收益**——`shell=False` + argv 数组传参 + argv 由本地代码签发**三者已经**结构性消灭了 shell 注入（不存在一个 shell 去解释这些字符）；再加一条字符禁令只是**在已关闭的门上再上一把锁**，代价却是误伤合法路径（例如安装目录本身含 `&`，或某个 MCP 服务的合法参数含 `|`）。因此裁决：**只禁止无法安全构成进程参数本身的字符**——NUL（`\x00`，`execve` 层面就传不进去）、CR / LF（换行会破坏帧与路径语义）、空字符串（`argv[0]` 为空无法解析）——**其余一律放行，由「永不经过 shell」保证语义**。P10 第 ⑥ 臂保留，它现在测的正是这条边界：这些字符**作为字面量**到达子进程。

**E9/E10 为什么这么紧**：`string` 是**唯一**能同时受「来源校验（整串逐字来自用户原文）」与「实例谓词（本地作者写的整值判据）」两级约束的类型。一个 `integer` 或 `object` 参数**两头都漏**：既无来源（模型可自由合成），也难写实例语义。v1 用类型限制把这条漏洞结构性地关掉（§11 第 7 项登记了放宽的触发条件）。

---

## 4. 命名空间与冲突

### 4.1 规范名的派生

**规范名由系统派生，不由作者手填**：`规范名 = f"{provider_id}.{alias}"`。作者只填 `provider_id`（必须已登记）与 `alias`（受字符集约束）。

- **为什么派生**：两个名字（一个手填的规范名 + 一个匹配用的原始名）会漂移，而漂移的后果是「准入记录指向 A，运行时匹配到 B」。
- **为什么 `alias` 而不是直接用 `raw_name`**：真实 MCP 服务的工具名可能是 `get-forecast`（含连字符）或 `doThing`（驼峰）。**规范名是本地受控文本**（进提示词、进能力声明、进审计），不能承载任意字符；`raw_name` 只用于匹配，因此只要求「非空、无控制字符、≤128」。
- **为什么 provider_id 不得含 `.`**：否则 `provider_id="a.b"` + `alias="c"` 与 `provider_id="a"` + `alias="b.c"` 会派生出同一个规范名（边界歧义）。E4 用字符集直接消灭这一类。

### 4.2 三类冲突与处置（全部 fail-loud，零静默优先级）

| 冲突 | 检查点 | 处置 | 为什么不是「后者覆盖前者」 |
|------|--------|------|--------------------------|
| **provider id 重复** | TOML 解析期 | 解析失败（TOML 表名重复即语法错误） | 用 `[tool_providers.<id>]` 表形态，让这一类冲突**在语言层就不可能发生** |
| **provider id 未登记** | E1 / `bootstrap` | `CONFIG_ERROR` | 配置不得发明身份 |
| **工具规范名冲突（含覆盖内置）** | E5 / 注册期 | `CONFIG_ERROR` | 「静默覆盖内置」是权限提升的最短路径：把 `file.read` 换成外部实现只需要一次配置编辑 |
| **能力 id 冲突** | E14/R1（合并目录上） | `CONFIG_ERROR`（复用 P7a reason） | 与内置能力同权，无例外 |
| **同一能力内的工具不覆盖** | E13 / R3 | `CONFIG_ERROR` | 见 §3 E13 |

**照实写明的一处不对称**：E5 的检查对象是**准入集**（代码常量），因此**服务端自报的重名不会触发任何错误**——服务端自报里的重名候选在准入匹配时会「一个 `raw_name` 匹配到一条准入记录」，多余的候选直接落入「未准入」计数（§8.3）。这是刻意的：**外部事实不产生 fail-loud**。

### 4.3 运行期增删（老板第 5 条的正式回答）

| 事件 | v1 行为 |
|------|---------|
| 服务端在会话中新增一个工具 | **不生效**。目录在握手期固定；新工具不在 `ToolCandidate` 快照里 ⇒ 既不可用也不可见 |
| 服务端在会话中移除一个工具 | **不生效**（同上）。该工具在快照里仍在 ⇒ 调用时会有一次失败（`provider_protocol_error` 或 `tool_reported_error`），随后按 §5.3 处置 |
| 服务端发 `notifications/tools/list_changed` | **不订阅、不处理**。收到即忽略（不改变目录、不产生事件）。诊断里记一次「收到未处理通知」计数 |
| provider 进程崩溃 | **收紧方向自动生效**：该 provider 标记 `unhealthy`，其全部工具立即转 `available=false`（§5.3） |
| provider 从崩溃中恢复 | **不自动恢复**。需重启会话 |
| 会话中修改配置文件 | **无影响**（配置只在 `bootstrap` 读一次） |

**一句话**：**运行期变化只能朝收紧方向自动生效**（裁决 3）。

---

## 5. provider 生命周期与传输

### 5.1 为什么只有 stdio（远端 transport 的独立论证需求）

远端 MCP（HTTP/SSE）会引入**与 P7a 天气完全同级的新出站面**：主机白名单、TLS、重定向拒绝、凭据、出站审计、响应大小与超时。P7a 为天气**一个**这样的面写了 §6 一整节。把远端 transport 塞进 P7b 会让这一份契约变成两份契约的材料，且首批工具（只读小工具）**不需要**它。

**决策**：v1 只有 stdio。远端 transport 的**接入点**已经存在（`ToolProvider` 的第二个实现 + 工厂一个分支），论证单独做（§11 第 1 项）。

### 5.2 命令与进程

**命令由代码签发**（裁决 6）。配置侧**只剩三个键**：

```toml
# config/mcp.example.toml（新增样例）
[tool_providers.demo]          # 只允许 enabled / handshake_timeout_ms / call_timeout_ms（E18）
enabled = true
handshake_timeout_ms = 5000
call_timeout_ms = 10000
# command = [...]  ← **不是配置项**。出现即 CONFIG_ERROR（tool_provider_invalid）
```

```python
# src/tools/provider_declarations.py —— 命令的唯一来源（E17）
EXTERNAL_PROVIDERS: tuple[ProviderDeclaration, ...] = (
    ProviderDeclaration(
        provider_id="demo",
        argv=(sys.executable, "scripts/mcp_demo_server.py"),   # 代码里，不在配置里
    ),
)
```

| 规则 | 内容 |
|------|------|
| argv 来源 | **本地代码**（`ProviderDeclaration.argv`）。配置**没有** `command` 键（E18）；配置无法引入任何程序 |
| argv 形态 | 字符串元组，长度 ≥1，元素非空；元素内**只禁 NUL / CR / LF**（E17，2026-09-26 二次修订：`;` `\|` `&` 等**是合法字符**，禁令已删）。**禁止 shell 字符串**（无 `shell=True`、无 `sh -c` 拼接）⇒ 消灭一整类注入——**这才是那条禁令原本想挡的东西，而它已经由「argv 数组 + `shell=False`」结构性挡住了**，不需要再靠字符黑名单 |
| 命令解析 | 首项含路径分隔符 ⇒ 按**仓库根**解析为绝对路径并校验 `is_file()`；否则 `shutil.which()`。**两者都失败 ⇒ CONFIG_ERROR**（`tool_provider_command_missing`）。**E17 的校验对象是代码声明的全部 provider**，与配置是否启用无关 |
| 解释器 | 用 `sys.executable`（**当前解释器**），不是 PATH 上的 `python`——避免运行到另一个环境（验收 N 组与 P10） |
| cwd | `ProviderDeclaration.cwd_from_repo_root=True`（默认）⇒ 子进程 cwd = 仓库根，使代码里的相对路径与在仓库根手跑一致 |
| **子进程环境** | **绝不传 `os.environ`**。按**白名单**构造 `env`：只从父进程复制下表命名的键（存在才复制），再覆写我们自设的固定值。**其余一切键——包括全部凭据——结构性不存在**（见下） |
| stdout | **只当协议通道**：严格按 §5.4 解析 |
| stderr | **钉为 `subprocess.DEVNULL`**（2026-09-26 订正，老板审查）。原稿写「丢弃或诊断缓冲由 Codex 定」**留有实现陷阱**：若实现成 `PIPE` 却**没有持续消费**，大量 stderr 会塞满管道缓冲区，子进程在 `write()` 上阻塞 ⇒ **provider 卡死**（且表现为「调用超时」这种与病因错位的症状）。v1 直接丢弃，**绝不进入任何面**（不进提示词/事件/审计/记忆/报告/回复）。需要看 stderr 时用 `--fault` 在**演示服务侧**打印，不靠 Agent 侧缓冲 |
| 生命周期 | `bootstrap` 期启动一次；由 `close()` 终止（§2.4 / §5.3）；**不得留孤儿** |

**子进程环境白名单（2026-09-26 新增，回答审查第 2 项）**：

`subprocess.Popen()` 默认继承整个父进程环境，而 LocalMind 进程里可能有 `DEEPSEEK_API_KEY` / `GLM_API_KEY` 等凭据——**原稿只写「不得注入任何凭据」，默认行为却恰好把凭据全送过去**。因此把规则写成可执行的白名单：

| 键 | 值来源 | 为什么需要 |
|----|--------|-----------|
| `SystemRoot` / `windir` | 复制（Windows） | Windows 下加载 DLL / socket 的前提，缺了子进程可能起不来 |
| `TEMP` / `TMP` | 复制 | 子进程临时目录 |
| `PATHEXT` / `ComSpec` | 复制（Windows） | 命令解析与 shell 互操作的最小集合 |
| `NUMBER_OF_PROCESSORS` / `PROCESSOR_ARCHITECTURE` | 复制（存在才复制） | 部分运行时的启动探测 |
| `PYTHONIOENCODING` | **设为 `"utf-8"`**（自设，不复制） | 帧内容含中文时的编码确定性 |
| `PYTHONUTF8` | **设为 `"1"`**（自设） | 同上，Windows 上的 UTF-8 模式 |
| `PYTHONDONTWRITEBYTECODE` | **设为 `"1"`**（自设） | 不在仓库里生成 `__pycache__` |

**规则的三条硬性表述**：

1. **禁止直接继承**：实现里**不得**出现 `os.environ` 传给 `Popen`（源码级断言，P10）。
2. **`PATH` 不在白名单**：`argv[0]` 在启动前已被解析成绝对路径（E17），子进程不需要 PATH。
3. **v1 没有任何 per-provider 环境注入口**：`ProviderDeclaration` 里**没有** `env` 字段——「不可能泄漏」优于「不泄漏」（同 P7a §6.3 纪律）。将来若要给某个 provider 传凭据，那是一次代码变更 + 一次独立论证，不在 v1。

**验收形态（P10）**：子进程自报其环境（演示服务器提供 `--dump-env` 臂，仅测试用）⇒ 断言「子进程 env 的**键集 ⊆ 白名单**」；并断言一份**测试现场注入的随机名秘密变量**（如 `LOCALMIND_TEST_SECRET_<uuid>`）**不在**子进程中。前者是穷尽式（任何非白名单键都会红），后者是端到端演示。

### 5.3 握手、超时、健康、关闭

| 项 | 规则 |
|----|------|
| 握手时机 | `bootstrap` 内、**构造聚合后端时一次**。不重试、不延迟到首次使用 |
| 握手内容 | `initialize` → `notifications/initialized` → `tools/list`。全程受 `handshake_timeout_ms` 约束（含进程启动） |
| 握手失败 | **bootstrap 不抛异常**（外部事实不 fail-loud，§7.2）。该 provider 标记 `healthy=false`，其全部工具不进 `active` ⇒ 能力不可用 ⇒ 诚实失败 |
| 健康判定 | `healthy` 只在两种情况下为真：握手成功 **且** 会话内未发生 §5.4 的协议层违规 / §5.5 的超限 / **任何一次超时（§5.3a）** / 进程死亡 |
| 单次调用 | 受 `call_timeout_ms` 约束。超时 ⇒ `TOOL_EXEC_ERROR` + `details.reason="provider_timeout"`（**复用** P7a 词汇），**并且按 §5.3a 终止进程 + 标记不可用** |
| 调用期间进程死亡 | ⇒ `provider_unreachable`（**复用**），并**标记该 provider 不可用** |
| 协议层违规 / 超限 | ⇒ 标记该 provider **不可用**（协议已破，后续调用不可信） |
| 不自动重启 | 崩溃后不重启、不重连（裁决 3） |
| 串行 | v1 **单线程串行**：同一时刻最多一个 in-flight 请求。不做 pipeline、不做并发（相关性判断与交错处理都因此变成不可能出错） |
| 关闭 | `close()`：关 stdin → `terminate()` → 宽限期 → 未退出则 `kill()` + `wait()` 回收。幂等；不抛异常（§2.2 ④） |

#### 5.3a 超时即作废协议流（2026-09-26 新增，回答审查第 4 项）

**原稿的漏洞**：超时后**仍把 provider 标记为健康**。但超时意味着**请求已在线路上、响应可能迟到**——一个迟到的响应会留在 stdout 里，被**下一次**请求读到；它带着**上一次**的 `id`，于是下一次调用会因为 id 不匹配而报协议错误。也就是说：一次超时**必然**污染下一次调用，且症状（协议错误）与病因（上一次超时）**在事件面上无法对应**——这是最难查的一类缺陷。

**规则（三条，全部 fail-closed）**：

| # | 规则 | 理由 |
|:-:|------|------|
| ① | **握手超时 ⇒ 终止进程 + 标记不可用**（`provider_timeout` 语义由诊断承载；bootstrap 不抛，§7.2） | 握手中断说明进程行为不可预期；留着它只会让后续帧错位 |
| ② | **调用超时 ⇒ 终止进程 + 标记不可用** | 同上；且**禁止**「继续读直到拿到 id 匹配的帧」这种补救——那等于给一个不听指挥的进程无限时间 |
| ③ | **一旦发生超时，该 provider 的协议流即作废**——不允许在同一进程/流上复用 | 迟到帧无法被可靠地丢弃（无长度前缀、无顺序号），唯一可靠的处置是**换一条流**；而 v1 **不重启**（裁决 3），故该 provider 本次会话就此不可用 |

**与「只收紧」一致**：这条让超时从「一次失败」升级为「一次不可用」，方向是**收紧**，不违反裁决 3。

**代价照实写明**：一个偶发慢响应（例如服务端冷启动）会让该 provider 在**整个会话**内不可用，代价高于「这一次调用失败」。这是刻意的取舍：本契约宁可让一次抖动变成一次**可解释的诚实失败**，也不接受「一次抖动污染后续若干次调用」的**不可解释错误**。

**验收（P4）**：超时后 ⇒ `provider_healthy=false`；第二次调用**零执行、零 `tool_execution`**（走「能力不可用」而非读旧帧）；诊断记 `timeout_count` 与 `failure_reason="timeout"`。

### 5.4 严格帧解析（畸形响应）

协议：**newline-delimited JSON-RPC 2.0**，一行一帧。

#### 5.4.1 版本协商

| 项 | 规则 |
|----|------|
| 客户端请求版本 | 代码常量 `_SUPPORTED_PROTOCOL_VERSIONS`（`src/adapters/mcp_adapter.py`），v1 = `("2024-11-05",)`。**闭集在代码里**——加一个版本 = 一次代码变更 + 审查 |
| 发送 | `initialize` 的 `params.protocolVersion` = 上表首项 |
| 响应校验 | `result.protocolVersion` 必须 ∈ 闭集。**不在闭集 ⇒ 该 provider 不可用**（外部事实 ⇒ 不 fail-loud，§7.2），诊断记 `failure_reason="protocol_version_unsupported"` + 服务端版本号（**只记版本串，不记其余自报文本**） |
| 缺字段 | 同上（视为不可用） |

#### 5.4.2 按方法区分的响应形状（**原稿的第一处硬错误**）

原稿把「`result.content` 缺失」**一律**判为协议违规——那是错的：`content` 只属于 `tools/call`。`initialize` 的结果是 `protocolVersion`/`capabilities`/`serverInfo`，`tools/list` 的结果是 `tools`。按原稿的规则，**正常握手会在 `initialize` 那一步就红**。因此逐方法钉死：

| 方法 | 请求 `params` | 响应 `result` 的必需形状 | 失败处置 |
|------|---------------|--------------------------|---------|
| `initialize` | `{protocolVersion, capabilities:{}, clientInfo:{name,version}}` | 对象，含 `protocolVersion`（∈ 闭集，§5.4.1）。`capabilities` / `serverInfo` / `instructions` **存在即忽略**（§1.4） | 不符 ⇒ `provider_protocol_error` + 不可用 |
| `notifications/initialized` | `{}` | **无响应**（通知） | 服务端为它回帧 ⇒ 该帧按 §5.4.3 的 `id` 规则判定（无 `id` ⇒ 当通知处理） |
| `tools/list` | `{}` | 对象，含 `tools`：**数组**（可空）。每个元素必须是对象且 `name` 为非空字符串；形状不合的元素**跳过并计数**（`malformed_tool_entries += 1`，外部事实不 fail-loud）。`nextCursor` 非空 ⇒ 只取本页 + 计数（§1.4） | `tools` 缺失或不是数组 ⇒ `provider_protocol_error` + 不可用 |
| `tools/call` | `{name: <raw_name>, arguments: {...}}` | 对象，含 `content`：**数组**（见 §5.4.4）。`isError` 若存在必须是 bool | 不符 ⇒ `provider_protocol_error` + 不可用（`isError` 语义见 §5.4.4） |

#### 5.4.3 帧级判定（`id` 对应规则）

| 输入 | 判定 | 处置 |
|------|------|------|
| 非 JSON 的一行 | 协议层违规 | `provider_protocol_error` + **provider 标记不可用** |
| JSON 但顶层不是对象 | 协议层违规 | 同上 |
| **无 `id`** 的合法 JSON 对象 | **通知**（外部服务可合法地主动发通知） | **忽略**，`unhandled_notifications += 1`（§8.3），**继续读**（不判违规）。同一在途请求期间累计 > 64 条 ⇒ 协议违规（防流式淹没），标记不可用 |
| **有 `id`** 但 ≠ 在途请求 id（含「有不匹配的迟到帧」） | 协议层违规 | 同上（**这条正是 §5.3a 要防的形态**：超时后复用流会命中它） |
| `id` 类型非整数 | 协议层违规 | 同上（v1 的请求 id 恒为自增整数） |
| `result` 与 `error` **同时**存在，或**同时都缺** | 协议层违规 | 同上 |
| `error` 存在（`result` 缺失） | 服务端协议层错误 | `provider_protocol_error` + 不可用（MCP 的 `error` 是协议层错误，不是工具错误） |

#### 5.4.4 `tools/call` 的 content 类型白名单与确定性转换

| 情况 | 判定 | 处置 |
|------|------|------|
| `isError == true` | **工具层**失败 | `TOOL_EXEC_ERROR` + `reason="tool_reported_error"`；**provider 保持可用**；`content` 里的文本**不渲染、不落任何面**（错误详情只记 `content_length` 与件数） |
| `content` 为空数组且 `isError != true` | 协议层违规 | `provider_protocol_error` + 不可用（无内容又非错误 ⇒ 无法确定性转成 `Result`） |
| 存在 `type != "text"` 的条目（`image` / `resource` / `audio` / 任意值） | **不支持的内容类型**（不是协议破，是我们的限制） | `TOOL_EXEC_ERROR` + `reason="provider_unsupported_content"`；**provider 保持可用**；零渲染 |
| 某条 `type == "text"` 但 `text` 不是字符串 | 协议层违规 | `provider_protocol_error` + 不可用 |
| 全部为 `text` 且至少一条 | 正常 | `text = "\n".join(items)`（**按序拼接，确定性**）⇒ `Result.ok({"text": text})` |

**为什么「不支持的内容类型」不判协议违规**：服务端返回 `image` 是 MCP 允许的**合法**行为，我们只是 v1 不支持渲染它。把它判成协议破会**错误地关闭一个健康 provider**，并让症状（provider 不可用）与病因（我们不会渲染图片）对不上。这条与 `tool_reported_error` 同族：**执行失败≠链路破损**。

**为什么拼接规则要写死**：它决定 `Result[dict]` 的**内容**，而内容进 `display`（§5.7）与云端出站判定的输入面。给实现留「stringify 还是 join、用不用分隔符」的自由，会让同一份服务端响应对应到不同的本地结果——那是不可复现。

#### 5.4.5 一切情况下的 stderr

**钉为 `subprocess.DEVNULL`**（§5.2），**不进任何面**。**不得**实现成 `PIPE` 而不消费：不消费的管道会被 stderr 写满，子进程阻塞在 `write()` 上，表现为「调用超时」——症状与病因完全错位（P10 第 ⑤ 臂仍要求 `--fault` 往 stderr 乱写而六面不受影响，`DEVNULL` 与「持续抽干的 PIPE」都能过，但只有前者不会卡死）。

**为什么「非 JSON 行 ⇒ 标记不可用」这么硬**：stdout 是协议通道；污染它就说明我们无法相信这条流上的任何后续内容。fail-closed 比「这一帧跳过、下一帧再说」安全得多。**照实写明代价**：一个打印 banner 到 stdout 的服务端会被判定为协议违规——这是正确的行为，且诊断快照会记下原因（§8.3）。

### 5.5 大小上限（定值，禁截断）

| 项 | 定值 | 超限处置 |
|----|:----:|---------|
| 单参数值 | 8192 码点 | `TOOL_EXEC_ERROR` + `reason="param_too_large"`，**零外发** |
| 请求帧 | 32768 字节 | 同上 |
| 单条响应帧 | 65536 字节 | `provider_response_too_large`（**复用** P7a 定值），**禁截断**，标记 provider 不可用 |

**为什么禁截断**：截断的 JSON 无法解析，截断的文本会静默丢信息。失败是诚实且可恢复的；截断是静默错误。这与 P7a §6.2 对天气响应的处置同法。

### 5.6 兼容性检查（外部事实 ⇒ 只影响 available）

握手期对每个**已准入**的工具做一次检查。**四条同时成立才算通过**（2026-09-26 加强，回答审查第 5 项末段——原稿只比参数键名，漏掉了「服务端要的我们给不了」与「我们要的服务端不认」两个方向）：

| # | 检查 | 方向 |
|:-:|------|------|
| ① | 自报 `input_schema` 是对象，且其 **`type == "object"`** | 形状前提（不是 object 就别谈 properties） |
| ② | **本地** `parameters["required"]` 的**每个**键 ∈ 自报 `properties` 的键集 | 我们要的，服务端得认 |
| ③ | 对 ② 中的每个键，自报 `properties[<key>]["type"] == "string"` | **类型也得对**——只查键名会让「本地声明 string、服务端要 integer」通过检查，然后在执行期收到一个格式错误的结果 |
| ④ | 自报 `required`（若存在，必须是数组）**⊆ 本地** `parameters` 的键集 | 服务端要的，我们得给——否则每次调用都会因缺参失败，属**已知必败**的接入 |

- 四条全过 ⇒ 该工具进入 `active`（前提：provider healthy）。
- 任一条不过（含 `input_schema` 缺失或形状不对——缺失按 `{}` 处理，同样落在 ①）⇒ **该工具不可用**（**不是** CONFIG_ERROR），诊断计数 `contract_mismatch_count += 1`，并记**失败的那一条编号**（②③④ 的语义差异决定是谁的问题：② 是我们声明错了，④ 是服务端版本不匹配）——**编号落在 §8.3 的 `contract_mismatch_clauses`**（2026-09-26 补：原 §8.3 字段表没列它，两节矛盾）。
- **检查的前置是「能唯一绑定到本地声明的那一条」**（2026-09-26 审查后补：原稿只写了四条，没有交代绑定失败这一档）：服务端**没自报**该工具（候选 0 条），或**重复自报**（候选 ≥2 条，绑不准），都进不了四条检查 ⇒ 该工具不可用、`contract_mismatch_count += 1`，**编号记 `not_reported`**（§8.3）。这一档与 ① 的区别是「对端根本没提这个工具」vs「提了但不认我们的契约」。
- **只读 `type` / `properties` / `required` 三者**（§1.4）；不读 `description`/`enum`/`default`/`additionalProperties`。

**为什么这四条值得做**：它把三类真实漂移——「本地声明说参数可调用但服务端不认识它」「键名对但类型不对」「服务端多要一个我们没声明的参数」——从一次**执行期失败**提前成一次**路由期的诚实失败**。而它**不会放宽任何权限**：四条都只能让工具从可用变不可用。

**照实写明一处代价**：③ 会把「服务端把参数声明为 `integer` 而本地声明为 `string`（两边其实能对上：整数字符串）」判为不可用。这是**刻意**的严格——v1 只接受字面同型；宽松的隐式转换会让「值是逐字来自用户原文」这条链条多一个变形环节（§1.1 第 7 行）。触发条件放宽登记在 §11 第 7 项。

### 5.7 显示净化（终端注入，2026-09-26 新增）

**位置**：`ResponseBuilder.build()`（`src/core/response_builder.py`）——**唯一**把原始值拼进 `display` 的地方（§6.5 已核实）。**实现点唯一**，不得在适配器里另写一份。

| 规则 | 内容 |
|------|------|
| 控制字符剥离 | 递归处理结果里的**字符串叶子**：删除 Unicode `Cc` / `Cf` 类字符（含 `ESC` `\x1b`、`\r`、C0/C1 其余成员），**保留 `\n` 与 `\t`** |
| 显示上限 | 单次工具结果的显示文本 ≤ **4096 码点**；超出则显示前 4096 码点 + **显式标记** `…（已截断显示，原文 N 码点）` |
| 作用域 | **所有**工具结果（不止外部工具）。既有工具的输出同样可能含控制字符（例如读到含 ANSI 的文本文件） |
| 不变量 | `narrative_reply` / episode / 事件 / 审计 / 报告**不受影响**——它们本来就不含值（§6.5）。本节的净化**只作用于 `display`** |

**为什么必须做**：`ESC` 序列能把终端变成攻击面——CSI 可清屏/移动光标伪造输出，OSC 52 可**写系统剪贴板**，OSC 8 可伪造超链接。P7b 引入了**第一类刻意不可信的外部文本**（一个任意进程的 stdout 内容），把这一层补上正当其时。

**为什么「显式标记」而不是静默截断**：静默截断会让用户以为那就是全部内容（同 §5.5 禁截断的理由）。标记让「显示被截断」这件事**可见**，而 §5.5 的帧级上限保证**真实结果**本身没被丢。

**回归影响（已核）**：唯一断言 `display` 内容的测试是 `tests/test_p0a_components.py:102-103`（断言 `"system.echo"` 与 `"hello"` 在其中），纯 ASCII、远低于上限 ⇒ **不变红**。既有 19 个场景**不**断言 `display` 原文（`display` 不落盘，`15 §8.2` 已定）⇒ 零回归。

---

## 6. 执行边界

### 6.1 唯一准入路径：两阶段能力路由（P7a 原样）

**P7b 对 P7a 的编排层零改动**。逐项确认：

| P7a 机制 | P7b 是否改动 |
|----------|:-----------:|
| 阶段一只渲染能力摘要（`capability_id` + `summary`） | 否 |
| 阶段二只渲染所选能力的工具的完整声明 | 否（渲染的是**本地撰写**的 `description`/`parameters`） |
| `capability_relevance()` 集合隶属权威 | 否（外部工具的能力归属写在 `ToolCapability.tools` 里，与内置同构） |
| `capability_resolution` 五值闭集 | 否（外部工具的不可用落既有的 `"unavailable"`） |
| 准入级来源校验（`supply_by_echo` 整串逐字） | 否（对外部工具自动生效） |
| 准入级实例校验（`param_instance_checks`） | 否（对外部工具自动生效） |
| `PendingToolInput` 续接（缺参 ⇒ `ASK_USER` 后补参） | 否（对外部工具自动生效） |
| `not_evaluated` 来源 ③（能力不可用早退） | 否 |
| 诚实失败文案与零云端 | 否（**同一常量**覆盖「provider 未配置」与「provider 离线」） |
| 提示词预算（工具 32/8192、能力 8/2048） | 否（上界不变；**外部内容不进字节账**） |

**「外部工具只在能力层存在」的机制**：E3。关态（`capability_routing.enabled=false`）+ 任何启用中的 provider = **起不来**。因此「绕过能力选择去调用外部工具」在 v1 里不是一个被禁止的行为，而是一个**不存在的状态**。

### 6.2 唯一执行出口：`GuardedToolExecutor`

外部工具的**副作用出口仍然只有一个**：`GuardedToolExecutor.execute()` 里那一行 `tool_result = self.tool_backend.execute(...)`。聚合后端**只实现** `ToolBackend.execute`，**不持有** `SafetyPolicy`、不做任何门禁判断、不直接返回给调用方。

**源码级断言**：`CompositeToolBackend.execute()` 与 `ToolProvider.execute()` 的调用点**唯一**在 `GuardedToolExecutor` 的调用链上；`App` 的任何分支都不得直接调用 provider。

### 6.3 出站边（新的、但唯一的实现点）

「出站边」= **参数值交给 `provider.execute()` 之前的最后一道**。它是 P7a「执行级（形态 + 秘密）」对外部工具的对应物，落点唯一：`CompositeToolBackend.execute()`。

| 检查 | 内容 | 拒绝语义 |
|------|------|---------|
| 秘密检测 | **复用**既有真源 `contains_sensitive_value` / `contains_bare_secret`（`src/safety/guarded_executor.py`）。**禁止在 P7b 新写任何凭据正则** | `TOOL_EXEC_ERROR` + `reason="param_secret_rejected"`，**零外发** |
| 大小 | §5.5 的定值 | `param_too_large`，零外发 |
| 名前缀归零 | 未准入的 `tool_name` ⇒ 直接 `TOOL_NOT_FOUND`（防御性，正常路径不可达） | `TOOL_NOT_FOUND` |
| 草案重校验 | **同一份** `validate_tool_call` 的一次调用点（`15` 「参数校验一份实现三层调用」的兑现）。与解析层**同一实现** ⇒ 幂等，不放宽也不新增判据 | `TOOL_PARAM_ERROR` + `details.reason` = 解析层判据（`param_missing` / `param_not_from_input` / …） |

**为什么出站边要重跑一次草案校验**：能力层的准入级校验住在**解析层**（`supply_by_echo` 整串逐字 + 实例谓词），而外部工具没有「我们写的 handler」可以兜底（§6.3 下一段同理）。这里再调用**同一份**实现，是为了让「值必须逐字来自用户原文」这条链条在**真正的出站点**上也有一个结构性检查——它不引入第二套判据，因此**不可能**放宽任何既有约束。

**为什么出站边必须存在（P7a 的复跑不够）**：P7a 的三级校验长在**能力层**（`supply_by_echo` 与实例谓词住在解析层），而 P7a 的**执行级**秘密检测住在**天气自己的 handler** 里。外部工具没有「我们写的 handler」，所以执行级秘密检测需要一个**共享的**落点——这就是出站边。它是**同一份检测器**的一次新调用点，不是一份新实现。

### 6.4 风险 / 批准档 / 副作用分类的唯一来源

| 项 | 来源 | 外部能否影响 |
|----|------|:-----------:|
| `risk_level` | 准入声明显式字段（E7） | ❌ |
| `approval_profile` | 准入声明显式字段（E15）+ `read_approval_profile()` 归一化兜底 | ❌ |
| `side_effect_class` | 准入声明显式字段，v1 恒 `read_only`（E8） | ❌ |
| `effective_risk` | 既有**只升不降**合成（`max(step, tool_def, dynamic)`），零改动 | ❌ |
| `requires_confirmation` | **只由风险驱动**（`13 §2.1`）；准入记录里没有这个字段 | ❌ |

**「只升不降」对外部工具照常成立的证据**：外部工具的风险路径上没有第二个输入（没有 preflight 目标的 `effective_risk` 抬升、没有 `dynamic` 覆盖），所以合成结果**恒等于**准入声明的 `risk_level`。这是一条**比内置工具更弱**的风险形态——照实写明：**外部工具无法通过任何外部输入把风险抬高**（它只能被本地声明为 `sensitive`/`dangerous`，届时走既有的确认/扣留路径）。

**`high_impact` 的形态**：若作者把某个外部工具声明为 `high_impact`，它会被既有的 P6 执行态**无条件关闭**（`SAFETY_IMPACT_CLOSED`）。v1 不预期使用它，但路径是通的、无需新代码。

### 6.5 结果入站：值不进持久面（**既有性质，P7b 的义务是守住它**）

现状（已核实）：

| 面 | 承载内容 | 是否含工具结果的**值** |
|----|---------|:---:|
| `display`（终端当回合） | `ResponseBuilder.build()` 逐字拼接 `key: value` | **是**（唯一位置） |
| 回复 `narrative_reply` | 「执行结果 N 条，已以结构化记录留存。」 | 否 |
| 记忆 episode | `_record_turn()` 用 `narrative_reply` + `sanitized_summary`；`_execution_summary()` 的注释写着 *without retaining any returned value*，只留**字段名** | 否 |
| 事件 JSONL | `_record_tool_events()` 只发 `tool_name/risk_level/verdict/outcome/error_code` | 否 |
| 报告 | `_active_report["tool_results"]` 同上结构键 | 否 |
| 审计 | `AuditEvent.params_redacted`（参数，不是结果） | 否 |

**P7b 的规定**：

1. **不得新增任何「工具结果值入持久面」的路径。** 具体地：外部工具的结果**不得**被塞进事件 `detail`、不得进报告、不得进审计、不得进 episode。
2. **`display` 里的值不得进入云端 payload。** P5/`05` 的出站边界已有真源；P7b 只加断言（复用 P7a 的既有出站检查，零新实现）。
3. **验收形态是回归守卫**：X7（行号见 §10.2 X 组）断言「外部工具的结果值在事件 JSONL / 报告 / 审计 / 记忆中**不可检索**」。这与 `05 §10.11 C7–C11`、`06 §6.4 E5` 的验收形态同族，但**机制不同**：那两处靠**消毒**，这里靠**值根本不进来**——消毒是兜底，这里是第一道。

**照实写明**：`display` 是唯一出现的值的地方，它是**终端当回合输出、不落任何盘**。若未来要把 `display` 落盘（例如会话导出），这条性质会被打破，届时需要重新论证。

---

## 7. 失败语义

### 7.1 注册期（本地作者错误 ⇒ fail-loud，`CONFIG_ERROR`）

| reason | 触发 | 归属 |
|--------|------|------|
| `tool_providers_require_capability_routing` | E3 | 配置 |
| `tool_provider_unknown` | E1 | 配置 |
| `tool_provider_invalid` | E16 / **E18（配置键闭集：未知键，含原 `command`）** / `argv` 元素形态非法 | 配置（E16/E18）/ 代码（argv 形态） |
| `tool_provider_command_missing` | E17 / §5.2 命令解析失败（**argv 来自代码**） | **代码**（2026-09-26 改：原为配置） |
| `external_tool_declaration_invalid` | E4/E6/E7/E9/E10/E15 | 代码 |
| `external_tool_name_conflict` | E5 | 代码 |
| `external_side_effect_not_supported` | E8 | 代码 |
| `egress_contract_invalid` | E11/E12 | 代码 |
| `capability_coverage_missing`、`capability_declaration_invalid` | E13/E14（**复用** P7a reason） | 代码 |

### 7.2 握手期（外部事实 ⇒ **不 fail-loud**）

**没有错误码，只有「不可用」**：

- `bootstrap` **不抛异常**；该 provider 全部工具不进 `active`；
- 相关能力 `available=false` ⇒ 走 P7a 的 `capability_resolution="unavailable"`、零执行、零云端、诚实失败文案（**复用同一常量**）；
- 原因记入**诊断快照**（§8.3），**不落事件流**（§8.1）。

**为什么外部事实不 fail-loud**：本地优先、离线优先。一个外部进程起不来**不应该**让本地 Agent 起不来——而且它可修的是外部环境，不是配置。这条与 P7a「天气失败不是降级、也不新增 `degradation` 组件」是同一纪律的直接延续。

**静态 vs 动态的分界线**（§5.2 与本节的分工）：**静态可判定**（命令不存在、超时值非法、id 未登记）⇒ CONFIG_ERROR；**动态**（进程启动失败、握手超时、崩溃、协议破）⇒ 不可用。

### 7.3 执行期（`TOOL_EXEC_ERROR` 的 `details.reason`）

P7a 的八值**原样保留**。P7b 复用其中四个、新增五个：

| reason | 来源 | 语义 |
|--------|------|------|
| `provider_timeout` | **复用** P7a | 握手/调用超时 |
| `provider_unreachable` | **复用** P7a | 进程起不来 / 已死 / 写管道失败 |
| `provider_response_too_large` | **复用** P7a | 单条响应帧 > 64 KiB |
| `provider_parse_error` | **复用** P7a | JSON 不合法（P7a 语义保持） |
| **`provider_protocol_error`** | 新增 | JSON 合法但协议不合法（§5.4 前五行）⇒ **并标记 provider 不可用** |
| **`tool_reported_error`** | 新增 | 服务端 `isError: true`（工具层失败，provider 仍可用） |
| **`param_secret_rejected`** | 新增 | 出站参数命中共享秘密检测，零外发 |
| **`param_too_large`** | 新增 | 单参数 > 8192 码点 或 请求帧 > 32 KiB，零外发 |
| **`provider_unsupported_content`** | 新增（2026-09-26） | 服务端返回了合法但我们不支持的 content 类型（非 `text`）；**provider 保持可用**（§5.4.4） |

**闭集**：这十三个值构成 `TOOL_EXEC_ERROR.details.reason` 的**完整**闭集；未在表中的值不得出现（闭集本身是 P7a §5.4 立的规，P7b 只做一次有记录的扩张——2026-09-26 由十二值扩到十三值）。

**「执行级拒绝用 `TOOL_EXEC_ERROR` 而不是 `SafetyDenied`」的理由**：与 P7a 的 `location_rejected` 同形——既有消费方（`_record_tool_events`、报告、场景断言）无需任何改动。

### 7.4 诚实失败与零云端（复用，零新增）

外部工具不可用 / 执行失败时：

- 零 `tool_execution` 事件（若从未路由）；
- `intent_final.capability_resolution` 落既有值；
- `reply_provenance="unfulfilled"`（既有三值，无新增）；
- **不新增「能力不可用」文案**（同一常量覆盖 provider 未配置与 provider 离线——对用户是同一件事：现在做不了）；
- 不触发 `evaluate_cloud_admission`（既有早退，`not_evaluated` 来源 ③）。

---

## 8. 可观测性与审计

### 8.1 事件闭集：**零扩展**（一条硬主张）

| 项 | P7b 改动 |
|----|:-------:|
| `_PERSISTED_KEYS`（`src/observability/sinks.py`） | **不改** |
| `_EVENT_FIELDS`（`src/main.py:1659-1707`，第二份独立副本） | **不改** |
| `degradation` 的组件集合 | **不新增**（provider 离线是「能力不可用」，不是降级路径——与 P7a 对天气失败同法） |
| 场景 `expect` 键集（`_EXPECT_KEYS`） | **不新增** |

**为什么不需要新键**：

- 「某能力此刻不可用」→ 既有 `intent_final.capability_resolution="unavailable"` + `capability_id`；
- 「某能力不可用是因为 provider 离线」→ 见 §8.2 的**登记的不对称**；
- 「外部工具执行成功/失败」→ 既有 `tool_execution`（`error_code="TOOL_EXEC_ERROR"`，与天气同形）；
- 「哪些工具是外部的」→ **可从工具名推导**（规范名带 `provider_id.` 前缀），报告按前缀统计即可。

**验收**：源码级（两份键表逐字符相等）+ 逐字段相等（关态与开态事件流）。

### 8.2 照实登记的一处不对称

报告的 `available=false` **不区分**「provider 未启用」与「provider 已启用但离线」——事件面上两者完全同形（这正是 §8.1 能做到零扩展的原因）。区分它们的唯一载体是**诊断快照**（非事件面，§8.3）。

**触发条件**（届时应重新论证是否落盘）：需要在一批 run 之间比较 provider 可用性时。

### 8.3 诊断快照（**不进事件流**）

`CompositeToolBackend.diagnostics()` 返回一个**具体类型**的结构（不进 `ToolBackend` 接口，§2.4）：

| 字段 | 内容 |
|------|------|
| `enabled_providers` | 配置里 `enabled=true` 的 provider id 元组（有序） |
| `provider_health` | 每个 provider 的 `healthy` 与 `failure_reason` |
| `admitted_count` / `served_count` | 本地准入数 / 服务端自报数 |
| `unadmitted_count` | **服务端自报但未被本地准入**的候选数（安全信号：本地声明落后于服务端，或服务端变了） |
| `contract_mismatch_count` | 通过准入但兼容性检查失败的数（§5.6） |
| `contract_mismatch_clauses` | **2026-09-26 新增**（回答实现审查：§5.6 要求「记失败的那一条编号」，原字段表没有它）：按 §5.6 判据分档的计数映射，键为闭集 `{schema_shape, local_required_missing, local_required_type, server_required_undeclared, not_reported}`（依次对应 §5.6 的 ① ② ③ ④，**`not_reported` = 服务端未自报该工具**——候选**缺失**或**重复**，即无法唯一绑定到本地声明的那一条；**不是**「未提供 `input_schema`」：自报了但 `inputSchema` 形状不合落在 ① `schema_shape`），未出现的键记 0。**分档的用途**（与 §5.6 的语义说明同一口径）：`local_required_*` 亮 ⇒ 多半**我们声明错了**；`server_required_undeclared` 亮 ⇒ 多半**对端版本漂移**；`schema_shape` / `not_reported` 亮 ⇒ 对端**根本不认这个契约**。三者对运维是三个不同的动作 |
| `unhandled_notifications` | 收到但未处理的**通知**帧计数（含 `tools/list_changed`，§4.3 / §5.4.3） |
| `pagination_ignored` | `tools/list` 返回非空 `nextCursor` 的次数（§1.4） |
| `malformed_tool_entries` | `tools/list` 里形状不合被跳过的条目数（§5.4.2） |
| `unsupported_content_count` | 命中 `provider_unsupported_content` 的次数（§5.4.4） |
| `timeout_count` | 握手/调用超时次数（§5.3a）；`>0` 时 `healthy` 必为 false |
| `closed` / `close_failures` | 已关闭标记 / `close()` 未能在宽限期内正常退出（走了强杀）的 provider 数（§2.2 / §2.4） |
| `protocol_version`（每 provider） | 服务端返回的版本串（**只记这一个字符串**，不记 `serverInfo`/`instructions` 的任何内容，§1.4） |

**`failure_reason` 闭集（2026-09-26 订正：由本节统一列举，`ProviderSnapshot` 字段注释不再重复）**——`provider_health[*].failure_reason` 与 `ProviderSnapshot.failure_reason` 共用这一份清单，未在表中的值不得出现。**注意它和 `TOOL_EXEC_ERROR.details.reason`（§7.3 十三值）不是同一份清单**：后者是「一次执行的失败原因」（进事件流，供报告统计），前者是「这个来源此刻为什么不可用」（**不进事件流**，只进诊断快照，§8.1/§8.2）：

| 值 | 含义 | 与 `TOOL_EXEC_ERROR` reason 的关系 |
|----|------|-----------------------------------|
| `unreachable` | 进程起不来 / 非零退出 / 崩溃 | 同族（复用 `provider_unreachable` 的语义，不共用载体） |
| `timeout` | 握手或调用超时（§5.3a；超时即终止进程） | 同族（`provider_timeout`） |
| `protocol` | stdout 上出现非 JSON 行、`id` 不匹配、`result`/`error` 非法等协议违规 | 同族（`provider_protocol_error`） |
| `oversize` | 响应帧 >64 KiB（**禁截断**） | 同族（`provider_response_too_large`） |
| `protocol_version_unsupported` | `result.protocolVersion` 不在闭集（§5.4.1） | **无对应**——它不是一次执行的失败，是握手期就确定的事实 |
| `closed` | 已由 `close()` 正常/强制关闭（§2.4） | **无对应** |
| `handshake_malformed` | `initialize` 响应形状不合法（§5.4.2） | 同族（`provider_protocol_error`） |

**为什么 `tool_reported_error` 与 `provider_unsupported_content` 不在本表**：它们发生时 **provider 仍然健康**（§5.4.4 把「我们的能力缺口」与「链路破损」分开），因此**不构成 `failure_reason`**；它们只在 `unsupported_content_count` 这样的计数里留下痕迹，或作为一次执行的 `TOOL_EXEC_ERROR.details.reason` 进事件流。

**消费方式**：确定性测试直接读它；`scripts/` 的诊断脚本可打印它。**不进事件流、不进报告**。

### 8.4 审计字段

`AuditEvent` 结构**零变更**，字段语义如下：

| 字段 | 外部工具下的形态 |
|------|-----------------|
| `tool_name` | **规范名**（含 `provider_id.` 前缀）⇒ provider 身份可推导，不新增字段 |
| `risk_level` | 准入声明的值（§6.4） |
| `params_redacted` | **键名级**：键 = 该工具的参数清单，值恒 `"***"`（由 E12 强制的 `audit_redact_all_params=True`） |
| `verdict` / `timestamp` | 既有语义 |

**「值不逐字落本地审计」是 E12 的义务**，而 E12 是**通用**不变式（对天气同样成立）。**不接受**「参数是本地小工具、无所谓」这类例外。

### 8.5 报告

| 项 | 要求 |
|----|------|
| 工具目录字节数 / 件数 | **必须记录**（P7b 是唯一一次往目录里加工具的改动，需可核） |
| 能力目录字节数 / 件数 | 必须记录 |
| 外部工具执行统计 | 按规范名前缀统计（零新键） |
| 值 | **不得**出现任何工具结果的**值**（既有性质，加断言） |
| run 快照 | **必须包含 provider 启用集合**（否则「有 provider 的 run」与「没 provider 的 run」会被判定为可比——`snapshots_are_fair` 的正确性依赖它） |

---

## 9. 配置与 bootstrap 接线

### 9.1 配置结构

```toml
# config/default.toml（P7b 后）——默认零外部来源
[tool_backend]
type = "builtin_only"

# 无 [tool_providers] 节 = 零外部来源。这是 fail-closed 方向的默认值，
# 与 eval 模板里 {{WEATHER_PROVIDER}} 默认 "none" 同纪律。

# config/mcp.example.toml（新增样例，不进 default）
[tool_providers.demo]          # 键闭集 = {enabled, handshake_timeout_ms, call_timeout_ms}（E18）
enabled = true
handshake_timeout_ms = 5000
call_timeout_ms = 10000
# 命令不在这里——它住在 src/tools/provider_declarations.py 的 ProviderDeclaration.argv（裁决 6 / §5.2）。
```

**为什么用 `[tool_providers.<id>]` 子表而不是数组**：TOML 的子表名重复是**解析期错误**，因此「provider id 重复」这一类冲突在**语言层就不可能发生**（§4.2）。

**配置里没有一个字段可以改变权限**（§1.1 第 10 行）：能改的只有「跑不跑」与「给多少时间」。**「跑哪个程序」已经不在配置里**（裁决 6）——原稿的 `command` 键被删除，出现即 `CONFIG_ERROR`（E18）。

### 9.2 `bootstrap` 顺序（P7b 的增补点用 **←** 标出）

```
1.  load config
2.  _capabilities_enabled(config)
←3. 工具提供者结构校验：
      a. 配置键闭集（E18）——未知键（含 command）⇒ CONFIG_ERROR
      b. 配置里的 provider id 必须 ∈ 代码声明（E1）
      c. **代码侧**：全部 ProviderDeclaration 的 argv 解析（E17，与是否启用无关）⇒ 失败即
         tool_provider_command_missing（**代码错误**，不是配置错误）
      d. 超时值（E16）、E3（providers 非空 ⇒ 能力层必须开启）
4.  model backend load + health_check
5.  create_memory_backend
6.  _workspace_root(config)（解析 + mkdir）
←7.  create_tool_backend(...)：
      a. 内置注册表 + 白名单 → active
      b. 外部准入声明（代码）→ E4–E12、E15 自校验（fail-loud）
      c. **环境白名单构造**（§5.2）——每 provider 一份，不传 os.environ
      d. 逐 provider 握手（动态，不 fail-loud）→ ProviderSnapshot
      e. 准入过滤 + §5.6 四条兼容性检查 → 外部 active
      f. 构造 CompositeToolBackend（内置 ∪ 外部）
      ⚠ **失败路径**：c–f 任一步抛错（例如第 b 步的 CONFIG_ERROR）时，**必须把本次已启动的
        provider 全部 close() 之后再抛**——否则一次启动失败会留孤儿进程（P11 第 ③ 臂）
8.  validate_tool_catalog(tool_backend.list_tools())      ← 现在覆盖外部工具
←9. validate_capabilities(BUILTIN + EXTERNAL, active, enabled=False, registered_tools=已知全集)
      （声明自校验 + E11/E12 由这次调用的**前半段**完成——它不看 `enabled`）
   +  validate_active_capabilities(BUILTIN + EXTERNAL, 已知全集)   ← **E13/E14 在这里，且无条件**
      （2026-09-26 审查后据实改写：原稿写 `enabled=...`，暗示这个值是 `capability_routing.enabled`
        的派生——**实现不是这样**，此处恒为 `enabled=False`，覆盖检查改为下一行**无条件**跑在
        **准入集**上。理由是检查对象：E13 要的是「声明出来的工具都得有能力覆盖」，与「这次运行
        有没有开能力层」是两个问题；若按运行态取值，关态下这条静态完整性检查会**静默消失**。
        运行态的覆盖仍在两处按运行态严格校验：`CompositeToolBackend` 与 `BuiltinToolBackend`
        的构造 + `ContextAssembler`（`capabilities_enabled` 时才跑，每回合都跑）。E3 已单独保证
        「provider 启用 ⇒ 能力层必开」）
10. create_safety_backend / cloud / evolution
11. ContextAssembler(..., capabilities_enabled=...)
12. IntentResolver / SafetyPolicy / AuthorizationManager / event sink
13. App(...)   ← **构造签名零变更**（新增的方法 `shutdown()` 不影响构造）
←14. 调用方责任：CLI（`src/cli/loop.py` 的 `finally`）、评估运行器子进程、诊断脚本
      都必须在 `finally` 中调用 `app.shutdown()`（§2.4）
```

**`known_tools` 已知全集（R2 的参照集）在 P7b 下的形态** = `BUILTIN_TOOLS` 键 ∪ `{weather.current}` ∪ **全部已准入的外部工具规范名**。它仍然是**代码里的确定性事实**（`16 §1.2` R2 的硬要求），**不得**由服务端自报反推、不得由配置拼。

### 9.3 eval 侧接线（`src/evaluation/`）

| 项 | 要求 |
|----|------|
| `render_instance_config()` | **不需要新占位符**（2026-09-26 收回）。原稿的 `{{PROJECT_ROOT}}` / `{{PYTHON}}` 只因命令住在配置里才存在；命令挪进代码后（裁决 6），解释器与仓库根由适配器在运行时取（`sys.executable` / `Path(__file__)` 上溯），**与配置无关**。渲染侧只多一件事：`mcp_on` 变体渲染 `[tool_providers.demo]`（三个键），`mcp_off` 不渲染该节；缺省（未给 provider 开关）⇒ 不渲染。**替换后校验**沿用既有规则（无 `{{` 残留） |
| `_VARIANTS` | 新增 `mcp_on` / `mcp_off` |
| `config_snapshot()` | **必须包含 provider 启用集合**（§8.5）；`snapshots_are_fair` 因此自动拒绝混合比较 |
| 场景 | 新增 **S19**（§10.3） |
| `_EXPECT_KEYS` | **不新增** |

---

## 10. 首批交付与验收

### 10.1 首批工具清单

| 工具 | 规范名 | 能力 | 来源 | 风险 | 说明 |
|------|--------|------|:----:|:----:|------|
| 获取当前时间 | `system.get_time` | `system.time` | 内置（**复用**） | normal | **不新增**。老板第 7 条明令不重复实现；也**不得**为它加时区/格式化参数（无已观测失败证据，`16 §1.4` 同纪律） |
| 查看文件属性 | `file.stat` | `files.info`（**新增能力**） | 内置（**新增工具**） | normal | 返回 `path/exists/is_dir/size_bytes/modified_at`，**不返回内容**。`file.list_dir` 只给名字，给不了大小/时间 |
| JSON 文本格式化 | `demo.json_format` | `text.format`（**新增能力**） | 外部（MCP stdio 演示服务） | normal | 首批外部工具。**刻意选一个纯函数式、只读、无网络、无路径的工具**，使 P7b 的首批交付**不新增任何网络或文件目标面** |

**措辞修正（2026-09-26，回应措辞修正第 1 条）**：原稿写「使首批交付**引入零新外发面**」是**不准确**的——用户原文确实会**离开 Agent 进程**进入 MCP 子进程，本契约自己也把它标为 `egress=True`（§2.3）。准确的表述是：

> **首批外部工具不新增任何网络目标或文件目标面；新增的是一个受控的本地进程出站面**——值的去向是一个**由代码声明、由同一台机器上的子进程承载**的进程，且该值仍受准入级来源校验、实例谓词与出站边秘密检测三重约束（§6.3）。

**不做**（老板第 7 条）：不新增天气工具、不新增文件读写工具、不新增 `system.*` 的其它工具、不把 `system.echo` 放进任何生产白名单（P7a §9.1 第 5 项保持）。

**`file.stat` 的注册要求**：

- 工作区边界走**单一入口** `resolve_workspace_target`（与既有文件工具同法，不新写第二份路径校验）；
- **必须注册 preflight**，形态与 `preflight_list_dir` **同族**：读工具、`requires_confirmation=False`、`approval_profile` 取 `tool_def` 值、workspace_escape 升为 `dangerous`（与 `file.read`/`file.list_dir` 同法，可审计）；
- **不得**要求目标存在（`exists=false` 是合法结果）；
- `risk_level="normal"`，`egress=False`（不离开进程）；
- 错误 reason 复用既有 `FILE_ERROR` 词汇（`path_type` / `workspace_escape`），**不新增**。

**`demo.json_format` 的准入声明要求**：

- `risk_level="normal"`、`side_effect_class="read_only"`、`approval_profile="standard"`（全部**显式**写出，E7）；
- 单参数 `text`（`string`），∈ `supply_by_echo`，有实例谓词（E9/E10/E11）；
- 谓词使用**共享的整值谓词工厂**（`src/tools/` 内，单一实现，首批外部工具统一使用）：非空、≤8192 码点、无控制字符、**非路径形态**（不以 `/`、`\`、`~`、盘符、UNC 开头）、**非 URL 形态**。这条是老板第 4 条边界（不得扩大可访问路径）在结构上的落点；
- `egress` 由管道**强制**为 `True`，`audit_redact_all_params` 由管道**强制**为 `True`（§2.3 / E12）。

**`scripts/mcp_demo_server.py` 的要求**：

- **stdlib-only、零第三方依赖、零网络**；
- newline-delimited JSON-RPC 2.0，实现 `initialize` / `notifications/initialized` / `tools/list` / `tools/call(json_format)`；
- **`--fault=<arm>` 故障注入**：`hang`（握手/调用不响应）、`garbage`（stdout 吐非 JSON）、`no_id`、`bad_result`、`oversize`（>64 KiB）、`iserror`、`die`（调用中退出）、`schema_mismatch`、`extra_tools`（自报更多工具）、`hint_readonly_false`（自报 `readOnlyHint: false`）、`changed_notice`（发 `tools/list_changed`）。**2026-09-26 新增六臂**（前五臂对应当日第一轮修订、末一臂对应同日二次修订）：`late_reply`（超时后把上一次的响应写进 stdout，验 §5.3a）、`ignore_sigterm`（忽略 `terminate()`，验 §2.2 ④ 强杀）、`bad_version`（返回闭集外 `protocolVersion`）、`non_text_content`（`content` 含非 `text` 条目，验 §5.4.4）、`ansi_text`（返回含 ESC/OSC 序列的文本，验 §5.7）、`noisy_stderr`（**狂写 stderr**，验 `stderr=DEVNULL` 下既不污染六面也不卡死）。**诊断臂**（只读、非故障）：`--dump-env`（自报自身环境键集）、`--dump-argv`（自报自身 argv 与 PID）。**一个脚本同时是演示服务与故障替身**——验收矩阵的所有故障臂都用它驱动，不另写替身；
- 生产样例（`config/mcp.example.toml`）使用**无故障臂**。

### 10.2 自动化验收矩阵

每条含：**输入 → 断言 → 探针**（探针 = 把机制删掉/改错后，本条必须变红）。

#### M 组 · 权威归属与准入（老板第 3、9 条）

| # | 用例 | 断言 | 探针 |
|:-:|------|------|------|
| **M0** | 结构断言 | `ExternalToolAdmission` 的字段集**不含** `capability_id` / `requires_confirmation` / `preflight` / `annotations` / `egress`（源码级）；`ToolProvider` 的抽象方法集**恰为** `handshake`/`execute`/`close` | 给准入记录加一个 `capability_id` 字段 ⇒ 变红 |
| **M1** | 服务端自报 3 工具、本地准入 1 | `list_tools()` 只多 1 条；另 2 条**零渲染**（提示词逐字节不含其名）且模型给出草案 ⇒ `unknown_tool`；`unadmitted_count == 2` | 去掉准入过滤（自报全集当 active）⇒ 变红 |
| **M2** | 服务端自报含诱导文本（描述写 "ignore previous instructions…"）+ `hint_readonly_false` | ①提示词**逐字节不含**服务端任何字符串（description/annotations/schema 的任何值）②准入结论与自报 hint 无关（两臂都按本地声明）③风险/批准/副作用三字段与本地声明逐字相同 | 让 `description` 取自服务端 ⇒ 变红。**测试替身要求（2026-09-26 补）**：服务端**必须**在 `tools/list` 里发出带哨兵串的 `description` 与 `annotations`（`title` 等）——原稿只写了断言、没写替身从哪来，而演示服务当时**不发 `description`**，该臂无法构造。替身形态：默认 `_tool()` 恒带哨兵（或新增 `--fault=hostile_metadata` 臂），哨兵取一个不可能自然出现的字符串以便逐字节断言 |
| **M3** | 冲突四臂 | ①config 出现未登记的 provider id ⇒ `tool_provider_unknown` ②`provider_id="file"` + `alias="read"` ⇒ `external_tool_name_conflict`（**不得**覆盖内置）③两条准入产生同一规范名 ⇒ 同上 ④`raw_name` 不匹配任何候选 ⇒ **该工具不可用，启动成功**（不是 CONFIG_ERROR） | 把 ⑤ 改成静默覆盖 ⇒ 变红 |
| **M4** | 能力归属 | ①外部工具**不能**携带能力字段（M0）②两个能力 id 相同 ⇒ R1 fail-loud ③**E13**：已准入但未被任何能力覆盖 ⇒ fail-loud（**provider 未配置时也必须红**） | 把 E13 的校验对象改回 `active` 集 ⇒ 第 ③ 臂在 provider 关闭时变绿 ⇒ 探针命中 |
| **M5** | 关态 × providers | `[tool_providers.demo] enabled=true` + `capability_routing.enabled=false` ⇒ `tool_providers_require_capability_routing`，**启动失败** | 删掉这条检查 ⇒ 外部工具在无能力层时进入提示词并可执行 ⇒ 变红 |
| **M6** | 可替换性 | ①`src/tools/` 的聚合后端源码对 `mcp`/`qwenpaw`/`jsonrpc`/`subprocess` **零命中** ②注册一个**第三种 kind 的替身 provider** ⇒ 聚合、准入、能力派生、执行、错误语义全部照常，**Core 零改动** | 让聚合后端 import 具体 provider ⇒ 变红 |
| **M7** | **命令由代码签发**（2026-09-26 新增，裁决 6） | ①配置里写 `command = [...]`（或任何非闭集键）⇒ `CONFIG_ERROR` / `tool_provider_invalid`（E18），**启动失败** ②`grep` 断言「`Popen` 的 argv 来自 `ProviderDeclaration`，代码里**没有**第二个 argv 来源」③在配置里把 `enabled` 改 true（不碰命令）⇒ 启动的仍是**代码里那一个**程序（用 `--dump-argv` 臂取子进程自报 argv 比对）④E17 的校验对象是**全部**代码声明的 provider：把一个**未启用**的 provider 的 argv 改坏 ⇒ 仍然 fail-loud | 让配置能提供 argv（把 `command` 加回键集）⇒ 第 ① 臂变绿 ⇒ 探针命中 |

#### P 组 · provider 生命周期与传输（老板第 5 条）

| # | 用例 | 断言 | 探针 |
|:-:|------|------|------|
| **P1** | 正常臂 | 握手成功 ⇒ 工具进 active、能力可用、`capability_resolution="routed"`、执行成功、`display` 含格式化结果 | — |
| **P2** | `--fault=die`（启动即退）/ 命令不存在之外的启动失败 | **bootstrap 不抛**；工具不可用；能力 `available=false`；`capability_resolution="unavailable"`；**零 `tool_execution`**；诚实失败文案 = 既有常量；零云端 | 让握手失败抛异常 ⇒ 变红 |
| **P2b** | **代码声明的 `argv` 首项不存在**（2026-09-26 改：不再是配置问题） | `CONFIG_ERROR` / `tool_provider_command_missing`（静态可判定 ⇒ fail-loud，§7.2）；**归属 = 代码**（§7.1） | 把它降级成「不可用」⇒ 变红；把它判成配置错误 ⇒ 归属断言变红 |
| **P3** | `--fault=hang`（握手不响应） | 受 `handshake_timeout_ms` 约束（**时钟断言**）；**超时后进程被终止**（§5.3a ①）；无孤儿进程；其余 provider 与内置工具**不受影响**（独立故障域）；诊断 `timeout_count == 1` | 去掉超时 ⇒ 启动挂死；去掉「终止进程」⇒ 进程存活 ⇒ 变红。**进程存活怎么断（2026-09-26 修正可实施写法）**：`hang` 臂**不会有任何成功调用**，因此拿不到 `--dump-argv` 自报的 PID——**保留 `Popen` 句柄**（测试用 `monkeypatch` 包住 `subprocess.Popen` 记下创建出的进程对象）后断言 `retained.poll() is not None`；用 PID 的写法只适用于「先成功调用过再关闭」的臂（P4 / P11 ①）。**禁止**用 `os.kill(pid, 0)` 探测：Windows 上它等价于 `TerminateProcess`（会把进程杀掉）；Windows 分支须走 `tasklist /FI "PID eq <pid>"` |
| **P4** | 调用超时（§5.3a ②③） | ①`TOOL_EXEC_ERROR` + `reason="provider_timeout"`；恰一条 `tool_execution` 且 `outcome != "allowed"`；零成功叙事 ②**超时后进程被终止**（PID 不存在）③**第二次调用零执行、零 `tool_execution`**（`provider_healthy=false`，走「能力不可用」而不是读迟到帧）④**构造一条迟到帧**（`--fault=late_reply`：先超时，再把上一次的响应写进 stdout）⇒ 第二次调用**不得**因此变成 `provider_protocol_error`（因为根本不该再读那条流） | 保留「超时但健康」⇒ 第 ③ 臂仍发事件 ⇒ 变红；删掉「终止进程」⇒ 第 ④ 臂出现协议错误 ⇒ 变红（这正是原稿的漏洞形态） |
| **P5** | 调用中进程死亡 | `provider_unreachable`；**且该 provider 后续不可用**（第二次调用零执行、零 `tool_execution`） | 去掉「标记不可用」⇒ 第二次调用仍产生事件 ⇒ 变红 |
| **P6** | 只收紧不放松 | 崩溃后即使进程恢复也不重新可用；`--fault=changed_notice` ⇒ active 集合**不变**、无事件、诊断计数 +1 | 让通知触发重新拉取 ⇒ active 集合变化 ⇒ 变红 |
| **P7** | `--fault=oversize` | `provider_response_too_large`；**不截断**；provider 标记不可用 | 改成截断 ⇒ 变红 |
| **P8** | 畸形四臂（`garbage` / `no_id` / `bad_result` / 顶层数组） | 各自 `provider_parse_error` / `provider_protocol_error`；**协议违规 ⇒ provider 标记不可用**（第二次调用零执行） | 把「不标记不可用」当默认 ⇒ 第二次仍有事件 ⇒ 变红 |
| **P9** | `--fault=iserror` | `TOOL_EXEC_ERROR` + `reason="tool_reported_error"`；**provider 保持可用**（下一次正常调用成功） | 把它当协议错误 ⇒ provider 被错误关闭 ⇒ 变红 |
| **P8b** | **帧结构按方法区分**（2026-09-26 新增，§5.4） | ①正常臂：`initialize` 的 `result` **不含** `content` 也**必须通过**（原稿会在此变红——这是本条的存在理由）②`tools/list` 的 `result` 含 `tools`；`nextCursor` 非空 ⇒ 只取本页 + `pagination_ignored += 1` ③`tools/call` 的 `result.content` 有一个非 `text` 条目 ⇒ `provider_unsupported_content` 且 **provider 保持可用**（下一次正常调用成功）④`protocolVersion` 不在闭集 ⇒ 不可用 + `failure_reason="protocol_version_unsupported"` ⑤无 `id` 的合法 JSON 帧**不判违规**（当通知，`unhandled_notifications += 1`，继续读）⑥`id` 与在途请求不匹配 ⇒ `provider_protocol_error` + 不可用 ⑦`result`/`error` 同时存在或同时缺失 ⇒ 同上 | ①把「`content` 缺失」一律判违规（原稿规则）⇒ 正常握手变红 ②把「无 id」判违规 ⇒ 第 ⑤ 臂变红 ③把 `unsupported_content` 判成协议违规 ⇒ 第 ③ 臂的 provider 被错误关闭、第二次调用变红 |
| **P10** | 进程、环境与管道（2026-09-26 加强） | ①**子进程 env 的键集 ⊆ §5.2 白名单**（穷尽式；子进程用 `--dump-env` 臂自报。**穷尽式的判据形式（2026-09-26 写明，防再写成抽样断言）**：`set(dumped_keys) <= set(_ENV_COPY_ALLOWLIST) \| {"PYTHONIOENCODING", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE"}`——只断言「某几个键不在」不算覆盖本臂）②父进程里**已知凭据变量**（各 provider profile 的 `credential_env` + 形如 `*_API_KEY`/`*_TOKEN`/`*_SECRET` 的键）在子进程中**不存在** ③测试现场注入一个**随机名**秘密变量（`LOCALMIND_TEST_SECRET_<uuid>`）⇒ 子进程中**不存在** ④源码级：实现里**没有**把 `os.environ` 传给 `Popen` ⑤`--fault` 在 stderr **狂写**任意内容 ⇒ ①**不出现在**提示词/事件/审计/记忆/报告/回复六面，②**调用不卡死**（`stderr=DEVNULL`；源码级断言**不是** `PIPE`） ⑥`argv` 含 `;`/`\|`/`&` 的单项**不被解释、逐字到达子进程**（`--dump-argv` 比对；**2026-09-26 二次修订**：E17 不再禁这些字符，本臂因此可执行——它就是那条禁令被删的判据） | 用 `env=os.environ` ⇒ 第 ①②③ 臂同时变红；用 `shell=True` ⇒ 第 ⑥ 臂变红；改回 `stderr=PIPE` 且不消费 ⇒ 第 ⑤ 臂的「不卡死」变红 |
| **P11** | **生命周期确定性回收**（2026-09-26 新增，回答审查第 3 项） | ①正常路径：`app.shutdown()` ⇒ provider 进程已退出（PID 不存在）、`list_tools()` 返回空集、`execute()` 一律 `TOOL_NOT_FOUND` ②**幂等**：连续调用两次 `shutdown()`（与 `ToolProvider.close()`）不抛、行为相同 ③**bootstrap 中途失败**：让第 7 步的准入校验抛 `CONFIG_ERROR`（例如造一个重复规范名），而握手已经启动过 provider ⇒ **不得留孤儿**（已启动的必须被关闭后抛出）④**工具执行抛错后**退出（`--fault=die` 已使进程死）⇒ `shutdown()` 仍能安全调用、不抛 ⑤**Ctrl-C**：CLI 在 `run()` 的 `finally` 中调用 ⇒ 无孤儿（`KeyboardInterrupt` 沿既有异常路径抛出）⑥`close()` 宽限期：`--fault=ignore_sigterm` ⇒ 走强杀并回收，`close_failures += 1`，**不抛异常**（**2026-09-26 补平台边界**：该臂依赖 **POSIX** 的 SIGTERM 语义；Windows 上 `Popen.terminate()` 直接 `TerminateProcess`，子进程**不可能**在宽限期内存活 ⇒ `close_forced` 恒 `False`。故该臂在 POSIX 上断言「强杀 + `close_failures == 1`」，在 Windows 上断言「`close()` 不抛 + 进程已退出 + `close_failures` 如实为 0」——**不得**在 Windows 上要求 `close_failures == 1`，那是不可满足的） ⑦`end_session()` **不**关闭 provider：一次会话结束后、同一进程内第二次会话仍可正常调用外部工具 | ①把 `close()` 从 `finally` 挪回 `end_session()` 边界 ⇒ 第 ⑦ 臂变红（第二次会话工具不可用）；②去掉 bootstrap 失败路径的补偿关闭 ⇒ 第 ③ 臂出现孤儿进程 ⇒ 变红 |

#### X 组 · 执行边界（老板第 1、2、4 条）

| # | 用例 | 断言 | 探针 |
|:-:|------|------|------|
| **X1** | 准入级来源校验对外部工具自动生效 | 模型编造参数值 ⇒ `param_not_from_input`；**零执行**；**零 `tool_execution`**；诚实失败 | 关掉准入级（`capabilities=None` 那一支）⇒ 值被外发 ⇒ 变红。**注意**：M5 已使该组合起不来，本臂用「能力层开启但绕过准入级」的替身路径验证 |
| **X2** | 实例谓词 + `PendingToolInput` 续接自动生效 | 模型把整句填进参数 ⇒ 剔除 ⇒ `param_missing` ⇒ `ASK_USER` ⇒ 补参后**同回合续接**（复用 P7a §4.4 通道，**零新增**） | 删掉续接 ⇒ 变红 |
| **X3** | `egress` 通用不变式 | ①某工具 `egress=True` 但参数 ∉ `supply_by_echo` 或 ∉ `param_instance_checks` ⇒ `egress_contract_invalid` ②`egress=True` 但 `audit_redact_all_params=False` ⇒ 同上 ③参数 `type != "string"` ⇒ `external_tool_declaration_invalid` ④**天气回填 `egress=True` 后，P7a C15 全绿** | 把 E11/E12 限成「只对外部工具」⇒ 天气的通用性断言变红 |
| **X4** | 风险与批准档不可被外部影响 | `effective_risk` 恒 = 准入声明值；`approval_profile` 闭集外 ⇒ 注册期 fail-loud；声明为 `high_impact` ⇒ `SAFETY_IMPACT_CLOSED`、零执行（既有扣留） | 让 `effective_risk` 读自报 ⇒ 变红 |
| **X5** | 唯一执行出口 + **P7a 矩阵对外部工具复跑** | ①`CompositeToolBackend.execute` 与 `ToolProvider.execute` 的调用点唯一在 `GuardedToolExecutor` 链上（源码级）②**把 P7a 的能力真值表（C3/C4/C5 诸臂）在「外部工具目录」上重跑一遍**：未路由/无关/不可用/越界各臂对外部工具逐行成立 | 让聚合后端直接执行（绕过 executor）⇒ ②的某个臂出现 `tool_execution` ⇒ 变红 |
| **X6** | 副作用面 | `side_effect_class != "read_only"` ⇒ `external_side_effect_not_supported` fail-loud（含 `local_side_effect` / `external_side_effect` / 任意未知值） | 允许 `local_side_effect` ⇒ 变红 |
| **X7** | 出站与入站的秘密处理 | ①用户原文含凭据 ⇒ 出站边拒绝、零外发、`param_secret_rejected` ②演示服务**故意返回**含凭据的结果 ⇒ 该值在**事件 JSONL / 报告 / 审计 / 记忆**中**不可检索**；`display` 中出现且**不落盘** ③`display` 的值**不进入**云端 payload | ①删掉出站边检测 ⇒ 秘密外发 ⇒ 变红 ②把结果塞进事件 `detail` ⇒ 变红 |
| **X8** | 审计字段 | `params_redacted` 的**键集** = 参数清单，值恒 `"***"`；`tool_execution` 事件里无参数值 | 关掉 `audit_redact_all_params` ⇒ 用户原文逐字落本地审计 ⇒ 变红 |
| **X9** | **显示净化**（2026-09-26 新增，§5.7） | ①演示服务返回含 `\x1b[2J` / OSC 52 序列的文本 ⇒ `display` 里**不含** `\x1b`（终端不被清屏、剪贴板不被写）②返回 5000 码点文本 ⇒ `display` 显示前 4096 + **显式截断标记**（不静默）③`narrative_reply` / episode / 事件 / 审计 / 报告**不受**净化影响（它们本就不含值，§6.5）④作用域是**所有**工具结果：给内置工具塞一个含控制字符的结果 ⇒ 同样被剥离 ⑤既有断言 `tests/test_p0a_components.py` 的 `"hello"` 仍在 `display` 中（纯 ASCII 不受影响） | 把净化只加在适配器出口（而不是 `ResponseBuilder`）⇒ 第 ④ 臂变红；去掉截断标记 ⇒ 第 ② 臂无法区分「这就是全部」与「被截断」 |

#### N 组 · 非干扰与预算

| # | 用例 | 断言 | 探针 |
|:-:|------|------|------|
| **N1** | 关态零非干扰 | `tool_providers` 为空 + `capability_routing.enabled=false` ⇒ 事件流与 P7a 关态**逐字段相等**；提示词不含能力段；两份键表逐字符相等 | 在关态下让能力层仍写 `capability_resolution` ⇒ 事件流多键 ⇒ 变红 |
| **N2** | 预算 | 工具目录 ≤32 件 / ≤8192 字节；能力目录 ≤8 件 / ≤2048 字节；**超限 fail-loud、禁截断**；报告记录新增后的**实际**字节数与件数 | 把超限改成截断 ⇒ 变红；把外部自报文本计入字节账 ⇒ `mcp_on` 与 `mcp_off` 的目录字节数不同 ⇒ 变红（外部内容零进字节账） |
| **N3** | 旧路径零回归 | `file.stat` 与两个新能力加入后，既有 18 场景（S01–S18）关/开复跑无回归；源码级：编排层（`main.py` 的决策分支 / `task_planner` / `control_policy`）**零新工具名字面量** | 在编排层加一个 `if tool_name == "demo.json_format"` 分支 ⇒ 源码断言变红 |
| **N4** | 场景 S19（§10.3） | 两臂（`mcp_on` / `mcp_off`）断言成立，且 `_EXPECT_KEYS` **未新增** | 为 S19 新增一个 `expect` 键 ⇒ `_EXPECT_KEYS` 不相等 ⇒ 变红 |
| **N5** | 快照可比性 | `config_snapshot()` 含 provider 启用集合；`mcp_on` 与 `mcp_off` 两 run **不可比** | 从快照里去掉 provider 集合 ⇒ 两 run 被判可比 ⇒ `snapshots_are_fair` 不再拒绝 ⇒ 变红 |

### 10.3 场景 S19

新增 `scenarios/S19_external_tool_unavailable.toml`：

| 步骤 | 输入 | 变体 | `expect` |
|:----:|------|------|----------|
| 1 | 请求把一段 JSON 文本格式化（`mcp_on` 臂） | `mcp_on` | `tool_any = ["demo.json_format"]`、`capability_any = ["routed"]` |
| 2 | 同一请求（`mcp_off` 臂） | `mcp_off` | `capability_any = ["unavailable"]`、`tool_none = true`、`cloud_any = false`、`action_any = ["PLAN_LOCAL"]` |
| 3 | 请求查看某文件属性（本地工具，两臂同） | 两臂 | `tool_any = ["file.stat"]`、`capability_any = ["routed"]` |

**variant 归属**：`mcp_off` 属**主列表**（`builtin_only` 默认臂，与 `base` 同族的确定性臂）；`mcp_on` 依赖本地子进程（**不依赖网络**，比 P7a 的 `weather_on` 更确定），但耗时可测差异较大——**归属按 P7a 对 `weather_on` 的既有规则处置**（若既有规则要求单独列出，则照办）。

### 10.4 报告硬性行

- 工具目录件数/字节数、能力目录件数/字节数（**新增后的实际值**）；
- 外部工具执行次数（按规范名前缀统计）；
- 「能力不可用」的计数（复用既有 `capability_resolution` 统计）；
- **不得**出现任何工具结果的**值**；
- run 快照含 provider 启用集合；
- **不得**出现「QwenPaw Skills 已接入」「MCP 生态已打通」「插件安全已解决」这类表述——v1 交付的是**接入点**，验证对象是仓库自带的演示服务端（§0.4 ③）；
- **不得**宣称「外部 provider 安全」或把 FR3 说成已覆盖任意第三方 provider（§0.4 ①）。

---

## 11. 遗留与明确不做

| # | 项 | 状态 | 理由 / 触发条件 |
|:-:|----|:----:|----------------|
| 1 | 远端 MCP transport（HTTP/SSE） | **不做** | 需要与 P7a §6 同级的独立出站论证（主机白名单、TLS、重定向、凭据、出站审计、大小与超时）。触发：出现必须远程的工具需求 |
| 2 | QwenPaw **原生** `skills_dir` 适配器 | **不做** | `project-report.md` 已采用 MCP stdio Provider 作为外部工具标准接缝；原生化需 QwenPaw 运行时的执行契约。触发：拿到该契约时（与 `04 §23` 的 ToolGuard L2 同批）。**`src/adapters/qwenpaw_adapter.py` 保持占位并在文件头写明本行** |
| 3 | 「零本地声明自动接入」 | **不做** | 它与裁决 1 直接冲突（自动准入 = 把外部自报当权威）。触发：同一 provider 的工具数使声明成本成为真实瓶颈，且需先给出「自动准入如何不成为权限提升」的论证 |
| 4 | 外部工具的**进程级沙箱** | **不做**（§0.4 ①） | 需要 OS 级隔离（容器/命名空间/seccomp）。**裁决 6 把 argv 收进代码不构成沙箱**——被声明的进程仍持宿主机权限 ⇒ **FR3 对任意第三方 provider 尚未满足**，只对「本地代码里声明过的 provider」的**工具调用**成立。触发：首个带副作用的动态工具立项时，与沙箱一并论证 |
| 5 | provider 健康的**运行期事件面** | **不做**（§8.2） | 当前只有诊断快照。触发：需要跨 run 比较 provider 可用性 |
| 6 | 运行期热插拔 / 自动重启 | **不做**（裁决 3） | 与本契约「动态只能收紧」的核心安全性质冲突 |
| 7 | 外部工具的**非 string 参数** | **不做**（E9） | 数字/枚举/结构化参数同时绕开来源校验与实例语义。触发：首批文本工具不足以覆盖真实需求，且需补「无来源校验的类型如何受约束」的论证 |
| 8 | `egress` 的**目标分类**（进程内 / 本机 / 网络） | **不做** | 当前二值足够（本机子进程与网络在「值离开进程」这一点上无区别）。触发：远端 transport 立项时，届时应把 `egress` 拆成三档 |
| 9 | 外部工具结果进入**云端上下文** | **明确不做** | P7a §6.6 同纪律：外部工具结果**不得**作为云端咨询的材料。触发：出现真实需求时，走 P5 `TaskBrief` 的既有真源并单独论证 |
| 10 | 新增 `degradation` 组件 | **明确不做** | provider 离线是「能力不可用」，不是降级路径（与 P7a 对天气失败同法） |
| 11 | 外部工具的**目标级动态风险评估** | **不做**（§0.4 ②） | 判不了（目标在外部进程内部）。代价已照实写明 |
| 12 | **真实 QwenPaw / 第三方 MCP 服务端的互操作测试**（2026-09-26 新增） | **不做** | 本阶段验证对象是仓库自带的 `scripts/mcp_demo_server.py`（按帧格式写的**最小实现**，不是合规性证明）。**在完成互操作测试之前，报告不得宣称「QwenPaw Skills 已接入」**（§0.4 ③ / §10.4）。触发：拿到 QwenPaw 运行时的 MCP 端点，或一个可安装的真实 MCP 服务端 |
| 13 | `_SUPPORTED_PROTOCOL_VERSIONS` 的**版本扩展**（2026-09-26 新增） | **不做**（v1 只有 `"2024-11-05"`） | 每加一个版本都要重新核对 §5.4.2 的逐方法响应形状（新版本可能改字段）。触发：真实 MCP 服务端因版本不匹配而不可用，且该服务端不可降级 |
| 14 | **显示净化的可配置化**（如放宽 4096 上限）（2026-09-26 新增） | **不做** | 显示上限是显示层性质，不是权限；让它可配置会把一个「防终端注入」的常量变成可被一次配置编辑放宽的东西（同 §1.2 的理由）。触发：真实用户反馈显示过短且无法用既有方式看到完整结果 |

---

## 12. 决策记录

| # | 决策 | 依据 | 被否方案 |
|:-:|------|------|---------|
| 1 | 权限由**本地代码**签发，外部自报只是候选人 | 老板第 3/9 条；`16 §11` 第 4 项 | ①能力映射进配置 ②信任 MCP `annotations` ③信任服务端 `description` |
| 2 | 外部文本**零进提示词** | 零成本消灭注入源；同时固定字节账上界 | 「服务端描述更准确，直接渲染」 |
| 3 | `ToolProvider` 由 **Core** 定义 | 依赖方向：`src/tools/` 不得依赖 `src/adapters/` | ①放 `src/tools/` ②放 `src/adapters/` |
| 4 | 外部工具的能力归属走**合并后的同一份目录 + 同一套校验** | `16 §1.1`「同一份声明两条路径不同结论」的警告 | 外部能力单独一套校验 |
| 5 | v1 只准入 **`read_only`** | 老板第 4 条；v1 无法约束外部进程 | 「声明即接受」 |
| 6 | v1 参数**只允许 `string`** | 只有 string 能同时受来源与实例两级约束 | 支持全部 JSON Schema 类型 |
| 7 | `ToolDef` 新增 **`egress`** 并把 P7a 的源码级断言升级为**通用注册期不变式** | `16 §11` 第 22 项的触发条件已到 | 对外部工具单独写一份断言 |
| 8 | 加 **E3**（providers 非空 ⇒ 能力层必须开启） | 把老板第 1 条变成结构性事实 | 「关态下也允许外部工具，只加告警」 |
| 9 | 加 **E13（R3'）**，校验对象从 `active` 改成**准入集** | 堵住「关着的门后面的潜伏配置错误」，代价为零 | 沿用 R3 |
| 10 | transport **只有 stdio** | 远端需独立出站论证；首批工具不需要它 | 一次做完 stdio + HTTP |
| 11 | 动态变化**只能收紧**，不热插拔/不自动重启 | 与「外部事实不产生放宽」同源 | 支持 `tools/list_changed` 热更新 |
| 12 | 静态可判定 ⇒ fail-loud；动态 ⇒ 不可用 | 与 P7a「配置错误 fail-loud / 天气失败非降级」的分工一致 | 命令不存在也降级成不可用 |
| 13 | 握手失败**不 fail-loud** | 本地优先、离线优先 | 启动即失败 |
| 14 | 事件闭集**零扩展**；`App` **构造签名**零变更；`ToolBackend` 接口**新增一个带默认实现的 `close()`**（**2026-09-26 修订**：原稿主张「三项零变更」，据实改为**两项零变更 + 一项必要变更**） | 「外部工具是一次**接入**，不是一次**架构变更**」；但**资源生命周期**是既有缺口——原稿的 `ToolProvider.close()` 没有任何调用方（审查第 3 项） | 新增 `provider_health` 事件键；把资源释放挂在 `end_session()` 上（会话边界 ≠ 进程边界，§2.4） |
| 15 | 「provider 离线 vs 未启用」的不对称**照实登记不修** | 对用户是同一件事；区分载体内是诊断快照 | 落一个新键 |
| 16 | 出站边复用**同一份**秘密检测器 | `05` 的单一真源纪律 | 为外部工具写第二份检测 |
| 17 | 结果**值不进持久面**（既有性质，P7b 只守不改） | 已核实：`_execution_summary` 只留字段名、`_record_tool_events` 只发结构键 | 「加一道入站消毒」（兜底方案保留现状，不作为第一道） |
| 18 | 首批外部工具**刻意选纯函数式只读工具** | 使首批交付**不新增网络或文件目标面**（**2026-09-26 措辞修正**：原稿写「零新外发面」不准确——用户原文确实离开 Agent 进程，本契约自己也标 `egress=True`；准确口径见 §10.1） | 首批就接一个真实的外部服务 |
| 19 | 接入一个新工具**必然**伴随一次本地代码变更 | 裁决 1 的实现方式；老板明令「不是一次接入大量工具」 | 零声明自动接入（§11 第 3 项） |
| 20 | `system.get_time` **复用不新增** | 老板第 7 条 | 为它加参数 |
| 21 | 演示服务与故障替身**同一个脚本**（`--fault`） | 故障臂覆盖度最大、替身维护成本最低 | 每个故障臂写一个替身 |
| 22 | `config_snapshot()` **必须含 provider 启用集合** | 否则 `snapshots_are_fair` 会把不可比的 run 判为可比 | 只在报告里记 |
| 23 | **命令（`argv`）由本地代码签发，配置只留 `enabled` + 两个超时**（2026-09-26，审查第 1 项） | 配置能决定「启动哪个程序」⇒ 一个配置文件换来一次 `bootstrap` 期（`GuardedToolExecutor` 之前）的任意本地进程启动，与「配置只控制传输」和「唯一副作用出口」**不能同时为真** | ①保留配置 `command` ②在配置里加路径白名单（白名单仍由配置给，可被一次编辑放宽） |
| 24 | **子进程环境用白名单构造，绝不继承 `os.environ`**（2026-09-26，审查第 2 项） | `Popen` 默认继承整个环境 ⇒ 原稿的「不得注入凭据」与默认行为**恰好相反** | 「审计一行日志说明我们没主动注入」（凭据仍被继承） |
| 25 | **超时即作废协议流并终止进程**（2026-09-26，审查第 4 项） | 迟到帧会在下一次调用被读到 ⇒ 一次超时**必然**污染后续调用，且症状与病因在事件面上无法对应 | ①超时后继续复用流 ②超时后读到 id 不匹配就丢弃该帧（迟到帧无法可靠丢弃，§5.3a） |
| 26 | **帧结构按方法区分 + 版本闭集 + `id` 对应规则**（2026-09-26，审查第 5 项） | 原稿把「`result.content` 缺失」一律判违规 ⇒ **正常握手在 `initialize` 就红**（`content` 只属于 `tools/call`） | ①一套形状通吃三个方法 ②不校验版本，收到什么用什么 |
| 27 | **显示净化落在 `ResponseBuilder`（唯一实现点），作用域为所有工具结果**（2026-09-26） | 防 ANSI/OSC 终端注入；P7b 引入第一类刻意不可信的外部文本 | ①只在适配器出口净化（漏掉内置工具）②静默截断（不可见） |
| 28 | **「外部 provider = 受信任的已安装代码」，FR3 对任意第三方 provider 尚未满足，照实登记**（2026-09-26） | 裁决 6 收紧了**声明**，不构成**沙箱**；不得把「声明收进代码」说成「插件安全已解决」 | 「argv 在代码里 ⇒ 进程安全」 |
| 29 | **不靠字符黑名单挡注入：E17 只禁 NUL / CR / LF / 空串**（2026-09-26 二次修订，老板复审） | `shell=False` + argv 数组 + argv 由代码签发已**结构性**消灭 shell 注入；再加字符禁令**没有安全收益**，却会误伤合法路径（安装目录含 `&`），且与本契约自己的验收臂（P10 ⑥ 用 `;`/`\|` 证明未被解释）**互相否定** | ①继续禁 `;` `\|` `&`（则 P10 ⑥ 跑不起来，两条规则只能活一条）②靠转义而非 argv 数组 |

---

## 13. 同步清单

> **分工口径（CLAUDE.md）**：`specs/modules/00-*.md` 工程契约**归 Codex 主导、Claude 审查**，故它们的**工程落地**一律列在 §13.2。两处例外归 Claude 侧（§13.1），且**同一文件可在两表各出现一次、各改各的层**：
> - `00-core-interfaces.md` 的**接口签名**（新增类型、字段增删、方法签名）——CLAUDE.md 明文归 Claude 主导；
> - `00-error-contract.md` 的**值域闭集**（本契约 §7 的 reason **十三**值与注册期 reason 子集）——属安全边界裁定，Claude 已落定文本；该文件其余内容与 `src/` 侧常量、映射函数位置等工程细节仍由 Codex 负责（§13.2 同列此文件）。

### 13.1 Claude 侧（本契约的连带修改）

| 文件 | 改动 |
|------|------|
| `CLAUDE.md` | 必读表新增 `17-p7b-mcp-qwenpaw-tool-ecosystem.md`（P7b 编码前必读） |
| `requirements.md` | 补 P7b 的功能需求（工具生态接入底座、外部工具的权威归属、首批工具）与非功能约束（**不新增网络或文件目标面**、事件闭集不变）；**2026-09-26 修订**：FR9 补裁决 6（argv 由代码签发）、环境白名单、`close()`/`shutdown()` 生命周期、超时作废协议流、帧结构逐方法、显示净化，以及 FR3 对任意第三方 provider 未满足的据实登记；删去「零新外发面」与「QwenPaw 已接入」口径 |
| `project-report.md` | §九 P7b 行回填为 MCP stdio 工具生态接入底座；QwenPaw 原生适配保留为可选后端接入点。**2026-09-26 修订**：P7b 行删去「零新外发面」与「三项零变更」，补裁决 6 / 环境白名单 / 生命周期 / FR3 未满足的登记 |
| `specs/modules/00-core-interfaces.md` | `ToolDef` 字段表加 `egress`；新增 `ToolProvider` 与三个新类型；**2026-09-26**：`ToolBackend` 加 `close()` 默认实现（§2.4）。**属接口签名级变更，故归 Claude 侧**（CLAUDE.md：接口签名由 Claude 主导）；Codex 可调整文件位置/命名/注释等实现细节 |
| `specs/modules/00-error-contract.md` | `TOOL_EXEC_ERROR.details.reason` 闭集从八值扩到**十三**值（2026-09-26 增 `provider_unsupported_content`）、`CONFIG_ERROR` 新增 P7b reason 子集——**Claude 已按本契约 §7 落定裁定文本**；该文件归 Codex 主导，Codex 负责镜像并补齐本契约未列出的工程细节（`src/` 侧错误码常量、映射函数位置） |
| `specs/modules/04-p3-safety-hardening.md` | §23 / 第 424 行补一句：ToolGuard L2 的论证已在本契约完成，结论 = 延后 + 触发条件（§11 第 2 项） |
| `specs/modules/07-p6a-observability-cli.md` | 配置节补 `[tool_providers]`（**三键，无 `command`**）；`07:361` 的「即插即用」在此得到兑现（补指向）。**2026-09-26 修订**：该处「`ToolBackend` 接口零改动」的说法按 §2.4 改为**一项必要变更**（新增 `close()`），并补 `App.shutdown()` 在 CLI `finally` 中调用的要求 |
| `specs/modules/08-p6b-evaluation-loop.md` | 场景清单 18→19（新增 **S19**）、变体 `mcp_on`/`mcp_off`、`run_meta` variant 枚举与 `config_snapshot` 含 provider 集合、§6 新增「工具生态接入区」（含「报告不得出现任何工具结果的值」这条回归防护）、§8.1 运行器测试补 S19 用例。**2026-09-26 收回**：`{{PROJECT_ROOT}}`/`{{PYTHON}}` 两个渲染占位符**不再需要**（命令已挪进代码，§9.3），§3.5 与修订 15 ⑤ 需按此改写 |
| `specs/modules/15-tool-orchestration-hardening.md` | `ToolDef` 表补 `egress`（与 `audit_redact_all_params` 同族标记） |
| `specs/modules/16-p7-practical-tools-capability-routing.md` | §11 第 4 项状态回填（「已由 17 回答」）、第 22 项标注「已在 17 §2.3 兑现」 |
| `specs/progress-summary.md` | P7b 立项 |
| `specs/clarifications.md` | 关闭 P7b 相关的咨询项，保留决策记录 |

### 13.2 Codex 侧（工程契约镜像）

| 文件 | 改动 |
|------|------|
| `specs/modules/00-project-scaffold.md` | `mcp_demo_server.py` 的位置与脚本约定；**新增 `src/tools/provider_declarations.py`**（§5.2 / §2.2 的落点，2026-09-26 裁决 6 引入）与 `src/adapters/mcp_adapter.py` 的目录行；`qwenpaw_adapter.py` 的 P6/P7 口径不一致（scaffold 写 "P6"、project-plan 写 "P7"）——**照实统一**并注明延后理由 |
| `specs/modules/00-adapter-factory.md` | 配置样例加 `[tool_providers.demo]`；工厂签名的 provider 装配 |
| `specs/modules/00-error-contract.md` | **复核** Claude 已按 §7 落定的值域闭集文本（**十三**值 reason + 注册期 reason 子集，2026-09-26 由十二值扩张），并补齐工程细节：`src/` 侧的常量定义、`Result` 构造点、错误映射函数位置 |
| `config/default.toml` | 无 `[tool_providers]` 节（零外部来源） |
| `config/mcp.example.toml` | **新增**可跑样例（三键：`enabled` + 两个超时；**无 `command`**，出现即 CONFIG_ERROR） |
| `config/eval.example.toml` | provider 节（三键；**无占位符**——命令已挪进 `src/tools/provider_declarations.py`，见 §9.3） |
| `scenarios/S19_*.toml` | 新增 |

### 13.3 实现顺序（建议）

1. `ToolDef.egress` + E11/E12 + **天气回填** + P7a C15 复跑全绿
2. `ToolCandidate` / `ProviderSnapshot` / `ExternalToolAdmission` + `ToolProvider`（Core，含 `close()` 四语义）
3. `ToolBackend.close()` 默认空实现 + `App.shutdown()` + `CompositeToolBackend.close()` + CLI/eval/脚本的 `finally`（§2.4；**先落生命周期再接进程**，否则第 5 步一开进程就没有回收路径）
4. `ProviderDeclaration` + 准入声明与 E1–**E18** 校验（`src/tools/provider_declarations.py` 与 `src/tools/`）
5. `CompositeToolBackend`：准入过滤、兼容性检查（§5.6 四条）、**出站边**（帧上限、共享秘密检测、错误映射）、诊断快照
6. `MCPStdioToolProvider`：握手 + **版本闭集**、**逐方法帧结构**（§5.4.2）、**id 规则**（§5.4.3）、内容白名单（§5.4.4）、两级超时**即作废协议流**（§5.3a）、**环境白名单**（§5.2）、大小上限、关闭、不自动重启
7. `ResponseBuilder.build()` 的**显示净化**（§5.7；与后端无关，可独立落）
8. `scripts/mcp_demo_server.py`（含 `--fault` 全臂：`late_reply` / `ignore_sigterm` / `bad_version` / `non_text_content` / `ansi_text` / `noisy_stderr` 与 `--dump-env` / `--dump-argv`）
9. `file.stat` + `files.info` 能力
10. `bootstrap` / 配置接线（三键闭集 + E18）+ E3 关态检查 + 启动中途失败的补偿关闭（§9.2 步 7）
11. eval：变体、S19、`config_snapshot`（**无占位符**）
12. 验收矩阵 M0–M7 / P1–P11 / X1–X9 / N1–N5

---

**契约状态：🔧 实现中（见文首状态行）。** 本文件是 P7b 的唯一编码依据；`src/` 的改动范围、接口签名与错误语义以本文件为准。任何偏离（新增字段、放宽闭集、扩大准入面）都必须先回到本文件改契约。
