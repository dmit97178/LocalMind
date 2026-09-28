# 11-reference-guard — 悬空指代识别与追问护栏契约

> 状态：🔧 实现中（Codex 首轮已实现并过 460 passed；**第四轮代码审查提出 5 项实现修正 + 1 项测试缺口，见 `specs/reviews/11-reference-guard-review.md` 与 §8 步骤 2b**）
> 阶段：P6d 之后的独立子项（自 P6d 审查移出，见 `clarifications.md` [2026-09-15 → 2026-09-16] 条目）
> 起草：2026-09-16（Claude）。依据：S02 真实复现证据（6/6 run 全失败，见 §0.1）。修订：2026-09-16 第四轮（§1.2 禁止集、§2.1 `_NON_REFERENTIAL_COMPOUNDS` + M4 纯短语匹配、§2.2 M1 两域、§2.3 按标记类搜索域、§7.1 第 18 项与 20b-20e、§8 步骤 2b）
> 依赖契约：`01-p0a-main-loop.md`（`NextAction`/`ASK_USER` 既有语义）、`05-p4-cloud-advisory.md`（**双判定拆分不得回退**）、`07-p6a-observability-cli.md`（`dispatch_decision` 封闭集——本契约 §5 扩展 1 键）、`08-p6b-evaluation-loop.md`（`expect` 封闭集与报告——本契约 §6 扩展）、`10-p6d-autonomous-escalation.md`（提示词 P 系列与 E 系列示例——本契约 §4 追加 P11/E6）
> 本契约**不**修改：`is_effectively_ready()` 语义、P4 双判定拆分、模型字段（`state`/`entities`/`missing_info`）的单一来源、云端准入否决集、dangerous/强制/禁止上云/授权/副作用安全边界

---

## 0. 触发证据与本轮边界

### 0.1 真实复现证据（S02，移除 `_guard_unresolved_reference` 后）

输入「把那个服务发布上去。」，无前文、项目状态可空、无可召回记忆（S02 的设计条件）。6 run 全失败：

| run | variant | `final_state` | `missing_info_count` | `should_consult` | 实际动作 | 结果 |
|---|---|:---:|:---:|:---:|---|---|
| `99575fe1e96e` | round1 | READY | **0** | false | `PLAN_LOCAL` | **`error_code: TOOL_NOT_FOUND`**——模型自拟了不存在的工具 |
| `1d993540b40f` | round1 | READY | 2 | true | `REQUEST_CLOUD` | `admitted_proposal` |
| `87fcb5e6f0f8` | round1 | READY | 2 | true | `REQUEST_CLOUD` | `admitted_proposal` |
| `e80e5f9ffaab` | round4 | READY | 2 | true | `REQUEST_CLOUD` | `admitted_proposal` |
| `7a4047ef6390` | round4 | READY | 2 | true | `REQUEST_CLOUD` | `admitted_proposal` |
| `fe213c377b8f` | round4 | READY | 2 | true | `REQUEST_CLOUD` | `admitted_proposal` |

**三条结论**：

1. **6/6 模型在第一轮就宣布 `READY`**，因此 `IntentResolver` 的轮次 1 提前返回生效，`rounds_used=1`、`continue_retrieval=false`——**四轮渐进循环从未启动**（`round4` 变体也一样）；「多给几轮就能自己搞明白」这个假设被证伪。
2. **失败有两种形态**：多数（5/6）是「`READY` + `missing_info` 非空 + 建议上云」→ 一个本地根本没读懂的任务被送去云端；少数（1/6）是「`READY` + `missing_info` 为空」→ 本地硬答，并因模型自拟工具而报 `TOOL_NOT_FOUND`。
3. **`missing_info` 不能作为触发依据**：形态 2 的 `missing_info` 是空的，而它同样失败。任何以 `missing_info` 为输入的规则都会漏掉形态 2——并且会重蹈 P4 双判定拆分明确废止的「`missing_info` 一票否决云端」（§3.2）。

### 0.2 本轮目标

**在「模型宣布读懂了、但任务对象在本轮任何来源中都无法确定」时，确定性地返回 `ASK_USER`**，且不触碰模型字段、不回退双判定、不让规则产物污染观测。

### 0.3 与 `_guard_unresolved_reference`（已删除）的根本差异

| 维度 | 旧规则（已删除） | 本契约 |
|---|---|---|
| 触发依据 | 词表命中即改写**模型字段** | 词表命中 **且三个来源全部为空** 才触发；**从不写模型字段** |
| 判定式 | 「输入里有『那个』→ 加 `missing_info`」 | 「指代对象在本轮**无任何可用来源**」——来源判定是主体，词表只是入口 |
| 句内自解 | 未处理（`把这段话翻译一下，它是什么意思` 被误判） | §2.3 显式排除（篇章自指名词） |
| 观测 | 规则产物伪装成模型输出（`missing_info` 被污染，S02 的 `action_any` 变成不可证伪） | 独立 `reason` + 独立事件字段，模型字段与规则产物**永不混流**（§5） |
| 覆盖主张 | 隐含「覆盖全部指代」 | 显式声明**只覆盖封闭标记集**，且不声称完备（§2.1、§10.1） |

---

## 1. 判定归属（三个裁决）

### 1.1 裁决一：护栏放在哪一层

**裁决：独立纯函数模块 `src/core/reference_guard.py`，由 App 计算，作为仅限关键字参数传给 `ControlPolicy.decide()`；优先级在 `decide()` 内实现。**

| 备选 | 否决理由 |
|---|---|
| 放进 `IntentResolver` | ① 解析器的职责是「模型输出 → `IntentCandidate`」映射，护栏是**策略性**判定，放进去会模糊 `10-p6d` §1.1 的「三个判断」归属（本地就绪是**确定性规则**的域）；② 解析器在 `READY` 时**提前返回**，护栏必须在其之后仍生效——放在循环外等于放在 App 侧；③ 护栏的输入是 `MinimalContext`，与解析器的模型调用无关，放这里会制造「没有模型调用也要跑解析器」的伪依赖 |
| 放进 `ControlPolicy` 内部自算 | `decide()` 只有 `candidate` 与 `cloud_state`，**没有 `current_input`/`relevant_history`/`project_state`**。为它注入整个 `MinimalContext` 会把一个纯规则模块耦合到上下文装配，且扩大其接口面；`10-p6d` §1.1 已把「确定性规则」限定在既有输入上 |
| 新建 `ReferenceResolver` 类/服务 | 无状态、无依赖、纯函数一件事——类只会增加构造与注入面。与既有风格一致的做法是**模块级纯函数**（对标 `evaluate_cloud_admission` / `is_effectively_ready`） |

**为什么决策仍必须落在 `decide()`**：`decide()` 是动作的**唯一判定实现**（`10-p6d` §4.3）。若 App 自行短路，`dispatch_decision` 事件与真实动作就会脱节。护栏只负责**产出事实**（是否悬空、由什么来源解析），**优先级由 `decide()` 实现**。

### 1.2 裁决二：判定输入与输出

```python
# src/core/reference_guard.py
@dataclass(frozen=True)
class ReferenceGuardResult:
    """Deterministic verdict on whether this turn's task object is resolvable."""

    triggered: bool
    resolved_by: str = "none"      # 封闭集：none | self_referential | same_turn | history | project_state
    marker_text: str = ""          # 仅内存：供回复模板使用；**禁止**落任何持久层（§5.2）


def detect_unresolved_reference(
    input_text: str,
    *,
    relevant_history: Sequence[str] = (),
    project_state: Mapping[str, object] | None = None,
) -> ReferenceGuardResult:
    ...
```

**输入侧的三条硬约束**：

- **`input_text` 必须是 App 已剥离 slash 指令的 `input_event.text`**（与 `context.current_input` 同源）。`/cloud ask …` 的指令头不得参与标记匹配。
- **签名中不得出现任何模型侧输入**：参数名与类型注解中不得出现 `IntentCandidate`、`candidate`、`entities`、`missing_info`、`final_state`、`risk_draft`、`suggested_tools`、`consultation_proposal`。这不是风格要求：让模型输出抑制护栏，等于把「模型过度自信」这个已被证据证实缺陷复制进安全网（§3.2）。**要有一个结构测试钉死该签名**（§7 第 18 项）。
  > **禁止集必须是精确列表，不得用 `state` 这样的子串**（2026-09-16 第四轮审查修正，我方契约 bug）：合法参数名 `project_state` 本身含 `state`，子串匹配**不可满足**。要求 `state` 只能以「完整参数名/完整注解词」形式比对（`\bstate\b` 或参数名精确相等），**且 `project_state` 必须存在**——否则等于把「不得读项目状态」写成了契约，与 §2.3 的 `project_state` 来源矛盾。
- 无状态、无 IO、无配置读取、无模型调用。

### 1.3 裁决三：判定优先级

`ControlPolicy.decide()` 的判定顺序（**相对本契约之前的顺序只插入第 2 步**；2026-09-17 由 `14-resolution-exhausted.md` §4 增补第 7 行并删除原「超轮次」行）：

| # | 条件 | 动作 |
|:--:|---|---|
| 1 | `admission.gate_result == "not_evaluated"`（2026-09-17 起该值**唯一**来源是 dangerous） | `REFUSE` |
| **2** | **护栏已评估且 `triggered`，且非 `force_cloud` 轮** | **`ASK_USER`，`reason="dangling_reference"`** |
| 3 | `admission.admitted` | `REQUEST_CLOUD` |
| 4 | `is_effectively_ready(candidate)` | `_decide_ready(candidate)` |
| 5 | `no_progress` | 条件化回答 / `ASK_USER` |
| **6** | **`resolution_exhausted`**（本次解析已用尽实例 `max_rounds` 且未有效 READY；与 `no_progress` 构造互斥） | **`ASK_USER`，`reason="resolution_exhausted"`**（`14-resolution-exhausted.md` §4；位置在护栏与准入**之后**——轮次用尽**不得**抢断 force/proposal 上云） |
| 7 | `candidate.missing_info` 非空 | `RETRIEVE_MORE`（此后只在「尚有轮次」时可达） |
| 8 | 其余 | `ASK_USER` |

> **`force_cloud` 轮「让位」的精确含义（2026-09-16 第二轮审查补，防误读）**：让位的是**动作**，不是**评估**。`/cloud ask <payload>` 在 App 侧被 `_parse_cloud_control()` 剥离后**照常走 `decide()`**（`main.py:268,327`），因此护栏**照常被评估并如实记录**——force 轮的 `reference_guard_result` 可以是 `triggered`，只是不会把动作改写成 `ASK_USER`。**不得**实现成「force 轮不计算护栏」（那会退化成 `not_evaluated`，与 §5.1「正常任务调度回合不得出现 `not_evaluated`」冲突，且会把「规则看出了指代悬空」这个事实从事件流里抹掉）。用户显式指令优先，但事实必须仍在。

**四条优先级理由**：

- **在 dangerous 之后**：dangerous 是不可绕过的安全元规则，优先级最高（既有语义不变）。
- **在云端准入**之前**：悬空指代不是「本地能力不足」，因此**不该走云端**——云端同样拿不到用户没说出口的服务名，把「把那个服务发布上去」发给强模型不会让它变成可执行的任务。它属于 `10-p6d` §1.1 的 **intent clarity** 域（任务本身不完整），不是 cloud benefit 域。**这不是「用 missing_info 否决云端」**（§3.2 逐条说明）。
- **在云端准入判断之后**（注意与上一条不矛盾）：`decide()` **先调用** `evaluate_cloud_admission()` 得到 `admission`，**再**由护栏改写动作。这样 `dispatch_decision.proposal_gate_result` 仍如实报告「准入本来会怎么判」（如 `admitted_proposal`），护栏只改写 `action`。**「判定」与「动作」分开记录**，才能让报告看见「模型提议上云、准入通过、但被护栏拦下」（§5.3、§6.2）。
- **`force_cloud` 轮让位**：用户显式 `/cloud ask` 是指令，优先于规则对「你没说清楚」的判断；且云端是只读建议、无执行权，让位不引入副作用风险。这一条同时消除了 S10/S12/S13 三个强制链场景的**动作**回归风险（§6.4 表 B）。**注意是「动作让位」不是「跳过评估」**——force 轮照常计算并记录 `reference_guard_result`（§1.3 的精确含义），因此**不得**对这三个场景断言检测结果（S12 的载荷含 `这份配置`，必然 `triggered`）。

---

## 2. 判定规则

### 2.1 标记集（封闭，且**显式不声称完备**）

**标记集是入口，不是判定主体。** 命中标记只说明「值得检查」，是否触发由 §2.3 的来源判定决定。

| 类 | 形态 | 例 |
|---|---|---|
| **M1** 指示限定词 + 可选量词（**+ 窗口内封闭集名词**） | `(这\|那\|该\|此)` + 可选量词 + `_CENTER_WINDOW` 内命中封闭集成员 | 那个服务、这份配置、该文件 |
| **M3** 第三人称代词 | `它 / 它们 / 他 / 他们 / 她 / 她们` | 把它关掉 |
| **M4** 篇章回指短语 | `上述 / 前述 / 上面提到的 / 前面提到的 / 之前提到的 / 刚才说的` | 按上述执行 |

> **编号缺 M2 是刻意的**：早期草案有一个「指示词 + 量词、无名词中心语」类（如 `把那个删掉`），其保证（`C` = 整集）在 v1 **已删除**，见 §2.2 的「M2 的并入」。保留编号空位以免与既有引用混淆，同时标记这是一次**有意的能力撤回**（不是遗漏）。

**量词集（封闭）**：`个 些 份 条 台 次 种 位 件 批 段 句 篇 张 部 组 套 项 款 则 页`。

**M4 是纯短语匹配，不得附加任何后置过滤**（2026-09-16 第四轮审查补）：上表六个短语本身就是完整的标记，命中即算命中，**搜索域与「紧邻不计入」按 §2.3 的按类规则**处理。**实现中不得加入「后一个字符是 `是` 就跳过」之类的条件**——`上述是模型输出。` 的 `上述` 就是篇章回指，正是本契约要抓的形态；这类未记载的放宽会让标记集的行为无法从契约预测（§7 第 20e 项锁定四个形态）。

**显式排除（不是遗漏，是有理由的排除——不得作为「覆盖不全」报告）**：

| 排除项 | 理由 |
|---|---|
| `我 / 我们 / 你 / 你们` | **言语情境自解**：说话人与受话人由会话本身确定，永远不需要追问 |
| `本`（如「本系统」） | 与「我们的」同类，是自身指称，不是悬空指代 |
| **固定搭配 `_NON_REFERENTIAL_COMPOUNDS`**（见下） | **该字符不构成指示限定词**——它是构词成分而非指代成分 |
| 话题路由指代（「继续之前的话题」「上面说的话题」） | **P5 `TopicTracker` 的职责**，S04 正是验收该能力；护栏介入会与话题路由判定冲突 |
| 方位指代（`里面 / 上面 / 其中`） | 几乎总锚定在同轮已具名的对象上（如「读取 notes/deploy.md 的内容，告诉我里面列了哪几项」），纳入只会增加误触发面 |
| 指示词 + 篇章自指名词 | 见 §2.3 的 `self_referential`（自解，不触发） |

**固定搭配排除集（封闭，`_NON_REFERENTIAL_COMPOUNDS`，2026-09-16 第四轮审查补）**：

| 组 | 成员 | 说明 |
|---|---|---|
| 连词/副词（左邻构词） | `因此 如此 为此 据此 从此 以此 就此 特此 至此 那么 这么 怎么 多么 应该` | `这/那/该/此` 只是构词成分。**`应该` 是最危险的一个**——它是最高频能愿动词之一 |
| 处所/时间限定（右邻构词） | `这里 那里 哪里 这儿 那儿 哪儿 这边 那边 哪边 这时 那时 此时 此刻` | 处所/时间指代，与 §2.1 已排除的方位指代同类 |
| 泛指限定词 | `其他 其它` | 「别的」的意思，不指称任何**已具名**对象，因而不可能悬空 |

实现规则（与 `_TOPIC_ROUTING_TERMS` 同构）：把上表每个成员作为**两字排除区**，命中区内的**任何**标记（M1 与 M3 都要查，`其它` 会同时命中 `它`）一律跳过——**排除是按出现位置生效的，不是按句子生效**：`因此那个服务要重启` 里的 `因此` 被跳过，`那个服务` 照常触发（§7 第 20b 项用这一对锁定）。

> **为什么是封闭清单而不是「左邻字符集」**：按左邻字符排除（如「左邻是 `对`/`与`」）会顺手误伤 `对此` / `与此` 这类**真篇章回指**。封闭清单的每一项都可单独测试、可单独撤销，与本契约其余标记集（M1/M3/M4、量词集、话题路由）风格一致。完备性声明同 §2.2。


> **完备性的诚实声明**：确定性词表**不可能**覆盖中文指代的全部形态。本契约只主张一个**可证伪的强命题**——「**封闭标记集内**的指代表达，在三个来源全空时必定被追问」。**不**主张「覆盖全部悬空指代」。漏检的后果是**退回既有行为**（模型判断 + 本地分档），即**不劣于本契约之前的状态**，不是安全漏洞。扩充标记集是正常的契约修订（附测试），不需要新架构。

### 2.2 候选指称集 `C` 的构造（无分词器条件下的可实现定义）

**不提取「名词」**——中文无词边界，本契约又明确不引入分词器，「指示词之后紧邻的名词」在工程上无定义（`那个服务发布上去` 无法判定中心语是 `服务` / `服务发布` / `服务发布上去`）。改为**封闭集成员在固定窗口内的查找**，这是唯一可实现且可证伪的定义。

| 标记 | `C` 的构造 |
|---|---|
| **M1** | 取指示词 + 可选量词**之后**的 `_CENTER_WINDOW = 8` 个字符作为窗口；在该窗口中查找两个封闭集的成员，但**只承认两个位置域**（见下）；同一位置取**最长匹配**，取最先命中者，记入 `C`（单元素） |
| **M3 / M4** | 无中心语窗口 → `C = _EXTERNAL_OBJECT_NOUNS ∪ _SELF_REFERENTIAL_NOUNS`（整集）：即「本轮前文里有没有任何可被指称的对象？」 |
| M1 两个位置域内**都无**成员 | `C = ∅` → **不触发**（fail-open：未识别形态一律放行） |

**M1 的两个位置域（2026-09-16 第四轮审查补，修「窗口过宽导致张冠李戴」）**：中心语必须与指示词构成**同一个名词短语**，因此只承认

- **域 A（紧邻）**：窗口**起点处**命中封闭集成员（`那个服务发布上去` → `服务`）；
- **域 B（修饰短语）**：窗口内**第一个 `的`** 之后紧接的位置命中（`那个刚部署好的服务` → `服务`；`那种类型的服务` → `服务`）。

两域各自取最先命中者，**取位置更靠前者**；其余位置一律不承认。窗口内的 `的` 只取第一个——更远的 `的` 已跨出该 NP。

> **为什么必须收紧**：原「窗口内最先命中者」会把**另一个 NP 的中心语**当成被指对象。可复现反例：`这项工作交给系统处理。` → `工作` 不在集内 → 窗口继续右扫 → 抓到 `系统` → `marker_text = "这项工作交给系统"`。判定（`triggered`）碰巧没错，但**追问文案里的被指对象是错的**，且这条机制同时是假触发的成因（`应该先看一下日志再决定。` 就是靠它越过 8 字符抓到 `日志`）。收紧后该输入退回 fail-open（`工作` 未识别 → 不触发），与 §2.2「M2 的并入」的裁决同向：**未识别形态一律放行**。
>
> **不得因此改动 §7 第 16 项**：`那个刚部署好的服务` 必须仍然触发且 `marker_text` 逐字不变——它是域 B 的边界锁。

**M2 的并入（v1 的能力撤回，实现前审查第 1 项）**：早期草案另设 M2「指示词 + 量词、无名词中心语」（`把那个删掉`），其 `C` = 整集，因而必然触发。**这条保证已删除**——它与 M1 的 fail-open **在表面上不可区分**：

| 输入 | 早期草案的归属 | 冲突 |
|---|---|---|
| `把那个删掉` | M2（无中心语）→ `C`=整集 → 触发 | 与下一行同为「那个 + 窗口无封闭集成员」，却给出相反判定 |
| `把那个什么来着发布上去` | M1（未识别名词）→ `C=∅` → 不触发 | 同上 |

在不引入分词器、不新增**动作词表**的前提下，「窗口里没有封闭集名词」既可能是「本来就没名词」（M2）也可能是「名词不在我们的集合里」（未识别 M1），二者**无法确定性区分**。**裁决：统一走 fail-open**——理由是它与本契约已声明的方向一致（宁可漏报、退回既有行为，也不误伤），而反向选择（把未识别 M1 也当整集）会在「对象已用路径/标识符具名、但不在封闭集里」的输入上制造误触发（§6.4 的 S13「分析这份堆栈转储的可能根因」正是这个形状）。

**代价与证据**：撤回后 `把那个删掉`（无先行语境）**不再被兜底**，退回模型判断 + 本地分档——即**不劣于本契约之前的状态**。已核对全部 16 个场景：**只有 S02 含裸「那个」**且它是 M1（窗口内含 `服务`）；S12/S13 的「这份配置 / 这份堆栈转储」分别命中 M1 与 fail-open；**没有任何场景依赖 M2**。恢复 M2 的前置条件已登记在 §10.2。

**`_EXTERNAL_OBJECT_NOUNS`（封闭集，外部对象）**：`服务 服务器 文件 目录 项目 系统 任务 工具 配置 脚本 接口 文档 数据库 集群 环境 模块 组件 记录 报告 日志 版本 分支 镜像 证书 密钥 账号 权限 计划 流程 用例 场景 缓存 队列`

**`_SELF_REFERENTIAL_NOUNS`（封闭集，篇章自指）**：`话 文字 文本 句子 段落 意思 表述`

> **该集合的准入规则（必须写进代码注释）**：只允许收录**只能指称本轮语言材料本身**的名词。收录任何可指称外部实体的名词（`服务 / 文件 / 项目 / 内容 / 描述 / 问题`…）都是**缺陷**——那会让真实悬空指代被静默放过，正是本契约要消除的失败。（`内容 / 描述 / 说明 / 回答 / 问题` 已按此规则**从早期草案剔除**：它们都能指称外部实体。）

**窗口内不做任何虚词剔除**（早期草案曾按字符剔除 `_FUNCTION_WORDS`，已删）：匹配对象是**封闭集成员**，虚词本就不在其中，剔除对结果无影响；而**按字符**剔除会蕴含「未来某个候选词含该字符即被切碎」的隐患（如 `一键部署` 里的 `一`），是净风险。`_FUNCTION_WORDS` 因此从本契约中**整体移除**。

**`_CENTER_WINDOW = 8`**：定长窗口是**可调常量**（§10.2），当前值由 §7 第 16 项边界测试锁定——窗口过短漏检常见形态，过长会把无关的前置名词当成中心语。

**多标记规则**：逐标记**独立**判定；**只要存在一个未解析标记即触发**；`marker_text` 取**第一个未解析标记**的原文（M1 含其窗口中心语，如 `那个服务`；M3/M4 为标记本身，如 `它` / `上述`），渲染前截断 ≤20 字符并去控制字符。

### 2.3 来源判定（判定主体）

标记 `m` **未解析** ⟺ **没有任何来源包含 `m` 的任一候选**（`m.C` 中的成员作为子串出现在该来源中）。**触发 ⟺ 存在至少一个未解析标记。**

| 来源 | 视为「已提供」的确定性条件 | `resolved_by` |
|---|---|---|
| **篇章自指** | ① M1 的窗口中心语 ∈ `_SELF_REFERENTIAL_NOUNS`（`这段话`/`这段文字`——所指即本轮语言材料本身，**不需要先行词**）；**或** ② 任意标记的 `C` 中任一自指成员作为子串出现在该标记**之前的同轮文本**里（`把这段话翻译一下，它是什么意思` 的 M3「它」属此类）。**② 一律用前缀域，不随 M4 的整轮域放宽**——「本轮的语言材料」只可能在被指语言之后被提及 | `self_referential` |
| **同轮前文** | `m.C` 中任一成员作为子串出现在 **`m` 的搜索域**里（搜索域按标记类定义，见下） | `same_turn` |
| **会话历史** | `m.C` 中任一成员作为子串出现在 `relevant_history` 的**任何一项**里 | `history` |
| **项目状态** | `m.C` 中任一成员作为子串出现在 `project_state` 的**实质字段**值里。`_PROJECT_STATE_SUBSTANTIVE_KEYS = {goal summary constraints topic_tags}`——**`project_id` / `title` / `status` / 时间戳一律不算**（`project_id` 是不透明标识符，对「那个服务指什么」零信息量；`title` 可能回显用户首句） | `project_state` |
| 全部未命中 | —— | `none`（**触发**） |

取源优先级：`self_referential > same_turn > history > project_state`（就近取源）——一个标记可能同时满足多个来源，取排序最前者。注意上表 ① 是**唯一**不需要「候选词出现在某处文本中」的来源，因为它所指的对象（本轮的语言材料）**按构造必然可得**。

> **`same_turn` 的搜索域按标记类定义（2026-09-16 第四轮审查补，修契约自相矛盾）**：
>
> | 标记类 | 搜索域 |
> |---|---|
> | **M1 / M3** | **标记起始位置之前**的同轮文本（前缀域） |
> | **M4** | **整轮文本**，但**排除**从标记起始位置起 `_CENTER_WINDOW` 个字符内的候选词（该窗口内的是它自己的 NP / 紧邻小句，如 `上述配置` 的 `配置`、`前面提到的 3 个用例` 的 `用例`） |
>
> **M4 为什么必须放宽到整轮**：篇章回指短语的功能是**引出**被指内容，`刚才说的是 X` 里的 X **出现在标记之后**。前缀域会让这一形态**永远无法解析**——`刚才说的是支付服务，把那个服务发布上去。` 的 M4 标记前缀为空 → 触发，与本契约 §2.4 例 2（该输入判 `same_turn` 不触发）**直接矛盾**。**「排除自身窗口」为什么必须加**：M4 的 `C` 是整集，若不排除，标记会被**自己的 NP 头**解析掉（`上述配置需要复核。` → 假阴性，而它恰恰是悬空指代）；用同一个 `_CENTER_WINDOW` 是因为**它正是本契约已有的「标记之后多远算它自己的东西」的唯一定长定义**（§2.2），不引入第二个常量。
>
> **M3 为什么必须留在前缀域**：`把那个服务发布上去，然后把它删掉。` 的第二个标记不得为首个标记凭空造出先行词（§7 第 11 项）。这是 M3 与 M4 的真实区别：**代词回指，篇章短语引出**。
>
> **不得**用「M4 标记后紧接 `是` 就整个跳过」之类的**未记载过滤**来代替这条规则：它会让 `刚才说的是什么？`（真悬空）被静默放过。首轮实现正是这么做的（`reference_guard.py:152`）——那不是任意放宽，而是**在契约自相矛盾处唯一能让 §7 第 3 项通过的补丁**，发现值得肯定，但正确修法是本条规则（§7 第 20e 项锁定四个形态）。
>
> **影响面已核对**：16 个场景**无一含 M4 短语**（`grep 上述|前述|刚才说的|前面提到的 scenarios/` 为空），故本条只影响 §7.1 的纯函数项与 §2.4 例 2。

> **这不是「上下文非空即已解析」。** 判据是**候选指称词出现在该来源中**的封闭集匹配；「上下文存在」既不充分也不被使用。被否决的三个替代方案及其可证伪反例：

| 被否决的替代 | 反例（证明其错误） |
|---|---|
| 同轮前文「剔除虚词后剩余长度 ≥ 2」 | `明天再把那个服务发布上去。` → 前缀剩 `明天再`（≥2）→ 误判已解析。**剩余字数只是「有前文」的代理，不是「有先行对象」的判据** |
| `relevant_history` **非空**即算已解析 | 历史只有 `今天讨论天气。` → 误判已解析 |
| `project_state` **非空字典**即算已解析 | **`projects.auto_create = true` 是全部配置（含评估基线 `config/eval.example.toml:36`）的默认值**，P5 自动建项目后 `_project_state_dict()`（`context_assembler.py:107-110`）恒返回非空 `{project_id, summary}` → **每一次真实运行、每一次评估 run 中护栏都永不触发**。不是「可能长期不工作」，是**必然不工作** |

**已知限制（诚实声明，进 §10.2 延期）**：`MinimalContext.project_state` 当前只暴露 `{project_id, summary}`（`context_assembler.py:110`）——排除 `project_id` 后**只剩 `summary`**，而 `summary` 是**会话摘要**，可能回显用户自己的原句，从而让「那个服务」被误判为已解析。真正需要的是项目**目标/约束**这类显式声明字段，当前未暴露，扩展它等于修改模型可见输入（本契约不动）。因此本契约**不声称**护栏在项目会话中可靠，只声称它比「非空即解析」严格得多。

**逐例验证（判定式的可证伪性）**：

| 输入 | 标记与 `C` | 判定 | 结果 |
|---|---|---|---|
| `把那个服务发布上去。` | M1「那个」→ 窗口 `服务发布上去` → `C={服务}`（外部） | 前缀 `把` 无候选；history 空；project_state 无实质值（S02 无 state；评估 run 为 `{project_id, summary=""}`） | **触发** ✔（S02） |
| `把这段话翻译一下，它是什么意思。` | M1「这段」→ 窗口中心语 `话` ∈ 自指 | `self_referential` | 不触发 ✔ |
| 同上（第二个标记） | M3「它」→ `C`=整集；前缀「把这段话翻译一下，」含 `话` | `self_referential`（同轮前文命中自指集） | 不触发 ✔ |
| `刚才说的是支付服务，把那个服务发布上去。` | M1「那个」→ `C={服务}` | 前缀「刚才说的是支付服务，」含 `服务` | `same_turn`，不触发 ✔ |
| `明天再把那个服务发布上去。` | M1「那个」→ `C={服务}` | 前缀「明天再把」**不含**候选；无 history；无实质 project_state | **触发** ✔（旧判据在此误放行） |
| `今天讨论天气。`（history） + `把那个服务发布上去。` | `C={服务}` | history 含 `服务`？**否** → 三个来源全空 | **触发** ✔（旧判据误放行） |
| 同 1 + `project_state={"project_id": "x"}` | `C={服务}` | `project_id` **非实质字段** → 不构成来源 | **触发** ✔（旧判据误放行） |
| 同 1 + `project_state={"summary": "目标是发布支付服务"}` | `C={服务}` | `summary` 是实质字段且含 `服务` | `project_state`，不触发 ✔ |
| `把它删掉。` | M3 → `C`=整集 | 前缀 `把` 无候选 | **触发** ✔ |
| `刚才说的是支付服务，把那个服务发布上去，然后把它删掉。` | M1 `C={服务}`（同轮已解析）+ M3 | 两个标记均被前缀解析 | 不触发 ✔ |
| `按上述执行。`（无 history） | M4 → `C`=整集 | 前缀 `按` 无候选 | **触发** ✔ |
| `把我们系统的数据迁移到新集群。` | 无（`我们` 已排除） | —— | 不触发 ✔ |
| `继续之前的话题：把检查清单列出来。` | 无（话题路由已排除） | —— | 不触发 ✔ |
| `把那个刚部署好的服务发布上去。` | M1 窗口（`那个` 后 8 字符）= `刚部署好的服务发` → 命中最早成员 `服务`（索引 5） | 无先行词 | **触发** ✔（窗口长度约束的边界例，§7 第 16 项） |
| `把那个我们上周刚部署好的支付服务发布上去。` | M1 窗口 = `我们上周刚部署好的`（8 字符）→ **无封闭集成员** | `C = ∅` | 不触发（**fail-open**，中心语落在窗口外）✔ |

---

## 3. 与既有决策的关系（不变量）

### 3.1 `is_effectively_ready()` 语义不变

护栏**不读**该函数、**不修改**它。`READY` 的判定含义（`project-plan.md` 定义式：`state == "READY"` 或高置信度且无 `missing_info` 且 `intent_type` 具体）逐字保留。护栏在 `decide()` 中的位置在 `is_effectively_ready` 分支**之前**，因此对 `READY` 候选同样生效——**这不需要也不允许改动该函数**。

### 3.2 P4 双判定拆分不回退（逐条对账）

`05 §1.3` 的 2026-09-14 决策：**不得用本地完整度判断（含 `missing_info`）一票否决云端咨询**。本契约**不违反**它，理由必须写清楚，因为二者表面相似：

| 质疑 | 回答 |
|---|---|
| 「悬空指代拦在准入之前，不就是一票否决云端吗？」 | 否决的理由**不是** `missing_info`（本地完整度），而是**任务对象不可确定**（intent clarity）。云端拿不到用户没说出口的对象，因此这不是「能力不足该上升」，而是「任务不成立」 |
| 「那它和 `missing_info` 什么关系？」 | **零关系**。判定式（§2.3）不出现 `missing_info`；签名（§1.2）不接受模型侧任何输入。证据支持：§0.1 形态 2 的 `missing_info` 为空却同样失败——任何以 `missing_info` 为输入的规则都漏掉它 |
| 「`is_effectively_ready` 是不是被绕过了？」 | 没有。它照常求值，只是 `READY` 不再意味着「动作一定是 `_decide_ready` 的结果」。`READY` 仍然**不压制** `ConsultationProposal`——`admission` 照常计算且照常被如实记录（§1.3、§5.3） |
| 「这会降低自主升级率吗？」 | 只对**对象不可确定**的轮次降低，且这些轮次的升级本就不该发生（发一个没有对象的任务给云端）。S09/S06 的自主升级观测对象是**任务对象明确**的复杂题，不受影响（§6.4） |

### 3.3 模型字段单一来源

护栏**只读** `input_text`/`relevant_history`/`project_state`（都不是模型输出），**不写** `state` / `entities` / `missing_info` / `suggested_tools` / `risk_draft` / `consultation_proposal`。**必须有测试断言触发前后候选对象全等**（§7 第 28 项）。

### 3.4 安全边界不动

dangerous、`force_cloud`、`deny_cloud`、provider 可用性、预算与冷却、`PrivacyPolicy`、`CloudBoundary`、出站预览、用户授权、副作用确认——**一律不改**。护栏只可能把动作**收窄**为 `ASK_USER`（不执行、不外发、无副作用），不可能放宽任何边界。`force_cloud` 轮护栏让位（§1.3）。

---

## 4. 提示词契约（质量路径；确定性规则才是保证）

**两层分工必须写进契约，避免后人把提示词当成安全保证**：

- **提示词（质量路径）**：让模型**自己**发现指代缺失并追问。这是我们要观测的能力（§6.2 的 `model_asked`），但它**不可作为保证**——§0.1 的 6/6 失败正是「模型自称 `READY`」。
- **确定性护栏（保证路径）**：模型没做到时，行为仍然正确。**正确性不依赖模型**。

**新增规则 P11（追加到 `10-p6d` §2.2 的 P 系列）**：

| 规则 | 必须表达的语义 |
|---|---|
| **P11 悬空指代必须追问** | 若用户的**任务对象**用指代表达给出（「那个服务」「它」「上述」等），而本轮输入、会话历史与项目状态**都没有**给出该对象的具体身份，则**必须**：`state` 取 `VAGUE`/`PARTIAL`、`missing_info` 写明缺失的**对象本身**、`should_consult=false`（云端也不掌握用户没说出口的对象，上云无益）。**不得**在这种情况下声明 `READY`，**不得**建议云端 |

**新增示例 E6（追加到 `10-p6d` §2.3 的 E 系列；编号跨契约显式引用，不构成本契约之外的隐式示例）**：

| # | 输入形态（抽象描述） | 期望 | 理由 |
|---|---|---|---|
| E6 | 一个**只有指代对象、无任何上下文**的操作请求（如「把那个服务发布上去」，无前文/无项目状态/无可召回记忆） | `state ∈ {VAGUE, PARTIAL}`、`missing_info` 含缺失对象、`should_consult=false` | 情形 1（目标或关键对象不明确）——**不得**判 `READY` |

> E6 的抽象描述**不得**写入 S02 的原文，避免泄题（沿用 `10-p6d` §2.3 的既有约束）。

**`10-p6d` 的两处同步**：§2.2 表尾加 P11 指针、§2.3 的「5 例（E1–E5）」加 E6 指针（本契约 §4 定义），使「本契约不追加**隐式**示例」的声明继续成立——E6 是**显式跨契约引用**，不是隐式追加。

---

## 5. 可观测性（`07-p6a` §2.2 扩展 1 键）

### 5.1 事件字段

`dispatch_decision` 的 `data` 键封闭集**增加 1 键**：`reference_guard_result`

| 键 | 取值（封闭集） | 语义 |
|---|---|---|
| `reference_guard_result` | `not_evaluated` \| `not_triggered` \| `triggered` | `not_evaluated` = **该回合根本没走 `decide()`**；`not_triggered` = 已评估且不触发；`triggered` = 已评估且触发 |

**JSONL 落盘：原样**（受限枚举，非自由文本，无计数改写）。

**`not_evaluated` 与 `not_triggered` 必须分开**（沿用 `10-p6d` §4.3 的教训）：默认值让「忘了接线」与「已评估但不触发」共用一值，会把接线缺陷静默统计成正常。

**`not_evaluated` 的合法来源是「未进入正常意图调度的回合」，不是缺陷本身**：**确认恢复流不运行 `decide()`**，其 `dispatch_decision` 合法记为 `not_evaluated`——`_handle_confirmation()`（`main.py:632-689`）在 **6 处**发出 `dispatch_decision`，全部携带 `CloudAdmissionDecision(False, "not_evaluated")`。这些回合没有正常任务上下文，**不得伪造 `not_triggered`**。

因此判据收窄为：**「正常用户任务调度回合」不得出现 `not_evaluated`**——这类回合 `decide()` 必被调用，`proposal_gate_result` 与 `reference_guard_result` 必然同时被评估。可证伪的判据（§7 第 26/27 项，二者成对）：**凡是 `reason ∈ _CONFIRMATION_REASONS`（`no_pending_operation` / `confirmation_session_mismatch` / `passphrase_not_configured` / `identity_verification_error` / `identity_denied` / `identity_locked` / `confirmation_verified`）的 `dispatch_decision` 事件，必须 `reference_guard_result == "not_evaluated"`；其余事件必须 ∈ {`not_triggered`, `triggered`}**。二者互为补充，任一侧单独成立都不足以证明接线正确。

### 5.2 禁入清单（在 `10-p6d` §4.1 的禁入清单基础上**追加**）

- **`marker_text` 不得落任何持久层**——它是**用户输入原文的片段**，属既有禁入清单「任务原文」。它只存在于内存，供回复模板使用。
- 回复模板渲染 `marker_text` 前必须**截断到 20 字符并去除控制字符**（沿用 07 §3 的终端消毒口径）。
- `NextAction.reason = "dangling_reference"`：`reason` 在 07 §2.2 中本就**不落盘**，无需扩展封闭集。

### 5.3 判定与动作分开记录（关键）

护栏触发时，`proposal_gate_result` **仍如实报告准入的判定**（如 `admitted_proposal`），`action` 为 `ASK_USER`。二者组合可读出：

| 组合 | 含义 |
|---|---|
| `proposal_gate_result=admitted_proposal` + `action=ASK_USER` + `reference_guard_result=triggered` | **模型提议上云、准入通过，但被悬空指代护栏拦下** |
| `proposal_gate_result=not_suggested` + `action=ASK_USER` + `reference_guard_result=triggered` | 模型未提议上云，护栏独立发现对象缺失（§0.1 形态 2） |
| `proposal_gate_result=admitted_proposal` + `action=REQUEST_CLOUD` + `reference_guard_result=not_triggered` | 对象可确定，正常自主升级（**不能被护栏误伤**——§6.4） |

---

## 6. 场景与验收（`08-p6b` 修订）

### 6.1 `expect` 封闭集扩展 1 键

`expect` 增加 **`reference_guard_any`**（bool；**true = 断言至少出现一次**，**false = 断言不出现**），求值来源 = 本步骤所属 turn 的 `dispatch_decision.reference_guard_result`：

- `true` ⟺ 存在至少一个 `dispatch_decision` 事件其 `reference_guard_result == "triggered"`；
- `false` 的判据是「**已评估**且全部为 `not_triggered`」。求值前若发现 `not_evaluated`，**该 step 记结构性失败（接线缺陷）**，**不得**当作 `false` 通过——`not_evaluated` 是「准入逻辑根本没跑」的同义缺陷信号，把缺省值当合法值正是 P6d 第一轮修掉的那类问题。

——这是**唯一**能让场景表达「模型自己追问 vs 规则兜底」的手段，正是 `clarifications.md` [2026-09-15 → 2026-09-16] 第 4 条要求的落点。

> **`false` 只对非 force 轮有意义**（2026-09-16 第三轮补）：`force_cloud` 轮（S10/S12/S13）**不得**使用本键的任何一侧——护栏照常评估、结果照常落事件，但动作一律让位给用户指令，因此那里唯一有意义的不变量是「动作没被改写」，见 §6.4 表 B。S12 的载荷含 `这份配置`，对它的 `=false` 断言是一条**必然失败**的红线。

### 6.2 S02 的四态（需求 6 与测试 7 的落点）

`08 §2.3` 的 S02 行与报告单元采用**互斥完备**的四态（按序判定）：

| 序 | 态 | 判据 | 计入 |
|:--:|---|---|---|
| 1 | `model_asked` | **模型候选自身**表达了「需要澄清」——`final_state ∈ {VAGUE, PARTIAL}` 且 `missing_info_count > 0`——**且**动作 = `ASK_USER` | **模型校准成功率** |
| 2 | `guard_rescued` | 动作 = `ASK_USER` **且** `reference_guard_result = triggered` **且非** ① | **兜底率**（**不计入**模型校准成功率） |
| 3 | `unattributed_ask` | 动作 = `ASK_USER` **且非** ①② | **接线/归因缺陷信号**（**不计入**模型校准成功率，也**不计入**兜底率） |
| 4 | `failed` | 动作 ≠ `ASK_USER` | 结构性失败 |

**②必须显式要求 `reference_guard_result = triggered`**（实现前审查第 2 项）：早期写法把 ② 定义为「`ASK_USER` 且非 ①」的**补集**，于是**任何**其它路径产生的 `ASK_USER` 都被误记为「护栏救援」。实测存在这样的路径——`state=READY` 且 `missing_info` 非空时，`_decide_ready()` 本身就会返回 `ASK_USER`（`project-plan.md` 决策表第 3 行「模型声称就绪却有缺失信息，矛盾信号」），此时护栏可能返回 `not_triggered`，但 ② 仍会点亮。**兜底率因此可能在护栏完全失效时依然漂亮。**

**③ `unattributed_ask` 是本次新增的必要出口**：`ASK_USER` 既非模型表达、也非护栏触发，说明追问来自某个**未被本契约建模的路径**（如上述 `READY + missing_info` 分流、`resolution_exhausted` 分流、`no_progress` 分流）。它不是「行为失败」（系统确实追问了），但它是**归因失败**，必须单列而不许并进 ②，否则护栏的覆盖情况不可证伪。S02 报告中 ③ > 0 即需逐 run 回溯是哪条路径。

**S02 必须硬断言 `reference_guard_any = true`**（实现前审查第 2 项，**推翻早期写法的结论**）：S02 的输入固定为「把那个服务发布上去。」、无先行轮次 → `relevant_history` 为空、`project_state` 为 `{project_id, summary=""}` → **护栏在该输入上确定性命中**，与模型输出无关（护栏不读模型字段）。因此这是**输入的性质**，不是模型能力的性质——断言它**不会**让 S02 在模型不改进时永久红，我早期以「会永久红」为由拒绝该断言是**错的**（那个理由只对「护栏行为取决于模型」的场景成立，而本契约从构造上排除了这种可能）。加上这条断言后，S02 才真正验证了**确定性保证路径在工作**，而不只是「最终动作恰好是 ASK_USER」：

| 断言 | 作用 |
|---|---|
| `action_any = ["ASK_USER"]` | 行为门：不硬答 |
| `reference_guard_any = true` | **确定性保证门**：护栏确实触发——挡住「检测器错误返回 `not_triggered`、而 `ASK_USER` 由别的路径给出」这一整类假通过 |

**`model_asked` 的判据不得包含 `reference_guard_result = not_triggered`**（早期草案的写法，已废）：护栏**不读任何模型字段**，而 S02 的设计条件（无历史、空检索库）使护栏**在每一次 run 上都确定性命中**——要求 `not_triggered` 会让 `model_asked` **永远不可达**，模型即便在 P11 改进后正确输出 `VAGUE + missing_info`，也一律被记成 `guard_rescued`。那是原缺陷的**镜像**：原本是规则把 S02 静默保送，改后变成规则把模型成绩静默抹掉。**护栏是否命中已经是独立的 `reference_guard_result` 字段，不需要再嵌进能力评价的判据里。**——注意与上一条「S02 断言 `reference_guard_any = true`」**不矛盾**：**能力评价**（① `model_asked`）不含护栏字段，**场景断言**（验证护栏本身）含护栏字段，二者用途不同。

> **「不含护栏字段」的适用范围必须限定在 ①**（2026-09-16 第三轮审查修正）：② `guard_rescued` 的判据**明确要求** `reference_guard_result = triggered`，③ `unattributed_ask` 的判据是「`ASK_USER` 且非①②」，也依赖 ② 的结果。因此准确的命题是「**只有 `model_asked` 的模型能力判据不含护栏字段**」，不是「态判定整体不含护栏字段」。两者容易混为一谈，但混同的代价不对称：把 ① 的判据加回护栏字段 → 模型成绩被抹掉（原缺陷的镜像）；把 ② 的判据去掉护栏字段 → 兜底率虚高（护栏失效也漂亮）。两处都必须保持现有写法。

**`should_consult` 不参与态判定**，单列为独立观测项：S02 中 `should_consult == true` 的比例 = 「把不可答任务送云端」的误判率。理由：把「会不会追问」与「不该上云时是否提议上云」压进同一个态，会让一个态承担两个判定，且与 S02 硬门（只看动作）脱钩；拆开后两件事都各自可证伪、互不掩盖。

**`failed` 的诊断细分**：`failed` 中若**候选满足 `model_asked` 的澄清条件**，额外记 `model_asked_but_not_ask_user`。这类失败**指向护栏覆盖缺口**（模型判对了、动作却没落到 `ASK_USER`），与「模型没读懂」是完全不同的处置方向——前者改护栏标记集/来源判定，后者改提示词 P11。报告必须能分辨，否则两种缺陷会互相掩盖。

**S02 的验收判据**：

- **硬门 1（行为）**：`failed == 0`；
- **硬门 2（确定性保证）**：S02 的 step `expect` **必须**含 `reference_guard_any = true`——断言护栏确实触发（理由与「为何不永久红」见上）；
- **观测项**：`model_asked` / `guard_rescued` / `unattributed_ask` / `failed` **四态之和 = run 总数**（四态互斥完备，任何 run 必落且只落一态）；此式是**恒等式**，不是「当 `failed == 0` 时三者之和等于 run 总数」的特例——早期写法只写三数之和，等于默认 `failed` 恒为 0，那正是硬门 1 要验的东西，不能预先假设。`guard_rescued` **不得**被计入模型主动追问——这是「S02 不得仅因兜底命中就被计为模型主动追问成功」的落实；`unattributed_ask` 同理**不得**被计入兜底率。
- S02 的 `expect` **不**加 `reference_guard_any = false`（早期草案写法，已废，理由见上）；四态**归因**仍由报告呈现，不由场景硬断言——但**护栏是否触发**是确定性事实，由硬门 2 断言。

> 场景侧还需一条**接线自检**：S02 的每一 run 都必须至少有一个 `dispatch_decision` 事件满足 `reference_guard_result ∈ {not_triggered, triggered}`（即非 `not_evaluated`）。若 S02 全为 `not_evaluated`，说明护栏压根没接进主链路——此时 `guard_rescued = 0` 会被误读成「模型学会了」，实际是护栏缺席。这是本契约最重要的一条假阴性防线。

### 6.3 `08 §6` 报告新增一行

报告须给出**每个场景**的 `reference_guard_result` 分布，并对 S02 单列四态（`model_asked` / `guard_rescued` / `unattributed_ask` / `failed`）。**只给汇总数不算达标**——四态必须可分辨，且 `unattributed_ask` 是独立一行，**不得**与 `guard_rescued` 合并。

### 6.4 回归红线（护栏不得误伤的场景）

**红线判据是「最终动作」，不是「检测结果」**——护栏的缺陷形态是**误改动作**（把本该自主升级/执行的轮次改成 `ASK_USER`），不是「检测到了什么」。据此分两张表。

**表 A：非 force 轮，必须 `not_triggered`**（若触发即为回归，须作为结构性失败处理——此时动作会被改写成 `ASK_USER`）：

| 场景 | 为什么不应触发 |
|---|---|
| S04（引用旧话题） | 有 prelude 建立的会话历史 → 来源 `history` 成立；且「继续之前的话题」已被排除在标记集外 |
| S05 / S01（简单自足任务） | 输入无指代标记 |
| S06 / S07 / S08 / S09（复杂题） | 任务对象已具名；即便出现指代，同轮前文即已给出具体对象 → 来源 `same_turn` 成立。**这是「不许误伤自主升级」的落点** |
| S11（`/cloud off`） | `deny_cloud` 不改变护栏判定；S11 输入无标记 |
| S14（文件确认） | 「里面」等方位指代已排除；`notes/deploy.md` 在同轮前文已具名 |
| S15 / S16 | 输入无标记 / 场景为会话收尾 |

（已核验：S08 的 `该结论` 与 S13 的 `这份堆栈转储` 命中 M1 但**窗口内无封闭集成员 → fail-open**，故不触发；若将来把 `结论`/`根因` 一类加入 `_EXTERNAL_OBJECT_NOUNS`，表 A 里**会**新增触发的是 S08——**那才是需要重新裁决的回归**，因为它是非 force 轮。）

**表 B：`force_cloud` 轮（S10 / S12 / S13），**不**断言检测结果，只断言动作**：

| 场景 | 检测结果 | 硬门 |
|---|---|---|
| S10 | 无标记（`我们` 已排除）→ `not_triggered` | 最终动作 = `REQUEST_CLOUD` |
| **S12** | **`这份配置` 命中 M1，窗口内含 `配置` ∈ `_EXTERNAL_OBJECT_NOUNS`，同轮前文/历史/项目状态均无该候选 → 必然 `triggered`** | 最终动作 = `REQUEST_CLOUD`（**护栏只观测、不拦截**） |
| S13 | `这份堆栈转储` 命中 M1 但窗口无封闭集成员 → fail-open `not_triggered` | 最终动作 = `REQUEST_CLOUD` |

> **S12 是本表存在的直接原因**（2026-09-16 第三轮审查）：早期写法把 S10/S12/S13 一并放进「必须 `not_triggered`」的表 A，而 S12 的**指令载荷本身**含 `这份配置`——slash 指令头虽被剥离，**载荷不剥离**（`_parse_cloud_control()` 返回的是任务文本）。于是「S12 必须 `not_triggered`」是一条**必然失败**的红线。修正的不只是这一行：**force 轮的护栏行为本身就是「照常评估、照常记录、只在动作上让位」**（§1.3 的精确含义），因此**对 force 轮断言检测结果在原理上就是错的**——它既测不出误伤（force 轮不可能被拦），又对检测器的任何正常演化过敏（如封闭集扩容）。表 B 只保留唯一有意义的不变量：**动作不被改写**。
>
> **反向风险同样要防**：不得因为「反正 force 轮让位」就把护栏在 force 轮**跳过计算**——那样 `reference_guard_result` 会退化成 `not_evaluated`，与 §5.1 冲突，且团队将失去「载荷里有多少悬空指代」这个观测（S12 正是唯一能稳定产出 `triggered` 的场景）。

### 6.5 定向复现验收（观测验收，不进 pytest）

S02 的 `round1`/`round4` 各 **≥3 run**，在**回滚后**的代码上执行（`clarifications.md` 已记录上一轮「基于临时改动得到的 S02 结果作废」）。判据：`failed == 0`。这是**观测验收**——阈值绑定随机模型输出，**不写进 pytest**（沿用 `10-p6d` §7.3 口径）。

---

## 7. 测试矩阵

### 7.1 纯函数（`tests/test_reference_guard.py`，无模型、无 IO）

| # | 测试 | 断言 |
|:--:|---|---|
| 1 | `test_dangling_demonstrative_np_is_triggered` | 「把那个服务发布上去。」无 history/state → `triggered is True`，`resolved_by == "none"`，`marker_text == "那个服务"`【需求 1】 |
| 2 | `test_self_referential_np_is_not_triggered` | 「把这段话翻译一下，它是什么意思。」→ `triggered is False`，`resolved_by == "self_referential"`【需求 2】 |
| 3 | `test_same_turn_antecedent_resolves` | 「刚才说的是支付服务，把那个服务发布上去。」→ `resolved_by == "same_turn"`【需求 3】 |
| 4 | `test_history_resolves` | 测试 1 输入 + `relevant_history=["我们讨论过支付服务。"]` → `resolved_by == "history"`。**历史必须含候选词**——写 `["…"]` 这类占位内容是空测 |
| 5 | **`test_unrelated_history_does_not_resolve`** | 测试 1 输入 + `relevant_history=["今天讨论天气。"]` → `triggered is True`——**锁定「历史非空即解析」的废止**（§2.3 否决表第 2 行） |
| 6 | **`test_project_id_alone_does_not_resolve`** | 测试 1 输入 + `project_state={"project_id": "p-1"}` → `triggered is True`——**锁定 P5 `auto_create` 导致的必然假解析**（§2.3 否决表第 3 行）。本项与第 7 项成对，缺一即无法证明实质字段白名单生效 |
| 7 | `test_substantive_project_state_resolves` | 测试 1 输入 + `project_state={"summary": "目标是发布支付服务"}` → `resolved_by == "project_state"`【需求 4】 |
| 8 | **`test_filler_prefix_does_not_resolve`** | 「明天再把那个服务发布上去。」→ `triggered is True`——**锁定「剩余字符 ≥2」的废止**（§2.3 否决表第 1 行） |
| 9 | `test_bare_pronoun_at_turn_start_is_triggered` | 「把它删掉。」→ `triggered is True` |
| 10 | `test_second_marker_resolved_by_antecedent` | 「刚才说的是支付服务，把那个服务发布上去，然后把它删掉。」→ `triggered is False` |
| 11 | **`test_bare_pronoun_cannot_invent_its_own_antecedent`** | 「把那个服务发布上去，然后把它删掉。」无 history → `triggered is True`。**早期草案在此判「不触发」是错的**：第二个标记不能为首个标记凭空造出先行词（首个标记本就悬空） |
| 12 | `test_first_and_second_person_pronouns_are_excluded` | 「把我们系统的数据迁移到新集群。」→ `triggered is False` |
| 13 | `test_topic_routing_reference_is_excluded` | 「继续之前的话题：把检查清单列出来。」→ `triggered is False`（P5 职责） |
| 14 | `test_discourse_anaphora_without_context_is_triggered` | 「按上述执行。」无 history → `triggered is True` |
| 15 | **`test_unrecognized_center_noun_fails_open`** | 「把那个什么来着发布上去。」→ 8 字符窗口内无封闭集成员 → `triggered is False`（§2.2 fail-open，把「不声称完备」钉成断言） |
| 15b | **`test_bare_demonstrative_without_center_noun_fails_open`** | 「把那个删掉。」无 history → `triggered is False`。**锁定 M2 撤回**：这一行与上一行在表面上不可区分，必须同判（§2.2「M2 的并入」） |
| 16 | **`test_window_boundary_still_finds_center_noun`** | 「把那个刚部署好的服务发布上去。」→ `triggered is True`（中心语落在窗口边界内；锁定 8 字符窗口不会把常见形态漏掉） |
| 17 | **`test_marker_text_is_first_unresolved_marker`** | 「把那个服务发布上去，然后把它删掉。」→ `marker_text == "那个服务"`（§2.2 多标记规则） |
| 18 | **`test_detector_accepts_no_model_derived_input`** | **结构测试**：`inspect.signature` 的参数名与注解中不出现 `candidate`/`entities`/`missing_info`/`final_state`/`risk_draft`/`suggested_tools`/`consultation_proposal`/`IntentCandidate`；且 **`state` / `project_state` 必须用完整词比对**（参数名精确相等，不得子串匹配）——把 §1.2/§3.2 的决策钉成可证伪断言，防止后人加入模型侧抑制源。**同时断言 `project_state` 参数存在**，防止把「不得读项目状态」误读成契约 |
| 19 | `test_self_referential_noun_set_excludes_external_entities` | 结构测试：`_SELF_REFERENTIAL_NOUNS` 与 `_EXTERNAL_OBJECT_NOUNS` **交集为空**（把 §2.2 的准入规则钉死） |
| 20 | `test_resolved_by_is_a_closed_set` | 枚举覆盖全 5 值，且未命中时为 `"none"` |
| 20b | **`test_non_referential_compounds_never_trigger`** | **全表覆盖**：遍历 `_NON_REFERENTIAL_COMPOUNDS` 每个成员，构造 `<成员>服务要重启。` → 全部 `triggered is False`（`因此服务` 这类「构词成分 + 封闭集名词」不得被当成 M1）。**外加位置性对照**：「因此那个服务要重启。」→ `triggered is True` 且 `marker_text == "那个服务"`——锁定排除是**按位置**生效、不是按句子生效 |
| 20c | **`test_center_noun_must_be_adjacent_or_after_first_de`** | **M1 两域锁**（§2.2）：① 域 A：`那个服务发布上去。` → `triggered is True`；② 域 B：`那个刚部署好的服务发布上去。` → `triggered is True` 且 `marker_text == "那个刚部署好的服务"`；③ 反例：`这项工作交给系统处理。` → `triggered is False`（`工作` 不在集内，不得跨越到下一个 NP 的 `系统`）。**必须含第 ③ 条**——缺它则「张冠李戴」这个缺陷无锁 |
| 20d | **`test_compound_exclusion_also_applies_to_pronouns`** | M3 路径同表排除：「其他任务怎么处理。」/「其它任务怎么处理。」/「其他人呢？」→ 全部 `triggered is False`。**必须含 `其它`**——它是 `其他` 的等义变体，只处理 `其他` 会留下同形漏洞 |
| 20e | **`test_discourse_anaphora_uses_whole_turn_excluding_own_window`** | **M4 搜索域五形态锁**（§2.3）：① 「刚才说的是支付服务，把那个服务发布上去。」→ `triggered is False` 且 `resolved_by == "same_turn"`（**与第 3 项成对**——第 3 项锁整句判定，本项锁它是**靠整轮域解析**而不是靠跳过标记）；② 「上述配置需要复核。」→ `triggered is True`（`配置` 落在标记自身的 8 字符窗口内，不得解析）；③ 「前面提到的 3 个用例。」→ `triggered is True`（同上，且**证明不是靠「紧邻」而是靠窗口**——`用例` 与标记之间隔着 ` 3 个`）；④ 「刚才说的是什么？」→ `triggered is True`（**证伪锁**：删掉首轮的「后接 `是` 就跳过」补丁后，这一形态不得跟着变成「不触发」）；⑤ 「上述是模型输出。」→ `triggered is True` 且 `marker_text == "上述"` |

### 7.2 决策层（`tests/test_control_policy.py`）

| # | 测试 | 断言 |
|:--:|---|---|
| 21 | `test_reference_guard_preempts_cloud_admission` | `READY` + proposal + `expected_benefit=0.9` + 云端可用（单跑 `evaluate_cloud_admission` 得 `admitted_proposal`）→ 传 `triggered=True` → `action == "ASK_USER"`、`reason == "dangling_reference"`、`requires_user_confirmation is False`；**且同用例内断言 `evaluate_cloud_admission` 仍返回 `admitted_proposal`**（准入判断未被污染）【需求 6】 |
| 22 | `test_reference_guard_yields_to_forced_cloud` | `cloud_state.force_cloud=True` + `triggered=True` + 有任务文本 → `action == "REQUEST_CLOUD"` |
| 23 | `test_dangerous_preempts_reference_guard` | `risk_draft="dangerous"` + `triggered=True` → `action == "REFUSE"` |
| 24 | `test_absent_reference_guard_preserves_existing_behavior` | 不传 `reference_guard` → 与既有断言逐字相同（`READY`+proposal → `REQUEST_CLOUD`；`VAGUE`+`missing_info` → `RETRIEVE_MORE`）——**P0-P5 行为不变的可证伪断言** |
| 25 | `test_not_triggered_reference_guard_proceeds_normally` | `triggered=False` → 走正常准入（`REQUEST_CLOUD`） |

### 7.3 App 层（`tests/test_main.py`）

| # | 测试 | 断言 |
|:--:|---|---|
| 26 | `test_scheduling_turn_reports_evaluated_guard` | **正常任务调度回合**（非确认恢复）的 `dispatch_decision.reference_guard_result ∈ {"not_triggered","triggered"}`，从不为 `not_evaluated`（§5.1） |
| 27 | **`test_confirmation_resume_reports_not_evaluated_guard`** | 确认恢复回合的 `dispatch_decision`：`reference_guard_result == "not_evaluated"` **且** `proposal_gate_result == "not_evaluated"`，`reason ∈ _CONFIRMATION_REASONS`——**锁定这个合法例外**，防止后人用伪造 `not_triggered` 来「修掉」它（§5.1） |
| 28 | `test_reference_guard_does_not_modify_candidate` | 护栏触发后，`candidate.state`/`entities`/`missing_info`/`suggested_tools` 与模型原始输出**全等**（§3.3）【需求 5】 |
| 29 | `test_dangling_reference_ask_user_reply_names_the_reference` | 触发时回复在模型侧文案**之后**追加规则生成行且含被截断的标记文本；`candidate.missing_info` **未被改写** |
| 30 | `test_guard_triggered_event_carries_no_marker_text` | 落盘 JSONL 行中**不含** `marker_text`、不含场景输入原文片段（§5.2；沿用 P6b 的铁律 4 检验） |
| 30b | **`test_force_cloud_turn_records_triggered_but_still_requests_cloud`** | **App 级「观测 vs 让位」证伪锁**（§1.3 精确含义、§6.4 表 B）：输入 `/cloud ask 排查这份配置的鉴权失败原因……` → **同一条** `dispatch_decision` 事件里 `reference_guard_result == "triggered"` **且** `action == "REQUEST_CLOUD"`。两个断言缺一不可：只有前者不能证明让位（护栏可能根本没接线），只有后者不能证明护栏被评估过（可能被实现成 force 轮跳过计算 → 退化成 `not_evaluated`）。本项与 §7.2 第 22 项成对——22 锁决策层纯函数行为，本项锁**事件流里的事实**。可直接套用既有强制链测试的构造（`tests/test_main.py:636` 一带：`bootstrap(..., model_backend_override=...)` + `app.cloud_enabled = True` + 注入 `CloudAdvisoryService`），输入换成 `/cloud ask 排查这份配置的鉴权失败原因：api_key=sk-EVAL-FAKE-000000-DEADBEEF。`，只多断言事件字段 |

> **第 26/27 项的落点说明（2026-09-16 第四轮审查补）**：本表的文件名是**建议落点**，不是验收判据——判据是**断言存在且非空转**。首轮实现把第 26 项折进 `test_handle_emits_ordered_runtime_events_and_one_completion`（`tests/test_main.py:268`）、把第 27 项放在 `tests/test_p6a_scenarios.py:106-108`（同时断言 `proposal_gate_result == "not_evaluated"` 与 `reason == "confirmation_verified"`），**已验收通过，不需搬迁**。真正缺的是**第 30 项**（见 §8 第 7 步）。

### 7.4 场景 schema（`tests/test_p6_scenarios_runner.py`）

| # | 测试 | 断言 |
|:--:|---|---|
| 31 | `test_reference_guard_any_is_accepted_and_closed` | `expect.reference_guard_any` 合法且须为 bool；未知键仍被拒绝 |
| 32 | **`test_reference_guard_any_not_evaluated_is_structural_failure`** | 事件流中该 step 的 `reference_guard_result` 全为 `not_evaluated` 时，`reference_guard_any=false` **不得**判通过（§6.1） |
| 32b | **`test_s02_attribution_requires_triggered_for_guard_rescued`** | 四态归因纯函数：`action=ASK_USER` + 候选**未**表达澄清（如 `final_state="READY"`）+ `reference_guard_result="not_triggered"` → 归因为 **`unattributed_ask`**，**不得**为 `guard_rescued`。**这是实现前审查第 2 项的证伪锁**——缺它则「护栏完全失效但兜底率依然漂亮」无法被发现 |

### 7.5 定向复现（不进 pytest）

| # | 项 | 判据 |
|:--:|---|---|
| 33 | S02 `round1` × ≥3 run + `round4` × ≥3 run | `failed == 0`；四态（`model_asked`/`guard_rescued`/`unattributed_ask`/`failed`）分布记录进报告；**每 run 的 `reference_guard_any` 必须为真**（硬门 2）且**每 run 至少一个非 `not_evaluated` 的 `reference_guard_result`**（§6.2 接线自检） |

---

## 8. 实现清单（Codex）

**顺序执行；每步完成即可跑对应测试。**

| 步 | 动作 | 文件 |
|:--:|---|---|
| 1 | 新建 `src/core/reference_guard.py`：`ReferenceGuardResult` + `detect_unresolved_reference()` + 封闭集（`_REFERENCE_MARKERS` / `_QUANTIFIERS` / `_EXTERNAL_OBJECT_NOUNS` / `_SELF_REFERENTIAL_NOUNS` / `_NON_REFERENTIAL_COMPOUNDS`）+ `_CENTER_WINDOW = 8` + `_PROJECT_STATE_SUBSTANTIVE_KEYS`。**模块 docstring 必须写明**「不声称完备」「`_SELF_REFERENTIAL_NOUNS` 的准入规则」「未识别形态 fail-open」与「M1 两域、`_NON_REFERENTIAL_COMPOUNDS` 按位置排除」（§2.1/§2.2） | 新增 |
| 2 | 补 §7.1 全部 **25** 项纯函数测试（含 15b M2 撤回锁 + 20b/20c/20d/20e 第四轮四项） | `tests/test_reference_guard.py`（新增） |
| 2b | **第四轮审查的五处实现修正**（§2.1/§2.2/§2.3 已同步）：① 新增 `_NON_REFERENTIAL_COMPOUNDS` 并按**位置**对 M1/M3 两条路径统一排除——**删除现有那个只对整串 `其他` 生效的相等判断**（`reference_guard.py:159`，实测 `其他任务/其它任务/其他人` 全部漏过）；② M1 中心语限定为**两域**（紧邻起点 / 第一个 `的` 之后），其余位置不承认；③ M4 的 `same_turn` 搜索域改为**整轮文本 − 标记起始位置起 8 字符窗口**，并**删除**「后接 `是` 则跳过」（`reference_guard.py:152`）——注意这两件事**必须同批做**：只删补丁会打破 §7 第 3 项；④ M3 的搜索域**保持前缀域不变**（§7 第 11 项）；⑤ 删除死代码 `unresolved_spans` / `_without_spans`（循环在首个未解析标记处 `return`，该列表恒为空） | `src/core/reference_guard.py` |
| 3 | `ControlPolicy.decide()` 增仅限关键字参数 `reference_guard: ReferenceGuardResult \| None = None`，按 §1.3 表把护栏插到第 2 步；新增 `reason="dangling_reference"` | `src/core/control_policy.py` |
| 3b | **同步工程契约签名**（接口签名属 Claude 主导，本契约已授权；签名块见下）：`decide()` 增 `reference_guard` 参数与 docstring 说明 | `specs/modules/00-adapter-factory.md:479` |
| 4 | 补 §7.2 全部 5 项决策层测试 | `tests/test_control_policy.py` |
| 5 | App：在 `decide()` 调用前用 `context` 调 `detect_unresolved_reference()` 并传入；`_handle_action` 的 `ASK_USER` 回复在护栏触发时追加规则行（**新增参数须仅限关键字 + 有默认值，默认路径逐字节不变**，沿用 `_build_local_reply` 的 P6d 手法） | `src/main.py` |
| 6 | `dispatch_decision` 事件增 `reference_guard_result`，并加进 07 §2.2 的键白名单封闭集。**两处白名单必须同步改**（漏一处即事件被静默丢弃） | `src/main.py:1357`（`_EVENT_FIELDS`）+ `src/observability/sinks.py:34`（`_PERSISTED_KEYS`） |
| 7 | 补 §7.3 全部 **6** 项 App 层测试（**含第 27 项确认恢复例外**——`_handle_confirmation` 的 6 处 `_record_dispatch_event` 一律传 `reference_guard=None`，**不得**改为伪造 `not_triggered`；**含第 30b 项 force 轮「如实记录但不让位」**——`/cloud ask` 载荷含 `这份配置` 时事件须 `triggered` + `REQUEST_CLOUD` 并存，**不得**在 force 轮跳过护栏计算；**含第 30 项落盘检验**——首轮实现遗漏了这一项，`_PERSISTED_KEYS` 白名单目前正确但**无测试锁住**，任何人把投影改成 `asdict()` 都会把 `marker_text` 写进 JSONL 而无红） | `tests/test_main.py`（第 27 项的断言位置可在 `tests/test_p6a_scenarios.py`，见 §7.3 备注） |
| 8 | 提示词：`_build_prompt` 增 P11 规则文本与 E6 示例（措辞可调，语义不可省）；补断言 P11/E6 文本存在的测试 | `src/core/intent_resolver.py`、`tests/test_intent_resolver.py` |
| 9 | `expect` 增 `reference_guard_any`（加入 `_EXPECT_KEYS` 与 bool 校验组，对标既有 `degradation_any`）；在求值器里按 §6.1 语义实现（含 `not_evaluated` → 结构性失败）；补 §7.4 全部 **3** 项测试 | `src/evaluation/scenarios.py:44,351` + `src/evaluation/runner.py`（`_evaluate`，对标 `degradation_any` 分支）、`tests/test_p6_scenarios_runner.py` |
| 9b | **S02 场景加硬断言**：`scenarios/S02_ask_user_when_insufficient.toml` 的 `expect` 增 `reference_guard_any = true`（§6.2 硬门 2）。这是覆盖脚本改动，须与步骤 9 的求值器同批落地，否则前置断言会先失败。**只改 S02**——S10/S12/S13 **不得**加任何 `reference_guard_any` 断言（§6.4 表 B） | `scenarios/S02_ask_user_when_insufficient.toml` |
| 10 | 报告增 `reference_guard_result` 分布 + S02 **四态**（`model_asked`/`guard_rescued`/`unattributed_ask`/`failed`，后三者独立成行，**不得**合并）+ `should_consult` 独立观测项 | `scripts/p6_report.py` |
| 10b | **四态归因纯函数**（`model_asked` 只看候选与动作、`guard_rescued` 须 `triggered`、其余 `ASK_USER` 落 `unattributed_ask`）与其测试 §7.4 第 32b 项 | `src/evaluation/runner.py` 或其报告模块、`tests/test_p6_scenarios_runner.py` |
| 11 | 全量 `pytest -q` + `ruff` + `mypy` | —— |
| 12 | 按 §6.5 跑 S02 定向复现（各变体 ≥3 run，**必须验证硬门 2 在真实 run 上成立**），结果并入 `08` 报告 | —— |

**不做**：不改 `is_effectively_ready()`、不改 `evaluate_cloud_admission()` 的任何分支、不改 `IntentResolver` 的解析与提前返回逻辑（只加提示词文本）、不改模型字段、不改 `_handle_confirmation` 的行为（只在步骤 6 补事件键）、不动任何安全边界。

**第 3b 步的目标签名**（替换 `00-adapter-factory.md:479` 的 `ControlPolicy` 块；`decide()` 增参属**接口签名变更**，按 CLAUDE.md 变更分类表由 Claude 主导、已在本契约授权）：

```python
# ── ControlPolicy ──
class ControlPolicy:
    def __init__(self) -> None: ...
    def decide(
        self,
        candidate: IntentCandidate,
        cloud_state: CloudControlState | None = None,
        *,
        resolution_exhausted: bool,                     # 必传，无默认值（14 §3.1/§3.2）
        no_progress: bool = False,
        reference_guard: ReferenceGuardResult | None = None,
    ) -> NextAction:
        """P4 起 App 每轮必传 cloud_state；P6d 由 no_progress 阻止空转检索。
        P6d 悬空指代护栏：reference_guard 由 App 用 MinimalContext 计算后传入
        （11-reference-guard.md）；为 None 时记 not_evaluated，不得默认成 not_triggered。
        P6 轮次用尽：resolution_exhausted 由 App 转发 resolver.last_resolution_exhausted
        （14-resolution-exhausted.md），决定是否落入 ASK_USER 而非 RETRIEVE_MORE；
        位置参数 round_count 已于 2026-09-17 随「超轮次不走云端」一并删除（14 §3.1）。
        """
```

---

## 9. 决策表

| 日期 | 决策 | 内容 |
|---|---|---|
| 2026-09-16 | **护栏层归属：独立纯函数 + `decide()` 实施优先级** | 见 §1.1。否决放进 `IntentResolver`（解析器 `READY` 提前返回，护栏须在其后仍生效；且会模糊「三个判断」归属）、否决在 `ControlPolicy` 内自算（`decide()` 无上下文输入，注入 `MinimalContext` 会把纯规则模块耦合到上下文装配）、否决新建 `ReferenceResolver` 类（无状态纯函数，类只增构造面） |
| 2026-09-16 | **判定输入不含任何模型侧字段** | 见 §1.2。让模型输出抑制护栏＝把「模型过度自信」复制进安全网；证据 §0.1 形态 2（`missing_info` 为空仍失败）直接证伪以 `missing_info` 为输入的方案。用**结构测试**钉死签名（§7 第 18 项） |
| 2026-09-16 | **优先级：dangerous > 护栏 > 云端准入（判定保持如实）** | 见 §1.3。护栏在准入判断**之后**改写动作，使 `proposal_gate_result` 仍如实报告准入判定、`action` 报告实际动作——「判定」与「动作」分开才能看见「模型提议+准入通过+被护栏拦下」 |
| 2026-09-16 | **`force_cloud` 轮护栏让位**（让位的是动作，不是评估） | 用户显式指令优先于规则对「你没说清楚」的判断；云端只读无执行权，让位无副作用风险。同时消除 S10/S12/S13 强制链的**动作**回归风险。**2026-09-16 第三轮修正**：原写法被读成「force 轮的检测结果也应为 `not_triggered`」并写成了回归红线，而 S12 载荷含 `这份配置` → 必然 `triggered`（`_parse_cloud_control()` 只剥离指令头、不剥离载荷）→ **必然失败的红线**。force 轮的正确不变量只有「动作不被改写」＋「护栏未被跳过计算」，见 §6.4 表 B 与 §1.3 的精确含义；测试锁 §7 第 30b 项 |
| 2026-09-16 | **`entities` 不作为「抑制来源」**（收窄用户在需求中列举的四来源之一） | 需求列出「当前句 / relevant_history / project_state / entities」四来源待裁决。**裁决：前三者成立，`entities` 不参与判定**——它是模型输出，而 §0.1 的 6/6 失败正是模型自称 `READY`；用模型的 `entities` 抑制安全网会复制同一缺陷。`entities` 若需使用，只允许作为**触发时的佐证记录**，不得抑制 |
| 2026-09-16 | **标记集封闭且显式不声称完备** | 见 §2.1。只主张可证伪的强命题「封闭集内的指代在来源全空时必被追问」；漏检后果＝退回既有行为（不劣于现状），不是安全漏洞。同时**显式排除** 我/我们/你/你们、本、话题路由指代、方位指代（各有理由，不得作为「覆盖不全」上报） |
| 2026-09-16 | **`_SELF_REFERENTIAL_NOUNS` 的准入规则** | 见 §2.2。只允许「只能指称本轮语言材料本身」的名词；收录任何可指称外部实体的名词都是缺陷。用**结构测试**钉死（§7 第 19 项） |
| 2026-09-16 | **观测：`dispatch_decision` +1 键，`marker_text` 永不落盘** | 见 §5。`not_evaluated` 与 `not_triggered` 分开（沿用 P6d 教训：默认值会把接线缺陷静默统计成正常）；`marker_text` 是用户输入片段，属既有禁入清单 |
| 2026-09-16 | **S02 四态分离，兜底不计入模型主动追问；行为门 + 确定性保证门双硬门** | 见 §6.2。四态按序判定，**引用护栏字段的只有归因态**：① `model_asked` 是**模型能力判据**，只看模型候选与最终动作、**不含护栏字段**（否则模型即便改进也会被规则静默抹掉）；② `guard_rescued` / ③ `unattributed_ask` 是**归因**，必须引用 `reference_guard_result`（否则任何路径的 `ASK_USER` 都会被记成兜底，兜底率在护栏失效时依然漂亮）。**「态判定不含护栏字段」只对 ① 成立，不得推广到全表**（早期表述过宽，已收窄）。场景侧另加硬断言 `reference_guard_any = true`（护栏在 S02 输入上确定性命中，属**输入的性质**，与模型能力无关，故不会永久红——早期以「会永久红」为由拒绝该断言已推翻） |
| 2026-09-16 | **提示词与规则分层：提示词是质量路径，规则是保证路径** | 见 §4。P11 + E6 让模型自己发现（要观测的能力）；护栏保证行为正确。**明确拒绝**把提示词当唯一保证 |
| 2026-09-16 | **拒绝「模型调用前先跑护栏」的省轮次优化** | 该方案能在纯悬空轮次省一次模型调用，但会让「模型本来会不会自己追问」**永远不可观测**——`model_asked` 的分母消失，本契约要测的能力无法证伪（与 `10-p6d` §2.1 情形 3 拒绝「模型可选本地」同一理由）。故护栏在**首轮模型输出之后**运行 |

### 9.1 实现前审查（两轮；Codex 提出，Claude 逐项实测后全部采纳）

**第一轮（5 项）**

| 日期 | 决策 | 内容 |
|---|---|---|
| 2026-09-16 | **`model_asked` 判据删去 `reference_guard_result = not_triggered`** | 护栏不读模型字段，而 S02 的条件使护栏**每 run 确定性命中** → 原判据使 `model_asked` **永远不可达**，模型即便 P11 后正确输出也被记成 `guard_rescued`——原缺陷的镜像（规则从「静默保送」变成「静默抹掉成绩」）。改判据只看**模型候选自身**（`final_state ∈ {VAGUE,PARTIAL}` 且 `missing_info_count > 0`）。`should_consult` 拆为**独立观测项**（送不可答任务上云的误判率），理由见 §6.2 |
| 2026-09-16 | **来源判定从「非空即解析」改为「候选指称词出现在该来源中」** | 三项实测反例：① 同轮「剔虚词后剩余 ≥2 字符」是「有前文」的代理不是判据（`明天再把那个服务发布上去` 误放行）；② `history` 非空即算（`今天讨论天气` 误放行）；③ **`projects.auto_create = true` 是全部配置含评估基线的默认值**（`config/eval.example.toml:36`），`_project_state_dict()`（`context_assembler.py:107-110`）恒返回非空 `{project_id, summary}` → **每一次真实运行与评估 run 中护栏都永不触发**（不是「可能长期不工作」而是必不工作）。新增 `_PROJECT_STATE_SUBSTANTIVE_KEYS` 白名单（`project_id`/`title`/`status`/时间戳不算），并把三条反例各钉一条测试（§7 第 5/6/8 项） |
| 2026-09-16 | **`H 提取` 改为「封闭集成员在 8 字符窗口内的查找」** | 「指示词之后紧邻的名词」在无分词器条件下**无定义**（`那个服务发布上去` 无法判定中心语是 `服务`/`服务发布`/`服务发布上去`）。改为封闭集 + 定长窗口 + 最长匹配 + 取最早命中；窗口内无命中 → **fail-open 不触发**（§2.2）。补多标记规则（任一标记未解析即触发，`marker_text` 取第一个未解析标记） |
| 2026-09-16 | **纠正「`decide()` 签名不变」的错误表述，授权签名变更并同步 00 契约** | 新增仅限关键字参数**就是**接口签名变更（CLAUDE.md 变更分类表，Claude 主导）。原表述见 `clarifications.md`（本条与状态快照）与本契约 §8，**已改**；`00-adapter-factory.md:479` 的签名块由 §8 第 3b 步同步。（`clarifications.md` [2026-09-14] P4 条目里的同一句话**不改**——那里 `decide()` 确实未变，仅 `CloudControlState` 增默认值字段） |
| 2026-09-16 | **`not_evaluated` 收窄为「未进入正常意图调度的回合」** | 实测：`_handle_confirmation()`（`main.py:632-689`）在 **6 处**发出 `dispatch_decision`，全部携带 `CloudAdmissionDecision(False, "not_evaluated")`，且该路径**不调用 `decide()`**。原「真实报告中不得出现」与之一处冲突。改为「**正常任务调度回合**不得出现」，并要求**不得伪造 `not_triggered`**；判据与反向断言成对（§5.1、§7 第 26/27 项） |

**第二轮（4 项：2 阻塞 + 2 同步残留）**

| 日期 | 决策 | 内容 |
|---|---|---|
| 2026-09-16 | **撤回 M2 的保证，统一 fail-open**（阻塞项 1） | 见 §2.2「M2 的并入」。`把那个删掉`（M2：指示词 + 量词、无中心语）与「有中心语但名词不在封闭集内」（未识别 M1）在**窗口上看不出差别**——都是「那个 + 8 字符内无封闭集成员」。要在不引入分词器/动作词表的前提下确定性区分二者，只能新增**封闭动作后缀规则**，那会把动作词表引进本契约（超出「薄契约、不引入通用 NLP」的边界）。**裁决：v1 直接删除 M2 的保证**，两种形态统一 fail-open 不触发。代价＝`把那个删掉` 退回模型判断，**不劣于本契约之前的状态**。已核对 16 场景：**无一依赖 M2**（只有 S02 含裸「那个」，且它是 M1）。测试锁：§7 第 15b 项（与第 15 项成对——两行必须同判）；恢复前置条件登记于 §10.2 |
| 2026-09-16 | **`guard_rescued` 必须显式要求 `reference_guard_result = triggered`；新增 `unattributed_ask`**（阻塞项 2） | 见 §6.2。原定义把 ② 写成「`ASK_USER` 且非 ①」的**补集**，于是**任何**其它路径的 `ASK_USER` 都被记为「护栏救援」——实测路径：`state=READY` 且 `missing_info` 非空时 `_decide_ready()` 自身返回 `ASK_USER`（`project-plan.md` 决策表第 3 行），此时护栏可为 `not_triggered`，② 仍会点亮 → **兜底率在护栏完全失效时依然漂亮**。改为 ② 须 `triggered`；既不属模型表达、也不属护栏触发的 `ASK_USER` 单列 **③ `unattributed_ask`**（归因失败信号，**不计入**兜底率也不计入模型成功率）。测试锁：§7 第 32b 项。另：`model_asked` 的判据**保持不含**护栏字段（第一轮已定）——两处结论并存的原因是用途不同：态判定评价**模型**，场景断言验证**护栏** |
| 2026-09-16 | **S02 加硬断言 `reference_guard_any = true`，同时**推翻**早期「会永久红」的拒绝理由**（阻塞项 2 后半） | 见 §6.2。S02 输入固定「把那个服务发布上去。」、无先行轮次、`relevant_history` 为空、`project_state` 仅 `{project_id, summary=""}` → 护栏**确定性命中**，且护栏**不读任何模型字段**。因此「护栏触发」是**输入的性质**而非模型能力的性质，断言它**不会**随模型不改进而永久红——早期拒绝理由只对「护栏行为取决于模型」的场景成立，而本契约从构造上排除了这种可能。加上后 S02 才真正验证**确定性保证路径在工作**：`action_any=["ASK_USER"]` 只是行为门，`reference_guard_any=true` 才是**确定性保证门**，挡住「检测器错误返回 `not_triggered`、而 `ASK_USER` 由别的路径给出」这一整类假通过。覆盖脚本改动＝§8 步骤 9b |
| 2026-09-16 | **修正两处同步残留** | ① `08-p6b-evaluation-loop.md:159` 仍要求 S02 `missing_info` 非空——与 §6.2 的四态冲突（`guard_rescued` 允许 `missing_info` 为空）。改为「**只有 `model_asked` 要求 `missing_info` 非空**」。② `clarifications.md:41` 仍提 `_FUNCTION_WORDS`（已从本契约整体移除，§2.2）且「不再靠词表收口」与新增的 `_EXTERNAL_OBJECT_NOUNS` 不一致。改为「**封闭候选集 + 来源匹配**」，并说明封闭集本身就是词表、被收回的是**虚词表**而非词表路线 |

**第三轮（1 项实际阻塞 + 3 处文字同步）**

| 日期 | 决策 | 内容 |
|---|---|---|
| 2026-09-16 | **force 云端场景与回归红线矛盾 —— 成立，且是必然失败的红线**（阻塞） | 见 §6.4 表 A/表 B 与 §1.3 的精确含义。`scenarios/S12_outbound_redaction.toml:22` 的载荷是 `排查这份配置的鉴权失败原因…`：`这份配置` 命中 M1、窗口内含 `配置` ∈ `_EXTERNAL_OBJECT_NOUNS`、同轮前文/历史/项目状态均无该候选 → **必然 `triggered`**；而 `force_cloud=True` 只是不把动作改写成 `ASK_USER`。原写法要求 S12 `reference_guard_any=false` → 每次运行必红。**修正**：① 把 S10/S12/S13 从「必须 `not_triggered`」移出；② force 轮改为断言**动作** `REQUEST_CLOUD` ＋ 检测结果**不作断言**（S12 必然 triggered，S10/S13 fail-open 不触发，都不该固定）；③ 新增**动作不变量**「护栏只观测、不拦截」＋**反向约束**「不得在 force 轮跳过护栏计算」（否则退化成 `not_evaluated`，与 §5.1 冲突，且抹掉「载荷里有悬空指代」这个事实）；④ 决策层第 22 项保留，**补 App 级第 30b 项**——同一条事件里 `triggered` 与 `REQUEST_CLOUD` 必须并存。**根因**：让位被读成了「检测结果也应为 not_triggered」，而 force 轮的 `_parse_cloud_control()`（`main.py:268,327`）只剥离指令头、**不剥离载荷**——任务文本照常进 `detect_unresolved_reference()` |
| 2026-09-17 | **§3.1 判定顺序表改版**（`14-resolution-exhausted.md` §4）：删除原第 3 行「`not_evaluated`（超轮次）→ ASK_USER」，新增第 6 行「`resolution_exhausted` → ASK_USER」 | 原超轮次规则不可达且位置错误（在准入门内、无 force 豁免），已随 `evaluate_cloud_admission()` 的轮次参数一并删除；`not_evaluated` 的来源收窄为唯一（dangerous），第 1 行判据随之收敛。**护栏的相对位置与让位语义完全不变**（仍是第 2 行，仍在准入之前）；轮次用尽排在护栏与准入**之后**，故 force 轮照旧 `REQUEST_CLOUD` |
| 2026-09-16 | **「四态之和 = run 总数」取代「三数之和」**（文字同步） | 见 §6.2 与 `08-p6b` §2.7、§6 G1。四态互斥完备，四态之和是**恒等式**；写成「三数之和」等于预先假设 `failed == 0`——而那正是硬门 1 要验的命题，不能写进验收判据 |
| 2026-09-16 | **「态判定不含护栏字段」收窄为「只有 `model_asked` 的能力判据不含护栏字段」**（文字同步） | 见 §6.2 的限定说明与 §9 对应行。② `guard_rescued` **必须**依赖 `reference_guard_result = triggered`（第二轮刚定的），③ 又依赖 ②，因此原表述过宽、自相矛盾。混同的代价不对称：① 加回护栏字段 → 模型成绩被抹掉；② 去掉护栏字段 → 兜底率虚高。两处都必须保持 |

**第四轮（实现后代码审查：2 项假阳性方向阻塞 + 1 项排除逻辑失效 + 1 项我方契约 bug；均已实测复现）**

| 日期 | 决策 | 内容 |
|---|---|---|
| 2026-09-16 | **新增封闭固定搭配排除集 `_NON_REFERENTIAL_COMPOUNDS`**（阻塞：**误伤方向**） | 见 §2.1。`_DEMONSTRATIVE_RE = [这那该此]` 是**字符级**匹配，于是把**构词成分**当成了**指示限定词**，实测（e2e 走 `decide()` 后动作确实变成 `ASK_USER / dangling_reference`）：`应该先看一下日志再决定。`→`marker_text="该先看一下日志"`、`因此服务需要重启。`→`"此服务"`、`如此配置就能生效。`→`"此配置"`、`那么文件应该先备份。`→`"那么文件"`、`这里需要注意脚本的权限。`→`"这里需要注意脚本"`、`这时任务会重新排队。`→`"这时任务"`、`此时配置已经生效。`→`"此时配置"`、`此刻脚本还在跑。`→`"此刻脚本"`。**这不是实现偏离契约，是我方契约的字面规则过宽**：§2.1 原文写「**指示限定词**」，而 `应该 / 因此 / 如此 / 那么 / 这里 / 这时 / 此时 / 此刻` 都不是指示限定词。三个加重情节：① 方向错——本契约在 §2.2/§5 反复声明「宁可漏报、退回既有行为，也不误伤」，而这些是**中文最高频的连词/能愿词/时间词**；② **16 个场景全绿**（无一覆盖这一类），即护栏的真实假阳性面在现有证据里**完全不可见**；③ 追问文案会把 `"此服务"` 这类垃圾串**直接展示给用户**（`main.py:837`）。**裁决**：新增封闭两字排除集（连词/副词、处所时间限定、泛指限定词三组），按**出现位置**对 M1/M3 统一排除。**不**采用「左邻字符集」——那会顺手误伤 `对此` / `与此` 这类真回指 |
| 2026-09-16 | **M1 中心语限定为两个位置域**（阻塞：张冠李戴 + 假触发同源机制） | 见 §2.2。原规则「窗口内最先命中者」会抓到**另一个 NP 的中心语**：`这项工作交给系统处理。` → `工作` 不在集内 → 右扫抓到 `系统` → `marker_text = "这项工作交给系统"`（判定对、**被指对象错**）。同一机制也是上一条假触发的通路（`应该先看一下日志…` 是靠它越过 8 字符抓到 `日志`）。**裁决**：只承认①紧邻起点、②窗口内**第一个 `的`** 之后；两域取位置更靠前者。收紧后 `这项工作交给系统处理。` 退回 fail-open（`工作` 未识别），与 §2.2「M2 的并入」同向。**必须保住 §7 第 16 项**（`那个刚部署好的服务` 是域 ② 的边界锁）；**必须保住 S12**（`这份配置的鉴权失败原因` 的 `配置` 在域 ①，不受影响——收紧不得把 M1 退回 fail-open） |
| 2026-09-16 | **`其他` / `其它` 的排除逻辑失效，改为按表排除** | 见 §2.1。实现里那个 `text[start-1:end+1] == "其他"` 的相等判断**只在「其他」是整个输入时成立**（`他` 之后还有字符就必然不等）。实测：`其他任务怎么处理。`→`triggered`(`marker_text="他"`)、`其他服务`→`triggered`、`其他人呢？`→`triggered`；`其它任务`→`triggered`（`其它` **根本没有对应判断**，`它` 被 M3 直接命中）。`其他/其它` 是高频泛指限定词，不指称任何**已具名**对象，与 `本` 同类（§2.1 排除表）。**裁决**：并入 `_NON_REFERENTIAL_COMPOUNDS`，并让排除**同时作用于 M3 路径**（`其它` 靠这一条才被挡住），下同表 `其它` 同义变体必须一起测（§7 第 20d 项） |
| 2026-09-16 | **M4 的搜索域改为「整轮 − 自身 8 字符窗口」，替换掉首轮那个「后接 `是` 则跳过」的补丁**（契约自相矛盾，**我方责任**） | 首轮实现里 `reference_guard.py:152` 的 `if text[match.end()] == "是": continue` **不是任意放宽**——实测把它删掉后 `刚才说的是支付服务，把那个服务发布上去。` 会因 M4 标记 `刚才说的` 前缀为空而**触发**，直接打破 §7 第 3 项。但根因在契约：§2.3 把 `same_turn` 的搜索域**一律**定为前缀，而 §2.4 例 2 又要求该输入判 `same_turn` 不触发——**两条规则不能同真**。且该补丁本身是错的：`刚才说的是什么？`（真悬空）会因同一个 `是` 被静默放过。**裁决**：① `same_turn` 搜索域**按标记类**定义——M1/M3 前缀域，M4 整轮域（篇章短语的功能是引出被指内容，其先行内容出现在标记之后）；② M4 的整轮域**排除标记起始位置起 `_CENTER_WINDOW` 个字符内的候选词**（否则 `上述配置需要复核。` 会被自己的 NP 头解析掉，变成假阴性；用 `_CENTER_WINDOW` 而不新增常量，是因为它正是本契约已有的「标记之后多远算它自己」的唯一定长定义）；③ M3 **必须**留在前缀域（§7 第 11 项：代词不得为首个标记凭空造先行词）；④ 删除该补丁。测试锁：§7 第 20e 项（五形态）。**Codex 的发现值得肯定**——它是在契约矛盾处唯一能让测试通过的选择。**影响面**：16 场景无一含 M4 短语，故只影响 §7.1 与 §2.4 例 2 |
| 2026-09-16 | **删除死代码 `unresolved_spans` / `_without_spans`** | `reference_guard.py:105,113,212-217`：循环在首个未解析标记处 `return`，该列表恒为空、`_without_spans` 恒为恒等函数。留一段「看起来在做去重」的假动作会误导后续修改者。**裁决**：删 |
| 2026-09-16 | **§1.2 / §7 第 18 项的禁止集含有不可满足的子串 `state`**（我方契约 bug，Codex 静默放宽而非上报） | §1.2 与 §7 第 18 项原文要求签名中不出现 `state`，而本契约**必需的**参数名恰是 `project_state` → 子串匹配**不可满足**。实现侧的处理是把 `state` 从禁止表里删掉（`tests/test_reference_guard.py:138`），**没有**在 `clarifications.md` 提出冲突——按 CLAUDE.md「遇到歧义时先提」应上报。**裁决（两份责任都在我方）**：改契约——禁止集写成**精确列表**（`candidate`/`entities`/`missing_info`/`final_state`/`risk_draft`/`suggested_tools`/`consultation_proposal`/`IntentCandidate`），`state` 只允许**完整参数名**比对，**并新增断言 `project_state` 参数必须存在**（否则等于把「不得读项目状态」写进契约，与 §2.3 的来源表矛盾）。这条**必须**由我改契约后 Codex 再改测试，不得让放宽留在实现里 |
| 2026-09-16 | **§7.3 第 30 项（`marker_text` 不落盘）缺失** | 全库 `marker_text` 只出现在 `src/core/reference_guard.py`、`src/main.py`、`tests/test_reference_guard.py`——**没有任何测试**断言落盘 JSONL 里没有它。`sinks.py:35` 的 `_PERSISTED_KEYS["dispatch_decision"]` 白名单目前**是正确的**，但把「投影改成 `dataclass.asdict()`」这类改动**不会有任何红**，而 `marker_text` 是用户输入片段（P6b 铁律 4）。**裁决**：补第 30 项，不得以「白名单已经对了」为由跳过 |



---

## 10. 不做与延期

### 10.1 明确不做

- **不做通用 NLP / 不引入新模型 / 不引入分词器**：封闭集成员查找 + 来源判定即达成目标；引入语义模型会把安全性重新押在模型上（§4）。
- **不覆盖「候选词出现在了来源中、但语义上不是同一个对象」的指代**：来源判定是**封闭集字面**匹配——`history` 里出现 `服务` 就视为可解析，不检查它是否真是「那个服务」。这是本契约**已知的保守边界**（方向是**漏报**，即退回既有行为，不是安全漏洞）。收紧它需要指代消解，超出薄契约范围。
- **不声称能识别所有指代表达**（§2.1）。`_EXTERNAL_OBJECT_NOUNS` 未收录的外部对象名 → 窗口无命中 → **不触发**（fail-open）。这是刻意的：宁可漏报也不误伤自主升级与强制链（§6.4）。

### 10.2 延期（有证据再立项）

| 项 | 触发条件 |
|---|---|
| **`_NON_REFERENTIAL_COMPOUNDS` 扩充 + 假阳性率观测** | 第四轮审查已证明「字符级匹配会把构词成分当指示限定词」是**结构性**风险，而不是个别漏项（§2.1）。排除集是封闭的，扩充是正常修订（附测试）。**但它不该靠人工不断补**：`unattributed_ask` / `guard_rescued` 的分布与真实 run 的追问文案是唯一能看见假阳性的地方——若出现「追问文案指向的对象与用户意图无关」的 run，优先怀疑这一类，把该固定搭配补进排除集并补 `20b` 的覆盖 |
| **恢复 M2（裸指示词 + 量词，如 `把那个删掉`）的兜底** | v1 已撤回（§2.2）。恢复的**前置条件**（缺一不可）：① 定义**封闭的动作后缀规则**（如量词后紧跟 `_ACTION_SUFFIXES` 成员）使「无名词」与「名词不在集合内」可确定性区分；② 有**真实 run 证据**表明这类形态系统性漏检且后果不可接受。当前 16 场景**无一依赖 M2**，故不阻塞 |
| **`MinimalContext.project_state` 暴露项目实质字段**（`goal`/`constraints`/`topic_tags`） | `_project_state_dict()`（`context_assembler.py:107-110`）当前只给 `{project_id, summary}`，排除 `project_id` 后**只剩会话摘要**——摘要是**派生文本**，可能回显用户原句而让悬空指代被误判为已解析（§2.3 已知限制）。扩展它等于**修改模型可见输入**，需单独评估对提示词与既有场景的影响 |
| `_EXTERNAL_OBJECT_NOUNS` / `_SELF_REFERENTIAL_NOUNS` 与 `_CENTER_WINDOW` 调参 | 出现真实 run 证据表明某一形态系统性漏检（含 S02 报告里的 `failed` / `model_asked_but_not_ask_user`）。当前 `_CENTER_WINDOW = 8` 是**未经真实数据校准的初值**，只由 §7 第 16 项的边界测试锁定方向 |
| 来源判定的语义层（指代消解） | 出现真实 run 证据表明「候选词命中但对象不同」导致的误放行 |
| `resolved_by` 进 JSONL | 报告需要按来源归因来指导集合维护时（当前只进内存，理由见 §5.1 的表达经济性） |
| 将护栏推广到「对象明确但**动作**不明确」的情形 | 与 `NextAction` 的 `missing_info` 分流存在职责重叠，需先有证据区分 |
