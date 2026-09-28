# 12-risk-draft-closed-set — risk_draft 闭集与归一化契约

> **状态：✅ 待实现**（2026-09-16 立项，Claude 裁决，Codex 实现）
> **依赖**：`05-p4-cloud-advisory.md`（§1.3 云端准入）、`01-p0a-main-loop.md`（§8.2 风险等级）、`10-p6d-autonomous-escalation.md`（§4.3 可观测性）、`08-p6b-evaluation-loop.md`（§2.5/§2.6 场景口径）、`04-p3-safety-hardening.md`（§4.6/§4.7 dangerous 语义）
>
> 本契约**只**钉死 `IntentCandidate.risk_draft` 的值域、归一化与消费语义。**不新增**模型能力、**不新增**安全机制、**不改变**任何既有不变量（deny_cloud / PrivacyPolicy / CloudBoundary / 出站预览 / 用户 grant / 预算 / 冷却 / 敏感执行链 / 回流后本地重判）。

---

## 0. 问题、根因与裁决

### 0.1 问题（真实运行证据）

S06/S08/S10/S13 的 `/cloud ask` 被拒，统一表现为：

```
cloud_gate_outcome = "vetoed"
proposal_denied_reason = "non_normal_risk"
```

而历史 run 中同一指令能正常产生 `admitted_forced → REQUEST_CLOUD`。**同一个用户显式指令，成功与否取决于模型当天选了什么词**——这是不可接受的不确定性，不是 provider 问题（P6c 不是根因）。

**根因（三层，缺一不可）**：

1. 旧 05 §1.3 把 `risk_draft != "normal"` 列为 **force 也不得绕过**的硬否决项；
2. `_INTENT_RESPONSE_SCHEMA.risk_draft` 只声明 `{"type": "string"}`，**没有值域约束**；
3. `_candidate_from_model_output()` 用 `_string_or_default(...)` 接受**任意字符串**，不校验闭集——契约隐含的 normal/sensitive/dangerous 从未被强制。

模型实际输出过 `low` / `medium` / `high`；这些值在映射前一律落进「非 normal」，于是硬否决生效。

> 注意证据的边界：被拒的取值**只能是 `medium` 或 `high`**（`low` 在本契约与 Codex 建议映射下都归 `normal`，不会触发拒绝）。这一点直接决定 §2.2 的映射裁决。

#### 0.1.1 2026-09-17 新增证据：自主升级臂被同一字段锁死（裁决 A/B 的直接触发）

R1/R2 落地后，`/cloud ask`（force）已恢复稳定，但**无显式指令**的自主升级臂仍全灭——同一形态、另一个后果：

| 场景 / 变体 | run | 观测 |
|---|---|---|
| S09 `base` | `59d7d496c4d1` / `e4300254db56` / `19724e4c4ff5` | 3/3 `READY`、`should_consult=true`、`expected_benefit=0.8`、`escalation_reason=architecture_tradeoff`；**3/3 `risk_draft=sensitive`** → `proposal_gate_result=vetoed` + `proposal_denied_reason=non_normal_risk` → 实际准入 **0/3**（目标 ≥2/3） |
| S06 `cloud_auto` | `58d6e8d607e2` / `27fc2188a3c9` / `c83b66b733d3` | 同形，`escalation_reason=reasoning_complexity`，实际准入 **0/3**（目标 ≥2/3） |

**读法（必须说清，否则会误修）**：

1. **P6d 的提议校准是好的**——`should_consult`、`expected_benefit`、`escalation_reason` 三项 3/3 正确，说明「该不该建议云端」这一层没问题；
2. **失败在风险语义与准入的交界**：模型把**只读的开放式分析题**判成了 `sensitive`（不是 `dangerous`，所以不是 13 的收窄问题），而准入层又拿这个值做否决；
3. 因此**不得**按「模型不会建议云端」处理（现象不是这个），**也不得**调低 `expected_benefit` 阈值（阈值不是原因，3/3 都过了阈值）；
4. 修法有两条且都要做：**R5**（模型侧的判定对象——纯分析题不该判 `sensitive`，§1.2.1）与 **R6**（确定性的准入与授权——即便模型仍判 `sensitive`，链路也不被锁死，§3.4）。只做 R5 会让链路继续依赖模型当天选什么词；只做 R6 会让「话题重要 = 敏感」这个错误语义长期留在数据里。

### 0.2 裁决（六条：R1–R4 于 2026-09-16 立项，R5/R6 于 2026-09-17 依 S06/S09 真实 run 追加）

| # | 裁决 | 落点 |
|---|---|---|
| **R1** | `risk_draft` 值域钉死为闭集 `{normal, sensitive, dangerous}`；**归一化是进入 Core 的唯一入口**，闭集外的值不得以原样进入 `ControlPolicy` / `TaskPlanner` / `GuardedToolExecutor` | §1、§2 |
| **R2** | `risk_draft` 是**模型断言**，不是确定性安全事实——它**不得**成为任何路径的云端开关。2026-09-17 起**完全移出否决集**：force 与 proposal 均不因该字段否决；`sensitive` 的保守表达改由**强制用户授权**承担（R6），不再由否决承担 | §3 |
| **R3** | `dangerous → REFUSE` **保留**（最高优先级、force 不可绕过）——它是 fail-safe 硬锁定：只可能多拒，不可能放行 | §3.1 |
| **R4** | 消费方**只读闭集**：ControlPolicy 不做归一化，但必须对任意输入有定义——闭集外值按 §2.1.1（危险方向宽容 → `REFUSE`；其余 → `sensitive`），**任何情况下不得退化为 `normal`** | §2.1.1 |
| **R5** | **判定对象钉死（2026-09-17，裁决 A）**：`risk_draft` 判的是**本回合实际请求的动作**——不是分析文本里讨论到的假设操作，不是目标系统的重要性或潜在影响。只读分析 / 排查建议 / 架构权衡 / 迁移规划 / 回滚方案设计**默认 `normal`**；`sensitive` 的**充分条件**是本回合实际含敏感数据，或本回合实际请求具有破坏性/不可逆/外发性质的副作用（工作区内**新建**文件不属此列——本字段是意图层风险，**不复制工具层的确定性风险**，见 §1.2 表注。**2026-09-20 补**：「会不会进确认链」是执行层事实，**不是**本条件的判据——P7a-0 后所有工作区写入都确认，而新建仍为 `normal`） | §1.2.1、§1.3 |
| **R6** | **`sensitive` 不再阻止提出云端建议，只禁止未经确认的外发（2026-09-17，裁决 B）**：`sensitive` 提案可准入 `REQUEST_CLOUD`，但该动作只能产出脱敏准备与**最终授权 preview**（无网络请求）；在**所有**隐私模式（**含 `convenient`**）下必须进 `AWAITING_AUTHORIZATION`，只认显式 `/cloud allow` 签发的用户 grant——**不得** policy grant，**不得**复用旧任务/旧 grant 的授权。**安全闭环（同日补钉）**：决定授权形态的不是模型自评本身，而是**有效授权风险** = `max(模型下界, 确定性升险结果)`——确定性信号只能升险、信号缺失即 `sensitive`（§3.5），否则本条款只是「确定性地传递模型结论」 | §3.2、§3.4、§3.5 |

**为什么 R2 是安全上成立的、而不是安全降级**（这段是本次裁决的核心论证，审查时逐条核对）：

1. **模型可控的字段不构成安全边界**。模型只要说 `normal` 就能通过旧否决项——一个被否决方自己就能绕过的检查，提供的不是安全，而是随机性。这与 2026-09-14 把 `suggested_tools` 移出 force 否决集是**同一类问题的同一个结论**。
2. **force 路径的保护是确定性的、且比任何模型措辞更强**：`deny_cloud` 最高优先级否决 → PrivacyPolicy 分类/脱敏/允许表 → **`AWAITING_AUTHORIZATION` 展示最终 payload** → 用户显式 grant → CloudBoundary 独立复核 → 唯一出口 → 预算/冷却。用户按下 `/cloud ask` 后**仍必须**在看过最终 payload 后点 `/cloud allow`。
3. **「敏感执行链」的确定性否决另有承担者**：`CloudControlState.task_has_sensitive_execution_chain`（App 确定性状态，非模型输出）保留在不可绕过否决集内。让 `risk_draft == "sensitive"` 再否决一次，是**模糊信号与确定性状态重复否决**——重复的那一份只会带来波动，不带来保护。
4. **R3 保留 dangerous 不产生同类问题**：它只能把请求推向「拒绝」，不能放行任何东西。
5. **R6 把 `sensitive` 的保守性从「否决」挪到「授权」，安全强度不降（2026-09-17）**：旧做法（`sensitive` 提案一律不升级）在模型把**纯分析题**误判为 `sensitive` 时，会把「强模型补足小模型」的路径整体锁死——真实 run 证据：S09（`base`）3/3 `risk_draft=sensitive` → `vetoed` + `non_normal_risk`、S06（`cloud_auto`）3/3 同形，自主升级 **0/3**（目标 ≥2/3）。新做法把同一份保守性表达为**强制用户授权**：链路可以走到 `REQUEST_CLOUD`，但 `outbound` 之前必须有**用户显式 grant**，且该 grant 只能由用户确认签发（`convenient` 也不例外）。外发仍必须过用户这一关，因此**没有放宽任何外发边界**；变的是「模型措辞能否决定链路走不走得下去」。
6. **R5 与 R6 是两条独立的修法，缺一不可**：R5 修**模型侧的判定对象**（纯分析题不该被判 `sensitive`），R6 修**确定性的准入与授权语义**（即使模型仍判 `sensitive`，链路也不被锁死）。R5 是提示词层面的收敛，其效果按观测口径看（不写成必过断言）；R6 是契约层面的硬规则，可按验收矩阵逐条断言。

### 0.3 边界声明（必须写清，防止实现侧把 schema 当防线）

`02-p1-ollama-backend.md` §3 的 `format="json"` **基线只保证合法 JSON，不保证 schema 一致**（该模式下 `supports_structured_output=False`）。因此：

> **schema 的 `enum` 是提示级约束（必要条件），闭集的强制点只能是解析层（充分条件）。**
> 任何以「schema 已经限制取值了」为理由省略 §2 归一化的实现，都属于违约。

**同理，`required` 也不保证字段存在**：schema 不被保证一致时，「字段缺失」与「字段是乱码」都是可能的模型输出，两者在语义上等价（模型没有给出可用断言）。因此 §2.2 把两者兜底到**同一档**（`sensitive`），而不是让缺失走「最低风险」通道——这是本契约自洽性的必要条件，不是保守偏好。

---

## 1. 闭集与语义

### 1.1 值域

```
RISK_LEVELS = ("normal", "sensitive", "dangerous")     # 小写，规范化后的唯一合法取值
```

`IntentCandidate.risk_draft` 在离开解析层后**必然**属于该闭集。这是后续所有消费方（ControlPolicy 三分档、TaskPlanner `risk_level`、GuardedToolExecutor `_effective_risk`、`_is_conditionally_answerable`）可以无条件依赖的前提。

### 1.2 三值语义（同时是提示词的规则文本）

| 值 | 含义（**只**表达这一件事，判定对象见 §1.2.1） | 本地执行档 | proposal 自动路径 | force 路径 |
|---|---|---|---|---|
| `normal` | 本回合请求的动作**既不含敏感数据、也不含需确认的副作用**（含只读分析、排查建议、架构权衡、迁移规划、回滚设计；工作区内**新建**文件见下注） | 直接进入计划 | 可准入 | 可上云 |
| `sensitive` | 本回合实际（a）**含**凭据/隐私数据，或（b）**请求**需要用户确认的副作用（**覆盖**已有文件、外部发送、系统修改等） | `PLAN_LOCAL` + 需确认 | **可准入**，但必须走**强制用户授权**（§3.2/§3.4）——不得 policy grant | 可上云（须过预览与 grant） |
| `dangerous` | **越权**（超出授权范围）、**恶意**、**规避安全控制**，或**无法形成有界目标**的明确破坏行为 | **`REFUSE`** | 不参与（模型**不得**为之提出上云建议） | **`REFUSE`** |

> **注（2026-09-17，与 `07-p6a-observability-cli.md` §6.1 对齐）：本字段是「意图层」风险，不复制工具的动态风险。** 工作区内**新建**文件（无覆盖、无路径逃逸）~~在工具注册表里就是 `risk_level="normal"`（07 §6.1）~~，故本回合「请求写一个新文件」**不**构成充分条件 (b)，判 `normal`；**⚠️ 2026-09-20 追注（P7a-0）**：划掉的那个**前提**已反转（注册表基线改为 `sensitive`、写操作一律确认），但**这一步的结论不变**——`risk_draft` 判的是**请求语义**（是否破坏性/不可逆/外发），**不表达「会不会被确认」**；判 `normal` 不会让工具层放宽（只升不降）。理由见 §9 末行。**覆盖已有文件**由 `preflight`（07 §6.3）确定性升险，**路径逃逸**由 preflight 判 `effective_risk="dangerous"`（§1.1 反向边界），二者都**只升不降**。因此「文件写入」只能作为**举例**保留在提示词里并注明这一分工，不得被理解为「凡 write 皆 `sensitive`」。~~否则 S14「新建无需确认」的验收口径立刻自相矛盾。~~ **2026-09-20 追注（P7a-0）**：划掉的那句所依据的验收口径已反转（新建**现在也确认**），但它**不构成**支持「凡 write 皆 `sensitive`」的理由——反转的是**工具层的确认策略**，不是本字段的判据；两者判据不同（前者「模型选得对不对」，后者「请求本身危不危险」），因此这里对提示词的约束**继续有效**。

> **`dangerous` 的定义于 2026-09-16 收窄**（规范见 `13-approval-profile-high-impact.md` §1）。收窄前的措辞「明确的破坏性 / 不可逆 / 越权意图」把「越权/恶意」与「**合法但高影响**」（生产迁移、线上切流、明确范围的批量操作）混为一类，使后者吃 `REFUSE` 这条**无补救路径**的死路。收窄后的边界：
>
> - **是** `dangerous`：越权 / 恶意 / 规避安全控制 / **无法形成有界目标**的破坏行为；
> - **不是** `dangerous`：任务**重要 / 关键 / 影响面大 / 涉及生产环境 / 规模大 / 复杂 / 篇幅长 / 模型自信程度高低**——合法且有界的此类意图归 `sensitive`；合法但无界的归 `sensitive`，其执行风险由 `approval_profile`（13 §2/§3）承接，**不**由本字段承接。
>
> **收窄只作用于模型措辞，不作用于确定性事实**：`preflight` 对工作区逃逸返回 `effective_risk="dangerous"` 属「越权」，恰好落在收窄后的定义内，保持不变（§2.4 反向边界）。闭集、归一化规则、消费语义、`REFUSE` 最高优先级**全部零改动**。

**禁止的语义扩张（必须写进提示词）**：`risk_draft` 表达的是「意图是否触及敏感/危险操作」，**不表达**任务难度、重要性、篇幅、影响面或模型的自信程度。

> 这条不是空泛提醒：真实 run 中模型正是把「开放式分析题（P99 延迟根因 / 架构选型）」标成 `high`。复杂度不是风险，这个混淆是本次 bug 的直接成因。

#### 1.2.1 判定对象：本回合**实际请求的动作**（2026-09-17 裁决 A）

上面的混淆还有一个未被前面的裁决覆盖的变体：模型不再按「难度」判，改为按**话题的重要性**判——看到「生产环境 / 线上切流 / 数据库 / 部署」就把整轮标成 `sensitive`。这同样是错的，同样会让纯分析题进不了自主升级路径（真实 run：S09 `base` 3/3、S06 `cloud_auto` 3/3 `risk_draft=sensitive`，两条自主升级臂 **0/3**）。因此把判定对象钉死：

> **`risk_draft` 判的是「本回合实际请求的动作」，不是分析文本里讨论到的假设操作，也不是目标系统的重要性或潜在影响。**

| 情形 | 判定 | 理由 |
|---|---|---|
| 只读分析 / 故障排查建议 / 架构权衡 / 迁移规划 / 回滚方案设计——即使话题涉及生产、切流、数据库、部署或高影响系统 | **`normal`** | 本回合**没有请求**任何工具执行、文件写入、系统修改或外部数据发送，输入里也**没有**凭据或隐私数据。「聊到」不等于「要做」 |
| 本回合**实际请求**执行迁移 / 修改线上配置 / 覆盖已有文件 / 外部发送 | **`sensitive`** | 这是同一话题的**动作版**——请求了需要用户确认的副作用（对照例） |
| 本回合请求在工作区内**新建**一个文件（不覆盖、不越界） | **`normal`** | 本字段判的是**请求本身的语义**：在工作区内建一个新文件不是破坏性、不可逆或外发动作。**2026-09-20 后它照样要经用户确认**（`07` §6.1 注册表基线 `normal → sensitive`，P7a-0），但那是**执行层对「模型可能选错工具/参数」的防线**，不是意图层风险——本字段**不复制**工具层的确定性风险，**也不表达**「是否会被确认」 |
| 本回合输入**实际含**凭据、密钥或隐私数据（哪怕只是让模型看一眼） | **`sensitive`** | ①：数据本身敏感，与是否执行无关 |
| （同上两行之外）任务重要 / 关键 / 影响面大 / 规模大 / 复杂 / 篇幅长 / 模型不自信 | **不改变判定** | 这些都不是风险信号（§1.2 禁止的语义扩张；合法但有界的高影响**执行**由 `approval_profile` 承接，见 `13-approval-profile-high-impact.md`，**不由本字段表达**） |

**`sensitive` 的两个充分条件（满足任一即 `sensitive`）**：① 本回合实际**含**敏感数据（凭据/密钥/隐私数据）；② 本回合实际**请求**具有破坏性、不可逆或外发性质的副作用（**覆盖**已有文件 / 外部发送 / 系统修改等）；工作区内**新建**文件不属此列，见上表注释。**2026-09-20 澄清**：条件 ② 的判据是**请求语义**，不是「会不会进确认链」——P7a-0 之后所有工作区写入都要确认（`07` §6.1），但「要确认」是执行层对**工具/参数选择不确定性**的防线，**不得**回灌成意图层 `sensitive`；两层各自只升不降，谁都不需要另一层同意。**除此之外不做保守推定**——把「聊到高影响系统」推成 `sensitive` 不是保守，是把本字段当成第二个 `approval_profile`（13 §1.3 已划定分工）。

**正例（本项目的真实场景）**：`scenarios/S06*.toml` 与 `S09*.toml` 的 base 任务都是**开放式分析题**（S09 的 `escalation_reason=architecture_tradeoff`、S06 的 `reasoning_complexity`），本回合只要求分析、不要求执行，且输入不含凭据 → **`risk_draft=normal` + `should_consult=true`**，应正常进入 `admitted_proposal`。

**对照例（构造用例，不改场景文本）**：同样的话题，但本回合请求「执行这次迁移 / 改这份线上配置 / **覆盖**这个已存在的文件」→ **`sensitive`**。它落进 R6 的强制用户授权路径，**不再**被否决。反例（同属「写文件」但不是 `sensitive`）：本回合请求在工作区内**新建**一个文件 → `normal`（§1.2 注；**2026-09-20 后它仍会被要求确认**，那是工具层的 `requires_confirmation`，与本字段取值互不推导）。

**`dangerous` 侧的禁令**：本回合请求的动作若属 `dangerous`（越权/恶意/规避安全控制/无界破坏），模型**不得**对它提出上云建议（`should_consult` 必须为 `false`）——`dangerous` 在 `decide()` 第 1 步即 `REFUSE`，建议一个必然被拒的升级是噪声，且会被读成「系统在考虑危险操作」。

### 1.3 提示词新增要求（`_build_prompt`）

在既有提示词后追加（规则文本，不依赖模型输出，按 10 §7.1 第 16 项的断言方式测试）：

1. `risk_draft` 的合法取值**只有** `normal` / `sensitive` / `dangerous` 三个，逐字输出，不得使用其它词表（明确点名禁止 `low` / `medium` / `high` / `critical` / 中文等级词）；
2. 三个值的定义（照抄 §1.2 的「含义」列）；
3. 「不确定时输出 `sensitive`」（fail-closed 的模型侧表达，与 §2.2 的兜底一致）。**限定语必须一并写进提示词**：不确定指的是「这一轮到底有没有真的请求副作用 / 有没有真的含敏感数据」；「话题本身听起来重要、复杂或影响面大」**不是**不确定，是无关信号，按第 6 条判；
4. 「任务复杂 / 篇幅长 / 你觉得重要，都**不是**非 `normal` 的理由」；
5. `dangerous` 是硬锁定：**仅在确有把握**是破坏性、不可逆或越权操作时使用；
6. **判定对象（2026-09-17 裁决 A，逐字写进提示词）**：「这个字段判的是**这一轮实际请求的动作**，不是你在分析里讨论到的假设操作，也不是目标系统的重要性。只是分析、排查、比较方案、规划或设计回滚方案——**即使话题是生产环境、线上切流、数据库或部署**——只要这一轮没有要求执行任何操作、也没有把凭据或隐私数据交给系统，就是 `normal`」；
7. **`sensitive` 的两个充分条件**：「这一轮**实际含**凭据、密钥或隐私数据；或这一轮**实际请求**具有破坏性、不可逆或外发性质的副作用（**覆盖**已有文件、外部发送、系统修改）。满足任一即 `sensitive`，**此外不做保守推定**。在工作区内**新建**文件属于 `normal`——你**不需要也做不到**用这个字段表达「执行时要不要用户确认」，那由本地确定性预检决定，与你的取值互不影响；覆盖与路径越界同样由本地预检只升不降，不由你表达」；
8. **`dangerous` 时不得建议上云**：「若这一轮请求的动作是 `dangerous`，`should_consult` 必须为 `false`」（与 §1.2.1 末段一致）。

---

## 2. 解析边界：归一化（唯一实现）

### 2.1 唯一实现

新增纯函数（无 IO、无依赖、不读配置、不调用模型）：

```python
def normalize_risk_draft(raw: object) -> tuple[str, str]:
    """返回 (归一化后的 risk_draft, resolution)。唯一实现，禁止在别处再写一份映射。"""
```

**落点（Codex 属地，位置与命名可调，但必须单一）**：`src/core/risk_vocabulary.py`（无依赖模块，`src/core/*` 与 `src/safety/*` 均可 import）。`RISK_LEVELS` 与 `LEGACY_RISK_MAP` 常量与函数**同处一模块**。

**调用点（穷举）**：

| 调用点 | 位置 | 作用 |
|---|---|---|
| 解析边界（**唯一产出点**） | `intent_resolver._candidate_from_model_output()` | 填充 `IntentCandidate.risk_draft` / `.risk_draft_resolution` |
| 防御性消费 | `control_policy`（`_is_dangerous` / 准入 / 分档 / `_is_conditionally_answerable`） | **只读闭集值**；闭集外值按 §2.1.1 的总量规则处理，**不得按 `normal`** |
| 防御性消费 | `guarded_executor._effective_risk()` | `_RISK_ORDER.get(..., default)` 的 default 改为 `sensitive`（现为 `0` = `normal`，是 fail-open 兜底），见 01 §8.2 |

**默认值语义（防止误读）**：数据类默认（`risk_draft="normal"`、`risk_draft_resolution="declared"`）服务的是**本地代码构造的候选**（App 合成、mock、测试替身）——可信来源。`resolution` 由解析层产生，消费方不得改写。

#### 2.1.1 消费层的总量规则（ControlPolicy 如何读闭集外值）

ControlPolicy **不做归一化**（归一化只在解析层做）。它只读闭集，且必须对**任意**输入有定义：

| 输入 | 行为 | 理由 |
|---|---|---|
| 闭集三值 | 按 §1.2 语义 | 正常路径 |
| **`strip().lower() == "dangerous"` 的闭集外写法**（`"DANGEROUS"` / `" dangerous "`） | 按 `dangerous`（`REFUSE`） | **危险方向的方向性宽容**：这不是第二份映射表（只影响 `dangerous` 一个 token 的识别，不产生任何 `normal`/`sensitive` 映射），而是「识别危险必须宽容」——把 `"DANGEROUS"` 降级为 `sensitive` 是安全维度上的 fail-open，且相对现状（`_is_dangerous` 今日已做 `.lower()`）是**行为倒退**，会造成「修 bug 顺手削弱了一处安全检查」 |
| 其余闭集外值（`"high"` / `"critical"` / `None` / `42` …） | 按 `sensitive` | fail-closed 到保守档；与 §2.4 同一逻辑：模型/调用方**什么也没断言** |

**与 §2.4 不冲突**：区分点在「是否是可识别的 `dangerous` 同一 token 的写法变形」。`"DANGEROUS"` 断言的就是危险（只是大小写不同）→ 宽容为拒绝；`"critical"` / 缺失 / 乱码什么也没断言 → 兜底为保守档。两个方向都朝安全侧。

**可达性**：正常链路上闭集外值**不可达**（解析层是模型侧 `IntentCandidate` 的唯一产出点）。此规则是给「绕过解析层的第二条构造路径」的防御；未来若新增任何从外部输入构造 `IntentCandidate` 的适配器，**必须**先过 `normalize_risk_draft()`——这是接口层义务（§5）。

> **实现归属（2026-09-16 代码审查补）**：本表是**一条规则**，必须只有**一份实现**。已出现的分工是 `control_policy._risk_for_policy()`（返回档位名）与 `guarded_executor._risk_value()`（返回排序值，当前把未知值映射为 `sensitive`）——两份手写渲染，语义上已出现分叉：同一输入 `" DANGEROUS "` 在前者得 `dangerous`、在后者得 `sensitive`。今天不可达（`ExecutionStep.risk_level` 只来自解析层归一化字段与注册表/预检的闭集值），但这是**同类 fail-open 的入口**。要求：本表实现**下沉到 `risk_vocabulary.py`**（如 `read_risk(raw) -> str`），消费方一律 `import` 同一函数，任何消费方**不得**再手写 `.lower()`/`strip()`/`in RISK_LEVELS` 判断。契约层对应的机检义务见 §4.3。

### 2.2 归一化规则（有序，命中即返回）

| 步 | 条件 | 归一化结果 | `resolution` |
|---|---|---|---|
| 1 | 字段缺失、非字符串（`None` / number / list / dict…）、或 `strip()` 后为空 | `sensitive` | `absent` |
| 2 | `raw.strip().lower()` 命中 `RISK_LEVELS` | 该值 | `declared` |
| 3 | 命中 `LEGACY_RISK_MAP`（闭表 3 条，见下） | 映射值 | `mapped_legacy` |
| 4 | 其余（**非空但不可识别**） | `sensitive` | `unrecognized` |

```
LEGACY_RISK_MAP = {"low": "normal", "medium": "sensitive", "high": "sensitive"}
```

**`resolution` 是受限枚举，4 值**：`declared` / `mapped_legacy` / `absent` / `unrecognized`。

**满足率与不变式**：规则 1–4 对**任意** `object` 有定义（函数是总量的），且 `risk_draft ∈ RISK_LEVELS` 恒成立。

> **缺失值归 `sensitive` 而不是 `normal`（2026-09-16 二轮修正，采纳 Codex 审查）**：§0.3 已声明「`format="json"` 基线不保证 schema 一致」——那么 schema 的 `required` **就不能**当作「字段存在」的保证。于是「字段缺失」与「字段是乱码」在认识论上是**同一件事**：模型**没有给出可用的风险断言**。把前者兜底为 `normal`、后者兜底为 `sensitive`，是同一个 fail-open 的双标（原写法即有此矛盾），已废除。
>
> **代价与可见性（照实写）**：若某模型/后端系统性漏字段，本地执行会普遍要求确认、proposal 自动升级会普遍退出。这是保守方向的代价，且 `risk_draft_resolution=absent` 的分布会在报告里直接暴露（§3.3）——据此修提示词/schema，而不是靠放宽兜底把问题藏起来。
>
> **数据类默认值不受影响**：`IntentCandidate` 的数据类默认（`risk_draft="normal"`、`risk_draft_resolution="declared"`）服务的是**本地代码构造的候选**（App 合成、mock、测试替身）——那是可信来源，不是模型输出。**解析层从不因字段缺失产出 `normal`**，因此「模型不写 = 最低风险」这条通道在模型侧根本不存在。

### 2.3 裁决：`high` → `sensitive`（**不采纳** Codex 建议的 `high/critical → dangerous`）

理由两条，任一独立成立：

1. **经验证据（决定性）**：真实 run 中触发本次 bug 的取值只能是 `medium` 或 `high`（§0.1），而这些取值出现在 S06/S08/S10/S13 这类**开放式分析题**上——模型用 `high` 表达的是「这题很重要/很复杂」，不是「这是危险意图」。若 `high → dangerous`，则**恰好是本次要修复的四个场景**会被硬拒绝（`REFUSE`，无任何补救路径），把「随机拦截」换成「确定性拒绝」，目标（恢复 `/cloud ask` 稳定可用）直接落空。
2. **安全论证**：`dangerous` 是产品级硬锁定（04 §4.6：P3 起永不可执行，「解锁留待后续阶段」）。把一个**外来/旧词表**的 token 提升为硬锁定，是对该 token 的语义过度主张；而它带来的安全收益为零（该字段本身可被模型绕开，§0.2 第 1 条），代价却是不可恢复的。

### 2.4 裁决：未识别 → `sensitive`（**不采纳** Codex 建议的 `→ dangerous`）

| 候选兜底 | 采纳 | 理由 |
|---|:---:|---|
| `normal` | ✗ | 明确的 fail-open：非法措辞获得「无需确认 + 可自动升级」的最高档资格 |
| `sensitive` | **✓** | fail-closed 到**保守档**：本地执行需确认、proposal 自动路径不参与。安全上已覆盖，且不制造不可恢复的拒绝 |
| `dangerous` | ✗ | ① `dangerous` 是「模型断言此意图危险」的语义，**解析失败什么也没断言**，把「看不懂」洗成「危险」是语义捏造；② 04 §4.6 的硬锁定不允许「无用户补救路径」的拒绝由一次解析抖动触发；③ 与既有解析层惯例相反——`_candidate_from_model_output` 的既有兜底一律降到**最不承诺**的那一档（非法 `state` → `VAGUE`、非法 `model_confidence` → `0.0`、非法 `escalation_reason` → `unknown`），`dangerous` 不是「最不承诺」，是「最强断言」 |

> **`dangerous` 在解析层的唯一来源**：模型显式声明（`declared`）。**不得**由缺失、格式错误或未识别值构造。
>
> **范围限定（2026-09-16 代码审查补）**：本条只约束**模型产出的 `risk_draft` 归一化层**，不是「`dangerous` 全系统只能由模型说出」。另有一条**确定性**的合法来源：工具层 `preflight`（07 §6.3）对工作区逃逸等确定性事实返回 `effective_risk="dangerous"`，那是 fail-safe 硬锁定，**不受本条限制、也不得**被本节任何兜底口径放宽。两句话的边界：**模型措辞不得把风险抬到硬锁定**（本条），**确定性事实必须能抬到硬锁定**（07 §6.3）。
>
> **与 13 的关系（2026-09-16）**：`13-approval-profile-high-impact.md` 收窄 `dangerous` 的**语义**（§1.2），不改本条的**来源规则**。两者叠加后的完整口径：`dangerous` 仍只能由「模型显式声明」或「确定性 preflight」产生；收窄只是让模型**更少**把合法高影响意图声明为 `dangerous`，确定性来源一条未动（13 §1.3 有对应机检）。

### 2.5 明确**不做**的匹配

不做模糊匹配、子串匹配、前缀匹配、正则猜测、中文等级词表。以下一律 `unrecognized → sensitive`：

`"medium-high"`、`"normal-ish"`、`"not normal"`、`"非 normal"`、`"低"`、`"很高"`、`"moderate"`、`"critical"`、`"low_risk"`、`" risk: high "`

理由：① 不可测试（没有闭表就没有确定性断言）；② 别名猜测会把 `"not normal"` 这类**否定式**猜成低风险，是真 fail-open；③ `critical` **不**追加进映射表——它未被观察到，为一个未被观察的 token 引入一条未测试的取值路径，与「闭表 + 可测试」的目标相反。若真实 run 观察到 `critical`，按 §4 的证据流程决定是否入表（入表也要有同一个 run 的证据，不得凭语义直觉加）。

---

## 3. 消费语义（三处，逐一钉死）

### 3.1 本地档（`ControlPolicy.decide()` 第 1 步与 `_decide_ready()`）——**语义不变**

| 归一化值 | 行为 |
|---|---|
| `dangerous` | `REFUSE`（最高优先级，最高优先于轮数上限与云端准入；**不变**） |
| `normal` | 既有置信度梯子（`PLAN_LOCAL` 无确认） |
| `sensitive` | 既有梯子 + `requires_user_confirmation=True` |

`_is_conditionally_answerable()`（10 §3.3）仍要求 `risk_draft == "normal"`——`sensitive`（含 `mapped_legacy` / `absent` / `unrecognized`）不参与条件化回答，走 `ASK_USER`。保守方向，不变。

> **本节的比较规则**：`risk_draft` 是闭集值，比较一律**对闭集精确比较** + §2.1.1 的方向性宽容（危险方向）。修法**不是**在 ControlPolicy 里补 `strip()`——现状「`_is_dangerous` 只 `.lower()` 不 `strip()`」与「其余分支直读字符串」的双标，正是「归一化没有单一归属」的症状；解法是把归一化上移到解析层（§2.2），ControlPolicy 退化为闭集读取 + 总量兜底。

### 3.2 云端准入（05 §1.3）——**本次核心修订**

**不可绕过否决集（force 与 proposal 共同适用，force 也不得绕过）**：`deny_cloud` / `dangerous`（防御性重复）/ `task_has_sensitive_execution_chain` / `cloud_enabled|provider_available` / `remaining_turns|cooldown` / force 且空任务。

**`risk_draft` 已完全移出该集合**：2026-09-16 先移出 force（R2），2026-09-17 再移出 proposal（R6，老板裁决）。**两个路径都不再因该字段否决**：

| 路径 | `normal` | `sensitive`（含 `mapped_legacy` / `absent` / `unrecognized`） | `dangerous` |
|---|---|---|---|
| **force**（`/cloud ask`，`has_task_text=True`） | `REQUEST_CLOUD` / `admitted_forced` | `REQUEST_CLOUD` / `admitted_forced` | `REFUSE` / `not_evaluated` |
| **proposal**（模型建议，无显式指令） | 可准入 / `admitted_proposal`，授权按隐私模式（`convenient` 可 policy grant） | **可准入 / `admitted_proposal`，但该动作只能产出脱敏准备与最终授权 preview**——所有模式（**含 `convenient`**）必须进 `AWAITING_AUTHORIZATION`，不得 policy grant、不得复用旧授权（§3.4） | `not_evaluated`（第 1 步早裁；模型亦不得为之建议，§1.2.1 末段） |

**为什么不再用否决表达保守（R2+R6 的合并理由）**：用户显式指令**不被模型措辞锁死**（R2，与 `suggested_tools` 同一非对称处理）；自动升级对 `sensitive` 的保守性**改由强制用户授权承担**（R6）——同一份保守，从「不让你走」改为「让你走到用户面前」。旧做法（`sensitive` 提案一律 `vetoed`）在模型把纯分析题误判为 `sensitive` 时会把自主升级路径整体锁死（S09 `base`、S06 `cloud_auto` 各 3/3 被锁，§0.2 第 5 点）。**R2 与 R6 不冲突也不重复**：R2 说的是「该字段不是安全边界」，R6 说的是「既然不是安全边界，就用真的安全边界（用户授权）来承接保守性」。

> **`non_normal_risk` 的处置（必须实现，不得留残留路径）**：否决项 3 删除后，`proposal_denied_reason == "non_normal_risk"` 在**任何**路径都不可达——`sensitive` 不再否决，`dangerous` 在 `decide()` 第 1 步早裁为 `REFUSE` + `not_evaluated`（`not_evaluated` 的准入内来源**只剩** dangerous 一处）。该枚举值**保留**（删值会牵动 07/08 的封闭集与历史报告的比对口径），但语义改为**保留值 / 不可达防御项**：出现即接线缺陷（残留的否决项 3 未被删净），按实现缺陷处理。验收侧由「force 轮不得出现」升级为**全域禁项**——**任何 run、任何路径都不得出现 `non_normal_risk`**（08 §2.6）。

### 3.3 可观测性（07 §2.2）

`intent_final` **新增 2 键**（受限枚举，**原样落盘**，无原文）：

| 键 | 类型 | 取值域 | 说明 |
|---|---|---|---|
| `risk_draft` | str | `RISK_LEVELS` 三值 | 归一化**后**的值（闭集 → 落盘安全） |
| `risk_draft_resolution` | str | 4 值 | 取值来源，回答「模型是不是在乱写」 |

**明确不入盘**：`risk_draft` 的**原始字符串**（自由文本，落在 07 的禁入清单内）。因此 `unrecognized` 时只有「发生了未识别」这一事实可见，不含模型原话——与既有无原文采集面一致。

**「`sensitive` 提案进入授权」不需要新枚举（2026-09-17 裁决 B 第 6 条）**：该事实已由**同一回合的两个既有结构化值**联合表达——`dispatch_decision.proposal_gate_result = "admitted_proposal"` **且**同回合 `intent_final.risk_draft = "sensitive"`。因此：

- **不新增**任何 `gate_result` / `denied_reason` 取值，**不改** 07 §2.2 与 08 的封闭集与报告聚合口径；
- 报告侧据此可直接聚合「`sensitive` 所致升级的 run 数」与「其中走到 `AWAITING_AUTHORIZATION` 的比例」（后者由 `cloud_consult phase="authorization_required"` 表达，属已有事件）；
- 若将来真要新增一个专门的枚举值，**必须先**同步 07/08 的封闭集、报告与历史 JSONL 的比对口径，并说明为何两个既有值的联合不足以表达——本轮不做。

**报告聚合（10 §7.4 G3 区）**：新增 `risk_draft` 与 `risk_draft_resolution` 分布。本次 bug 在旧 JSONL 里只留下 `non_normal_risk` 一个面（看不出模型写了什么、写了多少），部署后必须能从报告上一眼看出「非法措辞是否复发」。**2026-09-17 增补**：`non_normal_risk` 由「合法观测值」变为**全域禁项**（§3.2），其计数在报告里的正确读数是 **0**；非 0 即接线缺陷。

### 3.4 `sensitive` 提案的强制用户授权（2026-09-17 裁决 B，R6）

`risk_draft=sensitive` 的提案**可以**走到 `REQUEST_CLOUD`，但准入即被限定：

| # | 规则 | 落点 |
|---|---|---|
| 1 | 该动作**只**产出 `PrivacyPolicy` 脱敏准备与**最终实际 payload 的授权 preview**，**不得**产生网络请求 | 05 §1.4 状态机 `PREPARING → AWAITING_AUTHORIZATION` |
| 2 | **所有隐私模式（含 `convenient`）**下必须进 `AWAITING_AUTHORIZATION`；只有同 session 的显式 `/cloud allow` 才签发**用户 grant**（`create_user_grant`）；**不得**签发 policy grant，**不得**无人值守地同回合自动续 | 05 §1.4/§3.2/§5.3；`create_policy_grant` 的调用前置条件 |
| 3 | **不得复用**旧任务的授权，也不得复用本任务上一轮 grant 的边界——续咨询扩展同样按第 2 条走用户确认 | 05 §1.4 规则 6/7、§5.3 规则 2/4 |
| 4 | 用户确认后**既有检查一条不减**：`PrivacyPolicy` classify/redact/候选类别与来源校验、`CloudBoundary` 独立复核、grant 精确绑定、预算/冷却、审计链；preview / grant 指纹 / 实际 payload **逐项一致** | 05 §2.3.4/§3.2/§4.2/§5 |
| 5 | 识别出的秘密/隐私原值**不得**进入 payload、事件、审计或异常信息（原有不变量，本条款不放宽） | 05 §2.3/§4.3 |
| 6 | 拒绝 / 取消 / 超时后：清 pending、吊销 grant、零网络调用、无残留 payload 可被后续任务复用 | 05 §1.4 规则 3–5、§5.3 规则 5 |

**防御性拒绝的错误与审计契约（2026-09-17 补，防止实现侧各自发明）**——照 `04 §4.7` 的**防线分层**既有模式（同 `SAFETY_IMPACT_CLOSED` 的处置，`13 §4.1`）：

| 层 | 谁 | 行为 |
|---|---|---|
| **主防线** | `App`（`src/main.py`） | 正常分流时**根本不调用** `create_policy_grant()`——有效授权风险非 `normal` 时直接进 `AWAITING_AUTHORIZATION`。这是**正常响应**，不抛异常（`handle()` 有不抛异常契约，`04 §3.4`）；授权等待由 App 发**既有** `cloud_consult phase="authorization_required"` 事件表达 |
| **冗余防线** | `AuthorizationManager.create_policy_grant()` | 被非 `normal` 的有效授权风险调用时**拒绝签发**并抛出：`code = "CLOUD_AUTHORIZATION_REQUIRED"`（**复用既有错误码**，`00-error-contract.md` §2），`details.reason = "sensitive_policy_grant_forbidden"`，`recoverable=False`（同参数必然再次失败；补救路径是显式 `/cloud allow` 走 `create_user_grant`，不是重试） |

- **`AuthorizationManager` 不自己写审计**：它**没有**审计依赖，不新增。「接线缺陷」的可观测性由**调用方（App）**负责，且**走结构化运行事件、不写 `CloudAuditEvent`（2026-09-18 补钉，Codex 复审提出）**：App 捕获该异常后发**既有** `cloud_consult` 事件、`phase="denied"`、`denied_reason="sensitive_policy_grant_forbidden"`（`07` §2.2 的 `denied_reason` 封闭集**新增这一个本地否决类取值**，与 2026-09-13 P6c 的扩展同一做法：既有 stage、既有 key、无新采集面），随后照常进 `AWAITING_AUTHORIZATION`（fail-safe 方向：没有 grant 就不可能有出站），**不得**以任何方式补签 policy grant；
- **为什么本条的通道是可观测事件而不是审计流**（两条硬约束，任一条即足以否决）：
  1. `record_denial()` 的 `reason` 是**固定四值闭集**（`05` §4.3），枚举外值 fail-closed 抛 `SAFETY_CLOUD_BLOCK`——「多加一个原因码」不是多写一行，而是扩张一条**靠抛出保护**的闭集；
  2. `record_denial()` 的不变量是**每条任务清理路径恰一条**，事件形态是「本事件无轮次发生」的**终止语义**（`turn=0`、其余操作字段全零）。误调用**不是**任务的终止路径——App 之后还要进授权等待，用户还可能 `/cloud allow` 走通并产生后续 `cloud_consult` 事件；在此补一条会同时破坏「恰一条」与「终止语义」两条既有不变量。
  
  故要扩张的是 `07` §2.2 的 `denied_reason`（本地否决类本就是既有扩展点），而**不是** `CloudAuditEvent` 的 reason 闭集，也不是 `record_denial` 的四值枚举；
- **不消耗任何状态**：该次拒绝不签发 grant、不扣预算、不推进轮次、不写 pending、不改 `LocalTaskContext`；
- **错误码不需要新增**，故 `00-error-contract.md` 的错误码表**无需变更**（若 Codex 想在该表补一行 `details.reason` 备注，属其属地，Claude 审查）。

### 3.5 有效授权风险：确定性信号只能升险（2026-09-17 补，裁决 B 的安全闭环）

**问题**：§3.4 若把「任务是否为 `sensitive` 所致升级」**只**取自被准入候选归一化后的 `risk_draft`，那么这条接线的确定性**只是「确定性地传递模型结论」**——模型把真实敏感任务误判成 `normal`，续咨询就仍可能拿到 policy grant。这与 §0.3 的边界声明（「模型输出不是安全边界」）直接冲突：`risk_draft` 是**模型自评**，它可以作为**升险信号**，不能作为**降险依据**。

**裁决**：引入**有效授权风险**（effective authorization risk），它是签发 policy grant 时**唯一**被消费的风险值：

> `effective_authorization_risk = max(模型因果风险, 确定性升险结果)`
>
> 序：`normal < sensitive < dangerous`。**两个方向都不得下调**——确定性信号可以升险；「隐私扫描没发现问题」**不得**把模型声明的 `sensitive` 降回 `normal`；模型声明的 `normal` **不得**压过任何确定性升险信号。

| # | 确定性升险源（只能升，不能降） | 信号来源 | 何时可用 |
|---|---|---|---|
| 1 | `PrivacyPolicy` 对**实际 payload 候选**的分类结果：候选被判 `secret`、被判需拒绝，或脱敏后仍存在无法界定的敏感内容 → ≥ `sensitive` | `PrivacyPreparation`（05 §2.3） | 准备完成后即可知（grant 调用点最新） |
| 2 | `task_has_sensitive_execution_chain == True` → ≥ `sensitive` | 既有确定性状态（05 §1.3 否决集） | 准入时即知；**App 主链路该字段恒为 `False`**（05 §1.3 第 4 项），故本行升险**在 App 内不可达**——它的作用域是**其它调用方**（测试替身、未来编排）误传 `True` 时的冗余复核，不是 App 的防线 |
| 3 | 适用信号**缺失 / 求值异常 / 未求值** → `sensitive`（fail-closed 兜底） | —— | 只覆盖上表第 1、2 行 |

> **为什么工具计划 / preflight 风险不在本表里（2026-09-18 补钉，Codex 复审提出）**：原第 3 行把「任务内存在 `high_impact` 步，或存在覆盖 / 路径越界类 preflight 升险」列为升险源，但 `create_policy_grant()` 发生在**云端续咨询**阶段——此时**通常既没有 `ExecutionPlan`，也没跑过 preflight**。把它列为输入，「未求值即 `sensitive`」（第 3 行）就会让该信号**恒为 `sensitive`**：`normal + convenient` 的同回合自动续（R6 / B7 / `10` §7.1 第 18f 项）重新不可达，等于把本次裁决要修的洞换个位置再犯一次。反过来若由调用方硬传 `False`，则是**拿不可求值的信号当降险依据**，与本表「只能升」的方向相反。三条理由决定**删除**而不是改类型：
>
> 1. **两条链路正交**：工具风险由本地确定性 preflight 独立承担（`07` §6.3 的 `workspace_escape → dangerous`、`13` §2 的 `approval_profile` 只升不降），云端链路只回答「本回合要送什么出去」——工具计划不改变**外发内容**，本就不该进入签发判定；
> 2. **布尔值表达不了**：覆盖（`sensitive`）与路径越界（`dangerous`）是两个档位，用一个 bool 承载必然在实现侧丢信息；
> 3. **没有缺口可堵**：真实敏感执行链**已经是云端准入的硬否决**（05 §1.3 否决集第 4 项），`dangerous` 在第 1 步即 `REFUSE`——经准入而抵达 grant 调用点的任务，不存在「工具计划危险却被放过去」的情形。
>
> 故**不采纳** `deterministic_risk: str | None` 的替代方案：它只是给不可求值的信号换个类型名，反而要求云端链路持有工具计划，并把「`dangerous` 在调用前已被硬拒」写成又一条需要长期维护的约定。**反向断言**：`effective_authorization_risk()` 的签名中**不得**出现 `high_impact` / `preflight` / `approval_profile` 类参数（E3 校验参数名表）。

**时点与载体（两步，缺一不可）**：

1. **准入时冻结下界**：被准入候选归一化后的 `risk_draft` 落 `LocalTaskContext`，作为该任务的**模型下界**（同时仍是 `intent_final.risk_draft` 的观测值）——它是**下界**，不是最终值；
2. **授权时求有效值**：`create_policy_grant()` 的调用方在**调用点**用当时的确定性信号求 `max`，把**有效值**传给 `escalation_risk`。**不得**在准入时就把模型下界当作最终值直接传下去。

**参数语义（不新增参数名）**：`create_policy_grant(..., *, escalation_risk: str = "sensitive")` 的 `escalation_risk` 承载的是**有效授权风险**，不是模型原值，也不是「是否由 `sensitive` 触发升级」的布尔标记；只有 `"normal"` 可签发（§3.4）。闭集外的取值沿用 §2.1.1 的总量规则（→ `sensitive`）。签名变更登记见 §5、落点见 05 §3.2/§12。

**纯函数（新增，与 `normalize_risk_draft` 同层）**：

```python
def effective_authorization_risk(
    causal_risk: str,                  # 准入时冻结的模型下界（已归一化）
    *,
    payload_candidates_sensitive: bool = True,
    sensitive_execution_chain: bool = True,
) -> str
```

两个布尔信号**默认 `True`** 是刻意的 fail-closed 方向：调用方漏传任何一项，结果就是 `sensitive`（→ 强制用户授权），不会被静默降级为自动续。返回值恒属闭集 `RISK_LEVELS`；`causal_risk` 为闭集外值时先按 §2.1.1 归一化再比较。**参数表只有这两个**——工具计划与 preflight 类信号不进本函数（理由见上表后注），E3 的参数名断言钉死这一点。

**信号可得性是接线的义务，不是本函数的兜底义务**：调用点必须满足「准备阶段已完成」（升险源 ① 已求值）、「准入层的执行链状态已在手」（升险源 ② 已求值）。若某个调用点连这两个信号都拿不到，那是**接线缺陷**——此时记 `sensitive` 走强制授权（fail-closed），并落一条可观测标记（与 §3.4 的误调用同一处理方向），**不得**为了走通自动续而给信号填 `False`。

**这条不改动 §3.4 的任何一条**：`sensitive` 仍然只能由显式 `/cloud allow` 授权；新增的只是「哪些任务算 `sensitive`」不再由模型单独说了算。副作用方向也确认过：确定性升险只会让**更多**任务进强制授权，不会让任务更容易上云（唯一能上云的是 `normal`，而 `normal` 要求模型与全部确定性信号**同时**为 `normal`）。



---

## 4. 验收

### 4.1 归一化单元测试（表驱动，纯函数，必进 pytest）

| 输入 `raw` | 期望 `risk_draft` | 期望 `resolution` |
|---|---|---|
| `"normal"` / `"sensitive"` / `"dangerous"` | 原值 | `declared` |
| `"  NORMAL  "` / `"Sensitive"` / `"\tDANGEROUS\n"` | 对应值 | `declared` |
| `"low"` / `" LOW "` | `normal` | `mapped_legacy` |
| `"medium"` / `"Medium"` | `sensitive` | `mapped_legacy` |
| `"high"` / `" HIGH "` | `sensitive` | `mapped_legacy` |
| `"moderate"` / `"critical"` / `"medium-high"` / `"not normal"` / `"很高"` / `"low_risk"` | `sensitive` | `unrecognized` |
| 缺失 / `None` / `""` / `"   "` / `42` / `["normal"]` | `sensitive` | `absent` |

**不变式（表驱动，逐行断言）**：

1. `risk_draft ∈ RISK_LEVELS` **恒成立**——上表每一行都必须落在闭集内（这是「解析层是唯一归一化点」的机器可验证形式）；
2. **`dangerous` 只可能来自 `declared`**：上表全部用例中 `risk_draft == "dangerous"` 仅出现在第一行（显式声明行）；
3. `absent` 与 `unrecognized` **不得**产出 `normal`（表中 `low` 那一行 → `normal` 是**闭表内的显式映射**——`low` 明确断言了「低风险」，与「没有断言」是两回事）。

### 4.2 三层测试矩阵（**层次不得混用**）

**分层原则**：归一化**只**发生在解析层（§2.2），ControlPolicy **只**读闭集（§2.1.1）。把**原始模型字符串**直接喂给 ControlPolicy 是**错误的测试构造**——它测的是正常链路里不存在的状态，还会把 §2.1.1 的「闭集外防御」误读成策略语义。三层各自只测自己那层。

#### 4.2.1 第 1 层：归一化单元测试（纯函数）

见 §4.1，不重复。输入域 = 任意 `object`；输出域 = `RISK_LEVELS` × 4 值 `resolution`。

#### 4.2.2 第 2 层：解析 → 策略**集成**测试（原始值走完整链路）

构造：`_candidate_from_model_output({"risk_draft": <raw>, ...})` → `IntentCandidate` → 断言归一化结果 → 再交 `ControlPolicy.decide()`。**这一层是「force + low/medium/high」要求的落点**（用户 R5）。

| # | 模型原始值 | `candidate.risk_draft`（**必在闭集内**） | `resolution` | force：action / gate | proposal：结果 |
|---|---|---|---|---|---|
| I1 | `"low"` | `normal` | `mapped_legacy` | `REQUEST_CLOUD` / `admitted_forced` | `admitted_proposal`（可准入） |
| I2 | `"medium"` | `sensitive` | `mapped_legacy` | `REQUEST_CLOUD` / `admitted_forced` | **`admitted_proposal`**（强制用户授权，§3.4） |
| I3 | `"high"` | `sensitive` | `mapped_legacy` | `REQUEST_CLOUD` / `admitted_forced` | **`admitted_proposal`**（强制用户授权，§3.4） |
| I4 | `"  NORMAL  "` | `normal` | `declared` | `REQUEST_CLOUD` / `admitted_forced` | `admitted_proposal` |
| I5 | `"Sensitive"` | `sensitive` | `declared` | `REQUEST_CLOUD` / `admitted_forced` | **`admitted_proposal`**（强制用户授权，§3.4） |
| I6 | **`" DANGEROUS "`** | **`dangerous`** | `declared` | **`REFUSE`** / `not_evaluated` | **`REFUSE`** / `not_evaluated`（第 1 步早裁） |
| I7 | `"critical"` / `"moderate"` / `"很高"` | `sensitive` | `unrecognized` | `REQUEST_CLOUD` / `admitted_forced` | **`admitted_proposal`**（强制用户授权，§3.4） |
| I8 | 键缺失 / `""` / `None` | `sensitive` | `absent` | `REQUEST_CLOUD` / `admitted_forced` | **`admitted_proposal`**（强制用户授权，§3.4） |

**I6 是全矩阵唯一的 `REFUSE` 行**：`" DANGEROUS "` 先被 §2.2 归一化为 `dangerous`，再由第 1 步早裁。**断言顺序**：先断言 `candidate.risk_draft == "dangerous"`（归一层），再断言 `decide()` 结果（策略层）——两个断言都必须有，否则无法区分「归一化对了」与「策略误拒了」。

#### 4.2.3 第 3 层：ControlPolicy **单元**测试（只喂闭集三值）

| # | `risk_draft`（闭集值） | 路径 | 期望 action | `proposal_gate_result` | `proposal_denied_reason` |
|---|---|---|---|---|---|
| C1 | `"normal"` | force | `REQUEST_CLOUD` | `admitted_forced` | `none` |
| C2 | `"normal"` | proposal | `REQUEST_CLOUD` | `admitted_proposal` | `none` |
| C3 | `"sensitive"` | force | `REQUEST_CLOUD` | `admitted_forced` | `none` ← **由旧「不升级」翻转** |
| C4 | `"sensitive"` | proposal | `REQUEST_CLOUD` | `admitted_proposal` | `none` ← **由旧「不升级 + `non_normal_risk`」翻转（2026-09-17 R6）**；该路径的保守性由 §3.4 的强制用户授权承担，**不再由否决表达** |
| C5 | `"dangerous"` | force | `REFUSE` | `not_evaluated` | `none` |
| C6 | `"dangerous"` | proposal | `REFUSE` | `not_evaluated` | `none`（第 1 步早裁） |

构造注意：`has_task_text` 默认 `False`（fail-closed），**force 用例必须显式传 `has_task_text=True`**；proposal 用例须给有效 `ConsultationProposal` 且其余否决项全部通过。

**闭集外防御用例（第 3 层的合法性边界：直接构造候选，不经解析层）**——期望由 §2.1.1 决定，**不是** `sensitive` 一刀切：

| # | 直接构造的 `risk_draft` | 期望 | 依据 |
|---|---|---|---|
| D1 | `"DANGEROUS"` / `" dangerous "` | `REFUSE` | §2.1.1 危险方向的方向性宽容 |
| D2 | `"high"` / `"critical"` / `"normal-ish"` | 按 `sensitive`（force → `admitted_forced`；proposal → `admitted_proposal` + 强制用户授权，§3.4） | §2.1.1 保守兜底 |
| D3 | `None` / `42` / `""` | 按 `sensitive`（同 D2） | 同上 |

> D 组**不是**「策略语义的一部分」，而是**不变式断言**：闭集外值在真实链路里不可达（§4.4 第 3 项），D 组只钉死「万一可达」时的失败方向。因此 D 组**不得**被读成「ControlPolicy 支持这些输入」。
>
> **D2 与 I1 的差异不是矛盾，是层次**：直接构造 `risk_draft="low"` 会按 `sensitive`，而经解析层的 `"low"` 是 `normal`——因为 ControlPolicy **不持有**旧词表（否则就是第二份映射表）。这正是「闭集外值越早归一化越好」的机器证明，也是 §2.1.1 接口义务的依据。

#### 4.2.4 确定性与防漂移（本次 bug 的直接回归）

- 同一候选**重复 N 次**（N ≥ 20）→ `decide()` 的 action 与 `evaluate_cloud_admission()` 的 `gate_result` **恒定**；同一输入不得在 `admitted_proposal` / `admitted_forced` / `vetoed` 之间**漂移**；
- **`proposal_denied_reason == "non_normal_risk"` 是全域禁项（2026-09-17 升级）**：任何路径、任何闭合集值都不得产生该值（见 §3.2 处置段与 08 §2.6 硬性结构项）。旧口径「force 轮不得出现」已不够——proposal 路径也不再可达，出现即残留的否决项 3 未删净；
- 归一化是纯函数：同一 `raw` 的 100 次调用返回值逐一全等。

#### 4.2.5 `sensitive` 建议的准入与强制授权（2026-09-17，裁决 A/B 的落点）

> **组编号的作用域**：A/B/C/E 四组的字母**只在本小节内唯一**，与 §4.2.3 的 C1–C6 / D1–D3 **不是同一套编号**（后者测的是 ControlPolicy 收到闭集外值的失败方向，本小节测的是判定对象、准入授权与有效授权风险的求值方向）。跨契约引用时**必须**写成「`12` §4.2.5 X 组」或「`12` §4.2.5 E1」——单独写 `C1` 不足以定位。pytest 用例命名同样按 `§4.2.5` 前缀区分。

**A 组——判定对象（提示词层，观测口径）**：

| # | 用例 | 期望 |
|---|---|---|
| A1 | S09 `base` / S06 `cloud_auto` 的任务文本（只读开放式分析、输入无凭据） | 模型候选 `risk_draft=normal` + `should_consult=true` → proposal 准入 `admitted_proposal`。**观测口径**：真实模型输出带随机性，达标以定向真实 run 的分布计（10 §7.3），不写成单次必过的 pytest 断言；提示词规则文本本身按 12 §1.3 第 6/7 条做**规则文本断言**（10 §7.1 第 16 项同款做法） |
| A2 | 构造候选：同一话题但本回合**请求执行**（迁移 / 改线上配置 / 写文件） | `sensitive`（对照例；不要求它被否决，只要求它落进 §3.4 的强制授权路径）。**本项是确定性单测**——构造候选直接给 `risk_draft="sensitive"` 即可，不由模型输出驱动 |
| A3 | 构造候选：本回合输入**含**凭据/密钥 | `sensitive`（充分条件①） |

**B 组——准入与授权（确定性，全部进 pytest）**：

| # | 用例 | 期望 |
|---|---|---|
| B1 | 直接构造 `risk_draft="sensitive"` + 有效 proposal（无 force） | `REQUEST_CLOUD` + `gate_result=admitted_proposal`；**零**否决、零 `non_normal_risk` |
| B2 | 承 B1，隐私模式 = `convenient`，走到准备完成 | 进 `AWAITING_AUTHORIZATION`；**不得**出现 policy grant；授权前传输调用数 **0**、`outbound_bytes == 0`、无 `phase="outbound"` 事件 |
| B3 | 承 B1，隐私模式 = `strict` / `balanced` | 同 B2（三模式行为一致——本条款与隐私模式无关） |
| B4 | 承 B2，调用 `create_policy_grant(..., escalation_risk="sensitive")` | **拒绝签发**：抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"` + `recoverable=False`（§3.4 冗余防线表）；`remaining_turns` / 台账 / pending **不得**被该次拒绝消费；`AuthorizationManager` 自身**不**写审计（由 App 侧捕获后记） |
| B5 | 承 B2，用户拒绝 / 取消 / 超时 / 跨 session 输入 | 清 pending、吊销 grant、**零网络调用**；无残留 payload 可被下一任务复用 |
| B6 | 承 B2，用户显式 `/cloud allow` | 签发**用户 grant**；实际发送的 payload 与 preview 展示的内容集、grant 指纹**逐项一致**；秘密/隐私原值不出现在 payload、事件、审计与异常信息中 |
| B7 | 承 B1，`risk_draft="normal"` **且全部确定性升险信号均为否**的对照用例 | 行为与今日一致：`convenient` 且新增候选全为 allowlisted `user_entity` 时，续咨询可 `create_policy_grant(..., escalation_risk="normal")`（**有效值**为 `normal`）同回合自动续——**R6 不改动 normal 路径** |
| B8 | `escalation_risk` 默认值 | 不传该参数即视为 `sensitive`：`create_policy_grant(...)` 默认**拒绝签发**（fail-closed，变异探针：把默认值改成 `"normal"` 必须有用例变红） |
| B9 | 闭集外防御 | `escalation_risk` 为闭集外值（`"high"` / `None` / `42`）→ 按 `sensitive`（仍拒绝签发），依 §2.1.1 |

**C 组——危险与其它红锁不回归（确定性）**：

| # | 用例 | 期望 |
|---|---|---|
| C1 | `risk_draft="dangerous"` + 有效 proposal | `REFUSE` + `not_evaluated`，且**不进入** `REQUEST_CLOUD`（第 1 步早裁） |
| C2 | `task_has_sensitive_execution_chain=True` / `deny_cloud=True` / `cloud_enabled=False` / `provider_available=False` / 预算冷却 / force 空任务 | 各自照旧否决（§3.2 不可绕过集**一条未减**） |
| C3 | 提示词规则文本 | 含 §1.3 第 8 条（`dangerous` 时 `should_consult=false`） |

**E 组——有效授权风险：确定性只能升险（2026-09-17 补，§3.5；全部进 pytest，纯函数级 + 接线级）**：

> 编号从 **E** 起，与 §4.2.3 的闭集外防御 D 组区分开——两组测的是不同层：D 组测「ControlPolicy 收到闭集外 `risk_draft` 时的失败方向」，E 组测「有效授权风险的求值方向」。

| # | 用例 | 期望 |
|---|---|---|
| E1 | 模型下界 = `"normal"`，但 `payload_candidates_sensitive=True` | `effective_authorization_risk(...) == "sensitive"` → `create_policy_grant` 拒绝签发（**这是本次补丁要堵的洞**：模型误判不得让真实敏感任务拿到 policy grant） |
| E2 | 模型下界 = `"sensitive"`，两个确定性信号**全为 `False`** | 结果仍是 `"sensitive"`（**不得下调**——「隐私扫描没发现问题」不是降险依据，模型声明与确定性信号是 `max` 关系） |
| E3 | 模型下界 = `"normal"`，`sensitive_execution_chain=True` | 得 `"sensitive"`。**同项反向断言（2026-09-18 补）**：`effective_authorization_risk` 的参数名表中**不得**出现 `high_impact` / `preflight` / `approval_profile` 类信号——工具计划层不得重新接回本函数（照 §3.5 表后注） |
| E4 | 两个布尔信号**全部漏传**（只传 `causal_risk`） | 结果 `"sensitive"`（fail-closed 默认；变异探针：把任一默认值改成 `False` 必须有用例变红） |
| E5 | `causal_risk` 为闭集外值（`"high"` / `None` / `42`） | 先按 §2.1.1 归一化（`"high"` → `sensitive`；`None`/`42` → `sensitive`）再求 `max`，返回值恒属 `RISK_LEVELS` |
| E6 | 接线级（App）：模型下界 `normal` + 准备阶段发现 payload 候选含敏感项 | 该任务**不得**走 policy grant 分支：先出现 `authorization_required`，且授权前传输调用数 0 |
| E7 | 接线级（App）：`create_policy_grant` 被误调用抛 `CLOUD_AUTHORIZATION_REQUIRED` | App 捕获后发**既有** `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` 事件（见 §3.4 与 05 §3.2）并**转入授权等待**（无 grant、无出站、无 CloudAuditEvent），**不**重试同一调用、**不**补签 |
| E8 | **正例（2026-09-18 补，Codex 复审要求）**：模型下界 = `"normal"`，两个适用信号均为 `False`；接线级同条件 | 纯函数返回 **`"normal"`**；接线级**必须真的签出** `create_policy_grant(..., escalation_risk="normal")` 并同回合自动续（与 B7 / `10` §7.1 第 18f 项同一场景）。**本项是「有效授权风险不得退化成全员 `sensitive`」的可执行反证**——只测「升险方向」的矩阵会让「恒返回 `sensitive`」的实现全绿，这条把它钉住 |

### 4.3 事件与提示词断言

- **闭集不变式（属性式）**：对 §4.1 的**全部** raw 值（含缺失/畸形）逐一调用 `normalize_risk_draft`，断言 `结果[0] in RISK_LEVELS` 且 `结果[1] in 4 值枚举`——这是「解析层是唯一归一化点」的机器可验证形式；
- `intent_final` 的 `data` 键集 == 07 §2.2 封闭集；JSONL 落盘行含 `risk_draft` / `risk_draft_resolution` 且**不含**原始字符串；
- `_INTENT_RESPONSE_SCHEMA.risk_draft` 为 `{"type": "string", "enum": [...三值...]}`，且 `risk_draft` 进入 `required` 列表；
- **`_build_prompt` 的规则文本断言（2026-09-18 代码审查 F6 改写为要点清单）**：断言逐条对齐 §1.3，**不得**只断言零散英文短语——实测「`"task difficulty"` / `"production environment"` / `"large scale"` 等短语存在」式的断言在措辞被改窄时照样全绿（第 4 条的排除对象由「非 `normal`」被实现成「非 `dangerous`」即属此类）。要点清单：§1.3 第 1 条（三值合法取值 + 点名禁止 `low`/`medium`/`high`/`critical` 及中文等级词）；第 3 条含**限定语**（「不确定」专指本回合是否**真的**请求副作用 / **真的**含敏感数据；「话题听起来重要、复杂、影响面大」**不是**不确定）；第 4 条的排除对象必须覆盖 **`normal` 侧**（复杂/篇幅长/重要**都不是**取 `normal` 以外值的理由，而不是「不是 `dangerous` 的理由」）；第 6 条（判定对象 = 本回合实际请求的动作，而非讨论到的假设操作或目标系统重要性）；第 7 条含**「此外不做保守推定」**、**「判据是请求语义而非会不会进确认链」**与「工作区内新建文件为 `normal`」（2026-09-20 追加中间那一项——只说「新建是 `normal`」不加解释，模型会据此以为新建无需确认，与 P7a-0 后的实际行为矛盾）；第 8 条（`dangerous` ⇒ `should_consult=false`）；
- `guarded_executor._effective_risk()` 的 `_RISK_ORDER.get(...)` 兜底不是 `normal`（变异探针：把 default 改回 `0` 必须有用例变红——闭集下该分支不可达，故断言方式为**直接构造闭集外的 `ExecutionStep.risk_level` 并断言按 `sensitive` 处理**）；
- **消费方一致性（2026-09-16 代码审查补，对应 §2.1.1 的实现归属）**：把 §4.1 的全部 raw 值同时喂给**每一个**消费方入口（`ControlPolicy` 读取、`guarded_executor` 读取），断言两者给出**同一**分类——`dangerous` 的写法变体 ⇒ `dangerous`，其余闭集外值 ⇒ `sensitive`。这是「一条规则一份实现」的行为级机检，不依赖脆弱源码 grep；顺带在变异探针里把任一消费方改回手写 `.lower()` 判断必须有用例变红。

### 4.4 Done 定义

1. 归一化函数与闭集常量单一实现、无第二份映射（全文搜索可证；`LEGACY_RISK_MAP` 只出现在 `risk_vocabulary.py`）；**§2.1.1 的消费层总量规则同样单一实现**（下沉 `risk_vocabulary.read_risk()`，消费方只 `import`；不得存在第二份手写的 `.lower()`/闭集判断）；
2. §4.1 / §4.2 / §4.3 全部落地并进 pytest，**且三层测试各自只使用本层合法输入**（第 3 层不出现原始模型字符串）；
3. **闭集外值在真实链路不可达**：`decide()` / `evaluate_cloud_admission()` 的输入候选只由解析层或本地代码构造；无第二条从外部输入构造 `IntentCandidate` 的路径（§2.1.1 接口义务）；
4. **全域无 `non_normal_risk`**：S06/S08/S10/S13 的 `cloud_assisted` / base 变体以及**所有** run（含 S09/S06 `cloud_auto`）都不再出现该值（08 §2.6 全域禁项），且 `risk_draft_resolution` 分布里 `absent` / `unrecognized` 未占主导（否则是提示词问题，见 §2.2 代价段）；
5. **R5/R6 落地（2026-09-17 裁决 A/B）**：§4.2.5 的 A/B/C/**E** 四组用例全部进 pytest（A1 的**提示词规则文本**部分进 pytest，其**模型行为**部分按观测口径计）；`create_policy_grant()` 的 `escalation_risk` 参数与 `effective_authorization_risk()` 纯函数在 00-* 工程契约中镜像；`sensitive` 提案在 `convenient` 下同样进 `AWAITING_AUTHORIZATION`（无 policy grant、授权前零出站）；**有效授权风险不得回退为「模型原值」**（E1/E2 是这条的可执行形式）；
6. 默认 pytest 与 ruff 全绿；无接口签名以外的改动面。

---

## 5. 接口签名变更（Claude 授权，Codex 落代码与 00-* 工程契约）

| 变更 | 内容 | 兼容性 |
|---|---|---|
| `IntentCandidate` 新增字段 | `risk_draft_resolution: str = "declared"` | 带默认值，既有位置构造与关键字构造**全部兼容**；消费方只读 |
| 新增纯函数 | `normalize_risk_draft(raw: object) -> tuple[str, str]` | 新增，无既有调用方 |
| **新增纯函数（2026-09-17 R6 安全闭环；2026-09-18 参数收窄）** | `effective_authorization_risk(causal_risk: str, *, payload_candidates_sensitive: bool = True, sensitive_execution_chain: bool = True) -> str` | 新增，无既有调用方；两信号默认 `True` 是 fail-closed（§3.5）。与 `normalize_risk_draft` 同层（`risk_vocabulary.py`）。**参数表恰为这两个**：工具计划 / preflight 类信号不得接回本函数（§3.5 表后注、E3 反向断言） |
| `_candidate_from_model_output` | 解析 `risk_draft` 由 `_string_or_default` 改为 `normalize_risk_draft` | 行为变更**仅**在闭集外取值上（本契约的目的） |
| `_INTENT_RESPONSE_SCHEMA` | `risk_draft` 加 `enum`，并加入 `required` | 值域收紧，非新增字段 |
| `guarded_executor._effective_risk` | `_RISK_ORDER.get()` 兜底由 `normal` 改为 `sensitive` | 闭集下不可达；改的是 fail-open 兜底 |
| `ControlPolicy` 的 `risk_draft` 读取 | 由「`_is_dangerous` 做 `.lower()`、其余分支直读字符串」改为**闭集精确比较 + §2.1.1 总量规则** | 闭集外取值的行为不再是「非 `normal` 即否决」（这是 §3.2 修订在策略层的落地）；`"DANGEROUS"` 仍 `REFUSE`（与现状一致，未削弱）。真实链路中闭集外值不可达 |
| **`AuthorizationManager.create_policy_grant()` 新增关键字参数（2026-09-17 R6）** | `escalation_risk: str = "sensitive"`（关键字专用、带 fail-closed 默认值）：承载**有效授权风险**（§3.5），非 `"normal"` 时**拒绝签发**并抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"`（`recoverable=False`，**不写 `CloudAuditEvent`、不动 `record_denial`**，可观测性走 `cloud_consult phase="denied"`，见 §3.4 防线表） | **向后兼容的签名扩展**（既有调用点不传该参数即得 fail-closed 行为，不会静默放宽）；`convenient` 下 `normal` 任务的原自动续行为需调用方显式传 `"normal"` 才成立——这是本次改动的**有意代价**（把「谁可以无人值守」变成显式接线，可测）。00-* 镜像由 Codex 落 |
| **`ControlPolicy` 的 `risk_draft` 准入语义（2026-09-17 R6）** | proposal 路径**删除**「`risk_draft == "normal"`」准入条件；`evaluate_cloud_admission()` 的否决集**删除**否决项 3（`non_normal_risk` 枚举值保留、不可达） | 准入/否决逻辑简化，`decide()` 与 `evaluate_cloud_admission()` **签名不变**；`CloudAdmissionDecision` 结构不变 |

**无变更**：`ControlPolicy.decide()` 签名、`CloudControlState`、`CloudAdmissionDecision`、`evaluate_cloud_admission()`、`TaskPlanner.plan()`、事件 stage 集合、`proposal_denied_reason` 值域（`non_normal_risk` 保留为不可达值）。

---

## 6. 实现清单（供 00-* 工程契约展开）

| 项 | 预期位置 | 说明 |
|---|---|---|
| `RISK_LEVELS` / `LEGACY_RISK_MAP` / `normalize_risk_draft()` / `effective_authorization_risk()` | `src/core/risk_vocabulary.py` | 唯一实现（含 §3.5 的 `max` 语义与两信号 fail-closed 默认） |
| `IntentCandidate.risk_draft_resolution` | `src/core/schemas.py` | 带默认值新字段 |
| 解析边界调用 | `src/core/intent_resolver.py` | `_candidate_from_model_output` |
| schema + 提示词 | `src/core/intent_resolver.py` | `enum` + §1.3 的 8 条规则文本（第 6/7 条为 2026-09-17 裁决 A 的判定对象与 `sensitive` 充分条件，第 8 条为 `dangerous` 不得建议上云） |
| 准入侧：删除否决项 3 + 强制授权接线 | `src/core/control_policy.py`、`src/main.py` | proposal 准入不再读 `risk_draft`；App 把被准入候选的归一化 `risk_draft` 作为**模型下界**记入 `LocalTaskContext`（准入时冻结） |
| 有效授权风险的求值与传递 | `src/main.py`（调用点） | 授权时用当时确定性信号求 `effective_authorization_risk(...)`（§3.5），把**有效值**显式传给 `create_policy_grant(..., escalation_risk=…)`；非 `normal` 时不调用、直接进授权等待（§3.4 主防线） |
| 冗余防线的可观测出口 | `src/main.py`（`_handle_cloud*` 的捕获点） | 捕获 `CLOUD_AUTHORIZATION_REQUIRED` 后发 `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"`（§3.4），再进授权等待。**新增的只是一个 `denied_reason` 取值**，stage 与 data key 不变 |
| `sensitive` 提案的强制用户授权 | `src/safety/authorization.py` | `create_policy_grant()` 的 fail-closed 前置条件（§3.4）；`convenient` 分支不得绕过；被违规调用时抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"` |
| 提示词/报告观测 | `scripts/p6_report.py` | `non_normal_risk` 按**全域禁项**读（正确值恒 0）；`admitted_proposal` + 同回合 `risk_draft=sensitive` 的联合计数（§3.3） |
| 防御性兜底 | `src/core/control_policy.py` / `src/safety/guarded_executor.py` | 闭集外 → `sensitive`，但 `"DANGEROUS"` 类写法变形 → `dangerous`（§2.1.1 方向性宽容）；不持旧词表 |
| 事件 2 键 | `src/main.py`（App 唯一事件生产者） | `intent_final` |
| 报告聚合 | `scripts/p6_report.py` | `risk_draft` / `risk_draft_resolution` 分布 |
| 00-* 镜像 | `00-core-interfaces.md` §实现清单 新增 1 行（`risk_vocabulary` 模块 + **接口义务：任何新增的 `IntentCandidate` 构造路径必须先过 `normalize_risk_draft()`**）；`00-adapter-factory.md` 若涉默认值同步 | **Codex 属地，Claude 审查** |

---

## 7. 决策记录

| 日期 | 决策 / 发现 | 处理 |
|---|---|---|
| 2026-09-16 | 真实 run：S06/S08/S10/S13 的 `/cloud ask` 被判 `non_normal_risk` 拒绝，同一指令历史 run 可走通 → 用户显式指令的成败取决于模型自由措辞 | 出本契约：闭集 + 归一化 + 准入语义修订（R1/R2/R3）；05 §1.3 否决集、08 §2.5/§2.6 场景口径、07 `intent_final`、01 §8.2、04 §4.6/§4.7、project-plan §4.2 同步 |
| 2026-09-16 | Codex 建议 `low→normal / medium→sensitive / high+critical→dangerous`，未识别 → fail-closed | **部分不采纳**：`high → sensitive`（§2.3，经验证据 + 硬锁定不可恢复）；`critical` 不入表（§2.5，未观察到的 token 不引入未测试路径）；未识别 → `sensitive` 而非 `dangerous`（§2.4，解析失败不得捏造「危险」断言，且与解析层「降到最不承诺档」的既有惯例相反） |
| 2026-09-16 | 是否让 `sensitive` 阻止**只读**云端咨询 | **不阻止 force、阻止 proposal**（§3.2）：force 路径已强制最终 payload 预览 + 用户显式 grant，保护强于任何模型措辞；「敏感执行链」的确定性否决由 `task_has_sensitive_execution_chain` 承担，模糊信号不得与之重复否决。**追注（2026-09-17）：本条「阻止 proposal」的一半已被 R6 取代**——`sensitive` 提案改为可准入 + 强制用户授权，理由见下一行 |
| 2026-09-16 | 缺失字段的兜底是否也 fail-closed 到 `sensitive` | 初版判「**暂不改**」，理由是「`risk_draft` 已进 schema `required`，缺失即非合规输出」——**该理由被 Codex 审查推翻**（§0.3 自己就声明 schema 不是保证），已按 §2.2 第 1 行**单点翻转**为 `sensitive` + `resolution=absent`。翻转的原因不是新的 run 证据，而是**契约自洽性**：缺失与乱码都是「模型没有给出可用断言」，双标即 fail-open。代价（漏字段的模型会普遍触发确认）已在 §2.2 照实记录，并由 `absent` 分布可见 |
| 2026-09-16 | Codex 审查：ControlPolicy 测试矩阵把原始模型字符串直接喂给策略层，与「解析层唯一归一化」矛盾 | **采纳**：§4.2 改为三层矩阵（归一化单测 / 解析→策略集成 / 策略单测 + 闭集外防御用例），见 §4.2 分层原则。**部分偏离 Codex 提议**：其「闭集外一律按 `sensitive`」会**弱化**现状（`_is_dangerous` 今日已能识别 `"DANGEROUS"`），故 §2.1.1 增加**危险方向的方向性宽容**——`"DANGEROUS"`/`" dangerous "` 仍 `REFUSE`，其余闭集外值按 `sensitive` |
| 2026-09-16 | 实现后代码审查（S06/S08/S10/S13 全通过，本轮只审逻辑不重跑）：① 我方文档口径与 P6a 确定性升险冲突；② §2.1.1 出现两份手写实现且语义分叉 | ① **文档修正（Claude）**：§2.4「`dangerous` 的唯一来源」**限定为解析层**，并写明 07 §6.3 的 `workspace_escape → dangerous` 是另一条合法（确定性）来源；04 §4.6 同步加反向边界，防止实现侧把该 wording 读成「确定性危险也不得升险」；② **实现归属（Codex）**：§2.1.1 规则下沉 `risk_vocabulary.read_risk()`，§4.3 新增消费方一致性机检、§4.4 第 1 项扩容。详见 `specs/reviews/12-risk-draft-closed-set-review.md` |
| 2026-09-17 | **`risk_draft` 的判定对象未被钉死（裁决 A）**：S09 `base` 3/3、S06 `cloud_auto` 3/3 把**只读开放式分析题**判成 `sensitive`（`escalation_reason` 分别为 `architecture_tradeoff` / `reasoning_complexity`），两条自主升级臂实际准入 **0/3**（目标 ≥2/3）。P6d 的提议校准本身是好的（3/3 `should_consult=true`、`benefit=0.8`、原因正确），失败在风险语义与准入的交界 | **判定对象钉死（R5，§1.2.1/§1.3 第 6/7 条）**：本回合**实际请求的动作**才是判定对象；只读分析 / 排查建议 / 架构权衡 / 迁移规划 / 回滚设计**默认 `normal`**，即使话题涉及生产、切流、数据库、部署或高影响系统；`sensitive` 的**充分条件只有两个**——本回合实际含敏感数据、或本回合实际请求需确认的副作用。另外明确「话题重要」不是不确定信号（与第 3 条「不确定时 `sensitive`」的边界），以及 `dangerous` 时不得建议上云（第 8 条）。**不得**为此改写 S06/S09 场景文本，**不得**调低 `expected_benefit` 阈值 |
| 2026-09-17 | **Codex 复审提出四处缺口，其中三处会影响实现（本行起四条）** ① 若「任务是否 `sensitive`」只取自被准入候选的 `risk_draft`，则该接线只是**确定性地传递模型结论**，模型把真实敏感任务误判成 `normal` 时续咨询仍可能拿到 policy grant——与 §0.3「模型输出不是安全边界」冲突 | **出 §3.5：有效授权风险 = `max(模型下界, 确定性升险)`，确定性信号只能升险、不得降险**。模型自评**只作下界**；确定性升险源穷举 **2 项**（payload 候选分类、敏感执行链）+ 信号缺失 fail-closed 兜底（2026-09-18 收窄，见本表下一行）；准入时冻结下界、**授权时**求有效值；新增纯函数 `effective_authorization_risk()`（两信号默认 `True`）。验收 = §4.2.5 **E 组**（E1 堵洞、E2 禁止下调、E4 变异探针、**E8 正例**） |
| 2026-09-17 | ② 「文件写入」被列为 `sensitive` 充分条件，与 `07 §6.1`「`file.write` 新建基线 `risk_level="normal"`、覆盖才由 preflight 升险」**直接冲突**——照此实现后新建文件会重新进确认链，S14「新建无需确认」必然红 | **限定语义（§1.2 表注 + §1.2.1 表/充分条件/对照例 + §1.3 第 7 条）**：本字段是**意图层**风险，**不复制工具层的确定性风险**；工作区内**新建**文件 = `normal`；**覆盖**与**路径越界**由确定性 preflight **只升不降**（后者即 `workspace_escape → dangerous`，§1.1 反向边界）。「写文件」在提示词里只能作为**举例**出现并注明该分工。`clarifications.md` 的 S14 条目**风险层这一半就此关闭**（工具名/参数键那一半仍开放）。**2026-09-20 追注**：本行的**结论（新建 = `normal`）不变**，但**理由与后果变了**——「新建文件会重新进确认链 ⇒ 必然红」这一句的**前提已被 P7a-0 反转**（现在新建**确实**进确认链，且那是**预期行为**）。真正撑住本行结论的是前半句「本字段是意图层风险、不复制工具层的确定性风险」这条**分层**规则，以及「确认与否是执行层事实，不由本字段表达」——见下表末行 |
| 2026-09-17 | ④ 「固定原因码 + 最小审计」未定义：没给原因码，也没说谁写审计，而 `AuthorizationManager` **本身没有审计依赖** | **照 `04 §4.7` 防线分层既有模式（同 `SAFETY_IMPACT_CLOSED`）**：主防线在 App（非 `normal` 时**根本不调用** policy grant，直接进 `AWAITING_AUTHORIZATION`，不抛异常）；冗余防线在 `AuthorizationManager`（违规调用 → 抛**既有** `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"` + `recoverable=False`，**不消耗** grant/预算/轮次/pending）；**`AuthorizationManager` 不写审计**，可观测性由 App 捕获后记。错误码**无需新增** → `00-error-contract.md` 错误码表不变。验收 = E7。**2026-09-18 补**：App 侧的痕迹**走结构化运行事件**（`cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"`，`07` §2.2 新增该本地否决类取值），**不写 `CloudAuditEvent`**——`record_denial()` 的四值闭集与「每条清理路径恰一条 / 终止语义」两条不变量都不动（理由见 §3.4） |
| 2026-09-17 | **`sensitive` 提案被一律否决，把「强模型补足小模型」的路径整体锁死（裁决 B）**：同批真实 run 的 `proposal_gate_result=vetoed` + `proposal_denied_reason=non_normal_risk` 全部来自该路径；而 R2 已认定该字段不是安全边界，用它做否决只贡献随机性 | **`sensitive` 不再阻止提出建议，只禁止未经确认的外发（R6，§3.2/§3.4）**：① 可准入 `REQUEST_CLOUD`，但只产出脱敏准备与最终授权 preview；② **所有**模式（含 `convenient`）必须进 `AWAITING_AUTHORIZATION`，只认显式 `/cloud allow` 的用户 grant，**不得** policy grant、**不得**复用旧任务/旧 grant 授权；③ 授权后既有检查一条不减（隐私分类/脱敏、`CloudBoundary`、grant 绑定、预算、审计链；preview/grant/payload 逐项一致）；④ 秘密与隐私原值不入 payload/事件/审计/异常；⑤ `dangerous`、敏感执行链、`deny_cloud`、provider 不可用、预算冷却、空任务等**红锁一条不减**；⑥ `/cloud ask` 语义不变（其 preview 仍不是外发授权）；⑦ 可观测性不新增枚举——`admitted_proposal` + 同回合 `intent_final.risk_draft="sensitive"` 即为「`sensitive` 提案进入授权」（§3.3）。**否决项 3 随之删除，`non_normal_risk` 成为全域不可达的保留值**（§3.2 处置段）：验收由「force 轮不得出现」升级为**全域禁项**。落地后须重跑 S05 `0/3`、S09 `≥2/3`、S06 `cloud_auto` `≥2/3`、S11 `0/3`，且任何发生升级的 run 都必须先出现 `authorization_required` 且授权前 `outbound_bytes=0` |
| 2026-09-18 | **Codex 复审（上轮四处补钉后）提出两处阻塞**：① 有效授权风险的第 3 个信号（`high_impact` / preflight）在云端链路**不可求值**——policy grant 发生在续咨询阶段，此时通常既无 `ExecutionPlan` 也未跑 preflight；照「未求值即 `sensitive`」严格实现会让该信号**恒为 `sensitive`**，`normal + convenient` 自动续（R6/B7/18f）再次不可达，而硬传 `False` 又违反「不得降险」；且单个 bool 无法区分覆盖（`sensitive`）与越界（`dangerous`） | **采纳「从云端授权风险中删除该信号」**（§3.5 表后注）：工具计划 / preflight 与云端咨询是**两条正交链路**——外发内容的敏感度由 `PrivacyPreparation` 决定（升险源 ①），工具侧危险由本地 preflight 与 `13` 的 `approval_profile` 独立承担且只升不降；真实敏感执行链**本就是云端准入硬否决**，经准入而抵达 grant 调用点的任务不存在「工具计划危险却被放过去」的缺口。**不采纳**改为 `deterministic_risk: str | None`：那是给不可求值的信号换类型名，反把工具计划拖进云端链路。故签名收窄为**两个**关键字信号（§5/§6），E3 增**参数名反向断言**（不得重现 `high_impact`/`preflight`/`approval_profile` 类参数） |
| 2026-09-18 | 同上复审②：**正例缺失**——E 组只锁「升险方向」，一个「恒返回 `sensitive`」的实现可以让全组变绿 | **补 E8 正例**：模型下界 `normal` + 两个适用信号均为 `False` → 纯函数返回 `"normal"`，且接线级**必须真的签出** `create_policy_grant(..., escalation_risk="normal")` 并同回合自动续（与 B7/18f 同场景）。E8 是「有效授权风险不得退化成全员 `sensitive`」的可执行反证 |
| 2026-09-18 | 同上复审①的附带问题：**新的审计原因无法通过既有审计接口**——`record_denial()` 的 `reason` 是固定四值闭集（`05` §4.3），枚举外值 fail-closed 抛 `SAFETY_CLOUD_BLOCK`，E7 照原文实现必然红 | **改用可观测事件通道**（§3.4）：App 捕获后发**既有** `cloud_consult` 事件、`phase="denied"`、`denied_reason="sensitive_policy_grant_forbidden"`——`07` §2.2 的 `denied_reason` 封闭集新增该**本地否决类**取值（与 P6c 扩展同做法）；**不写 `CloudAuditEvent`**：`record_denial()` 的「每条清理路径**恰一条**」与「终止语义（`turn=0`、操作字段全零）」两条不变量都要求它只用于**任务终止**路径，而误调用之后任务还要进授权等待、还可能走通。错误码表、`record_denial` 四值枚举、`CloudAuditEvent` reason 闭集**均不变** |
| **2026-09-20** | **P7a-0（老板拍板）：`07` §6.1 的 `file.write` 注册表基线由 `normal` 改为 `sensitive`，新建与覆盖都进确认链。本契约为「文件写入」划定的语义边界是否要跟着改成 `sensitive`？** | **不跟着改（本字段取值与语义均不变）**：本契约定的是**意图层**风险——判据是**这一轮请求本身的语义**是不是破坏性/不可逆/外发；P7a-0 给出的理由是**「能力/工具的选择是模型的概率判断，不能让一次错误选择在无确认下改文件系统」**，这是**执行层对选择不确定性的防线**，与「用户这一轮请求的动作危险不危险」是两件事。若把新建也判 `sensitive`，本字段的含义就从「这个请求风险高」漂移成「这个请求会被确认」，而后者是**执行层事实**、由注册表基线与 preflight 决定：两个字段表达同一件事必然分叉（模型今天写 `normal` 明天写 `sensitive`，就只是在给执行层加噪声），且 `sensitive` 在本项目有**实义后果**（R6 强制用户授权、云端准入分档），把「新建文件」塞进去会给纯本地写操作挂上云端授权语义。**因此**：§1.2 表注、§1.2.1 表/充分条件/对照例、§1.3 第 7 条、§4.4 提示词断言清单均已就地补注「判据是请求语义，不是会不会进确认链」；工具名/参数键与 `risk_draft` 的**分层结构一字未动**（两层各自只升不降、互不需对方同意）。**验收口径**：涉及「新建文件」的断言的**层必须写明**——断 `risk_draft` 的用例仍期望 `normal`；断 AuditEvent / `requires_confirmation` / `safety_policy.check` 输入风险的用例改为期望 `sensitive`（`07` §6.4、`08` §2.6 的 S14 已按此分层改写） |
