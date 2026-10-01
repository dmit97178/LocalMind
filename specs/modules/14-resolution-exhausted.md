# 14-resolution-exhausted — 「理解轮次用尽」的调度语义契约

> **状态：✅ 待实现**（2026-09-17 立项，Claude 裁决，Codex 实现）
> **依赖**：`05-p4-cloud-advisory.md`（§1.3 每轮判定顺序与云端准入否决集）、`10-p6d-autonomous-escalation.md`（§4.3 两个封闭枚举、§4.5 准入唯一实现与「读一次传两次」、§3 轮次与 no-progress）、`07-p6a-observability-cli.md`（§2.2 事件键封闭集）、`11-reference-guard.md`（§3.1 判定顺序表）
> **上游**：`clarifications.md` 条目「S03 round1 暴露『理解轮次已耗尽』状态未传入 ControlPolicy」（2026-09-17，Codex 提出，含 S03 round1/round4 真实运行证据）
>
> 本契约**不新增**模型能力、**不改变**任何安全不变量（deny_cloud / dangerous / PrivacyPolicy / CloudBoundary / 出站预览 / 用户 grant / 预算 / 冷却 / 敏感执行链 / 悬空指代护栏）。它只修一件事：**Resolver 已知的「本次解析已经把轮次用尽」这个确定性事实，必须传进 `ControlPolicy`**，使调度不再产出「没有下一轮却要求 `RETRIEVE_MORE`」这种无法执行的动作。

---

## 0. 裁决摘要（对上游六点的逐条回复）

| # | 上游提议 | 裁决 | 依据 |
|:---:|---|---|---|
| ① | `decide()` 新增关键字参数 `resolution_exhausted: bool = False`；不加模型字段、不告知总轮数 | **采纳形状，否决默认值**：**必传关键字参数（无默认值）** | §3.2：带默认值时「忘了接线」与「真的还有轮次」不可区分，而漏传的后果**就是本次要修的 bug**（末轮返回 `RETRIEVE_MORE`）。与 `10 §4.5` 的 `admission` 去默认值同一裁定 |
| ② | App 按 Resolver 的确定性状态显式传值（达到实例 `max_rounds` 且未有效 READY → `True`） | **采纳意图，修正实现**：事实由 **Resolver 在循环出口记录**，App **只转发不重算** | §2.2：让 App 组合 `last_round_count == max_rounds and not ready` 是**第二处实现**（`10 §4.5` 第 3 条禁止的正是这种漂移）；Resolver 的自然出口本就是该合取的唯一判定点 |
| ③ | 判定优先级：dangerous / 悬空指代 / 云端准入 → 有效 READY → `no_progress` → **exhausted → ASK_USER** → 其余 `RETRIEVE_MORE` | **采纳**（插在第 5 与第 6 步之间，即 `no_progress` 之后、`missing_info` 之前） | §4：由 §2.1 的定义保证 exhausted ⟹ ¬READY ∧ ¬no_progress，故该位置**在行为上不敏感**，仍须写死顺序（防未来定义放宽后变成负载点） |
| ④ | **禁止**复用 `no_progress`；不得把轮次用尽写成 `last_no_progress=True` | **采纳，并升为不变式** | §2.3：两者**由构造互斥**（`no_progress` 走 `return` 早退，根本到不了置位行），且证据与观测含义都不同（「连续候选无变化 + 检索零增量」 vs 「预算用尽」） |
| ⑤ | 可观测落点：`dispatch_decision` 与 turn report 增布尔值 | **偏离**：落 `intent_final` +1 键（`resolution_exhausted`）；`dispatch_decision` 与 `turn_completed` 键集**不变**；新增 `NextAction.reason="resolution_exhausted"` 作为决策侧可区分值 | §6：`07 §2.2` 的分工原则是**按产生者**——该事实由 Resolver 在循环出口确定，与 `no_progress_detected`/`stopped_early` 同源同类，故与它们同 stage；且 `intent_final` 在 `decide()` **之前**发出，天然无「读一次传两次」风险 |
| ⑥ | 验收矩阵（`False`→`RETRIEVE_MORE` / `True`→`ASK_USER` / 不覆盖条件化回答 / 不抢断 force-proposal / S03 两变体） | **采纳并扩充**为 16 项（T1–T16，分决策层 / Resolver 层 / App 层 / 场景层），其中 **T8/T9 为变异探针** | §7 |

### 0.1 一处**必须记录**的行为变更：删除「超轮次不走云端」

上游第 3 点只要求「本修订不改变 force/proposal 云端路径」，**未涉及**既有规则 `05 §1.3` 第 2 步「`round_count > max_resolution_rounds` → `ASK_USER`（超轮次不走云端）」。本契约**删除该规则**（连同 `evaluate_cloud_admission` 的 `round_count` / `max_resolution_rounds` 两个参数与常量 `_MAX_RESOLUTION_ROUNDS`）。

三条理由（详见 §5）：

1. **不可达**：`intent_max_rounds` 被校验为 `1..4`（`src/main.py:1984`），`last_round_count ≤ max_rounds`，而判据是 `> 4`——任何合法配置下都不触发，是死代码。
2. **位置错**：它是**调度**规则（「别再空转，问用户」），不是**云端安全准入**规则。放在准入函数里使它天然位于 `admitted` 分支之前；一旦按实例上限接通，就会抢断 **force**（用户显式 `/cloud ask`）——而 `12 §3.2` 与 `11 §3.1` 已就同一条原理两次裁定：**规则侧/模型侧的不确定性只约束自动路径，不约束用户显式指令**（`risk_draft` 因此被移出 force 否决集；悬空指代护栏显式写了 `and not force_cloud`，`src/core/control_policy.py:73`）。同函数里的轮次判据**没有**这个豁免，是与既有原则不对称的化石。
3. **归因被污染**：它把「因为轮次用尽，准入没跑」塞进 `not_evaluated`（`10 §4.3` **当时的**来源②；该编号在 2026-09-20 已重排——现 ② = 确认恢复流，现 ③ = 能力终端性失败，本条所述来源已删除，见 §5）。而「轮次用尽」是**规则说不**（调度先裁了），不是「没到那一步」——`10 §4.5` 反复强调 `vetoed` 与 `not_evaluated` 必须分开，正是同一类混淆。

**对 proposal 自动路径的原始意图不再保留**（照实声明为行为变更）：P6d 的核心价值恰是「本地小模型卡住时由强模型补足」（`05 §1.3` 背景段自陈）；轮次用尽正是该价值最该生效的场景。「不要在无法成形的任务上花云端预算」已由 proposal 路径既有的资格条件（`expected_benefit ≥ 0.5`、`not_eligible_local_state`、`local_action_proposed`、`budget_exhausted`、`cooldown_active`）承接，不需要一条与 `is_effectively_ready` 无关的轮次门。

> **若上游要求保留该产物规则**：唯一自洽的形态是把它写成**否决集里一条「适用路径 = 仅 proposal」的显式否决项**（新增 `denied_reason="resolution_exhausted"`，`10 §4.3` 两张表各加一行），而不是复用 `not_evaluated`。本契约不采纳，因为它的实际效果是「本地模型彻底卡住时**不许**升级」——与 P6d 目标相反，且会把 S09/S06 的自主建议率门推向更难达成的方向。**不采纳决定可复议，但复议必须给出真实运行证据**（沿用 `10:588` 的「对已观测问题零收益的改动不予授权」纪律）。

---

## 1. 根因与不采纳的两个替代方案

### 1.1 事实链（S03 round1 真实证据）

| 环节 | 事实 | 证据 |
|---|---|---|
| 输入 | S03 修订后文本（「请安排一次内部培训，但培训主题、参与对象和时间都还没有确定。」），`intent_max_rounds = 1` | `scenarios/S03_stop_guess_at_cap.toml`（`rounds_ab = true`，`expect.rounds_max = 4`、`action_any = ["ASK_USER"]`、`tool_none = true`） |
| Resolver | 第 1 轮起 `should_continue = round_index < max_rounds = False`，**不检索**；循环 `range(1, 2)` 走完 → 落到自然出口（`src/core/intent_resolver.py:162-163`） | `last_round_count == 1 == max_rounds`，`last_no_progress == False` |
| Policy | 只收到 `round_count=1`，无法区分「第 1 轮后仍可继续」与「第 1 轮就是上限」；非 READY + `missing_info` 非空 → `RETRIEVE_MORE` | `src/core/control_policy.py:115-120` |
| 结果 | run `7707d503adc5`：`RETRIEVE_MORE`，场景要求 `ASK_USER` → 失败 | `clarifications.md` 2026-09-17 条目 |
| 对照 | `round4`（`max_rounds=4`）第 1/2 轮语义不变且检索零增量 → 既有 `no_progress` 早停 → `ASK_USER` 通过（run `b3c586291303`） | 同上 |

**结论**：不是模型缺陷、不是危险判断缺陷，是**调度输入缺一个确定性事实**。`round4` 变体之所以通过，靠的是 `no_progress` 这条**无关**规则碰巧覆盖了同一动作——这也正说明为什么不能靠「复用 `no_progress`」修（§2.3）。

### 1.2 不采纳：把常量换成实例上限

把 `evaluate_cloud_admission(max_resolution_rounds=resolver.max_rounds)` 接通即可让死代码复活，但会立刻产生两处回归（**照实列出，作为不可采纳的证明**）：

| 场景 | 接通后的结果 | 为什么错 |
|---|---|---|
| 第 `max_rounds` 轮终于得到有效 READY | `round_count > max` 为假（`4 > 4` 为假）→ **不触发**；若改成 `>=` 则触发 → `ASK_USER` | 用户被追问一个系统**已经理解并可以本地执行**的任务；与 `is_effectively_ready` 的语义直接冲突 |
| 末轮 + force `/cloud ask` | 触发 → `ASK_USER`，**抢断用户显式指令** | 违反 `12 §3.2` / `11 §3.1` 的非对称原则，并使 `08 §2.3` 的 S10/S12/S13 硬门（最终动作必须 `REQUEST_CLOUD`）回归 |

**根因是规则的位置（在准入门内部），不是常量与实例之分。** 因此修法是把该事实移出准入、放进 `decide()` 的**调度**段（§4），而不是改 `max_resolution_rounds` 的取值来源。

### 1.3 不采纳：加模型字段 / 提示词告知总轮数

上游第 1 点已排除，此处只记录理由：轮数上限是**本地预算**，不是意图属性。把它交给模型等于让模型输出影响自己的重试预算，且它是**概率性**的（模型可以永不承认耗尽），会把一个当前确定性的调度事实变成随措辞漂移的分布——与 `12 §3.2` 拒绝「用模型 `risk_draft` 当安全边界」是同一裁定。**`_INTENT_RESPONSE_SCHEMA` 与 `_build_prompt` 零改动**（`tests/test_intent_resolver.py:171-177` 的锁继续有效）。

---

## 2. 唯一事实源：`IntentResolver.last_resolution_exhausted`

### 2.1 定义（唯一，可证伪）

> **`last_resolution_exhausted == True` ⟺ 本次 `resolve()` 经「循环自然出口」返回**——即已走满实例 `max_rounds` 轮，且既未在第 124-127 行因有效 READY 早退，也未在第 155-159 行因 `no_progress` 早退。

等价不变式（三条，全部由构造保证）：

- **I1**：`last_resolution_exhausted == True` ⟹ `not is_effectively_ready(末轮候选)`
- **I2**：`last_resolution_exhausted == True` ⟹ `last_no_progress == False`（互斥）
- **I3**：`last_resolution_exhausted == True` ⟹ `last_round_count == max_rounds`

**边界钉死（三种容易被读错的形态）**：

| 形态 | `last_resolution_exhausted` | 说明 |
|---|:---:|---|
| `max_rounds=1`，唯一一轮非 READY（S03 round1） | **True** | 本轮即上限，且是自然出口 |
| `max_rounds=4`，前 3 轮签名不变且零增量、第 4 轮仍非 READY | **False** | 第 2 轮即 `no_progress` 早退——早退优先，**不得**因「跑满 4 轮」而伪装成 exhausted |
| `max_rounds=4`，第 2 轮 READY | **False** | READY 早退 |

> **末轮**不可能**判 `no_progress`（构造性，不是约定）**：`no_progress` 的整个计算被 `should_continue = round_index < self.max_rounds`（`src/core/intent_resolver.py:129`）门控——只有 `if should_continue:`（`:133`）之内才检索、才比较签名、才可能置位。末轮 `should_continue` 为假 ⟹ `no_progress` 恒 `False` ⟹ `:155 if no_progress:` 在末轮不可达 ⟹ **末轮非 READY 必落自然出口**。两条推论：① `max_rounds=k` 且末轮非 READY 时 `last_resolution_exhausted` 必为 `True`（I3 的反向形态）；② `no_progress` 早退时必有 `round_index < max_rounds`，故 `last_stopped_early`（`:157`）在该路径上**恒为 `True`**（既有冗余，本契约不清理，`last_stopped_early` 的用途也不新增）。**因此「末轮才判 `no_progress`」这个形态在代码里不存在**，任何以它为断言基础的用例（T11d 旧稿）都必须改写而不是保留。

### 2.2 实现落点（Codex）

| 位置 | 改动 |
|---|---|
| `IntentResolver` 字段 | 新增 `last_resolution_exhausted: bool = field(default=False, init=False)`（与 `last_no_progress` / `last_stopped_early` 并列） |
| `resolve()` 头部 | 与既有三标志一同复位：`self.last_resolution_exhausted = False` |
| `resolve()` 自然出口 | 在 `src/core/intent_resolver.py:162` 前**置 `True`**（`self.last_round_trace = tuple(traces)` 之前） |
| 复用既有状态 | 不改 `last_round_count` / `last_no_progress` / `last_stopped_early` 的任何语义；**不新增** `last_stopped_early` 的用途 |

> **为什么不让 App 算**：App 侧的等值写法 `last_round_count == max_rounds and not last_no_progress and not is_effectively_ready(...)` 需要 App 读 `resolver.max_rounds`、复刻三个早退条件，并自行引入 `is_effectively_ready`（App 当前不导入它）。这既是**第二处实现**（`10 §4.5` 第 3 条），也把「哪条路径算耗尽」从 Resolver 里搬到了 App 里——而循环结构恰是 Resolver 的私有知识。**App 只做转发**：`resolution_exhausted=self.resolver.last_resolution_exhausted`。

### 2.3 为什么**不能**复用 `no_progress`（上游第 4 点，升为不变式）

| 面 | `no_progress` | `resolution_exhausted` |
|---|---|---|
| 证据 | 连续两轮候选语义签名不变 **且** 本轮检索净增 0（`10 §3.1`） | 走满实例 `max_rounds` 且未 READY |
| 依赖检索 | **是**（`stats.degraded` / `new_memory_count` / 签名比较） | **否**（与检索层完全无关） |
| 触发位置 | 早退（**必**发生在 `round_index < max_rounds`，故该路径上 `last_stopped_early` 恒为 `True`——见 §2.1 结论段） | 自然出口（必为末轮） |
| 动作意图 | 「别再空转」→ 允许**条件化本地回答**（`PLAN_LOCAL`），仅非可条件化时 `ASK_USER` | 「预算用尽」→ **只能** `ASK_USER` |
| 观测语义 | 模型侧停滞信号（P6d 报告用它回答「为什么提前停止」） | 预算侧耗尽信号（回答「为什么跑满四轮」） |
| 报告污染后果 | 把「预算用尽」写成 `no_progress` → P6 报告会显示模型停滞率虚高、检索层被记假账 | 反之亦然 |

**互斥是构造性的**（I2）：`no_progress` 分支 `return`（`intent_resolver.py:159`）后根本执行不到置位行。因此**任何** `last_no_progress=True and last_resolution_exhausted=True` 的组合都是实现缺陷，T11/T12 直接锁死。

---

## 3. 接口变更（Claude 授权，Codex 落 00-* 与代码）

### 3.1 `ControlPolicy.decide()`

```python
    def decide(
        self,
        candidate: IntentCandidate,
        cloud_state: CloudControlState | None = None,
        *,
        resolution_exhausted: bool,                     # 必传，无默认值（§3.2）
        no_progress: bool = False,
        reference_guard: ReferenceGuardResult | None = None,
    ) -> NextAction: ...
```

**两处签名变化，一次落地**：

1. **删**位置参数 `round_count: int`——它的**唯一**消费者是被删除的准入轮次判据（§5）。留着它就是一个「传了却不用」的死输入，而它恰恰是本次要防止的误用形态（下一位读者会以为「轮次还在策略里被判定」）。
2. **增** `resolution_exhausted: bool`（仅关键字、必传）。

### 3.2 为什么无默认值（对上游第 1 点的唯一偏离）

`10 §4.5` 已就 `admission` 参数裁定过一次：**带默认值会让「忘了接线」与「合法值」共用同一个值**。本例中漏传的后果**正是本契约要修的 bug**（末轮落回 `RETRIEVE_MORE`），且它只在 `round1` 这类变体下暴露——默认值会把一个 mypy 能抓的接线错误，变成一个只能靠跑评估场景才发现的静默行为退化。

- 生产调用点只有 **2 处**（`src/main.py:340`、`src/main.py:1067`），成本可忽略；
- 测试调用点（`tests/test_control_policy.py` 约 40 处）**本来就要改**（`round_count` 参数被删），追加一个显式 `resolution_exhausted=False` 是同一批机械编辑；
- `no_progress` **本轮保持默认值不变**（理由与复议触发条件见 §9 第 1 条）——**不要**顺手改成必传。

### 3.3 `evaluate_cloud_admission()`

```python
def evaluate_cloud_admission(
    candidate: IntentCandidate,
    cloud_state: CloudControlState | None = None,
) -> CloudAdmissionDecision: ...
```

- **删** `round_count` 与 `max_resolution_rounds` 两个参数，**删**模块常量 `_MAX_RESOLUTION_ROUNDS`；
- `cloud_state=None → CloudControlState(cloud_enabled=False)` 的内部归一化**不变**；
- 该函数此后**只依赖候选与云端状态**——「唯一纯函数实现」的边界反而更干净；
- `tests/test_intent_resolver.py:235`、`tests/test_control_policy.py` 中所有 `round_count=` / `max_resolution_rounds=` 实参随之删除。

### 3.4 App 侧（两处，且只有两处）

| 位置 | 改动 |
|---|---|
| `src/main.py:340`（主调度） | 传 `resolution_exhausted=self.resolver.last_resolution_exhausted`；删除局部变量 `round_count`（`src/main.py:330`，删除后不再被引用；`turn_completed.rounds_used` 仍直读 `resolver.last_round_count`，`src/main.py:514` 不变） |
| `src/main.py:1067`（`_complete_cloud_consultation` 的本地重判） | **同一回合**的同一事实，同样转发（此前该路径在轮次用尽时也会落回 `RETRIEVE_MORE`，属同一 bug 的第二个出口） |
| `src/main.py:347`（观测调用） | 删 `round_count=round_count`；`candidate` / `cloud_state` 复用同一对象的要求不变（`10 §4.5`） |

**确认恢复流不受影响**：`_handle_confirmation()` 不调用 `decide()`，其 `dispatch_decision` 仍显式传 `CloudAdmissionDecision(False, "not_evaluated")`（`11 §5.1` 来源③）。

---

## 4. 判定优先级（`05 §1.3` 的新行序，行序即代码顺序）

| # | 条件 | 动作 | 变化 |
|:--:|---|---|---|
| 1 | `admission.gate_result == "not_evaluated"`（⟺ `risk_draft` 归一化为 `dangerous`） | `REFUSE` | 判据由「`not_evaluated` **且** dangerous」收敛为「`not_evaluated`」——因为 §5 之后 `not_evaluated` 只剩这一个来源，收敛后**方向是 fail-closed**（任何未来的新来源也走拒绝），同时消除 `decide()` 内第二次调用 `_is_dangerous` |
| 2 | 护栏 `triggered` 且非 `force_cloud` 轮 | `ASK_USER`，`reason="dangling_reference"` | 不变（`11 §3.1`） |
| ~~3~~ | ~~`round_count > max_resolution_rounds`~~ | ~~`ASK_USER`~~ | **删除**（§5；行序中不再有此步） |
| 3 | `admission.admitted` | `REQUEST_CLOUD` | 不变（**force 与 proposal 均在此放行，不受 exhausted 影响**） |
| 4 | `is_effectively_ready(candidate)` | `_decide_ready(candidate)` | 不变 |
| 5 | `no_progress` | 可条件化 → `PLAN_LOCAL`(`local_conditional_answer`)；否则 `ASK_USER`(`no_progress`) | 不变 |
| **6** | **`resolution_exhausted`** | **`ASK_USER`，`reason="resolution_exhausted"`** | **新增** |
| 7 | `candidate.missing_info` 非空 | `RETRIEVE_MORE` | 语义不变，但**此后只可能在「尚有轮次」时到达** |
| 8 | 其余 | `ASK_USER` | 不变 |

**位置为何在第 5 步之后（而不是之前）**：由 I1/I2，第 6 步为真时第 4/5 步必为假，两种排布**行为等价**。仍钉死顺序，因为：① 若未来放宽定义（例如把**非末轮**的 `no_progress` 也计为 exhausted，需同时改掉 `intent_resolver.py:129` 的门控），顺序立刻变成负载点，而「条件化本地回答优先于空手追问」是更好的结果；② 顺序写死在契约里，Codex 的实现顺序与测试断言就无需各自推理。**测 8 是变异探针**：把第 6 步移到第 4 步之前，T4/T5 必须变红（§7）。

**不被本步改变的路径（逐条声明）**：

- dangerous → `REFUSE`（第 1 步，最高优先级不变，T7）；
- 悬空指代护栏 → `ASK_USER`（第 2 步，且 force 轮照旧让位）；
- **force `/cloud ask` → `REQUEST_CLOUD`**（第 3 步）；轮次用尽**不得**抢断（T3）；
- **proposal 自动升级 → `REQUEST_CLOUD`**（第 3 步）；轮次用尽**不再**否决（§0.1 的行为变更，T3b）；
- `deny_cloud` / 敏感执行链 / 云端禁用 / 预算 / 冷却 / 空任务 各否决项 → 归因不变（T6）；
- `no_progress` 的条件化本地回答 → `PLAN_LOCAL`（第 5 步优先，T5）。

---

## 5. `not_evaluated` 来源收窄（三 → 二）与「超轮次不走云端」的删除

`10 §4.3` 第一张表的 `not_evaluated` 行改为：

> `not_evaluated` | 云端准入**根本没有进入**——本回合未产生准入评估。**穷举两种来源**（共同点是「准入没跑」，都不得记为 `vetoed`）：① **dangerous 早裁**（→ `REFUSE`，唯一仍在 `evaluate_cloud_admission` 内的来源）；② **确认恢复流等未调用 `decide()` 的回合**（合法例外，必须由调用方显式传入，不得依赖参数默认值）。
>
> （原来源②「超轮次早裁」随 `evaluate_cloud_admission` 的轮次参数一并删除——见 `14-resolution-exhausted.md` §5。）

**报告侧连带**：`08 §6` G3 中 `not_evaluated` 的括注由「（dangerous 或超轮次）」改为「（dangerous，或未进入正常调度的回合）」；`08 §2.3` S02 行的 `unattributed_ask` 归因清单里「超轮次」一项改为「`resolution_exhausted` 分流」。

---

## 6. 可观测性（对上游第 5 点的裁决）

| 落点 | 改动 | 理由 |
|---|---|---|
| `intent_final` | **+1 键** `resolution_exhausted`（bool，落盘原样）；键数 **13 → 14** | `07 §2.2` 的分工原则是**按产生者**：该事实由 Resolver 在循环出口确定，与既有 `no_progress_detected` / `stopped_early` 同源同类，故必须同 stage |
| `dispatch_decision` | **不变**（不增键） | 决策侧的可区分性由 `reason` 承担；且若把该事实放到决策事件，就要再补一条「读一次传两次」的纪律，而 `intent_final` 在 `decide()` **之前**发出（`src/main.py:323` vs `:340`），天然没有这个窗口 |
| `turn_completed` / `App.last_turn_report()` | **均不变** | 报告问题（「因预算耗尽而追问的占比」）已可由 `intent_final.resolution_exhausted` ∧ `dispatch_decision.action` 聚合；报告侧的唯一读取路径是 `intent_final` 事件（`src/evaluation/runner.py:320` 正是这样读 `no_progress_detected`），`_active_report`（`src/main.py:532-547`）无需第二份拷贝，也避免扩大 `tests/test_main.py` 的 turn-report 断言面 |
| `NextAction.reason` | 第 6 步固定为 **`"resolution_exhausted"`** | `reason` 是自由文本、按 `07 §2.2` **不落盘**，但会进事件 `data`；必须与 `"no_progress"`、`"local_conditional_answer"` 明确区分（上游第 5 点的最低要求）。**不得**沿用旧文案 `"Intent resolution exceeded the maximum round count."`——该文案属于被删除的超轮次分支，语义不同（「超出」 vs 「刚好用尽」） |
| stage 集合 | **不变**（不新增 stage） | 沿用 `10 §4.2`「按产生者分工，不新增 stage」的既有裁定 |

**报告聚合（`08 §6` G3）**：在既有「`no_progress_detected`·`stopped_early` 比例与轮次分布」之后追加 **`resolution_exhausted` 比例 + 其 `final_action` 分布**，与它们并列回答「为什么跑满四轮」。

- **允许的动作值**：`REQUEST_CLOUD`（耗尽后仍经 force/proposal 准入上云——`§4` 第 2/3 步优先于第 6 步）、`ASK_USER`（未获准入后的追问，主形态）、`PLAN_LOCAL`（仅优先级探针可见：生产上 `resolution_exhausted` 与有效 READY / `no_progress` 由 I1/I2 互斥）。
- **唯一明确禁止 `RETRIEVE_MORE`**（`§4` 第 6 步截断了它；出现即实现缺陷）。
- **必须按 `proposal_gate_result` 分组**（至少两桶：`admitted_forced`/`admitted_proposal` = 「耗尽后升级云端」；`not_evaluated`/`vetoed`/其余非准入 = 「未准入后追问」）。不分组会把两种相反结局混成一个数，正好抹掉 `§0.1` 那处行为变更的可观测面。
- **禁止**把它并入 `no_progress` 的统计口径（上游第 4 点）。
- **口径钉死**：`resolution_exhausted` 按 `intent_final` **事件**计数的**次数**（与 `no_progress_detected` / `stopped_early` 同法），**不是** run 占比——多回合 run 可 >1。报告以计数行呈现即可，措辞统一用「次数」。
- **既有观测缺口（照实记录，本次不改代码）**：`_complete_cloud_consultation`（`src/main.py:1061-1071`）在云端回流后重跑 `resolve()`/`decide()` 但**不发任何事件**（`_record_intent_events` 只在 `src/main.py:323` 调用、`_record_dispatch_event` 只在 `:352` 与确认恢复流 `:653-710` 调用），故该出口的 `resolution_exhausted` 不进 `intent_final`、不计入 G3 统计——`no_progress_detected` / `stopped_early` 有同样的缺口。读数时须知道 G3 的分子**不覆盖**该回合。

---

## 7. 验收矩阵（T1–T14）

### 7.1 决策层（`tests/test_control_policy.py`，直接构造候选）

| # | 用例 | 断言 | 性质 |
|:---:|---|---|---|
| T1 | `PARTIAL` + `missing_info` 非空，其他参数不变 | `resolution_exhausted=False` → `RETRIEVE_MORE` | 既有行为回归锁 |
| T2 | 同 T1 | `resolution_exhausted=True` → `ASK_USER`，`reason == "resolution_exhausted"`，**`reason != "no_progress"`**，`requires_user_confirmation is False` | 本契约主修复（上游第 6 点第一句） |
| T3 | 同 T1 + `cloud_state` 可放行 + `force_cloud=True` | `resolution_exhausted=True` → `REQUEST_CLOUD`，`gate_result == "admitted_forced"` | 不抢断用户指令（上游第 6 点 / `12 §3.2`） |
| T3b | 同 T1 + 合法 proposal（`should_consult=True`、`benefit ≥ 0.5`、无工具、状态 `PARTIAL`） | `resolution_exhausted=True` → `REQUEST_CLOUD`，`gate_result == "admitted_proposal"` | **行为变更锁**（§0.1）：轮次用尽不再否决自动升级 |
| T4 | 有效 READY + 高置信度（`_decide_ready` 的 `PLAN_LOCAL` 档） | `resolution_exhausted=True` → 仍 `PLAN_LOCAL` | READY 优先（上游第 3/6 点） |
| T5 | `no_progress=True` + 可条件化候选（ALMOST + 非 unknown + normal + 无工具建议） | `resolution_exhausted=True` → 仍 `PLAN_LOCAL` + `reason="local_conditional_answer"` | 不被覆盖（上游第 6 点） |
| T6 | `deny_cloud=True` + `resolution_exhausted=True` | `gate_result == "vetoed"` + `denied_reason == "deny_cloud"` | 安全否决不被轮次遮蔽 |
| T7 | `risk_draft="dangerous"` + `resolution_exhausted=True` | `REFUSE`，且 `admission.gate_result == "not_evaluated"` | 第 1 步最高优先级不变 |
| T8 | **变异探针 A**：把第 6 步的实现挪到第 4 步（READY）之前 | T4 与 T5 **必须变红** | 顺序纪律（§4） |
| T9 | **变异探针 B**：第 6 步的判据写成 `effective_risk == "sensitive"` / 写成读 `round_count` 的旧式判据 | T1 必须变红（`RETRIEVE_MORE` 会在 `False` 时也返回 `ASK_USER`） | 防「条件写偏」 |
| T10 | **一致性（改造 `10 §7.1` 第 15 项）**：对两枚举全取值各构造一例，断言 `decide()` 的动作与 `evaluate_cloud_admission()` 的 `admitted`/`gate_result` 一致 + `gate_result=="vetoed" ⟺ denied_reason!="none"` | `not_evaluated` 的来源**只覆盖 dangerous**；括号注改为「`decide()` 的 dangerous 重复判断已收敛为 `not_evaluated → REFUSE`，超轮次判据已删除」 | 防两处实现漂移 |
| ~~T10b~~ | ~~`10 §7.1` 第 15b 项（轮次来源边界值）~~ | **删除**（判据不存在了）；`15c`（读一次传两次）**保留**，但锚点改为 `candidate` / `cloud_state` 复用同一对象 | — |

> **T4/T5 的可达性（勿误读为层次违规）**：由 §2.1 的 I1/I2，`resolution_exhausted=True` 与「有效 READY」「`last_no_progress=True`」在**生产路径上不可能同时出现**——`IntentResolver` 只在自然出口（既非 READY 也非 no_progress）才把它置真。T4/T5 因此不是「把生产不可达的状态喂过层」（`10` 的层次纪律禁止的是后者），而是**故意的优先级探针**：只检验「参数被硬塞成矛盾组合时第 4/5 步是否仍胜出」，把 §4 的顺序纪律变成可执行断言（与 T8 的变异探针配套）。生产代码不存在构造这两组参数的路径，实现**不得**为它们加分支。

**必须同步删除/改写既有测试**（Codex 执行）：`tests/test_control_policy.py` 中 `test_round_count_over_four_asks_user_unless_dangerous`（约 `:255-262`，断言 `ASK_USER` + `"round" in reason`）**整个删除**——它锁的正是本契约删除的规则；`round_count=99` 的「unless dangerous」半边（约 `:165-175`）改为只断言 `REFUSE`（`dangerous` 与轮次无关）；`:705-726` 的 `over_limit` / `at_limit` 两例删除，`danger_decision` 一例保留。

### 7.2 Resolver 层（`tests/test_intent_resolver.py`）

| # | 用例 | 断言 |
|:---:|---|---|
| T11 | `max_rounds=1` + 非 READY 候选（S03 round1 的最小复现） | `last_resolution_exhausted is True`、`last_round_count == 1`、`last_no_progress is False`（I2/I3） |
| T11b | `max_rounds=4` + 第 2 轮 READY（mock 第 2 轮返回 READY） | `last_resolution_exhausted is False`（I1） |
| T11c | `max_rounds=4` + 第 2 轮签名不变且零增量（既有 no-progress 用例改造） | `last_resolution_exhausted is False`、`last_no_progress is True`、`last_stopped_early is True` |
| T11d | `max_rounds=2` + 两轮候选**签名相同**且第 2 轮（末轮）检索零增量 | `last_resolution_exhausted is True`、`last_no_progress is False`、`last_round_count == 2` —— 锁「末轮不判 `no_progress`、必走自然出口」（§2.1 边界表 + 结论段；I2 的构造性证明） |
| T11e | `max_rounds=4` + 四轮均非 READY 且每轮都有新 chunk（不触发 no_progress） | `last_resolution_exhausted is True`、`last_round_count == 4`、`last_no_progress is False`（自然出口的正常形态） |

### 7.3 App 层（`tests/test_main.py`）

| # | 用例 | 断言 |
|:---:|---|---|
| T12 | App 转发（**接线锁**）：`intent_max_rounds=1` + 非 READY 模型输出 | `dispatch_decision.action == "ASK_USER"`、`reason == "resolution_exhausted"`，且**事件流里**存在 `intent_final.resolution_exhausted == True`；零工具执行 |
| T13 | 观测调用一致性改造（`10 §7.1` 15c）：决策后改写 `resolver` 的可变状态再断言事件值 | 观测用的是捕获值（`candidate` / `cloud_state` / `resolution_exhausted` 同一组输入） |
| T14 | `_complete_cloud_consultation` 的第二个出口 | 轮次用尽 + 云端回流后本地重判 → `ASK_USER`(`resolution_exhausted`)，**不得** `RETRIEVE_MORE` |

### 7.4 场景层（`08 §2.3`）

| # | 场景 | 判据 |
|:---:|---|---|
| T15 | S03 `round1` 与 `round4` 各 ≥3 run | 两变体均 `action_any=["ASK_USER"]` + `tool_none=true`；**`round1` 的 `resolution_exhausted` 必须恒为真**（`max_rounds=1` ⟹ 唯一一轮即末轮 ⟹ 末轮不判 `no_progress` ⟹ 来源唯一）；`round4` 两种来源都合法（`no_progress` 提前结束或走满四轮），`rounds_max=4` 不变、两者**都不得判为失败**；**报告须按来源分列**（不得只给 `ASK_USER` 汇总数） |
| T16 | **回归红线**：S10/S12/S13 force 链（`round1` 变体若纳入 `rounds_ab`） | 最终动作恒为 `REQUEST_CLOUD`——轮次用尽**不得**抢断（T3 的端到端对照） |

> **场景文件无需改动**：`scenarios/S03_stop_guess_at_cap.toml` 的 `expect` 已是 `action_any=["ASK_USER"]` / `tool_none=true` / `rounds_max=4`；`expect` 键集合**不扩展**（`resolution_exhausted` 的断言落在 T12/T15 报告聚合与单测层，不进 `_EXPECT_KEYS`）。

---

## 8. 同步清单

### 8.1 Claude（本轮已同步 / 待同步）

| 文件 | 内容 |
|---|---|
| `05-p4-cloud-advisory.md` | §1.3 判定顺序第 2 步删除、第 4 步补 `resolution_exhausted` 分流、补一段「轮次用尽不改准入语义」的说明（与既有「提前停止不改准入语义」并列）；§14 重设计记录加行 |
| `10-p6d-autonomous-escalation.md` | §4.3 `not_evaluated` 三源 → 二源；§4.5 `evaluate_cloud_admission` 签名与「参数为何必须包含轮次」整段重写（含删除 `_MAX_RESOLUTION_ROUNDS`）；§4.5「读一次传两次」改为锚定 `candidate`/`cloud_state`；§7.1 第 15/15b/15c 项改造；§9 步 4 行 + 新增步 4c；§11 决策表加行 |
| `11-reference-guard.md` | §3.1 判定顺序表重编号 + 删第 3 行 + 补新第 6 行（`resolution_exhausted`）；§7 `unattributed_ask` 归因清单改名；§8 第 3b 步的目标签名同步；§9 决策表加行 |
| `08-p6b-evaluation-loop.md` | §6 G3 的 `not_evaluated` 括注、追加 `resolution_exhausted` 聚合；§2.3 S02 行 `unattributed_ask` 归因清单；§2.3 S03 行补两变体分列要求；§9 决策表加行 |
| `project-report.md` | §4.1–§4.2 同步轮次耗尽、提前停止和动作语义；具体判定顺序由本契约定义 |
| `01-p0a-main-loop.md` | 流程图第 4 步（`:261`）与关键约束（`:322`）改为 `decide(candidate, cloud_state, resolution_exhausted=…)` |
| `07-p6a-observability-cli.md` | §2.2 `intent_final` 键集 +1（`resolution_exhausted`）+ §10 决策表加行 |
| `CLAUDE.md` | 必读文档表增 `14-resolution-exhausted.md` |
| `clarifications.md` | 该条目移入「已解决」，保留裁决记录 |

### 8.2 Codex（工程契约镜像 + 代码 + 测试）

| 文件 | 内容 |
|---|---|
| `00-adapter-factory.md` | §3.2 `ControlPolicy.decide()` 签名块（`:485-499`，含 docstring 说明 `resolution_exhausted` 必传）与 `evaluate_cloud_admission()` 签名块（`:518-526`，删两参数）；`:411` 流程注释 |
| `src/core/intent_resolver.py` | §2.2 三处 |
| `src/core/control_policy.py` | §3.1 / §3.3 签名、删 `_MAX_RESOLUTION_ROUNDS`、第 1 步判据收敛、第 6 步新增、删旧超轮次分支 |
| `src/main.py` | §3.4 三处（`:340` / `:1067` 调用点、`:347` 转发）+ **`:1420-1424` 的 `intent_final` 键白名单**（`_sanitize_event_data` 会**静默丢弃**白名单外的键，漏改 = 新增键形同不存在）+ `:525-529` 构造 `final` dict 时加 `"resolution_exhausted": self.resolver.last_resolution_exhausted` |
| `src/observability/sinks.py` | `:25-31` 的 `intent_final` frozenset **同步 +1**（与 `main.py:1420` 是**两份**独立白名单，必须同时改，否则落盘阶段被过滤） |
| `src/evaluation/runner.py` | **必做**：`:271-272` 起计数器 `resolution_exhausted = 0` 与 `exhausted_actions: dict[str, int]`；`:320-323` 之后按 `intent_final.data["resolution_exhausted"] is True` 累加，并在同一 run 内与 `dispatch_decision` 的 `action`/`proposal_gate_result` **配对**成 `{gate_result: {action: n}}`（末轮事件顺序为 `intent_final` → `dispatch_decision`，配对以「本次 run 内最后一个 `dispatch_decision`」为准，与既有 `latest_action` 同法）；`:400-401` 的 summary 增 `"resolution_exhausted"` 与 `"resolution_exhausted_actions"` |
| `scripts/p6_report.py` | **必做**：`:83-84` 旁增 `resolution_exhausted` 读取，`:98` 总览行分列（**不得**并入 No-progress 计数），并按 §6 的分组要求在 G3 区渲染「耗尽后升级云端 vs 未准入后追问」 |
| `tests/` | §7 全矩阵 + §7.1 末尾的删除/改写清单 |
| `scenarios/` | **无改动** |

---

## 9. 遗留与明确不做

| # | 事项 | 本契约的态度 |
|:---:|---|---|
| 1 | **`no_progress` 与 `reference_guard` 的默认值隐患**：两者与 `resolution_exhausted` 同属「App 必须显式表态」的确定性事实，但都带默认值（`False` / `None`），漏传同样会静默退化成错误动作 | **本轮不改**（无真实事故证据，且 `10:588` 已立「对已观测问题零收益的改动不予授权」的纪律）。**复议触发条件**：一旦出现「忘接线」事故，或下一次改动本就要触碰这批调用点时，一并把 `no_progress` 改必传——届时应同时更新 `10 §4.5`/§7.1 与 `11 §5.1`。`reference_guard=None` 的 None 有 **`not_evaluated` 的独立语义**（确认恢复流的合法例外），**不得**一并改必传 |
| 2 | 模型侧感知轮数上限 | **不做**（§1.3）；`_INTENT_RESPONSE_SCHEMA` / `_build_prompt` 零改动 |
| 3 | 保留「超轮次不走云端」为 proposal-only 否决项 | **不做**（§0.1），但记录了唯一自洽形态与复议条件 |
| 4 | `turn_completed` 增 `resolution_exhausted` | **不做**（§6）：`intent_final` 已足够，且避免扩 `turn_completed` 的键集 |
| 5 | 8 个 `expect` 键的扩展 | **不做**：本事实的断言落在单测 + 报告聚合，不进 `_EXPECT_KEYS` |
| 6 | `max_resolution_rounds` 作为可配置项（上游提到「无法表达评估变体」） | **不做**：轮次上限的事实来源是 `execution.intent_max_rounds`（`1..4` 已校验），`decide()` 不再需要第二份轮次知识；若未来确需「按场景覆盖上限」，走配置层单一来源，**不得**在策略内重建轮次门 |

---

## 10. 决策记录

| 日期 | 决策 / 发现 | 处理 |
|---|---|---|
| 2026-09-17 | S03 `round1` 真实 run（`7707d503adc5`）暴露 `RETRIEVE_MORE`；根因＝轮次用尽的事实没进 Policy | **采纳修复方向**：Resolver 记录 `last_resolution_exhausted` → App 转发 → `decide()` 第 6 步 `ASK_USER`（§2/§4） |
| 2026-09-17 | 上游建议参数带默认值 `= False` | **偏离**：改必传（§3.2）。漏传的后果即本 bug，且与 `10 §4.5` 的 `admission` 先例同构——默认值把 mypy 能抓的接线错误变成只能靠跑场景才发现的静默退化 |
| 2026-09-17 | 上游建议由 App 组合 `max_rounds` / READY 条件 | **偏离**：事实在 Resolver 循环出口记录，App 只转发（§2.2）。App 侧组合即第二处实现，且需 App 引入 `is_effectively_ready` |
| 2026-09-17 | 上游要求 observable 落 `dispatch_decision` + turn report | **偏离**：落 `intent_final` +1 键（§6）。按 `07 §2.2` 产生者分工，与 `no_progress_detected`/`stopped_early` 同 stage；决策侧由 `reason="resolution_exhausted"` 承担 |
| 2026-09-17 | 既有「超轮次不走云端」（`05 §1.3` 第 2 步，`_MAX_RESOLUTION_ROUNDS=4`） | **删除**（§0.1/§5）：不可达（`intent_max_rounds ≤ 4` 且判据为 `>4`）、位置错（在准入门内、无 force 豁免，与 `12 §3.2`/`11 §3.1` 的非对称原则冲突）、归因污染（把「规则说不」记成 `not_evaluated`）。`not_evaluated` 三源收窄为二源 |
| 2026-09-17 | 删除该规则对 proposal 路径的后果 | **照实声明为行为变更**：轮次用尽**不再**否决自动升级——P6d 的目标恰是「本地卡住时由强模型补足」，而「无望任务不花预算」已由 5 条既有资格条件承接 |
| 2026-09-17 | `decide()` 的 `round_count` 参数 | **删除**（§3.1）：唯一消费者是被删的轮次判据，留着即死输入；`turn_completed.rounds_used` 不受影响 |
| 2026-09-17 | 第 1 步判据由「`not_evaluated` 且 dangerous」收敛为「`not_evaluated`」 | **采纳**（§4）：来源收窄后二者等价，收敛后方向 fail-closed（未来任何新来源也走 `REFUSE`），并消除 `decide()` 内对 `_is_dangerous` 的重复调用 |
| 2026-09-17 | **自审修正 A（Codex 复核）**：初稿边界表第 2 行与 T11d 断言「末轮才判 `no_progress`」 | **改写**（§2.1/§7.2）：该形态**不可达**——`intent_resolver.py:129` 的 `should_continue = round_index < max_rounds` 门控使末轮不检索、不算 `no_progress`，末轮必走自然出口。边界表重写并新增构造性结论段（含 `last_stopped_early` 恒真的既有冗余说明）；T11d 改为「`max_rounds=2` + 末轮签名不变 → `exhausted=True` ∧ `no_progress=False`」，从「锁一个不存在的形态」变为 **I2 的构造性证明**；连带同步 `10 §3.5` 的括注（`last_stopped_early` 恒真，该分支不可达）与 `08 §2.3` S03 说明的「共同覆盖」措辞 |
| 2026-09-17 | **自审修正 B（Codex 复核）**：初稿 §6 报告聚合写「`final_action` 应当恒为 `ASK_USER`/`PLAN_LOCAL`」 | **改写**（§6 + `08 §6` G3）：与 T3/T3b 直接冲突——轮次耗尽不否决 force/proposal 准入，`REQUEST_CLOUD` 合法。改为：允许 `REQUEST_CLOUD`/`ASK_USER`，`PLAN_LOCAL` 仅优先级探针可见，**唯一禁止 `RETRIEVE_MORE`**，并**按 `proposal_gate_result` 分组**呈现，否则行为变更在报告里不可见 |
| 2026-09-17 | **自审修正 C**：报告侧落点初稿写「`src/evaluation/*`（如需）」 | **升级为必做**（§8.2）：T15 要求报告分列，故钉死四处落点（`runner.py:271-272`/`:320-323`/`:400-401`、`p6_report.py:83-84`/`:98`、G3 分组渲染），并补记**两份** `intent_final` 键白名单（`main.py:1420-1424` + `observability/sinks.py:25-31`）——`_sanitize_event_data` 会静默丢弃白名单外的键，漏改会让新键在落盘阶段消失 |
| 2026-09-18 | **工具编排加固联动（`15-tool-orchestration-hardening.md` §2.5）**：本契约 `:32` 列举 proposal 路径既有资格条件时写的是 `suggested_tools_present` | **同步改名 `local_action_proposed`**（权威在 `10 §4.3`；判定源由 `suggested_tools` 改为 `intent_final.tool_intent`）。**本契约其余内容零改动**——轮次用尽与工具编排是两条正交链路，`resolution_exhausted` 的构造、优先级插入点与 T1–T16 矩阵不受影响 |
