# 05-p4-cloud-advisory — 分级授权的云端建议工具模块契约

> 状态：**✔️ 完成**（2026-09-25 收口；上一版为 ✅ 待实现——2026-09-17 修订。「2026-09-17 修订 + 2026-09-24 三轮凭据模型 / 诚实拒绝 / 云端写回」均已实现并通过**静态审查**：审查发现 1 处必改（拉丁标签左边界未登记收窄 ⇒ `.env` 式输入五面一致漏检，归 Codex）已修复并按变量级数据流逐条复核（`secret_scan.py` 现只保留契约允许的**右**边界条件）；修复带出的新面（`.env` 式凭据行替换后外发为「壳」）已登记为 §2.3c.6 第 10 行，不阻塞。详见 `specs/reviews/05-p4-cloud-advisory-review.md` 2026-09-25 节；基线为 ✔️ 完成——2026-09-14 修订已实现并通过审查，范围：§1.2/§1.3 云端咨询准入拆分、§2.5 TaskBrief `brief_unknowns`、§10.1/§10.9 测试、§11 Done 第 8 项；其余章节维持 2026-09-08 ✔️ 基线。基线修订依据：specs/clarifications.md 已解决区 2026-09-14 条，boss 已批准方向；决策记录与遗留项见 §14 决策表同日三条。基线验证：`404 passed`；S06/S08 `cloud_assisted` 的真实结构验收仍以 boss 的云端凭据为前置，见 09-p6c §11.4）
> 完成基线：2026-09-08 终验通过（上轮 6 必改 + 2026-09-06 四项裁决 + 2026-09-08 增量纯度裁决 + R1 + record_denial 全部落地；219 passed / ruff 通过；残留 2 个收尾微项见 specs/reviews/05-p4-cloud-advisory-review.md 终验章节）
> P6c 增补（2026-09-13）：§7/§8/§9/§13 已由 `modules/09-p6c-cloud-provider.md` 局部取代（云端适配器、配置形态、凭据体系、错误分类），安全骨架与授权语义不变。
> **2026-09-17 修订（代码待落地）**：S07 长上下文协同的老板裁决——取消 `brief_*` section 的独立 400 UTF-8 字节上限，**整包 `context_byte_budget`（默认 2048 → **32768**，绝对上限 65536）成为 TaskBrief 唯一字节硬边界**（同日二次裁决：先定 8192，最终钉死 32768，**中间值 8192 作废**；同时明确**不做**字段优先级截取、动态扩容 grant、二次长度确认三件事）；新增 §2.5 规则 7 确定性同值去重、§8 配置合法范围与「不做三件事」、§10.10 验收矩阵 A1–A8、§11 第 10 项。修订涉及 §2.2 / §2.3.5 / §2.5 规则 3·5·7 / §5.3 规则 7 / §8 / §10.8·§10.9·§10.10 / §11 / §12 / §14。**本次修订的代码尚未落地**：`src/safety/privacy_policy.py`（400 字节分支收窄为仅模型候选 + 配置范围）、`src/main.py`（去重与 bootstrap 默认值）、`src/safety/authorization.py`（范围判据统一）、`config/` 四份 TOML。修订依据：specs/clarifications.md 已解决区 2026-09-17 条；决策记录见 §14 同日第一条。**回标条件**：按 §10.10 A1–A8 + §11 第 10 项验收通过后，本文件回标 `✔️ 完成`——在此之前，本文件不得被当作「已实现」的基线引用，涉及章节（§2.5 规则 3/7、§8、§10.10）以**修订后**口径为准。
> **2026-09-17 二次修订（代码待落地）——`risk_draft` 判定对象 + `sensitive` 提案的强制授权（老板裁决 A/B）**：S06/S09 真实评估暴露两条**自主升级臂**全灭——S09 `base` 3/3、S06 `cloud_auto` 3/3 都被判 `risk_draft=sensitive` → `proposal_gate_result=vetoed` + `proposal_denied_reason=non_normal_risk`，实际准入 **0/3**（目标 ≥2/3）。裁决两项：**① 判定对象**——`risk_draft` 判**本回合实际请求的动作**，只读分析/排查建议/架构权衡/迁移规划/回滚设计默认 `normal`（即使话题涉及生产、切流、数据库、部署或高影响系统），`sensitive` 的充分条件只有「本回合实际含敏感数据」或「本回合实际请求需确认的副作用」；**② `sensitive` 不再阻止提出建议，只禁止未经确认的外发**——`sensitive` 提案可准入 `REQUEST_CLOUD`，但该动作只产出脱敏准备与最终授权 preview（零网络请求），**所有**隐私模式（**含 `convenient`**）下必须进 `AWAITING_AUTHORIZATION`，只认显式 `/cloud allow` 的用户 grant，**不得** policy grant、**不得**复用旧任务/旧 grant 授权；授权后既有检查一条不减。随之**删除 §1.3 否决项 3**（`non_normal_risk` 全域不可达，枚举值保留为不可达项）。修订涉及 **§1.3**（否决项 3 删除、准入条件、新增 **§1.3a**）、**§1.4**（状态机两处 + 规则 8）、**§3.2**（`create_policy_grant(..., escalation_risk="sensitive")` fail-closed 前置条件）、**§5.3** 规则 2/4、**§10.9**（第 16 例翻转 + 新增 17–19 例 + 端到端 `sensitive` 授权链）、**§11**（第 8/9 项改口径 + 新增第 11 项）、**§12**、**§14**。**场景文本一字不改、`expected_benefit` 阈值不调**。依据：specs/clarifications.md 已解决区 2026-09-17 S06/S09 条；语义权威见 `modules/12-risk-draft-closed-set.md` §1.2.1/§3.2/§3.4。**回标条件**：按 §10.9 第 16–23 例 + §11 第 11–13 项验收通过，且重跑 S05 `0/3`、S09 `≥2/3`、S06 `cloud_auto` `≥2/3`、S11 `0/3` 达标后回标 `✔️ 完成`。
>
> **2026-09-17 四处补钉（同日，Codex 复审提出后由 Claude 裁定；三处影响实现）**：① **有效授权风险**——授权形态不得只取自模型自评，改为 `max(模型下界, 确定性升险)`，确定性信号**只能升险**（§1.3a 扩写，权威在 `12` §3.5；新增纯函数 `effective_authorization_risk()`）；② **意图层风险限定**——工作区内**新建**文件为 `normal`（**2026-09-20 追注**：本条结论不变，但「新建」在**工具层**已改为需确认——P7a-0 把 `file.write` 注册表基线反转为 `sensitive`；本字段判的是**请求语义**，不表达「会不会被确认」，两者互不推导，`12` §1.2 表注），**覆盖/越界**由确定性 preflight 只升不降，本字段不复制工具动态风险（消除与 `07 §6.1` 及 S14 的冲突）；③ **含秘密文本就地替换**——新增 **§2.3b**（可替换秘密 → `[已脱敏:secret]` + `secret_placeholder`，该 section 不再整段拒绝；取代 2026-09-06 的「可选优化、不实现」降级裁定），S12 由此**结构可达**；④ **防御性拒绝的错误/审计契约**——§3.2 防线表（主防线在 App；冗余防线复用既有 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"`，`AuthorizationManager` 不写审计）。验收随之扩到 §10.9 第 20–22 例与 §11 第 12/13 项。**S12/S14 场景文本一字不改，阈值不调。**
>
> **2026-09-18 两处收口（Codex 复审上轮补钉后提出，两处都阻塞实现）**：① **参数收窄**——`effective_authorization_risk()` 删去 `high_impact_or_preflight_raised`：该信号在云端链路**不可求值**（policy grant 发生在续咨询阶段，通常既无 `ExecutionPlan` 也未跑 preflight），列为输入会让「未求值即 `sensitive`」把它恒判 `sensitive`，把 `normal + convenient` 自动续重新锁死；工具计划与 preflight 是**另一条正交链路**，本就不该进入签发判定（§1.3a 第 2/6 点、`12` §3.5 表后注），故签名**恰两个**布尔信号并加参数名反向断言。② **正例补齐**——验收矩阵补 §10.9 第 23 例（`normal` 仍然可达并真的签出 policy grant），因为只锁升险方向的矩阵会让「恒判 `sensitive`」的实现全绿。③ **审计出口改道**——误调用的痕迹由 App 发**既有** `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` **事件**承担，**不写 `CloudAuditEvent`**：`record_denial()` 的 `reason` 是四值闭集（枚举外值 fail-closed 抛 `SAFETY_CLOUD_BLOCK`），且其不变量是「每条任务清理路径**恰一条**」+「终止语义」——误调用之后任务并不终止（还要进授权等待、还可能走通），补一条会同时破坏两条不变量（§3.2）。**错误码表、`record_denial` 四值枚举、`CloudAuditEvent` reason 闭集均零改动。**
> 阶段：P4 重设计（模型提出咨询与候选上下文；规则、隐私策略和用户有限授权共同裁决外发；云端仅 advisory）
> 性质：编码前必读。本契约替代此前 P4「零实体」实现方向；旧 P4 代码仅作可回退基线，**不得**据此契约静默改写，直到本文件标为 `✅ 待实现`。
> 前序依赖：`00-core-interfaces.md`、`00-error-contract.md`、`00-adapter-factory.md`、`01-p0a-main-loop.md`、`04-p3-safety-hardening.md`。

---

## 0. 重设计目标、范围与不变量

此前 P4 的「零实体」方案能保证云端不接触用户内容，却使云端只有意图类别、没有实际问题，无法验证云端咨询的真实效用。本次重设计的目标不是恢复模型自动上传原文，而是建立：

> **模型提出建议 → 规则裁决 → 本地隐私缩减/脱敏 → 用户有限授权 → 最终边界复核 → 唯一出口发送**

> **2026-09-03 定位调整**：云端的核心价值是**受控推理升级**——以更大上下文与更强推理处理本地小模型难以稳定完成的复杂任务（复杂推理、架构权衡、代码分析、长上下文综合），联网资料检索只是升级原因之一。外发单位从「建议询问」升级为**最小推理任务包**（TaskBrief，§2.5）；安全骨架（模型仅建议、确定性裁决、PrivacyPolicy、有限 grant、CloudBoundary、唯一出口、advisory 回流、执行确认）全部不变。

### 0.1 P4 做的事

1. 模型通过 `ConsultationProposal` 建议是否咨询云端、提出候选上下文；模型没有联网或授权权力。
2. `ControlPolicy` 根据模型建议、用户明确指令、确定性否决规则、预算和冷却期裁决是否进入授权流程。
3. 新增独立 `PrivacyPolicy`：对候选内容进行来源分类、字段策略、类型/长度限制、凭据检测、脱敏和语义占位替换。
4. 引入任务绑定、预算绑定、可过期且不可扩大的 `AuthorizationGrant`，使同一任务的已授权 sub-turn 可复用而不反复确认。
5. `CloudBoundary` 对 PrivacyPolicy 的最终 package 做独立复核，`SideEffectGateway` 仍是唯一云端网络出口。
6. 保留云端 advisory、本地重解、受云端影响计划强制确认、非执行本地整合呈现和脱敏审计。

### 0.2 P4 不做的事

- 不允许模型直接调用 `CloudAdvisoryBackend`、直接创建 grant、批准候选字段或扩大已有 grant。
- 不实现永久/全局授权、跨任务授权、跨会话授权或「以后都允许」授权。
- 不允许秘密/凭据原值、完整连接串、未授权自由文本、代码、路径或日志外发。
- 不放宽 P3 的 Gate ①②③；云端影响的计划仍一律强制用户确认。
- 不让云端直接面对用户、产生 `ExecutionPlan`、标记 `approved` 或跳过本地验证。
- 不在本阶段重构旧 P4 代码；本契约完成后由 Codex 先同步 `00-*` 工程契约，再实现。

### 0.3 不变量

1. **控制权**：模型只提 `ConsultationProposal`；ControlPolicy 决定是否进入授权；PrivacyPolicy 决定可发送候选；用户 grant 决定具体外发边界；CloudBoundary 最终复核。
2. **用户否决优先**：用户输入明确「不要联网」/「不要发给云端」时，优先级高于模型建议和用户历史 grant，当前任务不联网。
3. **有限授权**：grant 绑定 task/session/provider/purpose/类别或确切 payload/max_turns/预算/expiry；不能扩大。
4. **唯一出口**：实际网络调用只在 `SideEffectGateway.execute_cloud_turn()` 内。
5. **云端不可信**：云端输出永远是 advisory；入站检查、本地重解、执行强制确认均不可绕过。
6. **审计最小化**：审计记录决策、边界、类别、脱敏结果、预算和拒绝原因；不记录原始秘密、未授权原文或 `analysis` 原文。

---

## 1. 模型建议与 ControlPolicy 裁决

### 1.1 ConsultationProposal（模型输出）

在 `IntentCandidate` 内新增字段 `consultation_proposal: ConsultationProposal | None`。模型只产生如下建议，不得产生 grant、payload 批准标记、provider 最终选择或执行计划：

```python
@dataclass(frozen=True)
class ConsultationProposal:
    should_consult: bool
    escalation_reason: str             # 受限枚举，见下
    expected_benefit: float            # 0.0..1.0，仅建议信号
    proposed_question: str = ""        # 待推理问题候选（不可信，仅作 TaskBrief 素材）
    local_attempts_summary: str = ""   # 本地已尝试候选摘要（不可信，仅作 TaskBrief 素材）
    candidate_context: list[ContextCandidate] = field(default_factory=list)
    reasoning: str = ""                # 仅本地使用，绝不自动外发

@dataclass(frozen=True)
class ContextCandidate:
    category: str                      # 见 §2.1，模型标签不可信
    label: str
    value: object
    source: str = "model_proposed"     # 固定为模型建议，不是可信来源
```

`escalation_reason` 是受限枚举：`reasoning_complexity` / `architecture_tradeoff` / `code_analysis` / `long_context_synthesis` / `specialized_analysis` / `current_information` / `unknown`。非法值归 `unknown`。`expected_benefit` 越界裁剪到 `0.0..1.0`。`proposed_question` / `local_attempts_summary` 是模型建议的**不可信候选素材**：只能作为 TaskBrief（§2.5）对应 section 的输入，经 PrivacyPolicy 扫描脱敏后使用；模型不能直接构造 TaskBrief、package、grant 或选择 provider。

> **何时应当提议（P6d 补，2026-09-15）**：本节只定义 `ConsultationProposal` 的**形状与取值域**，不定义模型应在何时建议云端——后者由 `10-p6d-autonomous-escalation.md` §2 钉死（五情形判定顺序、正反例、`model_confidence` 释义禁令、把 `escalation_reason` 的值域写进模型 schema）。该标准**不改变**本节任何字段语义、默认值与归一化规则；`should_consult=True` 仍然只是**建议**，是否升级由 §1.3 的确定性准入独裁。

### 1.2 用户云端指令

`InputEvent`/输入解析需识别两类本地控制指令（具体 CLI 语法由 Codex 在工程契约定，不能进入模型 prompt）：

| 指令语义 | 效果 |
|---|---|
| **允许本次问云端** | `force_cloud=True`：绕过**模型侧判断**——`READY`/`VAGUE`/`PARTIAL` 状态标签、置信度、`should_consult=False`、低效用建议、一般 `missing_info`（模型认为缺失的信息改经 TaskBrief `brief_unknowns` 外发，§2.5）、模型声明的本地动作（`tool_intent`，2026-09-18 前读 `suggested_tools` 清单）、**归一化后的 `risk_draft`（`dangerous` 除外）**均可被绕过；**不可**绕过：`deny_cloud`、dangerous 风险、真实工具执行态与敏感执行链（App 确定性状态，非模型输出）、云端禁用或不可用、单任务预算/冷却、PrivacyPolicy、CloudBoundary、出站预览和用户授权（完整否决集见 §1.3）。任务文本为空（`/cloud ask` 后无实质内容）时不得升级，走本地追问而非发送空任务。模型未提议时，TaskBrief（§2.5）仍由本地从原任务语义**逐字段脱敏构建**，并在 `AWAITING_AUTHORIZATION` 展示最终版本——**用户确认即对该内容的显式选择**，未经确认不得发送 |
| **不要联网** | `deny_cloud=True`：当前任务的最高优先级否决；清除/禁用当前任务的未消费 grant，不发网络 |

普通自然语言不得因包含“云端”二字就被当作指令；解析需使用明确命令/显式交互状态，避免误触发。

### 1.3 ControlPolicy 的双判定：云端咨询准入 vs 本地就绪（2026-09-14 拆分）

ControlPolicy 不调用模型。其输入扩展为：`IntentCandidate + CloudControlState + 确定性事实`（`no_progress` / `reference_guard` / `resolution_exhausted`）。轮次**不再是**策略输入——`decide()` 的 `round_count` 与 `evaluate_cloud_admission()` 的 `round_count` / `max_resolution_rounds` 已于 2026-09-17 删除（`14-resolution-exhausted.md` §3）。

```python
@dataclass(frozen=True)
class CloudControlState:
    cloud_enabled: bool
    force_cloud: bool = False
    deny_cloud: bool = False
    provider_available: bool = False
    remaining_turns: int = 0
    cooldown_active: bool = False
    task_has_sensitive_execution_chain: bool = False
    # 2026-09-14 新增：剥离 /cloud 指令前缀后的任务文本非空（App 确定性设置，不依赖模型输出）。
    # 默认 False 是 fail-closed：遗漏该字段的调用方在 force_cloud 下不升级（宁可本地追问，不误发空任务）；
    # P4 主链路 App 必须显式传值。既有离线调用（cloud_enabled=False）不受该字段影响。
    has_task_text: bool = False
```

**背景（为什么拆）**：`is_effectively_ready` 服务于「本地回答/执行就绪」（IntentResolver 提前停止、PLAN_LOCAL、TaskPlanner 入口），它的「无 `missing_info`」条件对本地执行是正确的。但真实 P6b 运行（S06/S08）暴露：本地小模型会把信息充分的开放式分析题连续判为 `PARTIAL/VAGUE + missing_info`，若云端准入复用该判定，`RETRIEVE_MORE` 会永远拦在云端之前——「由强模型补足本地小模型能力」的核心价值反过来受制于本地小模型的完整度判断。因此：

> **「本地回答/执行就绪」与「只读云端咨询准入」是两个独立判定。`is_effectively_ready` 语义不变、继续服务本地路径；云端准入有自己的确定语义，`missing_info` 不再一票否决云端咨询——模型认为缺失的信息改经 TaskBrief `brief_unknowns` 随包外发（§2.5）。**

**每轮判定顺序（`decide()` 内从高到低，固定）**：

1. `risk_draft == dangerous` → `REFUSE`（最高优先级；云端路径不参与评估）。**2026-09-20 修订（P7a）**：该判据的实现是 `admission.gate_result == "not_evaluated"` **且** `_is_dangerous(candidate)` 为真（`10 §4.3` 来源①）——`not_evaluated` 在 P7a 后**不再等价于 dangerous**，新增的来源③（能力终端性失败）**不**在此早退，而落到第 4 步（`16-p7-practical-tools-capability-routing.md` §3.8 ②）。分支体按来源分流的**义务**在此：漏分流会让能力缺失的回合返回 `REFUSE` + 理由句「草案被标记为危险」。
2. **悬空指代护栏已评估且 `triggered`，且非 force 轮** → `ASK_USER`（`11-reference-guard.md` §3.1；force 轮让位但照常评估）。
3. **云端咨询准入判定**（下述否决集 + 准入路径）→ 通过则 `REQUEST_CLOUD`（并结束本轮判定）。**2026-09-20 补（P7a）**：准入函数内部另有一个**早裁**——`force_cloud` 为假且能力终端性失败（`capability_resolution ∈ {unavailable, unrecognized}` 且无草案）时直接返回 `not_evaluated`（来源③），使该回合**不产生** `cloud_consult`。理由：云端是**推理**能力、不是联网检索，「本地没有实时数据能力」送去云端只会换来编造的实时数据（`16` §6.6）。它**不**覆盖 force 轮（与第 2 步 `and not force_cloud` 的既有非对称一致）。
4. 未准入 → **本地就绪判定**（语义不变）：有效 READY → 既有置信度/风险分档（`PLAN_LOCAL`/`ASK_USER`，均不再含云端分支）；`no_progress` → 条件化本地回答或 `ASK_USER`；**`resolution_exhausted`（本次解析已用尽实例 `max_rounds` 且未有效 READY）→ `ASK_USER`**；`missing_info` 非空 → `RETRIEVE_MORE`；否则 `ASK_USER`。

> **原第 2 步「`round_count > max_resolution_rounds` → `ASK_USER`（超轮次不走云端）已于 2026-09-17 删除**（`14-resolution-exhausted.md` §5）。它不可达（`intent_max_rounds` 校验为 `1..4` 而判据是 `> 4`），且位置错误——它是**调度**规则，放在准入函数内使其天然位于放行分支之前、**没有 force 豁免**，与本节「模型输出不得充当否决项」的既有裁决（`suggested_tools` 移出、`risk_draft` 于 2026-09-16 / 2026-09-17 两步移出）和 `11 §3.1` 第 2 步（`and not force_cloud`）已多次确立的非对称原则冲突；同时把「规则说不」记成了 `not_evaluated`，污染归因。轮次用尽的事实改由 `resolution_exhausted` 承担（第 4 步），`evaluate_cloud_admission()` 的 `round_count` / `max_resolution_rounds` 两个参数与常量 `_MAX_RESOLUTION_ROUNDS` 一并删除，`not_evaluated` 收窄为**两种来源**（dangerous 早裁、未进入正常调度的回合）。**2026-09-20 再修订（P7a）**：`not_evaluated` 由两种来源扩为**三种**——新增来源③「能力终端性失败早裁」（`16-p7-practical-tools-capability-routing.md` §3.8 ①、`10 §4.3`）。值域不变（仍是准入表的 9 值之一），且**不**违反「模型输出不得充当否决项」：该早裁读的是**注册期声明的能力存在性**（`capability_resolution` 由能力目录这一确定性事实派生），不是模型自评。

> **提前停止不改准入语义（P6d 补，2026-09-15）**：P6d 引入「连续两轮语义签名不变且检索零新增 → 提前停止」（`10-p6d-autonomous-escalation.md` §3）——它只在第 4 步的 `missing_info` 分流处把**空转的 `RETRIEVE_MORE`** 换成 `ASK_USER` 或条件化本地回答（`PLAN_LOCAL`，只读、无需确认——空计划按构造零副作用），位置在第 3 步**之后**。因此：有合法 proposal 的候选照旧先过云端准入并升级（提前停止不会吞掉升级建议）；否决集、安全分支与用户授权一律不受影响；`resolve()` 的返回候选原样携带 `consultation_proposal`。

> **轮次用尽不改准入语义（2026-09-17 补，`14-resolution-exhausted.md`）**：`resolution_exhausted` 与上一条同理，是**第 4 步的本地分流**（把「没有下一轮的 `RETRIEVE_MORE`」换成 `ASK_USER`），位置在第 3 步**之后**。它由 `IntentResolver` 在循环自然出口确定、App 原样转发（`decide(..., resolution_exhausted=…)` **必传、无默认值**），与 `no_progress` **互斥**且**不得**互相复用（两者证据不同：前者是「走满上限」，后者是「连续签名不变 + 检索零增」）。因此**轮次用尽的候选照样先过云端准入**：force 轮与 proposal 轮在轮次用尽时均可升级——旧规则「超轮次不走云端」已删除，理由见上。危险早裁、悬空指代护栏、各否决项与用户授权的相对顺序均不变。

**云端准入否决集（从高到低，任一命中即不升级、走第 4 步本地判定；「适用路径」列标注 `force` 的项 `force_cloud` 也不得绕过）**：

| # | 否决条件 | 适用路径 | 说明 |
|---|---|---|---|
| 1 | `deny_cloud=True` | force + proposal | 用户否决最高优先级 |
| 2 | `risk_draft == dangerous` | force + proposal | 防御性重复（第 1 步已 REFUSE） |
| ~~3~~ | ~~`risk_draft != "normal"`~~ | ~~仅 proposal~~ | **本否决项已于 2026-09-17 删除**（`12-risk-draft-closed-set.md` §3.2/§3.4，裁决 R6）——`risk_draft` **两个路径都不再否决**。理由链：① 该字段是**模型自由输出**，不是确定性安全事实（模型只要说 `normal` 就能通过本项），因此它不构成安全边界；② 2026-09-16 先把它移出 force（否则用户显式指令随模型措辞漂移，真实 run：S06/S08/S10/S13 的 `/cloud ask` 被判 `non_normal_risk`）；③ 2026-09-17 再移出 proposal——真实 run 显示自主升级臂被它**整体锁死**（S09 `base` 3/3、S06 `cloud_auto` 3/3 `risk_draft=sensitive` → `vetoed` + `non_normal_risk`，实际准入 0/3，目标 ≥2/3）。**`sensitive` 的保守性改由「强制用户授权」承担**（§1.3a）：链路可以走到 `REQUEST_CLOUD`，但外发前必须有用户显式 grant，**安全强度不降**——变的是「模型措辞能否决定链路走不走得下去」。**行号保留**，以免否决项编号（10 §4.3 的 `proposal_denied_reason` 表按编号一一对应）整体漂移 |
| 4 | `task_has_sensitive_execution_chain=True` | force + proposal | **真实工具执行态**：敏感执行链未结清——这是 App 确定性状态，不是模型输出。待确认的真实工具计划在用户发送 `/cloud ask` 时按 §1.4 规则 3「新输入取代」取消（计划不执行），**规则 3 先于准入裁决生效，主链路该字段恒为 `False`**——保留为防御性否决项，不宣称当前已生效；反过来说，捕获取消前的 pending 状态并传 `True` 会错误拦截用户显式 `/cloud ask`，不可取。若未来流程允许「待确认计划 + 云端咨询」并存，须新增 App 侧状态字段并经接口审查 |
| 5 | `cloud_enabled=False` 或 `provider_available=False` | force + proposal | 云端禁用或不可用。**当前 `provider_available` 由 App 的启用态决定（等于 `cloud_enabled`）**：启用态 bootstrap 已校验 provider profile、模型与凭据，能启动即静态可用；真实网络故障只能在调用时发现，提前探测会产生一次未经授权的云端请求，故不纳入决策阶段。**归因提示（2026-09-16 代码审查补）**：因此 `proposal_denied_reason="provider_unavailable"` 在本阶段不可达；运行期真实的 provider 不可达（网络/凭据失效/限流）呈现在**另一阶段**——`cloud_consult` 事件的 `denied_reason ∈ {auth, endpoint, rate_limited, unavailable}`（09 §错误分类）。两处 `denied_reason` **同名不同 stage、取值域不同**，按本表查 `provider_unavailable` 的读者应改看 `cloud_consult` |
| 6 | `remaining_turns <= 0` 或 `cooldown_active=True` | force + proposal | **单任务预算耗尽或处于冷却期**（§3.3/§5.1）。保证范围是**同一次云咨询任务及其续咨询 sub-turn** 的累计预算与冷却；普通对话轮次之间**不共享**预算（App 每轮生成新 `task_id` → 新台账），本契约不宣称跨轮限流。会话级/用户级限流与有界终态台账属新需求，见 §14 遗留 |
| 7 | `force_cloud=True` 且 `has_task_text=False` | 仅 force | **空任务不升级**：`/cloud ask` 后无实质任务文本时本地追问（ASK_USER/RETRIEVE_MORE），绝不发送空任务 |

> **`risk_draft` 只在归一化后的闭集上比较（2026-09-16）**：合法取值只有 `normal` / `sensitive` / `dangerous`。归一化（大小写与首尾空白统一、旧词表固定映射 `low→normal` / `medium→sensitive` / `high→sensitive`、**缺失/空/非字符串与未识别值一律 fail-closed 到 `sensitive`**）由解析层唯一实现 `normalize_risk_draft()` 完成（`12-risk-draft-closed-set.md` §2）——**闭集外的原始字符串不得进入 ControlPolicy**。
>
> **该字段在本表只剩一个作用（2026-09-17）**：本表**唯一**读 `risk_draft` 的地方是否决项 2（`dangerous`，防御性重复）；即第 1 步的 `REFUSE` 早裁。**两个准入路径都不再因该字段否决**（force 自 2026-09-16 起、proposal 自 2026-09-17 起）。`sensitive` 的保守性由 §1.3a 的强制用户授权承担，**不在本表表达**。判定对象的钉死（本回合实际请求的动作）见 `12-risk-draft-closed-set.md` §1.2.1。
>
> **本表如何读闭集外值**（策略层的防御规则，2026-09-16 二轮）：ControlPolicy **不做**归一化，只读闭集；对闭集外值必须总量有定义——`strip().lower() == "dangerous"` 的写法变形（`"DANGEROUS"` / `" dangerous "`）按 `dangerous` 处理（危险方向的方向性宽容），其余闭集外值（`None` / `42` / `"critical"` / `"high"` …）按 `sensitive`。**任何情况下不得退化为 `normal`**。详见 `12-risk-draft-closed-set.md` §2.1.1。（旧实现 `_is_dangerous()` 只 `.lower()` 不 `strip()`、其余分支直读字符串，是「归一化无单一归属」的症状——修法是把归一化上移，不是在策略层补 `strip`。）

**「模型是否提议了本地动作」的归属区分（2026-09-14 二轮修正；2026-09-18 判定源更换，`15-tool-orchestration-hardening.md` §2.5）**：模型建议的工具清单**不是否决项**——它本身是模型输出，小模型误建议一个工具就能把用户显式 `/cloud ask` 锁死，与本次拆分要修的 `missing_info` 锁是同一类问题。区分处理：

- **force 路径**：忽略模型侧的本地动作声明。云端咨询回合不执行任何工具（advisory-only + `check_response` 拦可执行标记），不存在副作用泄漏；若回流后本地计划受云端影响，仍强制确认并过 P3 三关（§6.3）。
- **proposal 自动路径**：仍要求**模型未声明本地动作**——模型自己声明了可行本地工具路径时，自动升级保守退出（这是**自动**升级的保守条件，不是用户指令的锁）。
- **判定源（2026-09-18）**：读 `candidate.tool_intent == "local_action"`（结构化草案的声明，`15` §2.4），**不再**读 `suggested_tools`——后者降级为纯观测字段，不再是任何判定的输入。观测面的对应值同时由 `suggested_tools_present` 改名为 **`local_action_proposed`**（`10 §4.3`）。

**准入通过条件（否决集全部未命中后，二选一）**：

- **force 路径（用户显式 `/cloud ask`）**：`force_cloud=True` 且 `has_task_text=True` → `REQUEST_CLOUD`（reason 标明 `forced`）。**不评估**模型状态标签、置信度、`should_consult`、`expected_benefit`、`missing_info`、`tool_intent`**、`risk_draft`（`dangerous` 除外，已由否决项 2 与第 1 步截住）**——`VAGUE`/`PARTIAL` + `missing_info` 非空同样升级；`sensitive`（含旧词表与未识别值）同样升级；模型未提议（`consultation_proposal=None`）时由 App 合成默认 proposal（`purpose` 取 `unknown`，TaskBrief 全部由本地构建，§2.5）。
- **proposal 路径（无显式命令，模型建议）**：`should_consult=True`、`expected_benefit >= 0.5`、`tool_intent == "none"`（模型未声明本地动作），且满足以下之一：
  - 有效 READY（`is_effectively_ready`，既有行为不变）；
  - **状态 ∈ {PARTIAL, ALMOST} 且 `intent_type` 非 `unknown`**（2026-09-14 新增）——目标已明确但本地小模型自认为信息不完整的候选，可进入受控云端授权；`missing_info` 随 TaskBrief `brief_unknowns` 发送。
  - `VAGUE` 或 `intent_type == "unknown"` 且无 `force_cloud` → **不自动升级**（走本地路径）。

#### 1.3a `sensitive` 提案的强制用户授权（2026-09-17 裁决，`12-risk-draft-closed-set.md` §3.4）

准入通过后，**本任务的有效授权风险**决定授权形态——`normal` 与否是任务级事实，**不逐轮重判**，也**不只听模型**：

| 有效授权风险 | 授权形态 |
|---|---|
| `normal` | 按既有隐私模式分流：`convenient` 下满足增量纯度即可 `create_policy_grant`（§3.2/§5.3）；另有用户确认路径 |
| **`sensitive`**（含 `mapped_legacy` / `absent` / `unrecognized`） | **强制用户授权**：`PREPARING → AWAITING_AUTHORIZATION`，只有同 session 显式 `/cloud allow` 才 `create_user_grant`。**所有隐私模式（含 `convenient`）**一律如此——不得 policy grant、不得无人值守同回合自动续、不得复用旧任务或旧 grant 的授权 |
| `dangerous` | 不适用（第 1 步已 `REFUSE`） |

**有效授权风险的求值（2026-09-17 补，`12-risk-draft-closed-set.md` §3.5 为权威）**：它是 `max(模型因果风险, 确定性升险结果)`，序 `normal < sensitive < dangerous`，**两个方向都不得下调**：

1. **模型因果风险只作下界**：准入时被准入候选归一化后的 `risk_draft` 记入 `LocalTaskContext`（同时仍是 `intent_final.risk_draft` 的观测值）——它是**下界**，不是最终值。理由是 `12` §0.3 的既有边界声明：**模型输出不是安全边界**；若把决策权只交给它，模型把真实敏感任务误判成 `normal` 时，续咨询仍可能拿到 policy grant。
2. **确定性升险源（只能升，恰两项）**：① `PrivacyPolicy` 对**实际 payload 候选**的分类结果（含 `secret` 命中、需拒绝、脱敏后复扫仍留命中）→ ≥ `sensitive`；② `task_has_sensitive_execution_chain=True` → ≥ `sensitive`。**中文自然语言凭据（§2.3c）经同一分类结果进入本项**——值区非空的命中即「含 `secret` 命中」，section 级拒绝（§2.3c.4 第 2 条的「替换后无任务语义」）即「需拒绝」；两者都在本项既有两项之内，**不新增信号**（2026-09-24 第三轮：凭据类不再有独立的「拒绝」处置，见 2.3c.4）。**工具计划 / preflight 类风险不进本链路**（2026-09-18 收窄，`12` §3.5 表后注为权威）：policy grant 发生在**续咨询**阶段，此时通常既无 `ExecutionPlan` 也未跑 preflight，把它列为输入会让「未求值即 `sensitive`」把该信号恒判 `sensitive`，`normal + convenient` 自动续（§1.4 规则 8、`10` §7.1 第 18f 项）再次不可达；工具侧风险由本地 preflight（`07` §6.3）与 `approval_profile`（`13` §2）**独立承担且只升不降**，真实敏感执行链本就是本表第 6 条的准入硬否决，故无缺口。
3. **失效兜底**：适用信号（①②）**缺失 / 求值异常 / 拿不到** → `sensitive`（fail-closed）。
4. **时点**：准入时冻结**下界**；**授权时**（`create_policy_grant()` 调用点）用当时的确定性信号求**有效值**，把有效值传给 `escalation_risk`。**不得**在准入时就把模型下界当最终值；**不得**为了走通自动续而给信号填 `False`。
5. **「隐私扫描没发现问题」不是降险依据**：它不得把模型声明的 `sensitive` 降回 `normal`——两者是 `max` 关系，不是覆盖关系。
6. 纯函数 `effective_authorization_risk(causal_risk, *, payload_candidates_sensitive=True, sensitive_execution_chain=True) -> str` 落在 `risk_vocabulary`（与 `normalize_risk_draft` 同层）；**参数表恰为这两个**，两信号默认 `True` 是刻意的 fail-closed 方向（漏传即得 `sensitive`）；工具计划类参数**不得**接回（`12` §4.2.5 E3 的参数名反向断言）。
7. **方向确认**：本条的净效果只会让**更多**任务进强制授权，不会让任务更容易上云——`normal` 要求模型与**全部适用**确定性信号**同时**为 `normal`；反过来说，**`normal` 必须仍然可达**（正例见 `12` §4.2.5 E8 与 §1.4 规则 8）——一个「恒判 `sensitive`」的实现同样违约，因为它把 `convenient` 的自动续咨询整条废掉。

**不变量（照 12 §3.4 逐条对齐）**：

1. `REQUEST_CLOUD` 对 `sensitive` 提案**只**产出 PrivacyPolicy 脱敏准备与**最终实际 payload 的授权 preview**——**零网络请求**，授权前 `cloud_consult` 的 `phase="authorization_required"` 事件必须存在且 `outbound_bytes == 0`；
2. 用户在看过 preview 后的显式 `/cloud allow` 是**唯一**外发授权；`/cloud ask` 打开的 preview **不是**授权（§1.2 语义不变）；
3. 授权后既有检查**一条不减**：PrivacyPolicy 分类/脱敏/候选类别与来源校验、`CloudBoundary` 独立复核、grant 精确绑定（task/session/provider/purpose/预算/有效期）、预算与冷却、审计链；preview 内容集 = grant 指纹集 = `context_items`，**逐项一致**（§2.3.4/§4.2）；
4. 识别出的秘密/隐私原值**不得**进入 payload、事件、审计或异常信息；
5. 拒绝 / 取消 / 超时 / 跨 session / 新输入取代：清 pending、`revoke_task`、**零网络调用**、无残留 payload 供下一任务复用（§1.4 规则 3–5、§5.3 规则 5）；
6. **`dangerous`、`task_has_sensitive_execution_chain`、`deny_cloud`、provider 不可用、预算/冷却、force 空任务**等红锁**一条不减**（§1.3 否决集，仅删除已废弃的第 3 项）；
7. 可观测性**不新增枚举**：同一回合 `dispatch_decision.proposal_gate_result="admitted_proposal"` + `intent_final.risk_draft="sensitive"` 即为「`sensitive` 提案进入授权」（`12-risk-draft-closed-set.md` §3.3）。

**实现侧的确定性接线**：App 在准入时把该因果风险（**模型下界**）记入任务状态（`LocalTaskContext`，仅本地）；在**任何** `create_policy_grant()` 调用点用当时信号求**有效值**并显式传入 `escalation_risk`（新增关键字参数，**默认 `"sensitive"` 即 fail-closed**——不显式传 `"normal"` 就拿不到 policy grant）。AuthorizationManager 侧的前置条件与防御性拒绝的错误/审计契约见 §3.2，签名变更登记见 `12-risk-draft-closed-set.md` §5。

**模型不可自评的部分**：模型能建议效用和候选上下文，但最终路由、准入与否决、预算、冷却、可用性、敏感执行链、用户否决均由确定性状态决定——**授权形态同样如此**（由归一化后的风险值决定，不由模型声明「我已经考虑过风险了」之类措辞决定）。

**`REQUEST_CLOUD` 之后的链路不变**：PrivacyPolicy prepare → `AWAITING_AUTHORIZATION` 展示最终 payload → 用户 grant → CloudBoundary → 唯一出口（§1.4/§3/§4）。`_handle_cloud` 既有防御分支（云端禁用 → denied 事件；无任何可安全发送候选 → `no_safe_context` 拒绝）保留为纵深防御——准入层是第一道闸，不是唯一一道。云端可对 `brief_unknowns` 中的缺失信息给出条件化分析，或经 §6.1 followup 协议（`requested_context_categories` 白名单）提出受限追问——追问机制无任何扩展。

### 1.4 授权交互与任务生命周期状态机

P4 的授权不是普通自然语言确认，而是 App 持有的**本地、会话绑定状态机**。新任务生成 `task_id` 的时点固定为：ControlPolicy 首次裁决 `REQUEST_CLOUD` 后、调用 PrivacyPolicy 前。App 允许在更早的每回合流程中生成候选 `task_id` 用于预算/冷却查询（`CloudControlState`），但该早期 id 必须与后续任务 id 同一，不得中途更换（2026-09-06 审查同步）。该 task_id 贯穿 preparation、grant、CloudRequestPackage、CloudAuditEvent 与后续本地 ExecutionPlan。

```text
IDLE
  └─ REQUEST_CLOUD → PREPARING(task_id)
PREPARING
  ├─ 无可发送 candidate 且无 fixed_config package → COMPLETED_LOCAL（本地 ASK_USER/回复）
  ├─ policy_grant 可签发（convenient 低风险实体，且本任务**有效授权风险**为 `normal`） → AUTHORIZED（P4 中 TaskBrief 恒含 free_text、首轮台账为空 → 实际不可达，保留为防御分支；增量纯度见 §3.2）
  └─ 需用户授权 → AWAITING_AUTHORIZATION(展示最终 payload + 边界)
      （本任务**有效授权风险**为 `sensitive` 时**必经此支**，与隐私模式无关——§1.3a）
AWAITING_AUTHORIZATION
  ├─ 同 session 明确「允许发送」 → AUTHORIZED（create_user_grant）
  ├─ 同 session 明确「拒绝」/「取消」/deny_cloud → CANCELLED
  ├─ 非确认普通输入 / task 或 session 改变 → CANCELLED（新输入按新任务处理）
  └─ 授权等待超时 → EXPIRED
AUTHORIZED
  ├─ gateway 成功一轮且 needs_more_info、无有效类别请求 → COMPLETED（consult 内改写收敛，§6.1 规则 1）
  ├─ followup 请求合法类别且本地产出新内容 → convenient 且新增候选全为 allowlisted `user_entity`（增量纯度，§3.2）**且本任务有效授权风险为 `normal`** 同回合自动续 / 其余 → AWAITING_AUTHORIZATION（续咨询挂起，§5.3）；**本任务有效授权风险为 `sensitive` 时一律走后者**
  ├─ followup 产不出新内容 / 扩张超限 / 后续轮失败 → COMPLETED（以最近部分 advisory 收敛，§5.3 规则 6）
  ├─ 最终 advisory / 本地回流完成 → COMPLETED
  ├─ 网络失败 / 入站拒绝 / 出站拒绝（首轮即失败、无在手 advisory）→ FAILED
  └─ grant 过期、deny_cloud、用户拒绝扩张 → EXPIRED/CANCELLED
```

**状态与会话规则**：

1. `PendingCloudAuthorization` 至少保存 `task_id`、`session_id`、`provider`、`purpose`、`PrivacyPreparation`、最终 preview、创建时间与 `authorization_deadline`；不保存原始 secret 或未授权原文。
2. 只有同一 `session_id` 的明确授权指令可恢复 `AWAITING_AUTHORIZATION`；跨 session 授权一律取消 pending，不发网络。
3. 任意非授权普通输入、用户取消、deny_cloud、session/task 切换均清理 pending；清理后不得保留未确认 payload 供下一任务复用。
4. `authorization_deadline` 固定为创建后 5 分钟（P4 常量，非配置）；超时清理 pending，返回 `CLOUD_AUTHORIZATION_EXPIRED` 的用户提示；不会创建 grant 或消耗预算。
5. 用户拒绝/取消/超时均不创建 grant、不发网络、不消耗 turn/context 预算；记录最小化拒绝审计（经 §4.3 `record_denial` 专用入口，事件形态与 reason 枚举见该节）。
6. P4 grant 的复用只覆盖同一 task 的连续 cloud sub-turn，不跨后续普通用户回合；任务完成、失败或取消后 grant 立即失效并从活跃状态移除。
7. 同一 task 同时至多一个活跃 grant；边界扩大续咨询（§5.3）的新 grant 签发即吊销旧 grant。
8. **`sensitive` 所致升级的任务不签发 policy grant（2026-09-17 裁决，§1.3a）**：任务级「有效授权风险」= `max(准入时冻结的模型下界, 授权时的确定性升险结果)`（§1.3a 第 1–5 点；`12` §3.5 为权威）。模型下界随 `LocalTaskContext`（§1.5）存活至任务终态；**每次** `create_policy_grant()` 收到的是**当时求出的有效值**，而不是准入时的模型下界，更不是「本轮新增候选的风险」（§3.2）。有效值为 `sensitive` 时，`convenient` 模式下**同样**进 `AWAITING_AUTHORIZATION`；用户 grant 也只能由同 session 的显式 `/cloud allow` 产生。**不得**用「上一轮已授权」「同一 session 已授权过」推断授权。`preparation` 的候选类别只能**升险**（§1.3a 升险源①），**不得**用于降险：「候选全是 allowlisted 实体」不构成把有效风险降回 `normal` 的理由（它是升险源的输入之一，不是降险依据）。

### 1.5 确认回合的本地任务语义（2026-09-03 新增）

授权确认发生在**下一用户回合**，此时「当前输入」已不是原任务。为让本地回流重解仍具备原任务语义，同时不把未授权原文写入任何授权结构：

1. App 维护会话绑定的 **`LocalTaskContext`**（仅内存、仅当前任务/会话）：原始 `InputEvent`、`task_id`、`escalation_reason`、结构化任务状态（intent_type、allowlisted 实体、轮次）。它**绝不**进入 pending 预览、grant、`CloudAuditEvent` 或云端 package；任务完成/失败/取消或会话结束即清除。实现形态不限定——具名 dataclass 或等价的 App 内部字段组合均可，以本条数据不变量为准（2026-09-06 审查同步）。
2. `PendingCloudAuthorization` 只保存 §1.4 规则 1 的脱敏 preview（TaskBrief 授权版本）与结构化任务状态。
3. 确认后的本地重解以 `LocalTaskContext` 的原任务语义为基础（§6.2），advisory 仅为 UNTRUSTED EXTERNAL REFERENCE；禁止用「继续」「允许」这类无语义占位输入参与重解。
4. 「原任务语义」（仅本地）与「授权边界数据」（可审计/外发）两类信息不得混用存储；审计与 grant 只见脱敏结果。

---

## 2. 数据来源分类与 PrivacyPolicy

### 2.1 内容分类（不可混淆）

每个候选字段必须带分类；未分类字段默认按最高风险拒绝：

| category | 含义 | P4 默认行为 |
|---|---|---|
| `fixed_config` | 固定配置/协议文本，非用户派生 | 可按策略自动发送 |
| `user_entity` | 从用户输入、模型实体、项目状态派生的结构化值 | 需 PrivacyPolicy 判定，严格模式确认；可在 grant 内复用 |
| `free_text` | 用户原文、摘要、自然语言、代码、日志、路径 | 默认需显式 grant；类型/长度限制 + 脱敏 |
| `secret` | 密码、令牌、密钥、连接串、认证材料 | 原值永不发送；仅可按规则替换为 `secret_placeholder` |
| `secret_placeholder` | 语义占位，如 `{label: "api_key", value: "present"}` | 可发送，不含原值 |

模型提出的 `entities`、摘要、字段名、分类标签都属于**不可信用户派生候选**，不因模型自称 `fixed_config` 或 `secret_placeholder` 自动信任。

### 2.2 PrivacyPolicy 职责与签名

新增本地安全层 `PrivacyPolicy`（位置建议 `src/safety/privacy_policy.py`）。它持有固定策略表，不调用云端/模型：

```python
class PrivacyPolicy:
    def prepare(
        self,
        proposal: ConsultationProposal | None,
        context: MinimalContext,
        task_id: str,
        session_id: str,
        provider: str,
        purpose: str,
    ) -> PrivacyPreparation:
        """分类、缩减、脱敏候选，绝不发送网络。"""
```

隐私模式（strict/balanced/convenient）在 `PrivacyPolicy` 构造期一次性注入（安装级固定配置），不随 `prepare()` 传入。

TaskBrief（§2.5）的入口通道：App 将其各 section 以 `ContextCandidate(source="local_task_context", category="free_text", label=brief_* 固定名)` 形式并入 proposal 候选传入 `prepare()`；PrivacyPolicy 对其执行与 free_text 相同的扫描/脱敏（**内容判据一条不减**），并校验 label 属于 §2.5 的固定集合（`source="model_proposed"` 的候选不得使用 `brief_*` label）。**但不对其施加独立长度上限**（2026-09-17 裁决，见 §2.5 规则 3）：`brief_*` section 没有自己的字节硬边界，唯一字节硬边界是整包 `context_byte_budget`。

`prepare()` 输出：

```python
@dataclass(frozen=True)
class PrivacyPreparation:
    candidates: list[PreparedContextItem]   # 允许请求 grant 的已脱敏候选
    denied: list[PrivacyDenial]             # 被拒绝/替换项目（不含原值）
    required_categories: frozenset[str]
    prepared_context_bytes: int             # 本批候选 UTF-8 序列化字节数，供单包上限检查与审计

@dataclass(frozen=True)
class PreparedContextItem:
    category: str
    label: str
    value: str | int | float | bool
    redacted: bool
    fingerprint: str                        # HMAC-SHA256 的本地比较标识；不记录原值或裸 hash（见 §3.1）
```

### 2.3 PrivacyPolicy 固定规则

1. 只接受 `fixed_config`、`user_entity`、`free_text`、`secret` 四类输入；未知类拒绝。
2. `fixed_config` 不能来自模型 proposal：只允许 PrivacyPolicy 自己从已验证的本地固定配置构造。
3. `secret`：检测敏感键、裸 token/JWT/私钥/连接串、高风险模式；原值永不进入 PreparedContextItem。若可识别字段存在则输出 `secret_placeholder`（如 `api_key: present`），否则仅记录拒绝原因。**检测形态与判据的唯一真源是 §2.3c**（含中文自然语言凭据、全角分隔符、边界成分与值区判据）——本条只声明「检测什么、原值零落点」，**不重复定义模式集**。
4. `user_entity`：仅可由 §2.3a 硬编码表中的精确 `(label, value)` 组合产生；表外 label、非枚举值、列表/dict、字符串拼接或超长值一律拒绝（不截断后发送）。
5. `free_text`：**模型提出的** free_text 候选最大 1 个、最多 1,500 UTF-8 **字节**（2026-09-17 明确：该上限**保留不变**——本次裁决只取消 `brief_*` section 的 400 字节独立上限，模型自由文本的长度限制不在放宽范围内；措辞由「字符」改为「字节」是**文档与既有实现对齐**，`privacy_policy.py` 一直按 `len(value.encode("utf-8"))` 判定，无行为变更）；先做凭据/高风险模式扫描、路径/连接串检测；**含可替换秘密时按 §2.3b 的就地替换规则处理（2026-09-17 裁决，取代 2026-09-06 的「可选优化、P4 不实现」降级裁定）**；剩余文本只可在需要显式授权的模式/授权下发送。TaskBrief（§2.5）各 section 是本地生成的 free_text item（固定 label、**无独立字节上限**，见 §2.5 规则 3），不计入该「1 个」限制，但计入单包 item/byte 上限。
6. code/log/path 统一归 `free_text`，不因 label 是 `code`/`log`/`path` 而降级。
7. PrivacyPolicy 输出只包含已脱敏值；未授权原文永不进入审计、grant 或 CloudRequestPackage。
8. **`label` 是不可信文本通道**（2026-09-03）：候选/section 的 `label` 必须通过非空、≤ 64 字符、`^[a-z0-9_]+$` 与敏感模式扫描；未过检即拒绝该候选，原值不得以任何形式进入 preparation、package 或审计。TaskBrief 的 section label 由本地固定（§2.5），不走模型候选通道。

### 2.3a P4 硬编码 user_entity 允许表与风险等级

模型的 `label`、分类和值均不可信。PrivacyPolicy 对模型 proposal 中每项候选执行**精确表匹配**；不能匹配即拒绝，绝不将任意短字符串、ID 或模型摘要作为“低风险实体”。P4 的完整允许表如下：

| label | 允许值（精确枚举） | category | 风险 | convenient 自动 grant |
|---|---|---|:---:|:---:|
| `language` | `python` / `java` / `go` / `rust` / `javascript` / `typescript` / `sql` | `user_entity` | low | ✅ |
| `database_engine` | `postgresql` / `mysql` / `sqlite` / `mssql` / `oracle` | `user_entity` | low | ✅ |
| `os_family` | `windows` / `linux` / `macos` | `user_entity` | low | ✅ |
| `runtime_family` | `python` / `nodejs` / `java` / `dotnet` | `user_entity` | low | ✅ |
| `error_class` | `timeout` / `connection_refused` / `permission_denied` / `not_found` / `parse_error` | `user_entity` | low | ✅ |
| `project_kind` | `cli` / `web` / `api` / `desktop` / `data_pipeline` | `user_entity` | low | ✅ |

- 比较规则：label 与 value 在 `strip().lower()` 后精确匹配；不支持前缀、子串、别名或正则匹配。
- `low` 的含义仅限「枚举值不携带用户特有内容」；它不等于模型可信。只有表中这 6 类值能在 convenient 模式取得 policy grant。
- `project_name`、`host`、`port`、`path`、`table`、`query`、`goal`、`summary`、`message`、`email`、`phone`、`code`、`log` 及所有未列 label 一律**不是**低风险 user_entity；需归为 free_text 或拒绝，不能自动外发。

### 2.3b 含秘密文本的就地替换（2026-09-17 裁决，取代 2026-09-06 的降级裁定）

**问题（S12 结构性不可达）**：08 的 S12 要求「含假 `api_key` 的任务」在授权预览中出现**占位**并继续走完受控云端链路；而 §2.3 第 5 条此前对含可替换秘密的 `free_text` **默认整段拒绝**，TaskBrief 的 goal/question 双双被拒 → 空包 → `no_safe_context`，链路**从未**到达授权等待。这不是场景问题（**场景文本一字不改**），是脱敏语义缺少确定性规则。

**裁决（确定性规则，不依赖模型）**：

| # | 规则 |
|---|---|
| 1 | 命中 §2.3 第 3 条检测的**可替换**秘密（边界可界定，如赋值形式的 `api_key=<值>`、裸 token/JWT/私钥/连接串）→ 在该 `free_text` 值中**就地替换为固定字面量 `[已脱敏:secret]`**，该 section **不再整段拒绝**；替换后的文本可进入 preparation 与授权 preview。**替换的作用域是「值区」**：字段名与分隔符**保留**（`api_key=[已脱敏:secret]`），只有值本身被移除——2026-09-24 口径统一（§2.3c.5），此前实现替换的是「字段名 + 分隔符 + 值」整个匹配串 |
| 2 | 若命中处能识别出字段名 → **另行**产出 `secret_placeholder`（`{label: "<小写字段名>", value: "present"}`，类别见 §2.3 表）；识别不出字段名则只做第 1 条。**`label` 必须是规范 ASCII 标签**（§2.3c.2 映射表；中文标签不得因 `^[a-z0-9_]+$` 不匹配而被**静默丢弃**——静默丢弃等于云端看不见脱敏事实，是该条要修的既有行为） |
| 3 | **原值零落点**：`payload` / 事件 / 审计 / 异常信息四处一律不得出现原值（既有不变量，本条不放宽）；替换发生在构造 `PreparedContextItem` **之前** |
| 4 | **纵深防御**：替换后**再跑一次**同一扫描；仍有命中即该 section **整段拒绝**（fail-closed），不做二次拼接式挽救 |
| 5 | **可替换性判定失败即整段拒绝**：边界无法界定（如无法确定秘密值的起止）或属于第 1 条模式**之外**的敏感内容 → 维持整段拒绝。**检测模式集由 §2.3c 的单一真源持有**；2026-09-24 裁决**已扩集**（中文自然语言凭据、全角分隔符、少量英文别名——本轮授权扩展，属安全边界变更，取代本条此前「本轮**不扩展**检测模式集」的表述），此后新增/修改模式仍须改 §2.3c 并经审查 |
| 6 | **确定性**：替换是输入的纯函数——同输入同输出，无模型参与、无「语义改写」。因此 fingerprint 稳定，§3.2 的增量纯度与「同 fingerprint 必同内容」不变量不受影响 |
| 7 | **不新增可观测面**：不新增事件、不新增枚举；preview 中占位的出现即用户可见的脱敏证据（`outbound_categories` / 预览内容集里含 `secret_placeholder`） |
| 8 | **不得依赖模型额外产出 `secret` 候选**：脱敏是 `PrivacyPolicy` 的确定性职责，与模型是否申报 secret 无关 |

**授权语义不变**：本条只让「含秘密的文本」有可能构成一个非空、已脱敏的 TaskBrief；它**不**降低任何授权门槛——外发仍必须过 §1.3a 的授权形态（含秘密的输入按 §1.3a 升险源①计入 ≥ `sensitive`，即**强制用户授权**）+ 完整 preview + 用户显式 `/cloud allow`。

**残留风险（照实记录）**：检测器**漏检**的后果是原值进入 payload。本条已由三件事兜住：第 4 条替换后复扫、§2.3 第 7 条（输出只含已脱敏值）、08 §8.1 的「JSONL 无原值」构造断言。**2026-09-24 起检测模式集已扩为中文自然语言形态（§2.3c）**，仍存在的具体缺口逐条登记在 §2.3c.6；若真实 run 观察到漏检，按 §10 立候选后再决定是否继续扩集。

- 新增/修改此表是安全边界变更，须改模块 spec 并经 Claude 审查；不得在 config 中扩展（config 侧口径见 §2.3c.1）。

### 2.3c 凭据检测的单一真源与中文自然语言形态（2026-09-24 裁决，安全边界变更）

**触发（安全阻塞）**：演示复现——输入 `我的账号密码是123456` 时，授权 preview 的 `brief_goal` **原样携带 `123456`**；`contains_sensitive_value(...)` 与 `contains_bare_secret(...)` 实测均为 `False`，`_redact_replaceable_secrets(...)` 不产生任何替换。根因是**同一判据存在多份实现**且全部锚定英文赋值式：`(password|passwd|secret|token|api_key)\s*=\s*\S+`（`guarded_executor` / `memory_hygiene` / `rule_only_backend` 三份不同定义 + `privacy_policy` 的标签捕获变体 + 7 份 TOML 拷贝）与 ASCII 裸 token 形态（`sk-` / `ghp_` / `eyJ` 两处逐字相同的拷贝）。`config` 里的 `sensitive_patterns` **只被 `RuleOnlySafetyBackend` 读取**，脱敏链路不读它，因此**配置无法补偿**。本条取代 §2.3b 规则 5 的「不扩展」表述。

#### 2.3c.1 单一真源（一处定义、全链路委托）

**「什么是凭据」全链路只能有一个定义**：一个模块（预期 `src/safety/secret_scan.py`，纯函数、无第三方依赖）持有标签闭集、分隔符闭集、**边界成分（T1–T3）**、值区判据与替换实现，导出四个入口：

| 入口 | 语义 |
|---|---|
| `scan_credentials(text)` | 命中列表：命中处标签族、规范 ASCII 标签、值区文本、判态结果（为空 / == 占位符 / 非空） |
| `redact_outbound(text)` | 出站处置：**值区非空即整段替换**（**2026-09-24 第三轮起出站与本地同一处置**；不再有「不可界定 ⇒ 原样保留」分支） |
| `redact_local(text)` | 落盘处置：**与出站同一实现、同一值区定义、同一字面量**（见 2.3c.4 第 1 条） |
| `contains_credential(text)` | 布尔；承接既有 `contains_sensitive_value` / `contains_bare_secret` 的语义（含扩展后的全部形态） |

**委托表（现状 → 期望）**：

| 位置 | 现状 | 期望 |
|---|---|---|
| `safety/guarded_executor.py` `_SENSITIVE_VALUE_RE` / `_BARE_SECRET_RE` / `contains_sensitive_value` / `contains_bare_secret` | 真源，但只认英文赋值式 + ASCII 裸 token | 逻辑**整体迁入** `secret_scan`；保留这两个函数名作薄包装（既有 import 不改），语义 = `contains_credential` |
| `safety/privacy_policy.py` `_ASSIGNED_SECRET_RE` / `_BARE_SECRET_RE` / `_redact_replaceable_secrets` | **第二份**模式定义 + 独立的替换实现 | 删除本地模式与替换实现，改用 `scan_credentials` + `redact_outbound` |
| `core/memory_hygiene.py` `_SENSITIVE_ASSIGNMENT_RE` / `_replace_bare_secrets` | **第三份**模式定义 + 逐 token 替换 | 删除本地模式，改用 `redact_local`（`_PROTECTED_PATH_RE` 等路径类保持不变） |
| `safety/rule_only_backend.py` `_DEFAULT_SENSITIVE_PATTERNS` | **第四份**模式定义 | L1 的可疑模式判据改用 `contains_credential`；`sensitive_patterns` 配置项改为**仅追加** |
| `safety/cloud_boundary.py` `_SECRET_REDACTION_PLACEHOLDER` | 与脱敏链路同值的常量（第三处硬编码） | 值不变，来源改为单一真源的常量 |
| `tools/weather_tools.py` 出站 `location` 拒绝 | 复用 `guarded_executor` 的两个函数 | 不改调用点，自动获得扩展后的判据 |
| `config/*.toml` `safety.l1_rules.sensitive_patterns`（7 份拷贝） | 与内建模式重复的英文赋值式 | 保留键位；内建检测集**恒生效**，配置项**只能追加，不得削弱或替换**（既有拷贝成为冗余追加，行为不变） |

**不变式**：
1. 新增/修改检测模式**只允许改这一个模块**；`config` 中的模式键**不得**成为绕开安全边界的开关（与 §2.3b 表后注同向）。
2. §2.1 的类别闭集不变，**不新增类别、不新增事件枚举、不新增错误码**（见 2.3c.4）。
3. `guarded_executor._SENSITIVE_PARAM_KEYS`（按**参数键名**遮蔽审计值）与 `redact_params` **不是**本检测集的一部分，保持原样——语义不同（键名级遮蔽 vs 文本内容扫描），不得合并。
4. 占位符自身必须落回「不可命中」态（2.3c.3），否则 §2.3b 规则 4 的复扫与 §4.1 的幂等自检会把所有已脱敏文本再次判为命中。

#### 2.3c.2 标签闭集与规范 ASCII 标签

**标签闭集（凭据类字段名；命中条件 = 标签 + 边界成分，见 2.3c.3 规则 1）**：

| 标签族 | 规范 ASCII 标签（`secret_placeholder.label`） |
|---|---|
| `password`、`passwd`、`passphrase`、密码、口令、账号密码、登录密码、用户密码、账户密码、密码短语 | 英文标签取原值小写（`passwd` → `passwd`）；中文标签 → `password` |
| `secret`、`api_key`、`apikey`、`private_key`、`access_key`、密钥、私钥、访问密钥、密钥串、凭据、凭证、连接串 | 英文标签取原值小写；中文标签 → `secret` |
| `token`、`auth_token`、令牌、访问令牌 | 英文标签取原值小写；中文标签 → `token` |
| 闭集之外（表未覆盖） | 兜底 `credential` |

- **英文标签取原值小写**是刻意保留：现有命中（如 `api_key=sk-…`）的 `secret_placeholder.label` 与 fingerprint 因此不变，S12 等既有链路零行为漂移。
- **中文标签一律映射**，不得因 `^[a-z0-9_]+$` 不匹配而静默丢弃占位符；兜底 `credential` 只用于防御闭集漏写，**闭集全覆盖是注册期/测试不变式**（逐条断言每个标签都产出合法 ASCII 标签，不出现兜底值）。
- **标签不要求左边界**（前缀不约束）：`账号密码是…` 由 `密码` 命中。CJK 与 `\w` 的交互使 `\b` 在中文语境失效（`我的密码=abc` 的 `\b` 不成立），因此**左边界不作为条件**。
- **右边界（第三轮钉死）**：两条**标签侧语法条件**，判断的是「这个标签在这段文本里是不是一个字段名」，**与值的形态无关**，见 2.3c.3 规则 1/4：
  - **拉丁标签**在「紧邻非 CJK 字符」形态（T3）下要求右边界：其后字符**不得**是 `[A-Za-z0-9_]`——`tokenizer`、`api_keys` 不命中；
  - **CJK 标签**在 T3 下**没有额外要求**：其后紧邻字符是**非 CJK、非空白**即触发 T3（`密码abc123`、`密码-abc` 命中）；紧随的是 **CJK 字符**时 T3 按定义不成立（T3 的定义本身就含「非 CJK」），且此时不存在 T1/T2 边界 ⇒ `密码学是什么`、`密钥管理体系` 不命中。理由：CJK 字符之间无词边界，「`密码` 只是更长词的一部分」与「标签 + 粘写值」在字符层面不可区分，故取更宽方向的语法条件；**该形态登记为语法边界**（2.3c.6 第 4 行），而不是形态豁免。
- **本闭集只收凭据**：`账号`、`用户名` 等**标识符**不属凭据（账号名本身不是秘密）——`账号是 alice` 不命中，登记为开放项（2.3c.6 第 4 条）。PII 类（身份证/手机号/银行卡）**不在本轮范围**，属另一类安全边界，须单独裁决。

#### 2.3c.3 命中条件与值区（确定性，无形态判据）

**2026-09-24 第三轮重写**：原「条款（分隔符 → 首个终止符）+ 终止符后的值形态片段回收 + 值区含内部空白的不可界定态」三件套**整体删除**，换成下面的「**边界成分 + 值区上界 = 行末**」模型。动因（Codex 编码前审查，见 `clarifications.md` 同轮条目）：旧模型用「片段是否为值形态（不含 CJK）」决定要不要继续纳入，**这本身就是一条形态判据**，与「不接受任何形态豁免」直接矛盾，且留下两处真实漏检——`密码 abc123`（裸空格不命中）与 `密码是abc，青山绿水`（终止符后的 CJK 片段不回收），与「secret 原值永不外发」冲突。

```
1. **命中（触发）= 标签闭集成员 + 边界成分**，边界成分是下列三条之一，**全部与值无关**：
   T1 显式分隔符闭集成员（= : ： ＝ 是 为 等于），标签与它之间允许空白；
   T2 空白（≥1 个空格 / 制表）；
   T3 紧邻的**非 CJK、非空白**字符（粘写形态：密码abc123、密码-abc；密码=abc 走 T1）；
      —— 「非 CJK」是 T3 定义的一部分，对两类标签同样生效：紧随字符是 CJK 时不成立；
   两条**标签侧语法条件**（判断的是「标签是不是一个字段名」，不是值的形态）：
   —— **拉丁标签**在 T3 下另要求右边界：其后紧邻字符不得是 [A-Za-z0-9_]
      （tokenizer 不命中）；
   —— **CJK 标签**在 T3 下**没有额外要求**：紧邻字符是「非 CJK、非空白」即触发
      （密码abc123 命中）；紧邻的是 **CJK 字符**时 T3 按定义不成立、且此时无
      T1/T2 边界 ⇒ 不命中（密码学是什么 / 密钥管理体系）——CJK 字符之间无词边界，
      「标签只是更长词的一部分」与「标签 + 粘写值」在字符层面不可区分，故取更宽
      方向的语法条件（登记在 2.3c.6 第 4 行，**不是**值形态豁免）。
2. **值区 = 标签之后到本行末尾的连续跨度**（首尾空白 strip，并去掉标签与值区之间的
   那个边界成分）。**值区之内的一切——终止符、标点、空白、中文、拉丁——一律不再
   切分、不再按形态筛选**：这就是「不存在归属不明的后续片段」的由来。
   值区为空（**已命中**、但标签之后本行没有非空内容，如 `密码：` / `password=` /
   `密码␠` 这类「有边界成分、无值」的形态）→ **顺延**：跳过紧邻的连续空行，取
   **下一个非空行**作值区（只顺延一次、不递归；不存在则值区为空）。
   理由：值很可能就写在下一行（`密码：\n…` 是常见记法），本地与出站必须同界。
   —— **2026-09-25 措辞收口**：顺延以**命中为前提**，而命中要求存在边界成分（规则 1）。
      行末的**裸标签**（`密码` 独占一行、其后无任何字符）三条边界成分全不成立
      （T1 无分隔符、T2 明文只含空格/制表、T3 无后续字符）⇒ **不命中**，因此也
      **不发生顺延**；该形态登记在 2.3c.6 第 4 行（与 `密码青山绿水` 同族：标签与值
      之间无边界成分），代价照实写明。
3. **判态（判态对象 = 值区；只看两件事）**：
   值区为空                            → 不可命中（其后已无任何字符，无外发面可言）
   值区 == 占位符字面量 [已脱敏:secret] → 不可命中（**占位符显式自免疫**，幂等由此成立）
   值区非空                            → 可替换（整段移除、原地替换，处置见 2.3c.4）
   —— 原「不可界定（值区含内部空白）」态**随本模型删除**：值区上界钉死在行末（必要时
      顺延一行、且不再有形态筛选）之后，「归属不明的片段」不再存在，因此不再需要
      「整段拒绝」这条凭据类处置（2.3c.4 同步收窄，只保留一条与凭据无关的诚实拒绝）。
4. **本轮显式删除、不得回归的判据**：任何「值像不像值」的判断——条款是否含 CJK、
   是否含内部空白、是否含空格、长度、是否像 base64 / 十六进制 / DSN——**一律不得**
   参与命中或判态。防误伤只靠**标签闭集 + 边界成分**（两者都是与值无关的确定性条件）。
   第 1 条的两条标签侧语法条件**是仅有的例外**：它们不问值长什么样，只问**标签在这段
   文本里是不是一个字段名**；且后果方向是**收窄识别语法**（登记在案），不是放行原值。
```

**判据的形状（对照演示与最小验收）**：

| 输入 | 标签 | 触发 | 值区 | 态 | 结果 |
|---|---|---|---|---|---|
| `我的账号密码是123456` | `密码` | T1（`是`） | `123456` | 可替换 | `我的账号密码是[已脱敏:secret]` + `secret_placeholder(label=password, present)` |
| `密码：abc 123` | `密码` | T1（`：`） | `abc 123` | 可替换 | `密码：[已脱敏:secret]`——**第三轮改**（原为不可界定 ⇒ 拒绝；值区上界钉死行末后归属不再不明 ⇒ **不再因「不可界定」被拒**，改为原地替换）。**注**：本行只描述**替换**；该文本若整段构成一个 section（本例即「只有凭据」），替换后已无任务语义 ⇒ 按 **2.3c.4 第 2 条诚实拒绝**整段拒绝、零外发（与 2.3c.6 交付验收 ② 一致） |
| `密码是青山绿水` | `密码` | T1（`是`） | `青山绿水` | 可替换 | `密码是[已脱敏:secret]`（第二轮修订，维持） |
| `密码：abc，123` | `密码` | T1（`：`） | `abc，123` | 可替换 | `密码：[已脱敏:secret]`（回收机制删除后由值区上界天然覆盖；**不得**产出两个并排占位符） |
| `密码是abc，今天天气不错` | `密码` | T1（`是`） | `abc，今天天气不错` | 可替换 | `密码是[已脱敏:secret]`——**第三轮改**：整行值区一并移除（旧版保留后半句，靠的正是「CJK 片段不回收」这条形态判据，已删除）。这是**为消除形态依赖而付的代价**，见下方取舍段 |
| `密码 abc123`（**裸空格**） | `密码` | **T2（空白）** | `abc123` | 可替换 | `密码[已脱敏:secret]`——**第三轮新增**（旧版不命中 ⇒ 原值外发，是漏检） |
| `密码 青山绿水`（裸空格 + 中文口令） | `密码` | T2 | `青山绿水` | 可替换 | `密码[已脱敏:secret]`——**第三轮新增** |
| `密码abc123`（粘写） | `密码` | **T3**（非 CJK 紧随） | `abc123` | 可替换 | `密码[已脱敏:secret]`——**第三轮新增** |
| `密码：\nabc123`（值在下一行） | `密码` | T1 + 值区为空 | `abc123`（顺延下一非空行） | 可替换 | `密码：\n[已脱敏:secret]`——**第三轮新增** |
| `计数器是123456` | —（无标签） | — | — | 不可命中 | 原样（普通数字陈述不误伤） |
| `今天讨论了api_key的实现方案` | — | — | — | 不可命中 | 原样（`api_key` 之后紧随的 `的` 是 **CJK 字符** ⇒ T3 按定义不成立，且此处无 T1/T2 边界；与 `密码学是什么` 同一类） |
| `密码学是什么` / `密钥管理体系` | —（**CJK 标签 + CJK 紧随**） | — | — | 不可命中 | 原样——**登记的语法边界**（不可与「标签是更长词的一部分」区分），见 2.3c.6 |
| `tokenizer` / `api_keys` | —（**拉丁标签右边界**） | — | — | 不可命中 | 原样（`izer` / `s` 属 [A-Za-z0-9_]） |
| `改密码是必要的` | `密码` | T1（`是`） | `必要的` | 可替换 | `改密码是[已脱敏:secret]`——**过度脱敏的已知代价**，见下方取舍段与 2.3c.6 第 2 条 |
| `token 过期了` / `api_key 读不到` | `token` / `api_key` | **T2（空白）** | `过期了` / `读不到` | 可替换 | `token[已脱敏:secret]` / `api_key[已脱敏:secret]`——**T2 带来的新代价**（本领域高频句式），见下方取舍段与 2.3c.6 第 3 条；修法方向**不得**是值形态豁免 |
| `api_key=sk-EVAL-FAKE-…` | `api_key` | T1（`=`） | `sk-EVAL-…` | 可替换 | `api_key=[已脱敏:secret]`（字段名保留，placeholder label 仍为 `api_key`） |
| `password = two words` | `password` | T1（`=`） | `two words` | 可替换 | `password = [已脱敏:secret]`——**第三轮改**（原为不可界定 ⇒ 拒绝；含空格口令**不再因「不可界定」被拒**）。**注**：与上一行同理——若该文本整段只有凭据，section 按 **2.3c.4 第 2 条诚实拒绝**被拒 |
| `api_key=[已脱敏:secret]` | `api_key` | T1（`=`） | `[已脱敏:secret]` | 不可命中 | 原样（**规则 3 的显式自免疫**，复扫与幂等成立） |
| `api_key=sk-EVAL-FAKE, see README` | `api_key` | T1（`=`） | `sk-EVAL-FAKE, see README` | 可替换 | `api_key=[已脱敏:secret]`——**第三轮改**：英文行文中的整段拒绝代价**消失** |

**误伤的取舍（2026-09-24 第三轮定稿，照实写明）**：`改密码是必要的`、`token 是无效的`、`token 过期了`、`api_key 读不到` 一类句子**会被命中并原地替换**（命中只看标签与边界成分，与值无关）。后果上界**确定且有界**：该行文本变为 `改密码是[已脱敏:secret]` / `token[已脱敏:secret]`（**不是**拒绝、**不会**外发原值），本地记忆的同一行被占位；若该回合要外发，则因升险源① ⇒ 进**强制用户授权**（用户可在 preview 上看到并拒绝）。**注意 T2（空白）是代价的主要来源**：中文行文不用空格，受影响的主要是「拉丁标签 + 空格 + 中文」这类技术句式（本领域高频）——这是本轮为关闭 `密码 abc123` / `密码 青山绿水` 两处漏检付出的**明码代价**。
**取这个方向的理由（2026-09-24 两轮被指出后两次翻转的裁决）**：反向取舍（值含 CJK 即豁免 / 片段含 CJK 即不回收）的失败模式是**真实中文口令原样外发到云端**——本安全边界不可接受的失败；本方向的失败模式是**个别普通句式被过度脱敏并要求一次确认**——可见、可拒绝、有界。**不接受任何形态豁免回归**（如「条款以 `的` 结尾即视为行文」「标签前一字非 `的` 即不算标签」「片段含 CJK 即停止纳入」）：它们都会重新打开漏检面，且 `系统密码是…`、`数据库密码是…` 恰好会被第二条误豁免。
**代价的消解方向（若真实 run 证明过度脱敏过于频繁）**：不是重新引入值形态判据，而是**提高标签侧的选择性**（更严的字段名形态、要求更强的赋值信号）；这需要单独裁决，按 §10 立候选。

**承诺口径（第三轮钉死）**：「凭据原值永不外发」的可判定面是——**一旦某段文本命中凭据标签（命中条件见规则 1），该标签之后、同一行内的一切内容（标签独占一行时顺延到下一个非空行）都被整体移除**。命中条件**不依赖值的形态**，因此不存在「因为值长得不像值而放行」的漏检面；**不在识别语法内**的形态如实登记（见 2.3c.6 第 6/7 条：标签与值之间无任何边界成分的粘写中文形态、值在标签之前、值跨多行续行）；既有的**裸密钥检测**（无标签形态的独立模式，见 2.3c.1 委托表）继续作为第二层，覆盖其中一部分。

#### 2.3c.4 处置：一处替换，出站与本地同源；只剩一条与凭据无关的诚实拒绝

1. **替换（唯一处置）**：命中且值区非空 ⇒ 把**整个值区**（2.3c.3 规则 2）原地替换为统一字面量 `[已脱敏:secret]`，字段名与边界成分保留（用户仍看得出「哪个字段被脱敏」）。**出站（`PrivacyPolicy.prepare()` → payload / preview / 审计）与本地落盘（`sanitize_for_memory` / `_sanitize_event_data`）用同一实现、同一字面量、同一值区定义**（单一真源，见 2.3c.1）。
   —— **值区内的内容全部移除**，无任何原值片段残留 ⇒ 交付验收 ④「五个面检索不到原值」成立。
   —— **不再有「凭据类整段拒绝」**：值区上界钉死在行末（必要时顺延一行）之后，归属不再不明，因此不需要 fail-closed 拒绝（第三轮删除旧「不可界定 ⇒ 整段拒绝」分支）。
   —— `[已脱敏:block]` **保留为最后兜底**（消毒后仍命中任一模式时使用），预期在生产路径上不再触发；测试须断言普通中文语句不产生 `[已脱敏:block]`。
2. **唯一保留的拒绝：替换后已无任务语义的 section**（第三轮新增，与凭据判据**无关**，是「诚实拒绝」）：某个 section 文本在替换完成后，若**剔除**① 占位符字面量 `[已脱敏:secret]`、② 标签闭集成员、③ 分隔符闭集成员、④ 空白与标点（`，,、；;。！!？?：:＝=（）()「」『』【】《》` 及 ASCII 标点）后**为空**，则该 section **整段拒绝**（denied 记**固定**原因文案、不含原值，**不新增错误码、不新增事件枚举、`phase` 闭集不变**）。
   **理由**：这类 section 已被脱敏吃到只剩字段名与占位符——云端拿不到任何任务语义，发出去只会换来无效或编造的回答；**拒绝比发送更诚实**（同 §1.4 的 `COMPLETED_LOCAL` 口径）。触发形态典型是**单行输入里凭据赋值与任务语义挤在同一行**（`密码是abc123，帮我分析这段代码` 的一行形态）：整行值区被移除 ⇒ 该 section 无任务语义 ⇒ 不上云、本地照常回答；**用户把凭据单独成行即可正常咨询**（多行输入时其它行不受影响，任务语义仍在）。
   **后果与对照**：`brief_*` 全部被拒 ⇒ 既有 `COMPLETED_LOCAL` 路径（§1.4），本回合零网络调用、本地照常产出回复——与旧版「不可界定 ⇒ 整段拒绝 ⇒ 可能 `no_safe_context`」相比，**触发面窄得多**（只针对「脱敏后语义为空」这一种形态，而不是「值区含空格」）。
3. **升险源①不变**：命中即落在 §1.3a 升险源①的既有两项里（「含 `secret` 命中」与「需拒绝」）→ 有效授权风险 ≥ `sensitive` → **强制用户授权**。本条不新增信号、不降低任何门槛。

#### 2.3c.5 占位符统一

- 凭据类占位符**全链路统一为字面量 `[已脱敏:secret]`**：`privacy_policy`（出站）与 `memory_hygiene`（落盘）此前分别产出 `[已脱敏:secret]` 与 `[已脱敏:sensitive]`，本次合并为一个字面量；`cloud_boundary` 的常量同值（来源改为单一真源）。
- `[已脱敏:path]`（受保护路径）与 `[已脱敏:block]`（最后兜底）**不是凭据类**，保持不变。
- 替换只作用于**值区**（字段名与分隔符保留），使 preview 里「哪个字段被脱敏」对用户可读——这是 §2.3b 规则 7「preview 中的占位即用户可见的脱敏证据」的落地形态。

#### 2.3c.6 已知缺口与残留风险（照实记录，逐条给触发条件）

| # | 缺口 | 取舍理由 | 触发条件 |
|:--:|---|---|---|
| 1 | **（第三轮已关闭）** `密码 abc123`（裸空格）不命中 | 旧模型把空格排除在分隔符之外；现由 T2「空白即边界成分」覆盖 | 已关闭，无需触发条件 |
| 2 | **中文句式的过度脱敏（已知代价，不是缺口）**：`改密码是必要的`、`token 是无效的` 会被命中并替换为 `[已脱敏:secret]`，该回合因此进强制用户授权 | 反向取舍（值含 CJK 即豁免）的失败模式是**中文口令原样外发**；见 2.3c.3「误伤的取舍」段 | 若真实 run 观察到某类中文句式**频繁**误伤 → 按 §10 立候选；**修法不得**是任何形态/语法豁免（会重开漏检面），方向是**提高标签侧选择性** |
| 3 | **T2 带来的新代价（2026-09-24 第三轮）：「拉丁标签 + 空白 + 中文」的技术句式被过度脱敏**——`token 过期了`、`api_key 读不到`、`secret 是什么` 会被命中并整行移除（本地记忆同一行被占位；若该回合外发则进强制用户授权） | 该形态与「`password 青山绿水`（拉丁标签 + 空格 + 中文口令）」在**字符层面完全同形**，无确定性区分手段；取安全侧的代价是可见、可拒绝、有界，反向则是中文口令原样外发 | 真实 run 观察到该类句式**频繁**误伤 → 按 §10 立候选；候选方向 = **提高标签侧选择性**（更严的字段名形态 / 要求更强的赋值信号），**不得**引入值形态判据 |
| 4 | **语法边界：标签与值之间无任何边界成分的形态**——(a) CJK 粘写（`密码青山绿水`、`password青山绿水`）；(b) **行末裸标签 + 值在下一行**（`密码\nabc123`，2026-09-25 补登记）——两者均不命中 | (a) CJK 字符之间无词边界，`密码青山绿水` 与 `密码学` 在字符层面不可区分；要覆盖它就必须把 `密码学`、`密钥管理` 一类普通词判为凭据（本领域高频，误伤面远大于该形态的凭据）。(b) 顺延以**命中**为前提，而命中要求存在边界成分；把「无边界成分的裸标签」也算作边界，等于把**任何以标签词结尾的行**（中文行文里 `…的密码` / `…的令牌` 收尾并不罕见）判成凭据 ⇒ 吞掉下一整行。**这是声明的语法边界，不是值形态豁免**——只要标签与值之间存在任一边界成分（T1/T2/T3），无论值是什么形态一律命中（第三轮的核心结论）。**代价照实写明**：(b) 的 `abc123` 原样外发，裸密钥层（无标签形态）只兜底其中一部分 | 真实 run 观察到该形态的实际泄漏 → 按 §10 立候选（方向：标签闭集的形态收紧或词典化、或为「独占一行的标签」单独设计一条需单独论证的边界成分，两者都要先算误伤成本） |
| 5 | **语法边界：值出现在标签之前**（`abc123 是我的密码`） | 识别语法是「标签 → 值」的顺序形态；反向覆盖需要把命中判据放宽到「标签出现即命中」，会把 `修改密码`、`请检查密码`、`密码学` 一并吞掉 | 同上 |
| 6 | **语法边界：值跨多行续行（超过顺延一行）** | 值区上界是行末（值区为空时顺延一个非空行）；无界顺延会吞掉整段文本 | 同上；另见 2.3c.1 的裸密钥检测作为第二层（无标签形态，覆盖一部分） |
| 7 | **新代价：替换后无任务语义的 section 被拒**（2.3c.4 第 2 条）——单行输入把凭据与任务挤在同一行时，该 section 整段拒绝、不上云（本地照常回答） | 脱敏已把该 section 吃到只剩字段名与占位符，外发只会换来无效或编造的回答；**拒绝比发送更诚实**。用户把凭据单独成行即可正常咨询 | 若真实 run 观察到用户频繁撞上该形态 → 按 §10 立候选（方向：回复里加一句可操作的改写提示），**不得**改为「发送只剩占位符的 section」 |
| 8 | `账号`、`用户名` 等**标识符**不属凭据闭集 | 账号名本身不是秘密（同句中的密码仍会被命中） | 需纳入时属 PII 类安全边界，单独裁决 |
| 9 | PII（身份证 / 手机号 / 银行卡）完全不在范围 | 与本轮的「凭据」是不同类别，误伤成本与判据形态都不同 | 需求方确认要做 → 另立契约 |
| 10 | **诚实拒绝判据的已知不精确（2026-09-25 补登记，方向相反的一侧）**：**左接标识符前缀**的凭据行（`.env` 形态 `DB_PASSWORD=hunter2`、`AWS_SECRET_ACCESS_KEY=…`）替换后剩 `DB_` / `AWS_` 一类**变量名前缀**，第 2 条的剔除项（标签闭集按子串匹配）**剔不掉前缀** ⇒ 该 section 被判为「仍有任务语义」⇒ **外发为壳**（一段只剩变量名与占位符、无任务价值的文本）。**本行随「标签不要求左边界」（2.3c.2）与修复后即可命中而新出现**：修复前这类输入根本不命中，连壳都不会产生 | 该 section **不含原值**（替换完整），外发与否可见于授权 preview、用户可否决，属不对称取舍的安全侧；**不得**用「剔除 ASCII 标识符残段」去修——那会把 `api_key=sk-…, see README` 一类**真任务文本**（见形状表第 468 行，期望外发为 `api_key=[已脱敏:secret], see README`）一并剔掉，代价更大 | 真实 run 观察到「壳 section 频繁外发、用户白白确认一次」→ 按 §10 立候选（方向：把「变量名前缀 + 标签」整体认作字段名再判空，须单独论证误伤面），**不得**引入值形态判据 |

**交付验收（本次裁决的最小面，测试用例见 §10.11）**：① `我的账号密码是123456` ⇒ preview 无 `123456` 且有占位；② 单行 `密码：abc 123` ⇒ 本地与出站替换同字面量，且因替换后无任务语义而**该 section 拒绝、零外发**；③ 普通数字陈述与不含标签的句子不误伤；④ `/cloud allow` 之后 payload / 事件 / 审计 / 异常 / 记忆五处均检索不到原值；⑤ **多行输入**（凭据一行 + 任务一行）⇒ 任务语义保留、凭据行被替换、section **不**被拒（可正常咨询）。

### 2.4 三种隐私模式

| 模式 | 行为 |
|---|---|
| `strict` | 每次 package 含 `user_entity` 或 `free_text` 都展示最终 payload 并确认；不复用历史 grant |
| `balanced`（默认） | 同一有效 task/session/provider/purpose grant 内，边界未扩大时可复用；首次含用户内容时确认 |
| `convenient` | `fixed_config` 与低风险 `user_entity` 可自动发送；`free_text` **首次外发**始终确认（TaskBrief 恒含 free_text → 首轮恒确认），已确认内容随任务内续咨询重发不需重复确认；续咨询新增候选全为 allowlisted `user_entity` 时自动续（增量纯度，§3.2）；secret 原值永不发送 |

模式仅改变「何时要确认」，不能允许 secret 原值外发，也不能越过 CloudBoundary/预算/用户 deny。

### 2.5 TaskBrief — 最小推理任务包（2026-09-03 新增）

推理升级要求云端看到**任务语义**而非仅意图类别。`TaskBrief` 是本地构建的脱敏任务简报，是 P4 的外发核心：

```python
@dataclass(frozen=True)
class TaskBrief:
    goal: str          # 任务目标（脱敏）；来源 = 用户本轮输入 current_input（规则 1/7）
    constraints: str   # 硬约束；来源 = 用户逐字陈述 + 已确认配置（规则 1；当前实现恒为空串）
    known_facts: str   # **仅用户逐字陈述**（2026-09-24 收窄，见规则 1；含推断即违约）
    evidence: str      # 相关片段/引用（检索所得，脱敏）；来源 = 记忆检索（规则 1）
    attempts: str      # **模型候选** local_attempts_summary（不可信自述，见规则 1）
    question: str      # 待推理问题；来源 = **模型候选** proposed_question（规则 1/7）
    unknowns: tuple[str, ...] = ()  # 逐条缺失信息（模型 missing_info 的本地转写，2026-09-14 新增；
                                    # tuple 逐条语义 + 默认空与既有 6 参位置构造兼容）
    project_note: str = ""          # 项目摘要段（2026-09-24 新增，规则 9）；默认空 ⇒ 与既有
                                    # 7 参位置构造兼容（`src/core/schemas.py` 现有调用零改动）
```

> **字段顺序与兼容性（2026-09-24 钉死）**：`known_facts` **保持第 3 位**（不因语义收窄而改名或挪位），新增字段一律**追加在末尾且带默认值**。这是本轮**唯一**的接口结构变更（`TaskBrief` +1 字段），已在 `clarifications.md` 同日条目备案。

规则：

1. **各 section 的来源与可信度（2026-09-24 第三轮校正）**：本节只**声明各段的来源与可信度**、并作废原「`constraints` / `known_facts` / `evidence` 优先来自配置、工具结果、记忆系统等结构化可信来源」的表述（该表述与规则 9 的事实身份要求直接冲突，实现者不得再按它组装）。**每个 section 实际取什么值，以规则 2、规则 7 与既有构造实现为准**——本表不得被读成「要新增/改造构造逻辑」（第三轮说明：上一版曾把 `question` 写成「用户任务语义」、把 `attempts` 写成「本轮实际执行记录」，与规则 2/7 的既有行为冲突；**以既有行为为准，不重构云端协议**）：

   | section | 来源（既有行为） | 可信度 | 不得来源 |
   |---|---|---|---|
   | `goal` | 用户本轮输入 `current_input`（**唯一来源**，规则 7 钉死） | 用户逐字陈述 | 模型自拟结论、云端回传文本 |
   | `question` | **模型候选** `IntentCandidate.proposed_question`（规则 2 的素材候选；空/缺省不生成，与 `goal` 同值即省略，均见规则 7） | **不可信候选**（模型产出，只是待推理问题的候选表述） | 不得由 `current_input` fallback 顶替；不得被当作事实 |
   | `constraints` | 用户逐字陈述 + 已确认配置项（`fixed_config`，逐字取值）；**当前实现恒为空串 ⇒ 恒不产生候选**（§10.10） | 用户逐字陈述 / 本地已确认 | 模型推断出的"隐含约束"、摘要 |
   | `known_facts` | **仅用户逐字陈述**（事实权威唯一来源，规则 9） | 用户逐字陈述 | 配置、工具结果、检索片段、**任何摘要**（摘要 = 推断）、`json.dumps(project_state)` 一类本地结构化块 |
   | `evidence` | **记忆检索所得片段**（逐字行 + 带固定前缀的摘要行，两类前缀见规则 9「会话摘要同身份」） | 逐字行 = 用户/助手历史原文；摘要行 = **推断**（带前缀） | 模型压缩出的"要点"、云端文本 |
   | `attempts` | **模型候选** `IntentCandidate.local_attempts_summary`（规则 2 的素材候选） | **不可信候选**——模型的自述，**不得**视为本轮实际执行事实 | 不得被当作事实、不得替代执行记录 |
   | `project_note` | 项目摘要（自动或人工），**必须带规则 9 的确定性来源前缀** | 自动摘要 = 推断；人工摘要 = 用户手写 | 无前缀的裸摘要文本 |

   **`known_facts` 的生产路径后果**（与规则 9 一致，不是补充说明）：本轮用户输入之外没有第二个合法来源，因此 `known_facts` 段**在生产路径恒与 `goal` 同源**、**恒被规则 8 的 T1 去重吸收**、**恒不进 payload**。这不是缺陷，而是「事实权威只认用户逐字陈述」的必然结果；实现者若发现某条内容"应该"进 `known_facts` 却又不能来自用户逐字输入，**答案是它该进 `evidence`（带来源前缀）或 `attempts`**，而不是放宽本行。
   **`attempts` 的口径照实写清**：它是**模型自述**，不是事实——因此它既不能作为「本地已尝试过 X」的证据，也不得被本地重解（§6.2）当作可信输入引用；与规则 5 对 `brief_unknowns` 的处理同类。
2. 模型 proposal 的 `proposed_question` / `local_attempts_summary` / `candidate_context` 只是素材候选；App/本地核心负责检索与组装，模型不能直接构造 TaskBrief、package、grant 或选择 provider。
3. 每个 section 经 PrivacyPolicy 后成为 `free_text` PreparedContextItem，label 使用本地固定名（`brief_goal` / `brief_constraints` / `brief_facts` / `brief_evidence` / `brief_attempts` / `brief_question` / `brief_unknowns` / `brief_project_note`——末项 2026-09-24 新增，见规则 9）。**section 没有独立的字节上限**（2026-09-17 裁决，取代原「单 section ≤ 400 UTF-8 字节——超过即整段拒绝」规则与 `section_too_long` 语义；理由：400 是 P4 的保守起步约束，真实场景证明它使长上下文协同结构性失效，见 `clarifications.md` 同日条目）：唯一字节硬边界是**整包 `context_byte_budget`**（§8），由 `PrivacyPolicy.prepare()` 在清洗与同值去重（规则 7）**完成之后**一次性校验；**超预算 → 整包 fail-closed**（`SAFETY_CLOUD_BLOCK`，不发网络、不落原文），**绝不截断后发送**，也绝不在授权后静默丢弃任何已展示内容——用户看到的 preview、grant 指纹与实际 payload 三者逐项一致（§2.3.4）。sections 仍计入 `max_context_items` 与单包字节预算。
   - **内容检查一条不减**：敏感信息、裸密钥/凭据、连接串、来源（`source="local_task_context"` + 本地固定 label 集合）与类别（`free_text`）**五项**逐项执行，与模型候选同一套判据；取消的只是长度维度，**隐私扫描未被放宽**。
   - **不得以缩短场景文本或拆条来迁就限制**：长上下文场景（如 S07）的任务文本是场景事实，不得为通过预算而删改写；section 也不得被拆成多个同 label item 来绕开预算——拆条只在语义本身就是逐条时使用（规则 5 的 `brief_unknowns`）。
   - **超预算的处置只有「整包拒绝」一种**（2026-09-17 第二轮裁决钉死）：不得按字段优先级丢弃次要 section 凑预算、不得为本包动态扩容已签发 grant 的边界、不得追加第二次长度确认。用户的外发确认唯一入口仍是既有 `/cloud ask` + 完整授权 preview。默认预算 **32768**，绝对上限 **65536**（§8 配置合法范围）。
4. 被拒绝/清洗的 section 记入 denied（不含原值）；TaskBrief 全空且无其他候选 → COMPLETED_LOCAL（§1.4），不发网络。
5. **`brief_unknowns`（missing information 的表达通道，2026-09-14 新增）**：云端咨询准入（§1.3）不再被 `missing_info` 一票否决后，模型认为缺失的信息必须有外发载体，使云端能给出**条件化分析**（「若 X 则…若 Y 则…」）或经 §6.1 followup 协议提出受限追问。`TaskBrief.unknowns` 是 `tuple[str, ...] = ()`（逐条语义；带默认值的新字段与既有 `TaskBrief(goal, constraints, known_facts, evidence, attempts, question)` 位置构造兼容，`src/core/schemas.py` 现有调用零改动）。构造规则：
   - 来源是 `IntentCandidate.missing_info`（模型输出，不可信）：App 取**前 3 条**（P4 常量），每条生成一个独立 `ContextCandidate(category="free_text", label="brief_unknowns", source="local_task_context")` item——**逐条**过 PrivacyPolicy 扫描/脱敏（无独立字节上限），不合并文本（合并后任一条命中敏感模式会整段丢失整个通道）；同名 label 多 item 并存，沿用 §5.3 规则 7 的 `brief_evidence` 先例。
   - 单条含敏感模式 → **整条拒绝**（denied 记固定敏感原因、不含原值），不影响其余条目（2026-09-17：**不再有 400 字节上限**，与规则 3 一致；单条仍计入整包 item/byte 预算）；`missing_info` 为空 → 无该 section。
   - `brief_unknowns` 是「本地模型自认的缺口」声明，不是用户陈述：云端与本地回流都不得将其视为已证实的事实；本地重解（§6.2）对它的处理与云端 analysis 相同——不可信引用。
   - 逐条准入上限（3 条）是**候选构造层**的取舍（保护单包 item/byte 预算，§2.3.5），不是对外发文本的截断——未入选条目根本不进入候选，与「不截断后发送」口径不冲突。上限是 P4 常量 `_BRIEF_UNKNOWN_LIMIT = 3`（实现侧），不得散落为字面量。
6. **概念结构与外发载体的映射（2026-09-14 三轮补钉）**：`TaskBrief`（`src/core/schemas.py`）是本地构建的**概念结构**，不是序列化进 package 的对象——真实外发由 App 把每个 section 映射为一个 `ContextCandidate(source="local_task_context", category="free_text", label=brief_*)`（§2.3.3 通道），`TaskBrief.unknowns` 的每个元素映射为一个独立的 `brief_unknowns` item。因此：① 实现侧**不构造 `TaskBrief` 实例再拆解**，只按本节的 section 与构造规则直接产出候选；② 契约新增字段必须同时给出对应的 `brief_*` label 与构造规则，不得存在「有字段无映射」的悬空项；③ 三者的对应关系是外发口径的唯一来源（用户看到的 preview、grant 指纹、实际 payload 一致，§2.3.4）。
7. **确定性同值去重（2026-09-17 新增，S07 长上下文协同联动）**：同一段文本不得被两条候选同时承载。触发案例：S07 的任务文本被 App 同时映射为 `brief_goal` 与 `brief_question`，同一内容占两份 item/byte 预算（在旧 400 字节规则下还双双被整段拒绝，直接导致 `no_safe_context`）。规则：
   - `brief_goal` ← `current_input`（原样，唯一来源）；
   - `brief_question` **只在模型给出非空 `proposed_question` 时生成**；**不得**再以 `current_input` 作为 `brief_question` 的 fallback；
   - `proposed_question.strip()` 与 `brief_goal.strip()` 完全相同时 → **省略** `brief_question`（不构造候选、不占 item/byte 预算、不进 denied）；
   - 只做**逐字符同值**比较（各自 `strip()` 后完全相等即视为同值），**不做**语义/相似度去重、不改写保留下来的文本、不合并不同 label 的内容——`brief_goal` 与 `brief_question` 语义相近但文本不同时，两条都保留；
   - 去重在 App 构造候选时（`_with_task_brief_candidates`）完成，**先于** `PrivacyPolicy.prepare()`，因此不可能造成「preview / grant 指纹 / 实际 payload」三者不一致；去重属于**候选构造层取舍**（同规则 5 的 3 条上限），不是对外发文本的截断。
8. **跨 section 确定性去重（2026-09-24 新增，扩展规则 7）**：规则 7 只处理 `brief_goal` 与 `brief_question` 的同值关系；真实 run 还观察到 `brief_facts` / `brief_evidence` 与任务目标/事实/约束重复——同一段文本被两条候选承载，外发上下文膨胀、用户审阅困难。本规则把同值去重**扩到全部 `brief_*` section**，判据全部确定性，落点仍在 `_with_task_brief_candidates` 内、`PrivacyPolicy.prepare()` 之前：
   - **优先级顺序（先到先得）**：`brief_goal` → `brief_question` → `brief_facts` → `brief_project_note` → `brief_evidence` → `brief_attempts` → `brief_unknowns`。丢弃只发生在「后者 vs 更早优先级」方向，结果与遍历顺序无关。
   - **归一化（唯一判据）**：NFC 归一化 + 首尾 `strip()` + 内部连续空白折叠为单个半角空格；**大小写不折叠**（折叠会误伤内容不同的候选）。
   - **T1 整段同值**：某 section 归一化后与更早优先级 section 的归一化文本**全等** → 丢弃后者（不构造候选、不占 item/byte 预算、不进 denied）。
   - **T2 行级同值**：多行 section（`brief_evidence` / `brief_unknowns`）逐行归一化；某行与更早优先级 section 的**任一行**全等 → 丢弃该行。
   - **T3 行级被包含（吸收源限于 `brief_goal` / `brief_question`）**：某行归一化后被 `brief_goal` 或 `brief_question` 的归一化文本**包含** → 丢弃该行。理由：goal/question 是本轮用户原话，云端已看到；历史片段把它整段裹在里面时，重复的正是这一句。**取舍照实记录**：被包含行若另有独有内容（如「User: 原话 / Assistant: 上次答复」的整段）会一并丢弃；若真实 run 观察到云端因缺该历史片段而质量下降，按 §10 立候选（不预设「改为行级截断」这类改写方案）。
   - **空 section 不生成候选**：归一化后为空的 section **不构造候选**——**既有实现已如此**（`_with_task_brief_candidates` 以 `value.strip()` 且 `!= "{}"` 过滤，`brief_constraints` 恒为空串故恒不产生候选）；本条把它写成契约，并要求**去重后变空**的 section 同此处理（不留空候选、不留 denied）。
   - **不做**：语义/相似度合并、跨行改写、模型参与、大小写折叠，也不把「丢弃」变成「改写保留下来的文本」。
   - **与预算的关系**：去重先于 `prepare()` 的整包字节校验，因此「仅因重复而超预算」的包现在可以通过——这是本规则的**意图**；规则 3 的「整包 `context_byte_budget` 是唯一字节硬边界、超预算只整包拒绝」**不变**（校验对象是去重后的内容）。
9. **摘要类内容的事实身份与来源标记（2026-09-24 新增）**：真实 run 观察到自动生成的项目摘要把用户事实**加强**（「波形仿真完成、没有明显故障」→「验证无故障」），再经 `brief_facts` 外发 ⇒ 云端把它当已知事实施加推理。裁决：
   - **事实权威**：用户**逐字陈述**（本轮 `current_input` 与历史 episode 的逐字文本）是唯一的事实权威；模型生成的摘要、概括、分析一律是**推断**，不得以事实身份外发，也不得替代用户陈述。
   - **`brief_facts` 收窄**：只承载**用户逐字陈述事实**。其确定性来源只有本轮用户输入，**与 `brief_goal` 同源 ⇒ 按规则 8 的 T1 恒被去重省略**——本次裁决后 `brief_facts` 在真实运行中**不再出现**。契约保留该 label 与 `TaskBrief.known_facts` 字段（兼容性与规则 6 的映射要求），但**不得**再有任何实现把它填成项目摘要、`json.dumps(project_state)` 或其它本地结构化块。
   - **`brief_project_note`（新 label）承载项目摘要**，值 = **确定性固定前缀** + 摘要原文，按摘要来源分流：
     - 自动摘要（`ProjectStore.update_auto` 写入，即 `"summary" not in manual_overrides`）→ 前缀标明「本地模型推断、未经用户确认，不得当作事实」；
     - 人工摘要（`set_manual` 写入，`"summary" in manual_overrides`）→ 前缀标明「用户手写」。
     前缀是本地固定字面量、**不由模型生成**且**幂等**（同一 section 重复构造不叠加）。来源判定只读 `manual_overrides`（本地持久化状态，模型不可写）⇒ 确定性。
   - **不得外发本地标识符**：`brief_*` 的任何值**不得**包含 `project_id` / `session_id` / `task_id`（此前 `brief_facts` 把 `json.dumps({"project_id": …, "summary": …})` 整体外发，本次一并取消）。
   - **会话摘要同身份**：`brief_evidence` 中 ContextAssembler 组装的行必须**自述来源且两类可区分**——模型生成的滚动摘要行用「本地模型推断、未经用户确认」同族前缀；逐字检索片段行用「本地历史片段（逐字）」前缀。具体文案由 Codex 定，但**两类前缀必须不同且都非空**。
   - **摘要生成提示词收窄（确定性提示词文本）**：项目摘要与会话摘要的生成提示词必须包含「只允许复述用户已陈述的内容与本轮实际发生的动作；不得推断结论、不得把未验证的推测写成事实；不确定的内容写成未解决事项」。这是提示词层加固，**不改变**「生成物是不可信文本」的既有前提（§2.3 规则 8 的标签通道与 §4.2 的边界均不变）。
   - **不得用模型做事实判定**：本规则与规则 8 的全部降级/去重都是确定性文本判定，**不得**引入模型改写、模型判定「是否同一事实」，或相似度合并。

---

## 3. 有限、不可扩大的 AuthorizationGrant

### 3.1 数据结构

```python
@dataclass(frozen=True)
class AuthorizationGrant:
    """不可变授权边界；消费状态不放在本对象。"""
    grant_id: str
    task_id: str
    session_id: str
    provider: str
    purpose: str
    authorized_categories: frozenset[str]
    payload_fingerprints: frozenset[str]    # HMAC-SHA256 本地比较标识，不是可枚举裸 hash
    max_turns: int                          # 1..3，单位：成功发起的网络请求轮数
    max_context_items: int                  # 单 package 最大 PreparedContextItem 数
    max_context_bytes: int                  # 单 package context_items UTF-8 序列化字节数
    expires_at: float
    issued_by: str                          # "user" | "privacy_policy"

@dataclass
class GrantUsage:
    """AuthorizationManager 私有的可变消费台账，不序列化到云端。"""
    reserved_turns: int = 0
    consumed_turns: int = 0
    consumed_context_bytes: int = 0         # 累计成功网络请求的 bytes，仅供审计观测
    cooldown_until: float | None = None

@dataclass(frozen=True)
class GrantUsageSnapshot:
    """供 CloudBoundary 只读复核的最小快照，仅由 AuthorizationManager 生成；不含可变状态。"""
    consumed_turns: int = 0
```

### 3.2 创建和验证

- fingerprint 一律用 per-installation secret 作为 key 的 HMAC-SHA256 生成；不使用无盐/裸 SHA-256，避免短文本或常见实体值可被离线枚举。HMAC key 不进入 grant、审计或云端。
- strict/balanced 模式下，首次需要发送用户派生内容时，App 展示 **PrivacyPolicy 输出的最终 payload**（非原始候选），向用户请求授权。
- 用户确认后由 `AuthorizationManager.create_user_grant()` 创建 grant；模型、CloudBoundary、云端后端均无创建权。
- **`create_policy_grant()` 的前置条件（2026-09-17 裁决，§1.3a）**：仅在**本任务的有效授权风险 = `normal`** 时可签发；`sensitive`（含闭集外的归一化结果）一律**拒绝签发**（抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"`，不创建 grant、不消费预算/turn、不写 pending），由 §1.4 转入 `AWAITING_AUTHORIZATION`。该前置条件**与隐私模式无关**——`convenient` 也在其内，且它单独成立、不被下面的增量纯度判定覆盖（增量纯度只回答「新增候选是否纯净」，不回答「本任务是否必须用户确认」）。错误与审计行为见上一条防线分层。
- convenient 模式下 `AuthorizationManager.create_policy_grant()` 可签发**同样有限、可过期、可审计的自动 grant**，纯度判定按**增量**（2026-09-08 裁决：已确认内容继承）：`新增候选 = fingerprint ∉ 该任务台账 payload_fingerprints`，要求新增候选**全部**为 §2.3a allowlisted `user_entity`；已确认继承（fingerprint ∈ 台账历史授权集合）的候选可随包重发，不受类别纯度约束。**不变量**：policy_grant 只能向台账新增 entity 类 fingerprint，free_text 类 fingerprint 只能经 `create_user_grant`（用户确认）进入台账——归纳成立，policy grant 无法借继承把任何新 free_text/secret 送出海（同 fingerprint 必同内容：fingerprint 为 item 四元组的 HMAC）。首次签发台账为空 → 新增=全部 → 全实体才可自动签发。不能扩大已有 grant，不能绕过任一确定性否决；新增候选为空时不得签发（App 应走 §5.3 规则 6 收敛）。
- `AuthorizationManager.validate(grant, package, task_id, session_id, provider, purpose, now)` 必须验证全部绑定项、过期、turn、单包 item/byte 限制、类别和 fingerprint。
- sub-turn 只能重用第一轮已授权 payload 的子集；不得携带云端追问文本或新增本地内容。
- `create_user_grant()` 的规范签名仍为 `(preparation, task_id, session_id, provider, purpose, now)`；`create_policy_grant()` 在其后**新增一个关键字专用参数** `escalation_risk: str = "sensitive"`（2026-09-17 裁决，`12-risk-draft-closed-set.md` §3.4/§5）——它承载**有效授权风险**（§1.3a），**默认值即 fail-closed**：调用方不显式传 `"normal"` 就签不出 policy grant。`create_user_grant()` **不**接受该参数（用户显式授权不需要它，其签名一字不改）。绑定字段由调用方（App 持有任务生命周期状态）显式传入，不得从 preparation 隐式推断。`purpose` 取 `escalation_reason` 归一化值（§1.1 受限枚举，代码白名单），不得使用自由文本。grant 的 `max_context_items`/`max_context_bytes` 由 AuthorizationManager 构造期注入（与 PrivacyPolicy 同源配置，构造期校验）。**这是本轮唯一的接口签名变更**，00-* 镜像由 Codex 落（§12）。
- **防御性拒绝的错误与审计契约（2026-09-17 补，`12` §3.4 防线表为权威）**——照 `04 §4.7` 的既有**防线分层**模式（同 `SAFETY_IMPACT_CLOSED`）：
  - **主防线在 App**：有效授权风险非 `normal` 时，App **根本不调用** `create_policy_grant()`，直接走 `PREPARING → AWAITING_AUTHORIZATION`（正常响应，不抛异常——`handle()` 有不抛异常契约）；授权等待由**既有** `cloud_consult phase="authorization_required"` 事件表达。
  - **冗余防线在 `AuthorizationManager`**：被非 `normal` 的有效风险调用时**拒绝签发**并抛 `CLOUD_AUTHORIZATION_REQUIRED`（**复用既有错误码**，本表错误码清单**无需新增**）+ `details.reason = "sensitive_policy_grant_forbidden"` + `recoverable=False`（同参数必然再次失败；补救路径是显式 `/cloud allow` 走 `create_user_grant`，不是重试）。
  - **不消耗任何状态**：不签发 grant、不扣预算、不推进轮次、不写 pending、不改 `LocalTaskContext`。
  - **`AuthorizationManager` 不写审计，调用方也不写 `CloudAuditEvent`（2026-09-18 补钉，Codex 复审提出）**：`AuthorizationManager` 没有审计依赖、不新增；接线缺陷的痕迹由 App 发**既有** `cloud_consult` 事件承担——`phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"`（`07` §2.2 的 `denied_reason` 封闭集**新增该本地否决类取值**，与 2026-09-13 P6c 扩展同一做法：既有 stage、既有 key、无新采集面），随后**转入授权等待**（fail-safe 方向），**不得**补签 policy grant。
  - **为什么不是 `record_denial()`（本轮被否决的两条路径）**：`record_denial()` 的 `reason` 是**固定四值闭集**（§4.3），枚举外值 fail-closed 抛 `SAFETY_CLOUD_BLOCK`——直接把新原因码传进去会被审计接口自己拒绝；而「把它加进闭集」也不成立，因为该方法的不变量是**每条任务清理路径恰一条**、事件形态是「本事件无轮次发生」的**终止语义**（`turn=0`、其余操作字段全零）。误调用**不是**任务终止路径：App 之后还要进授权等待，用户还可能 `/cloud allow` 走通并产生后续 `cloud_consult` 事件——在此补一条会同时破坏「恰一条」与「终止语义」两条既有不变量。故扩张的是 `denied_reason`（本就以本地否决类为扩展点），**不是** `CloudAuditEvent` 的 reason 闭集、也不是 `record_denial` 的四值枚举；错误码与审计结构**均零改动**。

### 3.3 消费、失败与冷却语义（唯一出口执行）

`AuthorizationGrant` 是不可变边界；`GrantUsage` 由 `AuthorizationManager` 按 `grant_id` 保存，且**只有** `SideEffectGateway` 可通过其受限方法变更。单位严格分离：

- `max_turns` / `reserved_turns` / `consumed_turns`：网络请求轮数；
- `max_context_items`：单 package item 上限；
- `max_context_bytes`：单 package context_items UTF-8 JSON 序列化字节上限；
- `consumed_context_bytes`：成功网络请求的累计 context bytes，仅供审计和后续策略观测，**不**与单包限制混用。

单轮执行的原子语义：

1. 在任何网络请求前，`reserve_turn()` 原子检查 `consumed_turns + reserved_turns < max_turns`，成功后 `reserved_turns += 1`；无法预留即 `CLOUD_BUDGET_EXCEEDED`，不发网络。
2. `AuthorizationManager.validate()`、PrivacyPolicy 或 `CloudBoundary.check_request()` 失败：释放 reservation；`consumed_turns`/`consumed_context_bytes` 不变；不进入冷却；写 denied audit。
3. 网络调用实际开始（调用 `CloudAdvisoryBackend.advise()` 前瞬间）：reservation 转为消费，`reserved_turns -= 1`、`consumed_turns += 1`、`consumed_context_bytes += package_context_bytes`。**网络尝试即消耗一轮**，避免调用方通过可控超时/连接失败刷免费重试。
4. 网络错误、超时、云端解析失败、入站 CloudBoundary 拒绝：不退款，已消费 turn 保持；进入任务冷却；写 error/denied audit。
5. 成功 advisory：已消费 turn 保持；若 `needs_more_info=True` 且 grant 还有预算和未过期，可进行下一 sub-turn；最终 advisory 后进入冷却。
6. 用户在 `AWAITING_AUTHORIZATION` 阶段取消/拒绝/超时：没有 reservation，不消耗预算、不进入冷却。
7. 用户在已发网络请求后取消只能阻止**未来** sub-turn/本地执行，不能退款已开始的网络请求；立即撤销活跃 grant 并进入冷却。

任务冷却默认 300 秒，可配置（§8 `cooldown_seconds`，允许范围 1..3600，构造期非法值 `CONFIG_ERROR`）；自「网络调用开始」起计算（不等网络响应），存于 `GrantUsage.cooldown_until` 或按 task_id 的等价本地台账。冷却期内 force_cloud 也不能绕过。

**任务级扩张上限（跨 grant，2026-09-03；计数起点同日复审钉死）**：AuthorizationManager 另按 `task_id` 维护任务台账——

- 同一任务全部 grant 的累计 `consumed_turns` ≤ `max_turns_per_task`（§8）；
- **首次 grant 不计入**重新授权；仅因 §3.4 边界扩大（新类别 / 新 fingerprint / 范围扩大）而签发的新 grant 计数，每任务最多 **2** 次（P4 常量，非配置）；
- 达到上限后：扩大边界的新 grant 不再签发（`CLOUD_BUDGET_EXCEEDED`），续咨询以最近部分 advisory 收敛（§5.3 规则 6）；P4 无同 grant sub-turn 可复用（§4.1）。

目的：堵住「通过反复重新确认换新 grant 无限扩张网络轮数」的口子——重新授权扩大的是内容边界，不是预算总量。

### 3.4 重新确认条件（任一满足即失效）

- task/session/provider/purpose 变化；
- 新数据类别出现；
- 新 `free_text` 值、不同 fingerprint、值范围扩大；
- 超过 `max_turns`、单包 `max_context_items` 或单包 `max_context_bytes`；
- `expires_at` 已过；
- 用户发出 deny_cloud；
- PrivacyPolicy 产生了新的拒绝/占位/脱敏结果，导致最终 payload 改变。

不允许「延长/扩展」旧 grant；重新确认必须创建新 grant。

---

## 4. CloudRequestPackage、CloudBoundary 与唯一出口

### 4.1 已授权请求包

`CloudRequestPackage` 只可由 PrivacyPolicy + 有效 grant 共同生成：

```python
@dataclass(frozen=True)
class CloudRequestPackage:
    task_id: str
    session_id: str
    provider: str
    purpose: str
    grant_id: str
    context_items: list[PreparedContextItem]
    allowed_scope: str
    turn: int
```

`context_items` 不含原始 secret、不含未授权候选、不含云端文本。包内不保存 `ConsultationProposal.reasoning` 或原始 `MinimalContext`。

**组装职责（钉死）**：首轮 package 由 `PrivacyPolicy.build_package(preparation, grant, turn=1) -> CloudRequestPackage` 生成——校验 grant 的 `authorized_categories`/`payload_fingerprints` 覆盖 preparation 的候选（否则 `CLOUD_AUTHORIZATION_REQUIRED`），覆盖校验失败即拒绝，不截取授权子集（2026-09-06 审查同步：单包上限由 PrivacyPolicy 构造期与 grant 签发期共同保证，build_package 内越限同样拒绝）。后续续咨询 package 由 App 以**重新 prepare 的完整 preparation** 交 `PrivacyPolicy.build_package(preparation, new_grant, turn=1)` 生成——P4 **不存在**同一 grant 内的 turn+1 续轮（2026-09-06 裁决）：云端按轮无状态，重发同值/子集不可能带来新信息，只会重复同样的追问；每次续咨询要么边界扩大（新 grant 签发即吊销旧 grant、`turn=1`，§5.3），要么以最近部分 advisory 收敛终止（§5.3 规则 6）。`CloudAdvisoryService`/`PrivacyPolicy` 不提供同 grant turn+1 派生；App/模型不得自行拼装 package。

**本地边界字段与传输载荷严格分离**：`fingerprint`、`grant_id`、`task_id`、`session_id`、`provider`、`purpose`、`turn` 是本地授权/审计字段，**不得**序列化进任何 `CloudAdvisoryBackend` HTTP 请求、prompt、header、日志或错误消息。适配器仅可序列化：

```python
{
  "allowed_scope": package.allowed_scope,
  "context": [
    {"category": item.category, "label": item.label, "value": item.value, "redacted": item.redacted}
    for item in package.context_items
  ]
}
```

序列化前适配器必须断言 payload 不含本地边界字段；该断言失败视为 `SAFETY_CLOUD_BLOCK`，不发网络。

### 4.2 CloudBoundary：最终独立复核

`CloudBoundary.check_request(package, grant, usage_snapshot)` 必须独立验证。`usage_snapshot` 是 §3.1 的 `GrantUsageSnapshot`，仅由 AuthorizationManager 生成；Boundary 对其只读，不得接受 App/模型提供的替代值。

1. package 字段完整、类型正确、provider/purpose/task/session/grant_id 与 grant 精确相同；
2. `turn == usage_snapshot.consumed_turns + 1`（与 §3.2 validate 的 turn 校验构成纵深防御）；单包 item 数 ≤ grant `max_context_items`、context_items UTF-8 JSON 字节数 ≤ grant `max_context_bytes`——这两项仅对照 grant 独立复核，不依赖快照；
3. 每个 item 的 category 在 grant `authorized_categories` 内；free_text/user_entity 的 HMAC fingerprint 属于 grant；
4. 无 secret 原值、裸凭据、高风险模式、完整连接串或未授权 path/code/log；
5. item 只含 PrivacyPolicy 允许的分类与标量值；`redacted=True` 的 secret 只能使用合法语义占位；
6. 任何失败 → `SafetyDenied(code="SAFETY_CLOUD_BLOCK")`，不得「删掉一点继续发」。

`check_response(result)` 保持现有入站语义：强制 `requires_local_validation=True`，拒绝 `approved`/`execution_plan`/`tool_calls` 等可执行标记。

### 4.3 SideEffectGateway（保持不变量）

`SideEffectGateway.execute_cloud_turn(package, grant, task_id, intent_id, turn)` 是唯一云端网络出口，顺序固定：

```
AuthorizationManager.reserve_turn      # §3.3.1；失败 CLOUD_BUDGET_EXCEEDED，不发网络
→ AuthorizationManager.validate
→ CloudBoundary.check_request(package, grant, usage_snapshot)   # 快照由 AuthorizationManager 生成；失败 release_turn
→ consume_reserved_turn                # advise() 开始前瞬间，§3.3.3
→ CloudAdvisoryBackend.advise          # 唯一网络调用
→ CloudBoundary.check_response
→ 记录 CloudAuditEvent

gateway 收到的 `grant` 是 Core 侧 `CloudGrant` 视角；进入检查链前必须 `isinstance` 确认为具体 `AuthorizationGrant`，否则 `SafetyDenied(SAFETY_CLOUD_BLOCK)`（fail-closed，防伪造边界对象）。
```

消费语义以 §3.3 为准：在 `advise()` 实际开始前 reservation 已转为消费；这里不得在成功后再次消费。Audit 必须覆盖 denied/error/allowed 三类结果。

`CloudAuditEvent` 每轮至少记录：`task_id`、`session_id`、`intent_id`、`turn`、`provider`、`purpose`、`grant_id`、`issued_by`、授权类别集合、每项 `{category,label,redacted,fingerprint_prefix}`、`package_context_items`、`package_context_bytes`、`consumed_turns`、`cooldown_until`、`verdict`、`reason`、`requested_context_categories`（归一化后）、`has_followup`、时间戳。它不得记录 item 原值、完整 fingerprint、HMAC key、原始 secret、未授权文本、云端 `analysis` 或 `followup_question` 原文或原始云端响应。

**无轮次拒绝审计（`record_denial`，2026-09-08 契约新增）**：任务在产生任何云端轮次之前被终止（用户取消、授权超时、跨会话、被新输入取代）不经过 `execute_cloud_turn`，其拒绝审计由同一出口的专用入口记录：`record_denial(task_id: str, session_id: str, reason: str) -> None`。

- `reason` 为固定四值枚举：`"user_cancelled"`（显式 `/cloud cancel|deny`）、`"authorization_expired"`（授权等待超时）、`"session_mismatch"`（跨会话）、`"superseded_by_new_input"`（新输入使 pending 失效）；枚举之外值 fail-closed 抛 `SafetyDenied(SAFETY_CLOUD_BLOCK)`。
- 事件形态（`CloudAuditEvent`）：`verdict="denied"`、`reason=<枚举值>`、真实 `task_id`/`session_id`、新 `audit_id` + 时间戳；其余操作字段全零——`turn=0`、`provider=""`、`grant_id=""`、`issued_by=""`、`intent_id=""`、`context_items=[]`、`package_context_items=0`、`package_context_bytes=0`、`consumed_turns=0`、`cooldown_until=None`、`requested_context_categories=()`、`has_followup=False`。全零表示「本事件无轮次发生」；任务已消费的轮次仍由同 task_id 的先前事件追溯。
- 最小化不变量同上段：不得包含候选值、preparation payload、grant 指纹、原始输入、`followup_question` 原文。
- App 是唯一调用方；每条任务清理路径（取消/超时/错会话/被取代）**恰产生一条** `record_denial` 事件，与 `revoke_task` 并行（后者管授权状态，前者管审计流）。审计流只经 gateway 出口写入——App 不得直接操作 `audit_log` 列表（包括「直写 gateway 持有的 list」这类绕过接口的形态）。
- `CloudTurnGateway` 测试替身须同步实现该方法。

任何 App/Core/CloudAdvisoryService/Adapter 以外模块不得绕过此入口直接调用后端。

---

## 5. sub-turn、预算与冷却

### 5.1 固定规则

- P4 最大 3 轮；每轮单独过 AuthorizationManager、CloudBoundary、SideEffectGateway 与审计。
- `CloudAdvisoryService` 只编排；只依赖 `CloudTurnGateway` 抽象，不 import `src/safety/*`、不直接持有后端。
- 云端追问的**唯一状态机输入**是 `AdvisoryResult.requested_context_categories`（受限白名单，§6.1）；`followup_question` 仅用于本地展示（标注云端非可信提示），不得回传云端、不得变成 context candidate、不得携带新的具体内容。本地按请求类别重新检索/生成候选 → PrivacyPolicy → 出现新 fingerprint 或新类别 → **新 grant + 重新确认**（§3.4）；产不出新内容 → 以最近部分 advisory 收敛（§5.3 规则 6）。任务级累计轮数与边界扩大型新 grant 次数受 §3.3 任务台账约束；编排归属见 §5.3。
- 每轮 package 只能包含其 grant 覆盖的候选；追加内容必经新 grant（§5.3）。P4 无同 grant turn+1 续轮（2026-09-06 裁决）。
- 任务级冷却：一次咨询结束/失败后记录冷却状态，未过期不得自动再次 REQUEST_CLOUD；用户 force_cloud 不能绕过冷却，除非 P4 spec 显式新增恢复流程（本期不做）。

### 5.2 预算

CloudControlState 至少跟踪：`remaining_turns`、`cooldown_active`。授权实际消费后由唯一出口写回状态，不能由模型声明已消费/未消费。

**字节限定的语义（二选一裁决记录）**：P4 不设跨轮累计字节预算——总暴露上限已被 `max_turns × 单包 max_context_bytes`（3 × 32768，2026-09-17 默认值上调后）天然封顶。单包 `max_context_items` / `max_context_bytes` 由 PrivacyPolicy 准备阶段与 CloudBoundary 复核阶段按**单 package 硬拒绝**（拒绝原因入审计），不得通过创建新 grant 解决；跨轮累计字节仅由 `GrantUsage.consumed_context_bytes` 供审计观测，不参与调度决策，`CloudControlState` 无对应字段。

AuthorizationManager 提供只读查询（`remaining_turns(task_id) -> int`、`cooldown_active(task_id, now) -> bool`，或等价只读视图），App 据此装配 `CloudControlState`；消费台账仍只有唯一出口可写。无活跃 grant 记录的新任务：`remaining_turns()` 返回 `max_turns`（满预算）、`cooldown_active()` 返回 `False`。

### 5.3 新内容 followup 的编排归属（2026-09-03 复审新增）

`consult()` 的同步循环与「新内容需重新授权」不能在同一循环里自动完成。归属钉死如下：

1. **`CloudAdvisoryService.consult(package, grant, task_id, intent_id) -> ConsultOutcome` 执行单轮受控咨询，不编排任何续轮（2026-09-06 裁决：P4 无同 grant turn+1 续轮）**。某轮返回 `needs_more_info=True` 且归一化后 `requested_context_categories` 非空时，**立即返回挂起结果（携带该轮已过 `check_response` 的部分 advisory）、不再派生下一包**——它无权创建 grant、无权调用 PrivacyPolicy、无权构建含新内容的 package：

   ```python
   @dataclass(frozen=True)
   class ConsultOutcome:
       status: str                                  # "completed" | "suspended"
       result: AdvisoryResult | None                # 已过 check_response 的 advisory；completed 为最终，suspended 为部分（仅用于非否决终止的收敛兜底）
       requested_categories: tuple[str, ...] = ()   # suspended 时归一化后的白名单类别
   ```

   `needs_more_info=True` 但归一化类别为空时在本层直接收敛：`completed`（`needs_more_info` 剥离、`followup_question` 清空）。单 grant 实际只消费 1 轮；`max_turns` 退化为防御性上限，任务级预算由 §3.3 台账约束。

2. **App 是新内容 followup 的唯一编排者**。收到 suspended 后：按请求类别本地检索/生成候选（来源与标签见规则 7）→ PrivacyPolicy 重新 prepare。有新 fingerprint/新类别 → 边界扩大，按模式分流：convenient 模式且**新增候选**全部为 allowlisted `user_entity`（增量纯度判定，§3.2）**且本任务有效授权风险为 `normal`** → `create_policy_grant(..., escalation_risk="normal")` 后**同一回合内**自动续；其余（新增含 free_text，如 memory_evidence 追问；**以及本任务有效授权风险为 `sensitive` 的一切情形**）→ 进入 `AWAITING_AUTHORIZATION`（§1.4/§1.3a）。无新 fingerprint/新类别（含产出候选全部与已发送 fingerprint 相同）→ 按规则 6 收敛。
3. **pending 续咨询扩展**：此路径的 `PendingCloudAuthorization` 额外保存归一化 `requested_categories` 与「续咨询」标记；preview 展示**旧 + 新全量 payload**（新 grant 必须覆盖新旧全部 fingerprint，§3.2）。任务级已消费轮数的唯一权威是 AuthorizationManager 任务台账，App 只经只读查询观测、不缓存副本；`LocalTaskContext` 保持任务级存活至任务终态（§1.5）。
4. **确认后继续**：App 调 `create_user_grant` / `create_policy_grant(..., escalation_risk=<本任务**有效授权风险**>)`（新 preparation；风险随任务存活、**只作下界**，确定性升险只能升不能降，**不得**按本轮新增候选重新判定——§1.3a/§1.4 规则 8）→ **签发即吊销旧 grant**（§1.4 规则 7）→ `PrivacyPolicy.build_package(preparation, new_grant, turn=1)` → 以新 package + grant 再次 `consult()`。`package.turn` 按 grant 内从 1 计；跨 grant 连续性由任务台账（累计 `consumed_turns` ≤ `max_turns_per_task`）约束，本次边界扩大签发计入重授权次数（§3.3，首次 grant 不计数）。
5. **终止路径（用户否决）**：续咨询挂起期间拒绝/取消/超时/deny_cloud → 清 pending、`revoke_task` 吊销活跃 grant、写最小拒绝审计 → 云咨询任务 `CANCELLED`/`EXPIRED`；本地基于 `LocalTaskContext` **无云端建议**继续回答（用户否决优先，部分 advisory 一并丢弃）。已消费轮数不退、冷却不变。
6. **收敛统一规则（2026-09-06 裁决）**：续咨询链终止时，只要手里存在已过 `check_response` 且**未经用户否决**的最近 advisory（部分或最终），App 一律以它走 §6.2 标准回流。适用触发：本地产不出新内容；扩张型新 grant 签发遇 `CLOUD_BUDGET_EXCEEDED`（同时向用户提示已达重授权/轮数上限）；后续轮次网络/边界失败；重新 prepare 超出单包上限（捕获 `SAFETY_CLOUD_BLOCK` 后收敛，不向用户抛拦截文案；不裁剪、不截断旧 item）。仅当用户否决（规则 5）或**首轮即失败、无任何在手 advisory** 时，才走「无云端建议」降级。App 在任务级内存状态保存最近部分 advisory，任务终态清除；部分 advisory 与最终 advisory 同等受 §6.2/§6.4 约束，不写入记忆、不进审计原文。
7. **followup 候选的来源与标签（2026-09-06 钉死）**：`memory_evidence` → 追加 `ContextCandidate(source="local_task_context", label="brief_evidence", value=检索片段)`——与原 section 并列成多个 item，**不合并文本**（合并后任一条命中敏感模式会整段拒绝），同名 label 多 item 允许并存，**逐 item 过敏感扫描、无独立字节上限**（2026-09-17，与 §2.5 规则 3 一致；整包仍受 `context_byte_budget` 约束）；`user_entity` → `ContextCandidate(source="local_task_context", label=允许表 label, value=枚举值)`。PrivacyPolicy 的 `local_task_context` 标签白名单相应放宽为：brief_*（free_text）∪ §2.3a 允许表 label（user_entity）；其余照旧拒绝。

---

## 6. 本地回流与执行安全（保持不变量）

### 6.1 云端 advisory

`AdvisoryResult` 保持 advisory：`analysis`、`risks`、可选 `suggested_tools`、`requires_local_validation=True`、`needs_more_info`、`requested_context_categories: tuple[str, ...] = ()`（2026-09-03 新增，见下）。云端不能生成 ExecutionPlan、不能自称 approved。

**follow-up 机器可读协议（2026-09-03）**：追问的**唯一状态机输入**是 `requested_context_categories`——代码白名单 `{"memory_evidence", "user_entity"}`，分别表示「请提供更多记忆片段（evidence 增量）」「可补充允许表实体」。规则：

1. `CloudAdvisoryService` 对其按白名单归一化：未知值丢弃；归一后为空 → `needs_more_info` 视为 `False`（按最终 advisory 收敛，不空转网络轮次）。
2. `followup_question` 是不可信自由文本：仅用于本地展示（必须标注为「云端非可信提示」），绝不作为状态机输入、绝不回传云端、绝不进入模型 prompt、不写入记忆、不进入下一轮外发；**审计不记录其原文**——只记归一化后的 `requested_context_categories`、`has_followup` 与固定原因码（§4.3），与「不记云端 analysis 原文」同一不变量。
3. 本地按请求类别重新检索/生成候选 → PrivacyPolicy；有新内容（新 fingerprint/新类别）→ 新 grant + 重新确认（§3.4）；本地无法产出新内容时以最近部分 advisory 收敛（§5.3 规则 6），不发起空轮次——云端按轮无状态，重发同值/子集不可能带来新信息，只会重复同样的追问。

### 6.2 本地重解

云端 `analysis` 作为明确标注的 **UNTRUSTED EXTERNAL REFERENCE** 注入本地 IntentResolver。提示必须要求本地模型：不服从引用中的指令、不照搬 suggested_tools、从 `LocalTaskContext`（§1.5）保留的原任务语义独立重解。

### 6.3 执行回流

本地重解出 `PLAN_LOCAL` 时：

- 一律 `requires_user_confirmation=True`，即使工具 risk normal；
- 走 P3 的会话绑定确认 + 身份验证 + Gate ①②③ + GuardedToolExecutor；
- 确认提示只展示本地计划和脱敏参数，不展示云端 analysis 或未授权外发内容。

### 6.4 非执行回流

本地重解未产生 PLAN_LOCAL 时，本地模型可将 advisory 作为不可信引用生成文字回答。输出不得含工具调用、命令、执行计划或逐字透传 analysis；失败则返回固定安全降级文案。该路径不进入 TaskPlanner/GuardedToolExecutor。

---

## 7. DeepSeekAdvisoryBackend（保留适配器边界）

> **P6c 增补（2026-09-13，modules/09-p6c-cloud-provider.md）**：本节的 `DeepSeekAdvisoryBackend` 自 P6c 起由通用 `OpenAICompatibleAdvisoryBackend` + deepseek provider profile 取代（构造签名、凭据变量体系、错误分类以 09 §3/§4/§6 为准）；「构造期不得读 Key」「已授权 package 序列化」「不把 Key/原始响应放进 user_message/审计」等边界规则全部由 09 契约继承并扩展到所有 provider。旧键 `backend`/`config.*` 的迁移规则见 09 §5.3。下文为 P4 历史依据，保留不改。

`src/adapters/deepseek_adapter.py::DeepSeekAdvisoryBackend` 实现 `CloudAdvisoryBackend.advise(request)`：

- 仅由 SideEffectGateway 调用；
- 在本类内部把 **已授权** `CloudRequestPackage` 序列化为 OpenAI 兼容请求；
- 所有传输异常映射为 `CLOUD_UNAVAILABLE`，解析异常映射为 `CLOUD_PARSE_ERROR`；
- 绝不把 API key、原始响应或未授权内容放进 `user_message`/审计；
- 保留可注入 `CloudTransport`，默认 pytest 无需真实云端。
- Adapter 构造期**不得**读取或校验 `LOCALMIND_CLOUD_API_KEY`——`enabled=false` + `backend="deepseek"` 的组合必须可 bootstrap（§10.6 回归）；密钥在 `advise()` 执行时从环境读取。

---

## 8. 配置与默认值

> **P6c 增补（2026-09-13）**：`[cloud_advisory]` 配置形态自 P6c 起更新为 `provider` + `[cloud_advisory.connection]` + `[cloud_advisory.policy]`（09 §5.1）；本节样例中 `backend` 与 `[cloud_advisory.config]`（含 api_base/model/max_turns）为 P4 历史形态，按 09 §5.3 迁移映射，兼容期至 P7。凭据变量自 P6c 起改为 provider 专属（09 §4.1），`LOCALMIND_CLOUD_API_KEY` 仅保留 deepseek 兼容回退。下文为 P4 历史依据，保留不改。

```toml
[cloud_advisory]
enabled = false
backend = "noop"
privacy_mode = "balanced"             # strict | balanced | convenient
max_turns_per_task = 3
max_context_items = 12                 # 最坏 6 sections + 3 个 brief_unknowns item = 9（§2.5 规则 5）+ 实体/模型候选余量；
                                       # 2026-09-14 由 8 上调——8 会让 brief_unknowns 拆分后的合法任务包被整包拒绝
context_byte_budget = 32768             # 允许范围 256..65536（65536 = 绝对硬上限），构造期非法值 CONFIG_ERROR；
                                       # 2026-09-17 由 2048 上调（§2.5 规则 3：整包预算成为 TaskBrief 的唯一字节硬边界）；
                                       # 同日老板裁决最终取 32768（中间值 8192 已作废）
cooldown_seconds = 300                 # 允许范围 1..3600，构造期非法值 CONFIG_ERROR
grant_ttl_seconds = 600

[cloud_advisory.config]
api_base = "https://api.deepseek.com/v1"
model = "deepseek-chat"
request_timeout_seconds = 60
allowed_scope = "仅提供分析建议，不生成执行命令或计划"
```

- `api_key` 仅来自 `LOCALMIND_CLOUD_API_KEY`，不得写进 toml。
- `privacy_mode`、预算、TTL、cooldown 均在构造期严格校验，非法为 `CONFIG_ERROR`。
- **`brief_*` section 没有独立字节上限**（§2.5 规则 3，2026-09-17）。`max_context_items` 覆盖 brief sections、`brief_unknowns` 逐条 item 与实体；`brief_unknowns` 是**第 7 个 label 但最多 3 个独立 item**——最坏 item 数 = 6 sections + 3 unknowns = 9，这是默认值上调到 12 的依据；同值去重（§2.5 规则 7 省略 `brief_question`）只可能减少实际 item 数，不改上限。
- **`context_byte_budget` 是 TaskBrief 的唯一字节硬边界**：默认 **32768**（2026-09-17 由 2048 上调——2048 在 S07 这类长上下文任务上会让整包被拒，云端协同结构性失效；同日老板裁决最终定为 32768，绝对硬上限 65536）。整包经清洗与同值去重后仍超预算 → **整包 fail-closed**（`SAFETY_CLOUD_BLOCK`），不截断、不发送任何未完整展示给用户的内容。item 上限是记账约束，字节上限是暴露约束，二者不互相替代。**本次只动默认值与超预算处置口径**：隐私扫描、来源/类别校验、preview/grant/payload 逐项一致（§2.3.4）与 `CloudBoundary` 独立复核（§4.2）**全部不变**。
- **超出预算时的处理只有一种：整包拒绝**（2026-09-17 老板裁决钉死，**明确不做**下列三件事）：
  1. **不做字段优先级截取**——不得按 label 优先级丢弃「次要」section 去凑预算；
  2. **不做动态扩容 grant**——不得因内容更多而放宽已签发 grant 的边界，也不得为容纳本包而改写预算；
  3. **不做二次长度确认**——不得因超预算再向用户追问一次「是否同意发送更大的包」。
  用户的外发确认**就是**既有 `/cloud ask` + 完整授权 preview（§1.4/§2.4），不存在第二个确认入口；超预算即 fail-closed 收尾，不新增交互步骤。
- **配置合法范围（构造期校验，非法值 `CONFIG_ERROR`，不得留给实现猜测）**：`max_context_items ∈ [1, 100]`；`context_byte_budget ∈ [256, 65536]`。下限 256 是「一个可辨认最小包」的合理性下限（更小的配置必然只装得下空值或占位内容），**不构成可用性保证**——预算是否够装下某类场景的任务包由运维配置决定，不够时按上一条 fail-closed，绝不放宽或截断。上限 65536 是单包外发暴露的天花板。`PrivacyPolicy` 与 `AuthorizationManager` 必须使用**同一判据**（既有偏差：`PrivacyPolicy.__init__` 只校验 `>= 1`，无上界）。
- `enabled=true` 且 `backend="noop"` 是配置矛盾：bootstrap 抛 `CONFIG_ERROR`——noop 仅用于 `enabled=false` 的默认组合，不参与真实咨询（否则会为占位响应空耗 turn 预算）。
- 允许的 provider、purpose、字段类别是代码/策略白名单，不由配置任意扩大。

---

## 9. 错误码（工程契约后续同步）

> **P6c 增补（2026-09-13）**：本表授权/预算/冷却类错误码不受影响；云端传输类错误自 P6c 起按 09 §6.1 细分——新增 `CLOUD_AUTH_INVALID` / `CLOUD_ENDPOINT_INVALID` / `CLOUD_RATE_LIMITED` / `CLOUD_CREDENTIAL_MISSING`，`CLOUD_UNAVAILABLE` 收窄为「传输失败与 5xx」（401/403/404/429 不再落入本码）。下表为 P4 历史依据，保留不改。

在原 `CLOUD_UNAVAILABLE`、`CLOUD_PARSE_ERROR`、`SAFETY_CLOUD_BLOCK` 外，重构后需增加或明确：

| code | 场景 | user_message |
|---|---|---|
| `CLOUD_AUTHORIZATION_REQUIRED` | 需要新授权/授权范围扩大 | "该云端咨询需要你的确认后才能发送。" |
| `CLOUD_AUTHORIZATION_EXPIRED` | grant 过期/绑定不匹配 | "云端授权已失效，需要重新确认。" |
| `CLOUD_BUDGET_EXCEEDED` | turn/内容预算耗尽 | "本次云端咨询已达到预算限制。" |
| `CLOUD_COOLDOWN_ACTIVE` | 任务冷却中 | "云端咨询暂处于冷却期，请稍后再试。" |
| `SAFETY_CLOUD_BLOCK` | PrivacyPolicy/CloudBoundary 拒绝内容 | "数据发送到云端被安全策略拦截。" |
| `CLOUD_TURN_LIMIT` | sub-turn 编排达上限的内部信号（不直接暴露用户） | —（由本地整合流程处理） |

---

## 10. 测试要求

### 10.1 模型建议与规则裁决

- 模型 `should_consult=True` 但 cloud disabled、deny_cloud、预算耗尽、cooldown、后端不可用、敏感执行链限制任一成立 → 不发送。
- 模型 `should_consult=False`，用户 force_cloud=True 且其他条件通过 → 进入 PrivacyPolicy/授权流程；**即使 state=PARTIAL/VAGUE 且 `missing_info` 非空**（准入拆分后，§1.3）；**即使 `risk_draft` 为 `sensitive` 或旧词表 `low`/`medium`/`high` 或未识别值**（2026-09-16：该字段是模型输出，不得否决用户显式指令；`dangerous` 除外，走第 1 步 REFUSE）。
- `risk_draft` 的闭集归一化与未识别值兜底见 `12-risk-draft-closed-set.md` §2——模型输出 `"high"`/`"critical"`/任意措辞，不得改变 force 路径的准入结论。
- **`risk_draft` 也不得改变 proposal 路径的准入结论（2026-09-17，§1.3a）**：模型 `should_consult=True` 且其余资格条件（`expected_benefit`、模型未声明本地动作 `tool_intent == "none"`、目标明确）通过时，**`sensitive`（含旧词表/未识别/缺失归一化结果）同样准入** `REQUEST_CLOUD`。改变的只有**授权形态**：`sensitive` 一律强制用户授权（所有隐私模式含 `convenient`），`normal` 才可能走 policy grant。**唯一例外是 `dangerous`**——第 1 步 `REFUSE`，且模型不得为之建议。
- 用户 deny_cloud=True → 最高优先级拒绝，旧 grant 不可复用。
- 模型提出 provider/grant/approved 或伪造分类 → 无法改变 ControlPolicy/PrivacyPolicy 决定。

### 10.2 PrivacyPolicy 与分类

- 模型将 password/token/JWT/连接串/用户原文伪装进任意 `entity`/`summary`/`label`/`reasoning` → 原值不出现在 preparation/package/audit；按规则拒绝或生成 `api_key: present` 等占位。
- free_text/code/log/path 都按高风险文本处理，长度、类型和模式限制生效。
- `api_key: present` 可进入已授权 payload，原始 api key 不可进入。
- strict/balanced/convenient 三种模式分别按 §2.4 的确认规则验证。
- 允许表精确匹配（§2.3a）：表外 label、非枚举值、大小写/空白归一化（`strip().lower()`）、列表/dict/超长值一律拒绝；仅命中表内精确 `(label, value)` 才可作为 `user_entity`，其余归 `free_text` 或拒绝。
- `label` 走私（§2.3 规则 8）：模型把原文/凭据塞进任意候选的 `label`（含 secret/free_text 的 label）→ 原值不出现在 preparation/package/`CloudAuditEvent`；非法 label（超长、`^[a-z0-9_]+$` 之外、含敏感模式）一律拒绝该候选。

### 10.3 grant

- strict 模式每次外发（含续咨询重发）均需用户确认并签发新 grant。
- balanced 模式：首轮确认签发；续咨询一律新 grant + 确认（P4 无同 grant turn+1 续轮，无 grant 复用）。
- convenient 模式：首轮确认；续咨询新增候选全为 allowlisted `user_entity` 时由 `create_policy_grant` 自动签发（增量纯度，§3.2），其余新 grant + 确认。
- 新类别、新 free_text fingerprint、范围扩大、task/session/provider/purpose 变更、过期、超 turn/预算均要求新 grant。
- grant 不能被模型创建/延长/扩大；用户 deny_cloud 后不可复用。

### 10.4 CloudBoundary 与唯一出口

- 直接构造任意 package（额外字段、未授权 item、secret 原值、错误 provider、超预算、错误 grant）→ `SAFETY_CLOUD_BLOCK`；不能依赖 App 正确构建。
- `package.turn != usage_snapshot.consumed_turns + 1` → `SAFETY_CLOUD_BLOCK`：Boundary 的 turn 复核独立于 validate 生效；`usage_snapshot` 只能经 AuthorizationManager 获取，gateway 不得自行计算或传入陈旧值。
- 单包 item 数或 UTF-8 字节数超 grant 上限 → 硬拒绝（`SAFETY_CLOUD_BLOCK` / 隐私拒绝），不得通过创建新 grant 绕过。
- `record_denial`（§4.3 无轮次拒绝审计）：枚举外 reason → `SAFETY_CLOUD_BLOCK` fail-closed；合法 reason 产生**恰一条**操作字段全零的最小事件（`turn=0`、空 items、无任何原文/指纹），不影响 `execute_cloud_turn` 路径、预算与冷却状态。
- App 不得直接写 `audit_log` 列表；测试断言审计流只经 gateway 出口（`execute_cloud_turn` / `record_denial`）增长。
- `CloudAdvisoryService` 不直接调用 `backend.advise`，实际网络调用只在 SideEffectGateway。
- 每轮 sub-turn 都调用授权验证、出站检查、入站检查、审计；followup 不携带云端或用户新增自由文本。

### 10.5 回流与审计

- 云端影响 PLAN_LOCAL → 一律强制用户确认，仍过 P3 三关。
- 非执行回流由本地整合，不透传 analysis，不输出命令/工具调用。
- CloudAuditEvent 含 task_id/intent_id/turn/provider/purpose/grant_id、类别/脱敏结果、预算消耗与 verdict/reason；不含原始秘密、未授权文本或 analysis 原文。

### 10.6 回归

- 默认 `enabled=false` 时不需要云端 API key，现有本地闭环测试保持全绿。
- 单元测试一律 fake transport / fake clock，不依赖真实云端或真实时间。

### 10.7 授权状态机与 pending 生命周期（§1.4）

- 同 session 明确确认 → `create_user_grant` 并发送；grant 绑定字段与 §1.4/§3 一致。
- 拒绝 / 取消 / deny_cloud / 非确认普通输入 / task 或 session 切换 → `CANCELLED`：不发网络、不耗预算，pending 清理后不得复用其 payload。
- fake clock 超过 `authorization_deadline`（5 分钟）→ `EXPIRED`，返回 `CLOUD_AUTHORIZATION_EXPIRED` 提示，不创建 grant、不消耗预算。
- 授权成功后任务完成/失败/取消 → grant 从活跃状态移除，不得跨后续普通用户回合复用（§1.4 规则 6）。
- **`sensitive` 所致升级的强制授权（§1.3a/§1.4 规则 8，2026-09-17）**：隐私模式取 `convenient` 时同样必须进 `AWAITING_AUTHORIZATION`——断言该回合**无** policy grant、授权前传输调用数 0 且 `outbound_bytes == 0`；`create_policy_grant()` 以 `escalation_risk` 非 `"normal"` 调用（含不传参数的默认调用）一律拒绝签发且不消费预算/turn；`create_user_grant()` 的签名与行为**一字不改**。

### 10.8 推理升级与任务包（§2.5/§1.5/§3.3，2026-09-03）

- 复杂推理/架构权衡/代码分析场景：TaskBrief 各 section 来源正确（硬约束/事实/片段来自配置、工具结果或记忆检索，而非仅模型摘要）；各 section 均经 PrivacyPolicy 的敏感/凭据/来源/类别检查，**无独立字节上限**（2026-09-17，§2.5 规则 3）——超长 section 只要整包在 `context_byte_budget` 内即正常外发；整包超预算才整包拒绝（`SAFETY_CLOUD_BLOCK`，不截断外发）；preview / grant 指纹 / 实际 payload 三者逐项一致。字节边界与同值去重的验收矩阵见 §10.10。
- followup 走 `requested_context_categories` 白名单（§6.1）：未知/空类别 → 按最终 advisory 收敛（`needs_more_info` 视为 False）；请求 `memory_evidence`/`user_entity` 且本地产出新内容 → 新 grant + 重新确认（convenient 且新增候选全为 allowlisted `user_entity` **且本任务有效授权风险为 `normal`** 时同回合自动续，增量纯度见 §3.2，因果风险见 §1.3a）；产不出新内容 / 产出全部已发送过 / 扩张超限 → 以最近部分 advisory 收敛并提示上限（§5.3 规则 6）。任务级累计 turn 超 `max_turns_per_task` 或边界扩大型新 grant > 2 → `CLOUD_BUDGET_EXCEEDED` 后收敛（首次 grant 不计数）。
- `consult()` 挂起语义（§5.3）：合法类别请求 → `ConsultOutcome(status="suspended", result=部分 advisory)` 并携带归一化类别，不再派生下一包；空/无效类别 → `completed`（`needs_more_info` 剥离、`followup_question` 清空）。
- 续咨询编排（§5.3）：convenient 且新增候选全为 allowlisted `user_entity`（增量纯度，§3.2）**且本任务有效授权风险为 `normal`**（§1.3a）→ `create_policy_grant(..., escalation_risk="normal")` 同回合自动续；其余需确认 → `AWAITING_AUTHORIZATION`（pending 含 `requested_categories`，preview 含旧 + 新全量 payload）；确认后新 grant 签发即吊销旧 grant、新包 `turn=1`、任务台账累计与重授权计数生效。增量纯度四象限测试：空台账全实体（过）/ 空台账含 free_text（拒）/ 有继承 + 纯实体新增（过）/ 有继承 + free_text 新增（拒）。**第五例（2026-09-17 新增）**：`sensitive` 所致升级的任务在第 1 个象限（全实体新增）也不得自动续——必须进 `AWAITING_AUTHORIZATION`。
- 终止路径（§5.3）：续咨询挂起后拒绝/超时/deny_cloud → 清 pending、`revoke_task`、经 §4.3 `record_denial` 写无轮次拒绝审计、任务 `CANCELLED`/`EXPIRED`；已消费轮数不退、冷却不变；本地可无云端建议继续。四条清理路径各有断言——首轮与续咨询的显式取消（`user_cancelled`）、授权等待超时（`authorization_expired`）、跨会话输入（`session_mismatch`）、新输入取代 pending（`superseded_by_new_input`）均**恰产生一条** record_denial 事件，事件不含任何候选原文，并与 revoke_task 断言并列。
- 审计断言：followup 轮次的 `CloudAuditEvent` 不含 `followup_question` 原文，仅含归一化 `requested_context_categories` 与 `has_followup`。
- 确认回合后本地重解使用 `LocalTaskContext` 原任务语义；pending/grant/审计/包内无未授权原文或秘密；「继续」类占位输入不参与重解。
- fake transport 断言包内含 brief sections（任务语义）而非仅意图类别，且云端对已确认任务包可产出有信息量的 advisory。

### 10.9 云端准入拆分回归（§1.3/§2.5 规则 5，2026-09-14 新增）

**准入矩阵（ControlPolicy 单元级，全部确定性、不依赖模型替身的行为细节——只喂候选）**。构造注意：`has_task_text` 默认 `False`（fail-closed），force 路径用例必须**显式传 `has_task_text=True`**；既有离线用例（`cloud_enabled=False`）不受该字段影响：

> **层次纪律（2026-09-16 二轮）**：本矩阵是 ControlPolicy **单元级**，`risk_draft` **只喂闭集值**（`normal`/`sensitive`/`dangerous`）。原始模型字符串（旧词表 `low`/`medium`/`high`、大小写/空白变体、未识别值、缺失值）的覆盖属于**归一化层与集成层**，权威全表在 `12-risk-draft-closed-set.md` §4.1 / §4.2 第 1–2 层；把原始值直接喂给 ControlPolicy 会测一个正常链路里不存在的状态（`12-risk-draft-closed-set.md` §4.2 分层原则）。

| # | 候选 / 状态 | 期望 |
|---|---|---|
| 1 | `force_cloud=True` + PARTIAL + `missing_info` 非空 + 有任务文本 | `REQUEST_CLOUD`（forced） |
| 2 | `force_cloud=True` + VAGUE + 有任务文本 + `consultation_proposal=None` | `REQUEST_CLOUD`（forced；purpose=`unknown`，brief 全本地构建） |
| 3 | `force_cloud=True` + `has_task_text=False`（空任务） | 不升级——本地 ASK_USER/RETRIEVE_MORE，绝不 REQUEST_CLOUD |
| 4 | `force_cloud=True` + dangerous | `REFUSE` |
| 5 | `force_cloud=True` + `deny_cloud=True` | 不升级，本地路径 |
| 6 | `force_cloud=True` + 模型声明了本地动作（`tool_intent="local_action"`；2026-09-18 前用 `suggested_tools` 非空构造） | `REQUEST_CLOUD`（forced）——模型建议不是用户指令的锁（2026-09-14 二轮修正） |
| 7 | `force_cloud=True` + `task_has_sensitive_execution_chain=True` | 不升级（真实工具执行态，App 确定性状态） |
| 8 | `force_cloud=True` + `cloud_enabled=False` / `provider_available=False` / `remaining_turns<=0` / `cooldown_active=True` | 各自不升级（禁用/不可用/预算/冷却逐例） |
| 9 | `force_cloud=True` + `risk_draft` 为闭集值 `"normal"` / `"sensitive"` | **2026-09-16 翻转**：→ **`REQUEST_CLOUD`（forced）**。`"dangerous"` 见第 4 例（`REFUSE`）。旧口径「`sensitive` 不升级」已废——它让用户显式指令取决于模型措辞（`12-risk-draft-closed-set.md` §0.1）。**原始措辞（旧词表/变体/未识别/缺失）不进本矩阵**，见上「层次纪律」 |
| 10 | 无 force + PARTIAL + `missing_info` 非空 + proposal（`should_consult=True`, benefit≥0.5）+ intent 非 unknown + `tool_intent="none"` | `REQUEST_CLOUD`（proposed，缺失信息随 TaskBrief） |
| 11 | 无 force + proposal 有效 + `tool_intent="local_action"` | 不自动升级（自动路径的保守退出；与第 6 例对照——force 忽略建议、自动路径尊重建议） |
| 12 | 无 force + PARTIAL + `missing_info` 非空 + 无 proposal / `should_consult=False` / benefit<0.5 | 保持本地 `RETRIEVE_MORE`（不升级） |
| 13 | 无 force + VAGUE + proposal 有效 | 不自动升级 |
| 14 | 无 force + PARTIAL/ALMOST + intent_type=`unknown` + proposal 有效 | 不自动升级（目标不明确） |
| 15 | 无 force + 有效 READY + proposal 有效 | `REQUEST_CLOUD`（既有行为回归不破） |
| 16 | 无 force + proposal 有效 + `risk_draft` 为闭集值 `"sensitive"` | **2026-09-17 翻转**：→ **`REQUEST_CLOUD`（proposed）**，且该回合起进入**强制用户授权**（§1.3a）——`convenient` 下同样不得签发 policy grant、不得同回合自动续。旧口径「不自动升级 + `vetoed` + `non_normal_risk`」已废：否决项 3 已删除（`12-risk-draft-closed-set.md` §3.2/§3.4） |
| 17 | 判定对象回归：候选来自 S09/S06 型**只读开放式分析**（构造：`risk_draft="normal"` + `should_consult=True` + benefit ≥ 0.5 + 无 force + 有效 READY） | `REQUEST_CLOUD`（proposed），与第 15 例同形。**模型是否真的输出 `normal`** 属提示词层，按 A 组口径验收：规则文本进 pytest（`12` §1.3 第 6/7 条），模型行为按真实 run 观测（`12` §4.2.5 A 组、10 §7.3） |
| 18 | 无 force + proposal 有效 + `risk_draft="normal"` + `convenient` + 新增候选全为 allowlisted `user_entity` | `create_policy_grant(..., escalation_risk="normal")` 可签发（既有 convenient 自动续**不回归**；R6 明确不改 `normal` 路径） |
| 19 | 承第 16 例，调用 `create_policy_grant(..., escalation_risk="sensitive")`，**含不传该参数的默认调用** | **拒绝签发**：抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"` + `recoverable=False`；不创建 grant、不消费预算与 turn、不写 pending；链路停在 `AWAITING_AUTHORIZATION`（fail-closed 默认值，`12` §3.4） |
| 20 | **有效授权风险：确定性升险（2026-09-17 补，`12` §3.5）**——模型下界 `"normal"` + 准备阶段发现 payload 候选含敏感项 | 有效值升为 `sensitive` → `create_policy_grant` 拒绝签发；App **主防线**根本不调用它，直接进 `AWAITING_AUTHORIZATION`；反向用例（模型 `"sensitive"` + 两个适用信号全否）仍拒绝签发——**不得下调** |
| 21 | 纯函数 `effective_authorization_risk()` 的 fail-closed 默认与参数表 | 两个布尔信号全部漏传 → 返回 `"sensitive"`；变异探针：把任一默认值改成 `False` 必须有用例变红。`causal_risk` 为闭集外值 → 先按 `12` §2.1.1 归一化再比较，返回值恒属 `RISK_LEVELS`。**参数表反向断言（2026-09-18 补）**：签名中不得出现 `high_impact` / `preflight` / `approval_profile` 类参数——工具计划层不得接回本函数 |
| 22 | **含秘密文本的就地替换（§2.3b，S12 链路）**——`free_text` 含赋值形式的可替换秘密（如 `api_key=sk-EVAL-FAKE-…`），且该 section **除凭据外还含任务语义文本**（2026-09-25 补此限定） | 该 section **正常进入** preparation（不再是 `section_too_long` / 整段拒绝）：文本中该值被替换为 `[已脱敏:secret]`、另产 `secret_placeholder`；端到端走到 `cloud_consult phase="authorization_required"` 且 `outbound_bytes == 0`；原值不出现在 payload / 事件 / 审计 / 异常；替换后复扫仍有命中 → 整段拒绝（对照例）。**限定**：若凭据**独占**该 section（脱敏后无任务语义），按 §2.3c.4 第 2 条**诚实拒绝**（第三轮新增，第五列不再适用）。S12 场景属前者：`/cloud ask 排查这份配置的鉴权失败原因：api_key=…` 的凭据之前已有任务语义 ⇒ 替换后仍非空 ⇒ 正常进入、`cloud_any=true` 不变 |
| 23 | **正例：`normal` 必须仍然可达（2026-09-18 补，`12` §4.2.5 E8）**——模型下界 `"normal"` + 两个适用信号均为 `False`（准备阶段候选全为 allowlisted 实体、执行链为 `False`） | 纯函数返回 **`"normal"`**；接线级**必须真的签出** `create_policy_grant(..., escalation_risk="normal")` 并在同回合自动续（与第 18 例同场景）。**本项是「有效授权风险不得退化为恒 `sensitive`」的可执行反证**——缺了它，只锁升险方向的矩阵会让一个恒返回 `sensitive` 的实现全绿 |

**`risk_draft` 子矩阵（2026-09-16，`12-risk-draft-closed-set.md` §4.2 为权威全表）**：该处的**三层**矩阵覆盖——① 归一化单测（全部原始值与变体，含缺失/畸形）、② 解析→策略集成（旧词表 `low`/`medium`/`high` 与变体 `" DANGEROUS "` 走完整链路，断言闭集结果与最终 action）、③ 策略单测（只喂闭集三值）+ 闭集外防御用例（`"DANGEROUS"` → `REFUSE`，其余闭集外值 → `sensitive`）——以及**确定性防漂移断言**（同一候选重复 ≥20 次 → 同一输入不得在 `admitted_proposal` / `admitted_forced` / `vetoed` 之间漂移；2026-09-17 改口径，原表述为「`admitted_forced` 与 `non_normal_risk` 之间不得漂移」，见 `12-risk-draft-closed-set.md` §4.2.4）。P4 侧只额外加一条硬性要求：

> **`proposal_denied_reason == "non_normal_risk"` 是全域禁项（2026-09-17 升级）**：**任何** run、**任何**路径都不得出现。否决项 3 删除后该值在 force 与 proposal **两条**路径都不可达（`sensitive` 不再否决；`dangerous` 在 `decide()` 第 1 步早裁为 `REFUSE` + `not_evaluated`），出现即**残留的否决项 3 未被删净**，按实现缺陷处理，与 08 §2.6 的同名结构项一致。枚举值本身**保留**在 `proposal_denied_reason` 值域内（删值会牵动 07/08 封闭集与历史报告比对口径），语义改为「保留 / 不可达」（10 §4.3）。

**`brief_unknowns` 表达（§2.5 规则 5）**：

- `missing_info` ≤3 条 → 逐条成独立 `brief_unknowns` item（source=`local_task_context`、category=`free_text`），外发 payload 可见全部条目；>3 条 → 仅前 3 条进入候选，超出的不外发（候选构造层取舍，非文本截断）。
- 单条含敏感模式 → 该条拒绝（denied 记固定原因、无原值），其余条目不受影响；**不再有 400 字节上限**（2026-09-17，与 §2.5 规则 3 一致），单条只受整包 item/byte 预算约束。
- `missing_info` 为空 → 无 `brief_unknowns` item。
- `brief_unknowns` item 计入 `max_context_items` 与单包字节预算（与既有 section 相同）；`_BRIEF_LABELS` 封闭集扩为 7 个 label，`source="model_proposed"` 的候选使用 `brief_unknowns` label 仍被拒绝（§2.2 通道规则回归）。

**端到端（App 级，fake backend）**：

- `force_cloud=True` + PARTIAL + missing_info 候选走完整链路 `REQUEST_CLOUD → prepare（含 brief_unknowns）→ AWAITING_AUTHORIZATION → grant → outbound → cloud_return → 本地回流`。
- `force_cloud=True` + **VAGUE + `consultation_proposal=None`**（`/cloud ask <开放式分析题>` 原样输入，本地模型判 VAGUE、模型未提任何建议）同样走完上述完整链路——App 级证明「无 proposal 的 force 升级」不只在 ControlPolicy 单元层成立；断言外发 payload 含 `brief_goal`/`brief_question`（全本地构建）且 `purpose=unknown`。
- 云端禁用 / deny_cloud 时同输入走纯本地路径且无 `cloud_consult` 事件。
- **`sensitive` 提案端到端（App 级，fake backend；隐私模式取 `convenient`——最能暴露漏网的配置）**：无 force + proposal 有效 + 闭集值 `risk_draft="sensitive"` → 完整链路走到 `cloud_consult phase="authorization_required"`；断言 **`outbound_bytes == 0`、传输调用数 0、无 policy grant 事件、无 `phase="outbound"`**；`/cloud allow` 后出现 `authorized`/`outbound`，且实际 payload 与 preview 展示的内容集、grant 指纹**逐项一致**，秘密/隐私原值不出现在 payload、事件、审计与异常信息中；另跑拒绝 / 取消 / 超时三条路径，各断言**恰一条** `record_denial`、零网络调用、pending 与 grant 均已清理。
- **`sensitive` 提案 + force 的对照**：`force_cloud=True` + `has_task_text=True` + `risk_draft="sensitive"` 与上一条走**同一条授权路径**（`admitted_forced` 仍是准入口径 `forced`，授权形态同样强制用户）——两条路径在授权环节**不得**有差异。
- **含秘密文本端到端（App 级，fake backend；S12 链路的确定性载体）**：任务文本含赋值形式假密钥（S12 同款 `api_key=sk-EVAL-FAKE-…`）→ App 构建出**非空** TaskBrief（goal/question 均为替换后的文本）→ 走到 `cloud_consult phase="authorization_required"`、授权前 `outbound_bytes == 0`；preview 内容集含 `secret_placeholder`；断言 payload / 事件 / 审计 / 异常四处**均不含原值**；`/cloud allow` 后实际发送的 payload 与 preview 逐项一致。
- **有效授权风险端到端（App 级，fake backend）**：构造「模型下界 `normal` + 准备阶段发现敏感候选」的任务，断言**全程没有** policy grant 的签发尝试（`convenient` 下亦然）且先出现 `authorization_required`——这是 §1.3a 主防线的可执行形式（对应 `12` §4.2.5 E6）；再构造一次**误调用** policy grant 的路径，断言抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"`，App 捕获后发 `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` **事件**（**不写 `CloudAuditEvent`**、`record_denial` 计数不因此 +1）并转入授权等待（E7）；最后跑一条**正例**：模型下界 `normal` + 两个适用信号均为 `False` → 真的签出 `escalation_risk="normal"` 并同回合自动续（E8）。

### 10.10 TaskBrief 字节边界与同值去重（§2.5 规则 3/7，2026-09-17 新增）

> **触发**：S07 长上下文云端协同的真实 run——任务文本约 225 个中文字符，被 App 同时映射为 `brief_goal` 与 `brief_question`，两段各自超过旧「单 section ≤ 400 UTF-8 字节」上限，`PrivacyPolicy` 双双按 `section_too_long` 整段拒绝 → `no_safe_context` → `cloud_assisted` 在**结构上**无法进入授权链。老板裁决：**删除 `brief_*` 的独立字节上限，整包 `context_byte_budget` 成为 TaskBrief 的唯一字节硬边界**；不放宽隐私扫描，不允许截断，不允许改写场景文本。**同日二次裁决（Codex 经 `clarifications.md` 转达）**：默认预算最终定为 **32768**（中间值 8192 作废），绝对上限 **65536**；超预算只做整包拒绝，**不做**字段优先级截取、**不做**动态扩容 grant、**不做**二次长度确认——既有 `/cloud ask` + 完整 preview 就是唯一的外发确认；隐私扫描与 payload 一致性不变。

| # | 用例 | 期望 |
|:--:|---|---|
| A1 | `brief_goal` 为 401+ UTF-8 字节（如 225 个中文字符），整包仍在 `context_byte_budget` 内 | 该 item 正常进入 preparation（**不**出现 `section_too_long`、不进 denied）；端到端可继续走到授权等待 |
| A2 | `proposed_question` 为空 / 缺省 | **不生成** `brief_question` 候选（**不得**回退为 `current_input`）；`brief_goal` 仍为 `current_input` |
| A3 | `proposed_question.strip() == current_input.strip()`（S07 原型） | 该轮只有一条 brief 候选（`brief_goal`）：无 `brief_question` item，也无对应 denied；对照旧行为（两条候选、两条 denied） |
| A4 | `proposed_question` 非空且与 `brief_goal` 文本不同 | 两条候选并存，各自内容原样保留（不做语义改写、不做相似度合并） |
| A5 | 清洗 + 去重完成后整包字节 > `context_byte_budget`（默认 32768 下即 ≥ 32769） | **整包** fail-closed（`SAFETY_CLOUD_BLOCK`）：无网络调用、无原文落地、无部分外发；不得截断后发送。**负向观测（2026-09-17 二次裁决）**：该回合**不得**出现 `cloud_consult` 的 `phase="authorization_required"` / `"authorized"` / `"outbound"` 事件，**不得**创建授权 pending，**不得**新增任何长度确认交互（不追问「是否同意发送更大的包」），**不得**丢弃单个 section 凑预算，**不得**改写 grant 边界；整包字节**恰为** `context_byte_budget`（如 32768）时正常通过 |
| A6 | 某 section 文本内含敏感值/裸密钥（即使整包远未超预算） | 该候选按原敏感判据被拒（denied 记固定原因、不含原值）——取消长度上限**未**放宽隐私扫描 |
| A7 | 授权链路一致性 | 授权 preview 展示的内容集、grant fingerprint 对应的内容集、`CloudRequestPackage.context_items` **逐项一致**；授权后不得静默截断或丢弃任何已展示内容 |
| A8 | S07 `cloud_assisted` 端到端（`scenarios/S07_long_context_value.toml`） | 任务文本**保持原样不改写**；授权前该回合的 `cloud_consult` 事件 `phase="authorization_required"` 且 **`outbound_bytes == 0`**（该 phase 不传真实字节，取事件默认值），此时不存在 `phase="authorized"`/`"outbound"` 事件；`/cloud allow` 后出现 `cloud_consult` 的 authorized/outbound 事件且 `outbound_bytes > 0`，随后 `local_reintegrate=true` |

- 配置范围用例：`max_context_items` 取 0 或 101、`context_byte_budget` 取 255 或 65537 → bootstrap 期 `CONFIG_ERROR`；边界值 1/100 与 256/65536 合法。
- **附带修正（同一代码分支的既有后果，须一并覆盖）**：`brief_evidence`（含 §5.3 规则 7 的 followup 追加 item）与逐条 `brief_unknowns` 过去也走同一个 400 字节分支——**记忆检索片段超过 400 字节时被整条静默丢弃**（denied 记 `section_too_long`，但该原因不在事件字段里，用户只看到内容凭空少了一截）。取消该分支后，这类 item 只要整包在预算内即正常外发；测试须覆盖「>400 字节的检索片段作为 followup item 不再丢失」。**不因此放宽**任何敏感模式判据。
- 实施落点（Codex 属地，详见 §12）：`src/safety/privacy_policy.py` 的 `max_bytes = 400 if is_brief_section else 1500` 分支——**`brief_*` 必须完全跳过长度判据**，**不是**放宽到 1,500：任何独立字节上限都会破坏「整包预算为唯一字节硬边界」，正是本次要修的形态（1,500 只保留给 `source="model_proposed"` 的 free_text）；`src/main.py` 的 `_with_task_brief_candidates`（规则 7 去重）、bootstrap 两处默认值 `2048 → 32768`、`privacy_policy` 与 `authorization` 两处配置范围校验、四份 TOML。

### 10.11 中文凭据检测与全链路脱敏（§2.3c，2026-09-24 新增）

> **触发**：安全阻塞——`我的账号密码是123456` 的授权 preview 原样携带 `123456`。驱动器是「同一判据多份实现 + 全英文形态」。C1–C5 与 C12 是检测器层（假 backend，零网络），C6–C8 是 App 级端到端，C9–C11 是既有链路的非回归。
>
> **2026-09-24 第二轮修订**：C2/C3/C4 重写（删去「值区是否为 CJK 形态」这一判据），新增 C12 覆盖中文口令。
>
> **2026-09-24 第三轮修订（本轮）**：**C12 整体重写**——「终止符 + 片段回收 + 不可界定」模型删除，改为「边界成分（T1/T2/T3）+ 值区上界 = 行末（必要时顺延一行）」；C2 从「不可界定 ⇒ 拒绝」改为「可替换 ⇒ 原地替换」；C3 补 T2/T3 的新反向断言；C4 的判据改为「值区 == 占位符字面量」；**C6/C7 的输入形态与期望按新模型改写**（`C6` 必须用**多行**输入才能走到授权；`C7` 的拒绝改由「替换后无任务语义」触发）；C13 **新增**，专测两条标签侧语法条件与三处语法边界。

| # | 用例 | 期望 |
|:--:|---|---|
| C1 | `scan_credentials("我的账号密码是123456")` | 命中 1 处；标签族含 `密码`、规范标签 `password`、值区 `123456`、态 = 可替换 |
| C2 | `密码：abc 123` 与 `password = two words` | 态 = **可替换**（值区非空）；`redact_outbound` 输出 `密码：[已脱敏:secret]` / `password = [已脱敏:secret]`，**不含** `123` / `words`。**反向断言**：不存在「值区含内部空白 ⇒ 不可界定 ⇒ 拒绝」这条分支（第三轮删除） |
| C3 | `计数器是123456`、`今天讨论了api_key的实现方案` | **零命中** ⇒ 不替换、不拒绝、不影响任何判据。**注**：`改密码是必要的` 与 `token 过期了` **不在**本行（前者见 C12 ④，后者属 T2 的已知代价，见 C13 ④） |
| C4 | `api_key=[已脱敏:secret]`、`密码是[已脱敏:secret]` | **零命中**（**占位符显式自免疫**：值区 == 占位符字面量 `[已脱敏:secret]`，与是否含 CJK 无关）；`redact_outbound` 幂等：同输入调两次输出相同，第二次零替换 |
| C5 | 闭集覆盖与规范标签 | 标签闭集每个成员都产出 `^[a-z0-9_]+$` 的规范标签且**不触发兜底 `credential`**；英文标签取原值小写（`api_key=…` 的 placeholder label 仍为 `api_key`，既有 fingerprint 不漂移） |
| C6 | App 级：**多行输入**（任务一行 + 凭据一行，如 `请帮我评估这套加密方案\n我的账号密码是123456`）+ 强制云咨询（fake backend） | 授权 preview 文本**不含原值**且含 `[已脱敏:secret]`；preparation 含 `secret_placeholder`；**任务语义那一行保留**（section **不**被拒）；`phase="authorization_required"` 存在且 `outbound_bytes == 0`；有效授权风险 ≥ `sensitive` ⇒ 全程无 policy grant 签发尝试 |
| C7 | App 级：**单行**输入把凭据与任务挤在一行（`密码是abc123，帮我分析这段代码`） | 整行值区被替换 ⇒ 该 section 剔除占位符/标签/分隔符/空白/标点后**为空** ⇒ **该 section 拒绝**（denied 记固定原因、不含原值；**不新增错误码 / 事件枚举**）；无 `authorization_required`/`authorized`/`outbound` 事件、零网络调用、无残留 payload；**本地回复照常产出** |
| C8 | **五面零残留（`/cloud allow` 之后）** | payload、事件流（JSONL）、`CloudAuditEvent`、异常 message/details、记忆（episodes / 摘要 / 检索结果）**五处均检索不到原值**——逐面一条构造式断言，不是抽样 |
| C9 | 记忆落盘处置（§2.3c.4 第 1 条） | 命中且值区非空 → 就地替换**整个值区**为 `[已脱敏:secret]`（**与出站同字面量、同值区定义**）；**不得**整段 `[已脱敏:block]`；**不含标签**的普通中文语句写入后与原文逐字一致（零误伤）；值区含中文、含空格、含标点时**同样全部移除**（反向断言：不存在按形态保留片段的路径） |
| C10 | 单一真源的外在证据 | 同一批样本（C1–C4、C12、C13 全表）经 `guarded_executor.contains_sensitive_value`、`privacy_policy` 出站扫描、`memory_hygiene` 落盘扫描、`rule_only_backend` L1 判据**判定一致**；`config` 声明空 `sensitive_patterns` 时内建检测集**仍生效**（内建恒生效、配置仅追加） |
| C11 | 键名级遮蔽非回归 | `redact_params` 仍**按键名**遮蔽（`_SENSITIVE_PARAM_KEYS`），未被用作内容扫描（反向断言：值含中文凭据但键名不敏感时，遮蔽形状不因此改变） |
| C12 | **命中与值区（第三轮重写，§2.3c.3 规则 1–3）** | ① **T1**：`密码是青山绿水` ⇒ 可替换，输出不含 `青山绿水`；`密码：abc，123` ⇒ 输出不含 `abc` 与 `123`，且**不得**产出两个并排占位符（`密码：[已脱敏:secret]`）；② **T2（裸空格，本轮关闭的漏检）**：`密码 abc123` ⇒ **命中**，输出 `密码[已脱敏:secret]`（反向断言：**不存在**「裸空格不算边界」的分支）；`密码 青山绿水` ⇒ 命中，输出不含 `青山绿水`；③ **T3（粘写）**：`密码abc123` ⇒ 命中，输出 `密码[已脱敏:secret]`；④ `改密码是必要的` / `token 过期了` ⇒ **命中**（过度脱敏，**已知代价**），该回合进**强制用户授权**——测试**不得**断言这类句子零命中（T2/T3 的代价照实登记在 2.3c.6，不得写成缺口掩盖） |
| C13 | **标签侧语法条件与值区上界（第三轮新增）** | ① **拉丁标签右边界**：`tokenizer`、`api_keys` ⇒ **零命中**（`izer`/`s` 属 `[A-Za-z0-9_]`）；② **CJK 标签 + 紧随 CJK 字符 ⇒ 不命中**：`密码学是什么`、`密钥管理体系` ⇒ **零命中**（**登记的语法边界**，不是形态豁免；**同一节的对应正向断言**：`密码abc123`（紧随非 CJK、非空白）**必须命中**——CJK 标签在 T3 下没有额外要求，「不触发」只针对紧随 CJK 字符这一种情形）；③ **第一条的反向断言**：`token 过期了`（T2）**必须命中**——右边界只作用于 T3，**不得**被扩大成「拉丁标签后跟空格即不命中」；④ **T2 的代价照实断言**：`token 过期了` / `api_key 读不到` ⇒ 命中且整行值区被移除（本地记忆同一行被占位），**不得**因「像普通句子」而放行；⑤ **值区上界 = 行末**：`密码：abc，123，456` 与 `密码是abc，今天天气不错` ⇒ 值区为**整行**（后者输出为 `密码是[已脱敏:secret]`，**不得**保留后半句——旧版的「CJK 片段不回收」判据已删除）；⑥ **顺延一行**：`密码：\nabc123` ⇒ 值区 = 下一行 `abc123`，输出 `密码：\n[已脱敏:secret]`；`密码：\n\nabc123`（中间空行）⇒ 顺延跳过空行后取 `abc123`；`密码：` 位于文本末尾（**后面没有任何非空行**）⇒ 值区为空 ⇒ **不可命中**（反向断言：**不得**把「标签在末尾且其后无内容」判成命中）；**2026-09-25 补**：行末**裸标签**（`密码\nabc123`，标签后无任何边界成分）⇒ **零命中、且不触发顺延**（顺延以命中为前提；登记为 2.3c.6 第 4 行 (b)，测试**不得**断言其命中——它是声明的语法边界，不是实现漏做）；⑦ **值区为空不等于拒绝**：值区为空是「不可命中」，**不得**触发任何拒绝分支（第三轮之后凭据类不再有拒绝处置） |

### 10.12 云端答案写回、跨 section 去重与摘要事实身份（2026-09-24 新增）

> **触发**：通用云端链路的三类问题——`/cloud allow` 续接回合在 `_handle_request` 内**提前短路**（`main.py:304–306`），既绕过 `_record_turn` 也未被其它路径补偿 ⇒ 云端结论**不入任何记忆**（下一轮短追问找不回）；与此同时，产出授权 preview 的那一回合**照常**走 `_record_turn` ⇒ 同一输入留下两条 episode，且**临时授权提示被当成 Assistant 回复**写进语义记忆。`brief_*` 之间跨 section 重复（膨胀 + 审阅困难）；自动摘要把用户事实加强后经 `brief_facts` 外发（事实污染）。W1/W1b/W2/W2b 对应写回（含**单条 episode 不变式**与两条异常分支），W5–W6 对应去重，W7–W9 对应事实身份，W10 是非干扰。

| # | 用例 | 期望 |
|:--:|---|---|
| W1 | App 级：云端最终答案写回（**每任务恰好一条 episode**） | `/cloud allow` 回合**成功收敛或 fallback 收敛**时 `memory.store_episode` **恰好一次**；episode 内容 = `User: <原回合用户输入>` + `Assistant: <该任务最终回复（带云端来源标记）>`；`metadata.topic/session_id/project_id` 与**冻结的**回合一致；`recorder.record` / `_topic_records` / `_topic_turn_counts` / `_update_project_memory` 与普通回合**同一条链** |
| W1b | **非终结回合写零 episode**（2026-09-24 第二轮钉死） | ① 产出「需要你的确认后才能发送」preview 的那一回合**不调用 `_record_turn`**（其四条副作用链——`store_episode` / `recorder.record` / `_topic_records` + `_topic_turn_counts` / `_update_project_memory`——**均不推进**），因此**临时授权提示永不进入语义记忆、会话滚动摘要或项目摘要**；该回合只经 `_record_cloud_event`（`phase="authorization_required"`）留事件与审计。② **取消 / 授权失效 / 跨会话不匹配 / 被新输入取代**四种终结路径同为零 episode（`memory.store_episode` 调用次数 0）——拒绝事实由各自的 `denied_reason` 事件承载。③ **云端挂起追问（`status == "suspended"`，回复是一次受限追问）同样零 episode**：该回合的回复不是终结答案，把它写成 Assistant 段等于把追问当结论存进记忆（`main.py:1218–1228` — `/cloud allow` 路径下它同样在 `main.py:304–306` 提前返回，本就不写）；补参回合是**独立的一次普通回合**，按该回合自身内容正常写入一条 |
| W2 | 续接回合不新增意图解析 | 写回用的是**冻结的** topic/intent 快照（**载体 = `LocalTaskContext`**，见下方规范文本；**不得**为承载它而改动 `PendingCloudAuthorization` 或任何跨模块结构），**不得**为该回合重跑意图解析来补 `decision`；断言方式：该回合 `intent_resolver` 调用次数为 **0** |
| W2b | **状态损坏分支：只兜底，不写回**（2026-09-24 第二轮钉死） | `_handle_cloud_authorization` 中 `_local_task_context is None` 时：**撤销**该任务 grant、清空 `_pending_cloud`、返回 `_CLOUD_FALLBACK_REPLY`、**不写 episode**（`memory.store_episode` 调用次数 0）、**不新增任何 `denied_reason` / 错误码 / 事件枚举值**（既有枚举已足够表达）。**该分支在当前状态机下不可达**（两处 `_pending_cloud` 创建点均位于 `_local_task_context` 非空的路径下游；唯三的置空点之一同时清 pending），因此本行**必须用定向测试**（测试内强制 `app._local_task_context = None`）而非端到端场景覆盖 |
| W3 | 结果不失忆（端到端） | `允许` 之后的短追问（如「刚才云端说的第二点展开」）的上下文里含该 episode 的检索片段 ⇒ 记忆连续性成立 |
| W4 | 写回同样过消毒 | episode 经 §4.1 写入消毒（同一真源），不含未脱敏凭据（与 C8 的记忆面同源） |
| W5 | 去重 T1/T2/T3 | `facts` 与 `goal` 同源（T1）、`evidence` 行与 `goal` 全等（T2）、`evidence` 行包含 `goal`（T3）→ 对应候选/行**不进 payload、不进 preview、不占 item/byte 预算、不进 denied**；断言落在**真实 payload 字节**上（**不得**只断言 preview 文本） |
| W6 | 去重不误伤 | 语义相近但文本不同者都保留（沿用 A4 口径）；大小写不同不折叠；**T3 的包含判定只以 `brief_goal`/`brief_question` 为吸收源**（其它 section 之间不得互相吸收） |
| W7 | `brief_facts` 不再出现 / `brief_project_note` 分流 | 自动摘要项目：payload 中**无** `brief_facts` 候选，`brief_project_note` 以固定前缀开头；人工摘要项目（`set_manual("summary", …)`）前缀不同且标明「用户手写」；两种情形值中均**不含** `project_id`/`session_id`/`task_id` |
| W8 | evidence 两类行前缀可区分 | 同一包的 `brief_evidence` 中，滚动摘要行与逐字检索行前缀**不同且都非空** |
| W9 | 摘要提示词收窄 | 项目摘要与会话摘要两处生成提示词都含「只复述用户已陈述内容与本轮实际动作 / 不得推断结论 / 不得把未验证推测写成事实 / 不确定写成未解决事项」的固定文本（**对提示词字符串断言，不对模型输出断言**） |
| W10 | 非干扰 | 去重与事实身份标记**不改变**任何授权/预算/安全判据：C6–C8 结论在这些改动后仍成立；`brief_*` 仍无独立字节上限；超预算仍整包拒绝；§10.9 的 23 例与 §10.10 的 A1–A8 不回归 |

**写回的完整口径（W1/W1b 的规范文本，2026-09-24 第二轮补钉）**

- **单条不变式**：一个云端任务**最多写一条**语义 episode，且**只在终结时写**。终结 = 成功收敛 / fallback 收敛 / 取消 / 授权失效 / 跨会话不匹配 / 被新输入取代 / **云端挂起追问（回复是一次追问，不是答案）**。写一条的只有**收敛**两种；其余五种写零条。
- **User 段来源**：`LocalTaskContext.input_event.text`——即**原回合用户输入**（该字段已存在，`InputEvent.text`，无需新增载体；`LocalTaskContext` 在任务创建时构造，`/cloud allow` 与续咨询两个等待回合读到的都是**同一个原始请求**）。**不得**使用 `/cloud allow`、`/cloud cancel` 等控制命令原文作为 User 段。
- **抑制条件（确定性，不看回复文案）**：某回合若产出了 `phase="authorization_required"` 事件，则该回合**不写 episode**（`sub_turn=1` 首轮与 `sub_turn=2` 续咨询同等对待）。判据用**事件**而非回复文本，因为事件是结构化观测、与回合一一对应；**不得**用「回复是否以授权提示结尾」这类文本匹配做判据。**2026-09-25 措辞对齐（等价形式，实现已在用）**：该事件的产出与本回合 `_pending_cloud` 的创建是**同一个代码点**（`main.py:1378` 先建 pending、随后写事件，用的是本回合 `task_id`），因此实现上以**本回合挂起状态**作判据（`cloud_preview_pending = _pending_cloud is not None and _pending_cloud.task_id == task_id`，`main.py:432-435`）与「本回合有该事件」**逐一回合等价**，且同样落在「结构化状态、非文本匹配」之内；两条路径（`/cloud allow` 授权路径与直连路径）**同等适用**。
- **topic / intent 来源与载体（2026-09-24 第三轮统一，只有一种说法）**：进入 AWAITING_AUTHORIZATION 时**冻结**该回合的 topic 与 intent 快照，终结回合按冻结值重建 `_record_turn` 所需的 `decision` / `candidate`，**不得为该回合重跑意图解析**（W2 断言 resolver 调用次数 0）。**载体 = `LocalTaskContext`**（该任务的语义容器；该对象的既有注释声明其**不进入 pending / grant / audit**，因此可安全承载）——`PendingCloudAuthorization` **不**承担快照职责，任何文档行若提到它承载 topic/intent，以本行为准。这是**内部结构**变更，**不改** `core/interfaces.py` 的任何签名。
  **读取时机（实现要点，Codex 属地）**：`/cloud allow` 回合进入 `_consult_cloud` 之前就要把**快照与 User 段取出**——`_consult_cloud` 在收尾（`main.py:1239`）与云端失败（`main.py:1216`）两条路径上都会把 `_local_task_context` 置空，之后再读就只剩 `None`（那属于 W2b 的状态损坏分支，不是正常收敛）。`_handle_cloud_authorization` 在 `main.py:1170` 已经判过一次 `_local_task_context is None`，快照读取与该判空同点即可。
- **写入链一致**：终结回合的写入**复用** `_record_turn`，因而与普通回合同样触发 `recorder.record`、`_topic_records`、`_topic_turn_counts`、`_update_project_memory` 四条副作用链（06 §2.4 记录的「代价：一次本地项目摘要更新、零次新增云端调用」即指此）；**不得**另写一条只调 `store_episode` 的旁路。
- **写入位置（`/cloud allow` 续接路径专属）**：该回合在 `main.py:304–306` 提前短路，**不会**自然流到 `main.py:426–433` 的 `_record_turn`，因此必须在 `/cloud allow` 路径上**显式补一次**（在 `_consult_cloud` 返回之后，无论其返回的是云端结论还是 fallback 文案）；调用点位置归 Codex 决定（`_handle_cloud_authorization` 内，或改为让该分支把回复交回 `_handle_request` 统一记录）。**两个不得**：① **不得**把补记放进 `_consult_cloud` 或 `_complete_cloud_consultation`——二者是 `/cloud allow` 续接路径与**同回合直连路径**（`_suspend_for_followup` 的 `create_policy_grant` 分支）的**共享**出口，放进去会让直连路径出现两条 episode（直连路径本就走 `main.py:426–433`）；② **不得**在补记之后再走一遍 `main.py:426–433`，同一回合两条 episode 是同一条错误。
- **与 P3 口令确认路径的差异，及其理由**：P3 确认链**保留**「确认回合 + 执行回合」两条 episode，而云端链**只保留一条**。差异源于两条链的 User 段承载不同——P3 确认回合的 User 段是**占位文本**，原始请求文本**只存在于第一条 episode**，丢弃即丢失；云端链的终结 episode 的 User 段**就是原始输入**，因此先写一条、后写一条只会造成重复（检索时授权提示还会作为上下文参与），按「无重复 + 不失忆」取舍。
- **已登记代价**：取消 / 失效 / 不匹配 / 被取代 / **挂起追问**五条路径上，**用户的原始请求文本不进入记忆**（拒绝或挂起的事实只在事件与审计里）。这与「原请求 + 临时提示」的替代方案相比少了连续性；**不预先实现**替代方案，若真实 run 观察到「用户回头追问被取消（或曾被追问）的任务」的连续性缺口 → 按 §10 立候选，候选方向是**在终结回合写「原输入 + 该回合用户可见的终结回复」**，**不得**退回「把临时授权提示写成 Assistant 段」那一版。
- **挂起回合零 episode 在两条路径上都成立（2026-09-25 修正，原「已登记的不对称」作废）**：上一版曾登记「同一挂起形态在**直连路径**上仍会把追问文本写成 Assistant 段」——**该登记不成立，已删除**。原因：追问路径（`_suspend_for_followup` 落到创建 pending 的那条，`main.py:1377-1389`）**两条路径共用**，而 `main.py:432-435` 的挂起判据对本回合 `task_id` 同样成立 ⇒ 直连路径的挂起回合**也不写 episode**。原登记把两条不同的东西混为一谈：`create_policy_grant` **成功**的那条分支（`main.py:1376`）确实「不短路、照常经 `main.py:432` 写入」，但它**不是挂起**——它同回合直接咨询并返回**云端答案**，写一条 episode 且 Assistant 段是答案，**这正是应有的行为**（它与 `/cloud allow` 路径的差别只是「谁签发 grant」，不是「写不写」）。**正确的不变式**：凡产出授权挂起（`phase="authorization_required"`）的回合零 episode；凡终结回合恰一条 episode。

---

## 11. 验收标准（新 P4 Done 定义）

1. 用户禁止联网时，模型任何建议均不触发网络调用。
2. 用户明确请求云端时，可绕过模型效用建议**与本地小模型的完整度判断**（state/置信度/missing_info，§1.3），但不能绕过 §1.3 否决集、PrivacyPolicy、grant、预算或 CloudBoundary。
3. 含用户派生内容的首次外发显示最终 payload，授权严格绑定任务/会话/provider/purpose/预算/有效期；边界不扩大时按模式复用。
4. 密钥、token、完整连接串、未授权自由文本永不外发；允许语义占位替代。
5. 云端网络调用仅经 SideEffectGateway，sub-turn 最多 3 轮、每轮均检查。
6. 云端输出不能直接执行；受云端影响计划仍强制确认并过三层安全。
7. 默认离线测试与 ruff 全绿；Core 不 import 具体云端 SDK 或 safety 具体实现。
8. §10.9 准入回归矩阵 **23 例** + `risk_draft` 子矩阵（权威全表在 `12-risk-draft-closed-set.md` §4.2）+ `brief_unknowns` 表达 + 端到端 force 链路（含 VAGUE + 无 proposal 的 App 级完整链路、`sensitive` 提案的强制授权链路、含秘密文本的就地替换链路、有效授权风险的 App 级主防线与 `normal` 正例）全部落地；S06/S07/S08 `cloud_assisted` 变体经真实运行完成 `force_cloud → 授权 → 外发 → cloud_return → local_reintegrate`（评估侧要求见 08 契约 §2.5），`local_only` 变体保持原本地决策规则。
9. `risk_draft` 闭集落地（2026-09-16）：归一化唯一实现（缺失/畸形/未识别 → `sensitive`，`resolution` 4 值含 `absent`）、schema `enum` + `required`、提示词规则文本、`intent_final` 两键落盘、**全域不出现 `non_normal_risk`**（2026-09-17 由「force 轮不出现」升级）、三层测试不混层（`12-risk-draft-closed-set.md` §4.4）。
10. **TaskBrief 字节边界与同值去重（2026-09-17）**：`brief_*` 无独立字节上限、独立 `section_too_long` 语义删除、整包 `context_byte_budget`（默认 32768，绝对上限 65536，范围 256..65536）为唯一字节硬边界；超出预算只做整包拒绝（不做字段优先级截取 / 动态扩容 grant / 二次长度确认）；`brief_question` 只在模型给出非空 `proposed_question` 时生成且同值时省略；§10.10 的 A1–A8 与配置范围用例全部落地；S07 `cloud_assisted` 经真实运行到达 `authorization_required`（授权前 `outbound_bytes=0`）并完成 `授权 → 外发 → cloud_return → local_reintegrate`，S07 任务文本未被改写或截短。
11. **`sensitive` 不阻止建议、只阻止未经确认的外发（2026-09-17 裁决，§1.3a/§3.2）**：`sensitive` 提案可准入 `REQUEST_CLOUD`（proposal 路径不再因 `risk_draft` 否决）；**所有**隐私模式（含 `convenient`）下必须进 `AWAITING_AUTHORIZATION`，只认显式 `/cloud allow` 的用户 grant，`create_policy_grant(escalation_risk≠"normal")` 一律拒绝签发（默认值即 fail-closed）；授权前零网络调用、`outbound_bytes == 0`，授权后既有检查一条不减、preview/grant/payload 逐项一致、秘密与隐私原值不入任何落点；`dangerous` / 敏感执行链 / `deny_cloud` / provider 不可用 / 预算冷却 / 空任务等红锁一条不减；`normal` 路径的 convenient 自动续不回归（§10.9 第 18 例）。判定对象钉死为**本回合实际请求的动作**（`12-risk-draft-closed-set.md` §1.2.1），`risk_draft` 的提示词规则文本按 `12` §4.2.5 A 组验收。
12. **有效授权风险 = `max(模型下界, 确定性升险)`（2026-09-17 补，§1.3a；`12` §3.5 为权威）**：模型因果风险**只作下界**，确定性信号**只能升险、不得降险**——「隐私扫描没发现问题」不得把模型声明的 `sensitive` 降回 `normal`；适用信号缺失即 `sensitive`（fail-closed 默认）。求值时点是**授权时**（`create_policy_grant()` 调用点），准入时冻结的只是下界。纯函数 `effective_authorization_risk()` 与 `normalize_risk_draft()` 同层，**参数表恰为两个**（payload 候选分类 / 敏感执行链；**2026-09-18 收窄**：工具计划与 preflight 类信号不进本链路，理由见 §1.3a 第 2 点，反向断言见 §10.9 第 21 例）。**双向都验**：升险用第 20/21 例，**正例（仍能签出 `normal`）用第 23 例**——只锁升险方向的矩阵会让「恒判 `sensitive`」的实现全绿。§10.9 第 20/21/23 例与 `12` §4.2.5 E 组（含 E8）落地。
13. **含秘密文本的就地替换（2026-09-17 裁决，§2.3b）**：可替换秘密就地替换为 `[已脱敏:secret]` + 另产 `secret_placeholder`，该 section 不再整段拒绝（取代 2026-09-06 的「可选优化、不实现」）；替换后复扫仍有命中即整段拒绝（fail-closed）；边界不可界定或属检测模式集之外 → 维持整段拒绝；替换是纯函数（fingerprint 稳定，增量纯度不受影响）；不新增事件或枚举；**授权门槛不变**（含秘密输入按升险源①计入 ≥ `sensitive`，即强制用户授权）。§10.9 第 22 例与其端到端用例落地，S12 场景文本一字不改。**第 13 条的两处口径由第 14 条修订**（替换作用域 = 值区；检测模式集已扩集），其余不变。**2026-09-24 第三轮再加一处**：凭据类**不再有「不可界定」态**（§2.3c.3 规则 3），故本条的「边界不可界定 → 维持整段拒绝」在**凭据路径上不再触发**；它仍适用于 §2.3b 的其它分类路径（如自由文本按高风险文本限长脱敏后的复扫失败）。
14. **中文凭据检测与全链路脱敏（2026-09-24 裁决，§2.3c；安全边界变更）**：单一真源（一处定义、全部委托点收敛到同一模块；config 的模式键仅追加、内建恒生效）、标签/分隔符/终止符闭集、值区三态判据（不可命中 / 可替换 / 不可界定）、两种处置（出站 fail-closed 整段拒绝、本地落盘最大区间替换且**不得**整段 block）、凭据占位符全链路统一为 `[已脱敏:secret]`、`secret_placeholder` 的 label 必须是规范 ASCII 标签且**不得静默丢弃**；**不新增错误码、不新增事件枚举、不新增类别**；升险源①与授权门槛零变化（含中文命中即强制用户授权）。最小验收 ①preview 无原值且有占位 ②不可界定形态 fail-closed ③普通数字陈述不误伤 ④`/cloud allow` 后五面检索不到原值；§10.11 C1–C12 全部落地；§2.3c.6 的**已知缺口**逐条登记且**未被任何实现偷偷放宽**。**2026-09-24 第二轮修订（安全承诺不得降低）**：删去「条款含 CJK ⇒ 非值区形态」判据（它使 `密码是青山绿水` 原样外发），值区三态改判「是否为空 / 是否 == 占位符字面量 / 是否含内部空白」，**防误伤改由标签闭集承担、不靠值形态**；新增**跨终止符值形态片段回收**（`密码：abc，123` 的 `123` 一并移除）；明确**误伤方向的不对称取舍**（宁过度脱敏、不漏检中文口令，且**禁止**任何形态/语法豁免，否则 `系统密码是…` 会被误豁免）。**「secret 原值永不进入 payload」的承诺由此重新成立**，缺口清单相应从「含 CJK 值判不可命中」改为「中文句式过度脱敏（已知代价，非缺口）」。C12 覆盖上述四点。**2026-09-24 第三轮修订（编码前审查再纠，安全承诺的最后一处漏洞）**：第二轮仍留了一条**形态判据**——「终止符后的片段若不含 CJK 才回收」，于是 `密码 abc123`（裸空格）与 `密码是abc，青山绿水`（CJK 后缀）仍会外发原值；这与「不接受任何形态豁免」自相矛盾。本轮**整体删除**「条款 / 终止符闭集 / 片段回收 / 不可界定」四件套，改为**边界成分（T1 显式分隔符 / T2 空白 / T3 紧邻非 CJK 字符）+ 值区上界 = 行末（值区为空时顺延到下一个非空行）**：值区内**一律不再切分、不再按形态筛选**，「归属不明的后续片段」由此不存在 ⇒ **凭据类「整段拒绝」处置随之删除**（只保留一条与凭据无关的「替换后无任务语义的 section 拒绝」，即 2.3c.4 第 2 条的诚实拒绝）。**唯二的形态相关条件移到标签侧**（拉丁标签的右边界 `tokenizer`；CJK 标签紧随 **CJK 字符**时 T3 不成立、紧随非 CJK 非空白字符时**照常触发** `密码abc123`），判断的是「标签是不是字段名」而非值的形态，且方向是**收窄识别语法**、逐条登记在 §2.3c.6。**登记的新代价**：T2 使「拉丁标签 + 空格 + 中文」的技术句式（`token 过期了`、`api_key 读不到`）被过度脱敏并进强制授权——与 `password 青山绿水` 在字符层面同形、无确定性区分手段，代价方向仍是不对称取舍；**消解方向是提高标签侧选择性，不得回收值形态判据**。三处**语法边界照实登记**（标签与值之间无边界成分的 CJK 粘写、值在标签之前、值跨多行续行），并说明裸密钥检测（无标签形态）作为第二层覆盖其中一部分。§10.11 C1–C13 全部落地。
15. **云端最终答案写回 episode（2026-09-24 裁决，§2.5 与 `06` §2.4）**：云端咨询的最终答案（含 followup 子回合结果与 `_CLOUD_FALLBACK_REPLY` 兜底）与普通回合走**同一条** `_record_turn` 链（episode / recorder / topic 计数 / 项目摘要更新），续接回合**不新增意图解析调用**；episode 的 User 段 = 原回合用户输入，Assistant 段带云端来源标记（固定前缀）；取消/失效/跨会话等控制确认**不**写回（口径见 §10.12 与 `clarifications.md` 2026-09-24 条目）。§10.12 W1–W4 落地。**2026-09-24 第二轮补钉（每任务恰好一条 episode）**：① 产出授权 preview 的回合**不写 episode**（事件判据：本回合有 `phase="authorization_required"`），临时授权提示永不进入记忆/会话摘要/项目摘要；② `/cloud allow` 续接回合因 `main.py:304–306` 提前短路而**不会**自然走到 `_record_turn`，必须在**该路径上显式补一次**（**不得**放进 `_consult_cloud` / `_complete_cloud_consultation` 这两个与同回合直连路径共享的出口，否则直连路径双写）；③ 取消/失效/不匹配/被取代四种终结路径**零 episode**（已登记的代价：这些路径上用户的原始请求文本不入记忆），**不写回**的兜底分支仅限 `_local_task_context is None` 的状态损坏（撤 grant + 清 pending + 返回 fallback + 零 episode + **不新增任何枚举值**，且该分支在现行状态机下不可达、须用定向测试覆盖）。§10.12 W1/W1b/W2/W2b/W3/W4 落地。**2026-09-24 第三轮补钉**：① **冻结快照的载体统一为 `LocalTaskContext`**（此前文档里另有「`PendingCloudAuthorization` 冻结 topic/intent」的旧说法，**作废**——该对象不承担快照职责），并写明**读取时机**：`/cloud allow` 回合必须在进入 `_consult_cloud` **之前**取出快照与 User 段（`main.py:1239` 收尾与 `main.py:1216` 失败两条路径都会把 `_local_task_context` 置空）；② **终结枚举补入「云端挂起追问」**——该回合的回复是一次追问而非答案，同样**零 episode**（把它写成 Assistant 段等于把追问当结论存进记忆），补参回合是独立的一次普通回合、按其自身内容正常写入；③ ~~照实登记一处**未处理的不对称**：同一挂起形态在**直连路径**上仍会把追问文本写成 Assistant 段~~ —— **2026-09-25 作废**：该不对称**不存在**（挂起判据 `main.py:432-435` 对本回合 `task_id` 在两条路径上同等成立；`create_policy_grant` 成功的那条分支不是挂起、写一条 episode 且 Assistant 段是云端答案）。③′ 现口径：**挂起回合零 episode 在两条路径上都成立**（第三轮实现审查，见 `reviews/05-p4-cloud-advisory-review.md` 2026-09-25 节）。
16. **TaskBrief 跨 section 去重与摘要事实身份（2026-09-24 裁决，§2.5 规则 8/9）**：跨 `brief_*` 的 T1/T2/T3 确定性去重（归一化口径唯一、优先级先到先得、**真实 payload** 上生效、无模型参与、无相似度合并）；`brief_facts` 收窄为「用户逐字陈述」因而恒被 T1 去重省略；项目摘要改走 `brief_project_note` 并按 `manual_overrides` 分流确定性前缀（自动 = 本地模型推断、人工 = 用户手写）；`brief_*` 不外发 `project_id`/`session_id`/`task_id`；会话摘要行与逐字片段行前缀可区分；两处摘要提示词按 §2.5 规则 9 收窄。§10.12 W5–W10 落地。

---

## 12. 预期实现清单（供后续工程契约展开）

| 项 | 预期位置 | 说明 |
|---|---|---|
| ConsultationProposal / ContextCandidate | `src/core/schemas.py` | 模型建议数据结构 |
| CloudControlState / ControlPolicy | `src/core/control_policy.py` | 组合裁决、预算/deny/force |
| **凭据检测单一真源（2026-09-24 新增；第三轮改判据集）** | `src/safety/secret_scan.py`（预期落点） | 标签闭集 / 分隔符闭集 / **边界成分 T1–T3** / **值区判据（值区为空 / == 占位符字面量 / 非空）** / 两套替换（`redact_outbound`、`redact_local`）/ `contains_credential`；**全链路唯一模式定义**（§2.3c.1）。**第三轮删除**：终止符闭集、跨终止符片段回收、不可界定态、任何值形态判据。`guarded_executor` 的两个函数降为薄包装，`privacy_policy` / `memory_hygiene` / `rule_only_backend` / `cloud_boundary` 全部委托；`config.sensitive_patterns` 仅追加、内建恒生效 |
| PrivacyPolicy | `src/safety/privacy_policy.py` | 分类、脱敏、占位、准备候选；**含 §2.3b 的含秘密文本就地替换（替换后复扫）**；含 build_package（首轮 package 组装 + grant↔preparation 校验）。**2026-09-24 起不再自带模式定义与替换实现**（委托 §2.3c 单一真源），`_BRIEF_LABELS` 增 `brief_project_note`。**2026-09-24 第三轮**：`prepare()` 另含一条与凭据判据无关的 **section 级诚实拒绝**——替换后剔除占位符/标签/分隔符/空白与标点后**为空**的 section 整段拒绝（§2.3c.4 第 2 条；denied 记固定原因文案，**不新增错误码、不新增事件枚举**） |
| AuthorizationGrant / Manager | `src/safety/authorization.py` | 创建、校验、过期、不可扩大；`create_policy_grant(..., escalation_risk="sensitive")` 的 **fail-closed 前置条件**（非 `"normal"` 拒绝签发并抛 `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"`，§1.3a/§3.2 防线表）；**本身不写审计、也不写 `CloudAuditEvent`**（2026-09-18：误调用的痕迹由调用方发 `cloud_consult phase="denied"` 事件承担，`record_denial` 四值闭集与「恰一条」不变量均不动） |
| CloudRequestPackage / CloudAuditEvent | `src/core/schemas.py` | 已授权 package 与最小审计 |
| PrivacyPreparation / PreparedContextItem | `src/core/schemas.py` | 隐私准备与外发 item 结构（fingerprint 仅本地） |
| TaskBrief | `src/core/schemas.py` | 最小推理任务包：本地构建、逐字段脱敏、固定 label |
| TaskBrief 候选构造与同值去重 | `src/main.py`（`_with_task_brief_candidates`） | `brief_goal ← current_input`；`brief_question` 仅在模型给出非空 `proposed_question` 时生成，与 goal 同值即省略；**不做 `current_input` fallback**（§2.5 规则 7）。不构造 `TaskBrief` 实例再拆解（§2.5 规则 6）。**2026-09-24 扩展（§2.5 规则 8/9）**：跨 `brief_*` 的 T1/T2/T3 确定性去重（唯一归一化口径、固定优先级）；`brief_facts` 收窄为「用户逐字陈述」⇒ 与 goal 同源恒被 T1 省略；项目摘要改由 `brief_project_note` 承载并按 `manual_overrides` 加确定性前缀；值中不得含 `project_id`/`session_id`/`task_id` |
| 云端答案写回 episode（2026-09-24 新增；**第二轮补钉**） | `src/main.py`（`_handle_cloud_authorization` 返回边界）、`LocalTaskContext` | 续接回合的最终回复（含 followup 结果与 `_CLOUD_FALLBACK_REPLY`）必须走同一条 `_record_turn` + `_record_tool_events`；写回**零新增意图解析调用**；episode 的 User 段 = 原回合用户输入（`LocalTaskContext.input_event.text`），Assistant 段带云端来源标记。**第二轮**：① **每任务恰好一条 episode、只在终结时写**——产出授权 preview 的回合（有 `phase="authorization_required"` 事件）**不写**（其四条副作用链均不推进），取消/失效/不匹配/被取代四种终结路径**零** episode；② 补记调用点**必须**在 `/cloud allow` 路径上，**不得**放进 `_consult_cloud` / `_complete_cloud_consultation`（与同回合直连路径共享 ⇒ 会双写）；③ 补记所需快照 = topic + intent（**载体统一为 `LocalTaskContext`**，其声明为「不进入 pending/grant/audit」的**本地**语义容器；原输入与 `project_id` 已在其内；**`PendingCloudAuthorization` 不承担快照职责**）；④ **第三轮**：终结枚举补入**云端挂起追问**（回复是追问、不是答案 ⇒ 同样零 episode）；⑤ **第三轮**：快照须在进入 `_consult_cloud` **之前**读取（`main.py:1239` 与 `main.py:1216` 会把 `_local_task_context` 置空） |
| 单包预算与配置范围 | `src/safety/privacy_policy.py`、`src/safety/authorization.py` | 唯一字节硬边界是整包 `context_byte_budget`（默认 32768，绝对上限 65536，范围 256..65536，§8）；item/byte 两处构造期校验用同一判据 |
| LocalTaskContext | `src/main.py`（App 会话字段） | 仅本地的原任务语义；绝不进入 pending/grant/审计/云端包。**2026-09-17 增补**：另持有本任务**因果风险下界**（准入时被准入候选归一化后的 `risk_draft`，§1.4 规则 8）——它是**下界**，不是最终值 |
| 准入侧的因果风险（下界）传递 | `src/core/control_policy.py`、`src/main.py` | proposal 准入不再读 `risk_draft`；App 从 `CloudAdmissionDecision` / 候选取该值作为**下界**记入 `LocalTaskContext`（最终值在授权时用 `effective_authorization_risk()` 求），**不得**从 `preparation` 或隐私模式反推（§1.3a） |
| 有效授权风险的求值与主防线 | `src/main.py`（`create_policy_grant()` 调用点）、`src/core/risk_vocabulary.py` | 授权时用当时信号求 `effective_authorization_risk(...)`（§1.3a；`12` §3.5 为权威，**恰两个**布尔信号）；非 `normal` 时**不调用** policy grant，直接进 `AWAITING_AUTHORIZATION`；误调用被拒时捕获并发 `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` **事件**（**不写 `CloudAuditEvent`**，§3.2） |
| GrantUsageSnapshot | `src/safety/authorization.py` | validate 返回的只读快照 |
| CloudBoundary | `src/safety/cloud_boundary.py` | 最终独立复核 |
| SideEffectGateway | `src/safety/side_effect_gateway.py` | 唯一出口、消费预算、审计 |
| CloudAdvisoryService / ConsultOutcome | `src/core/cloud_advisory.py` | 同一 grant 内 sub-turn 编排：consult() 返回 ConsultOutcome，新内容请求挂起归 App（§5.3），仅依赖接口 |
| App / bootstrap | `src/main.py` | 用户指令、授权交互、依赖注入 |
| DeepSeek adapter | `src/adapters/deepseek_adapter.py` | 已授权 package 序列化与传输接缝 |
| 配置 / 脚本 / 测试 | `config/`、`scripts/`、`tests/` | §8、§10 |

---

## 13. 后续预留（不在 P4）

- 用户显式外发内容的可视化比较、字段编辑和 GUI 授权体验。
- 更精细的语义隐私分类（PII/企业机密/知识产权）与 L2 检测（P6）。
- 真实 project memory（P5）接入后的最小摘要选择；仍须经 PrivacyPolicy 与 grant。
- provider 选择策略、多 provider 审计与故障切换；provider 改变必须重新授权。（2026-09-13 注：最小底座已由 modules/09-p6c-cloud-provider.md 落地——单活动 provider、profile 白名单、专属凭据、切换重授权；多 provider 协作/故障切换仍在预留。）
- 非执行回流的引用溯源、流式整合和更强的语义防注入。

---

## 14. 重设计记录

| 日期 | 决策 / 审查发现 | 处理 |
|---|---|---|
| 2026-09-02 | 零实体 P4 安全但云端无实际问题内容，无法验证受控云端咨询效用 | 重开 P4：改为分级、授权的上下文外发 |
| 2026-09-02 | 模型若能直接决定求助/外发会越过本地主权 | 引入 ConsultationProposal；模型只建议，ControlPolicy + PrivacyPolicy + 用户 grant 共同裁决 |
| 2026-09-02 | 永久/宽泛授权会导致范围漂移和重复确认困境 | 引入 task/session/provider/purpose/预算/有效期绑定且不可扩大的 AuthorizationGrant |
| 2026-09-02 | 旧 P4 唯一出口、advisory、本地回流和执行确认仍是有效安全边界 | 全部保留；仅重构触发与外发授权语义 |
| 2026-09-02 | 四项实现前阻塞复审：①状态机→§1.4 ②允许表→§2.3a ③消费语义→§3.1/§3.3 ④fingerprint 边界→§4.1，均闭合；补 §10.2 allowlist 测试与 §10.7 状态机测试；清理 project-plan 残留重复块 | 标记 ✅ 待实现，Codex 同步 00-* 工程契约后实现 |
| 2026-09-02 | Codex 复审发现两处阻塞：Boundary 签名拿不到 usage 却要求校验 turn；remaining_context_budget 与「单包硬限制+累计仅审计」矛盾 | §4.2 签名改为 (package, grant, GrantUsageSnapshot)，快照仅由 AuthorizationManager 生成；删除 remaining_context_budget，字节限定钉死为单包硬拒绝（§5.2）；PrivacyPreparation.context_budget_used 改名 prepared_context_bytes |
| 2026-09-03 | 老板决策：P4 从「外部资料咨询」重定位为「受控云端推理升级」——云端价值在推理而非检索；需钉住升级原因、最小任务包、自由文本授权、跨轮扩张限制、确认回合本地语义 | knowledge_gap→escalation_reason（7 值枚举，§1.1）；新增 TaskBrief（§2.5）、LocalTaskContext（§1.5）、label 不可信通道规则（§2.3.8）、任务级扩张上限（§3.3）、followup 类别语义（§5.1）、§10.8 测试；max_context_items 默认 3→8；状态回 📝 起草中，复审后恢复 |
| 2026-09-03 | Codex 复审新契约，3 处补齐：follow-up 缺机器可读协议；section 超 400 字节「截断/拒绝」语义矛盾；重授权计数起点不明 | AdvisoryResult 新增 `requested_context_categories` 白名单（{memory_evidence, user_entity}），归一后为空或本地产不出新内容按最终 advisory 收敛，`followup_question` 降级为仅展示（§5.1/§6.1/§10.8）；section 超限统一为整段拒绝不截断、denied 记固定原因（§2.5/§10.8）；首次 grant 不计数，仅边界扩大型新 grant ≤ 2（§3.3/§10.8）；状态恢复 ✅ 待实现 |
| 2026-09-03 | Codex 复审发现阻塞：① 新内容 followup 的编排归属未定义——consult() 同步循环只能派生同值/子集，无法同时完成「新 grant + 重新确认」；② `followup_question` 允许进「审计摘要」与「不记云端原文」不变量冲突 | 新增 §5.3：consult() 只编排同一 grant 同值/子集，遇合法新类别请求返回 `ConsultOutcome(suspended)`；App 为唯一编排者（policy grant 同回合自动续 / user 确认续），pending 增 `requested_categories` + 续咨询标记、preview 展示旧+新全量；新 grant 签发即吊销旧 grant（§1.4 规则 7：同 task 单活跃 grant）；新包 turn=1，跨 grant 由任务台账约束；拒绝/超时/deny_cloud → revoke + 终止，轮数不退；§1.4 状态机增续咨询迁移；审计只记归一化类别 + `has_followup`，不记 `followup_question` 原文（§4.3/§6.1/§10.8） |
| 2026-09-06 | 返工审查（specs/reviews/05-p4-cloud-advisory-review.md）：5 必改——①云端链路在 handle() 错误边界外 ②§5.3 App 编排未实现（suspended 死路）③boundary 残留 v1 label 黑名单 ④label 缺敏感模式扫描 ⑤max_context_items 默认 3≠8；另有 7 建议 + 7 备案 | Codex 确认续咨询在 P4 实现不降级（维持 §5.3，不改契约降低目标）；4 处措辞已同步（§1.4 task_id 时点、§4.1 覆盖校验拒绝、§1.5 LocalTaskContext 实现形态、§2.3.5 占位降级为可选）；按审查清单修复后复审 |
| 2026-09-06 | Codex 指出状态机矛盾：suspended(result=None) 与「产不出新内容按最终 advisory 收敛」并存时无 advisory 可收敛；复核发现同 grant turn+1 续轮不可达（云端按轮无状态，重发同值/子集只会重复追问，属有害循环）——收回审查清单中「派生 turn+1 包」的提议 | 四项裁决钉死：① `ConsultOutcome.suspended` 携带已过检**部分 advisory**（§5.3 规则 1）；② 收敛统一规则（§5.3 规则 6）：产不出新内容/扩张或轮数超限/后续轮失败/重 prepare 超包限 → 一律以最近在手 advisory 走 §6.2，用户否决与首轮失败才走无云端建议降级；③ 删除同 grant turn+1 续轮（§1.4/§3.3/§4.1/§5.1/§6.1 同步），续咨询只有「扩张新 grant turn=1」与「收敛」两态；④ followup 候选来源钉死（§5.3 规则 7）：memory_evidence→brief_evidence 附加 item、user_entity→local_task_context+允许表 label，PrivacyPolicy local-source 白名单放宽为 brief_* ∪ 允许表（审查必改 #6） |
| 2026-09-08 | Codex 发现 convenient 自动续与 `create_policy_grant` 全包纯实体判定冲突：TaskBrief 恒含 free_text → 自动续不可达；复核确认首轮自动签发分支同样不可达（`_with_task_brief_candidates` 恒注入 brief_goal，返工审查漏判，已补记） | 裁决采用**已确认内容继承（增量纯度）**：纯度判定改为「新增候选（fingerprint ∉ 任务台账 payload_fingerprints）全为 allowlisted user_entity」，已确认继承候选可随包重发；继承权威为任务台账而非旧 grant 有效性（新 grant 签发即吊销旧 grant，以旧 grant 有效性为条件会与吊销语义纠缠）；不变量：policy_grant 只能向台账新增 entity fingerprint，free_text 只能经用户确认进入台账（同 fingerprint 必同内容，HMAC 四元组）；新增候选为空 → 不签发、按 §5.3 规则 6 收敛；首轮行为不变（台账空 → 全实体才自动），P4 convenient 语义 = 首轮恒确认 + 纯实体增量自动续；§2.4/§3.2/§5.3/§10.2/§10.8 同步，无签名变更，00-adapter-factory docstring 由 Codex 同步 |
| 2026-09-08 | P4 完成验收复审（specs/reviews/05-p4-cloud-advisory-review.md 复审章节）：214 passed / ruff 通过；上轮 6 必改全部落实（错误边界、§5.3 编排、boundary 黑名单、label 敏感扫描、默认 8、local source 白名单），增量纯度四象限测试齐全 | **基本通过——仅 1 项轻量必改 R1**：`_followup_candidates` 的 user_entity 候选缺 `source="local_task_context"`（§5.3 规则 7 偏差，无安全后果——仍受允许表 (label,value) 精确匹配约束）；遗留建议 6 项（取消审计、失败路径吊销、死代码簇、`>`/`>=` 一致性、超限错误码、台账卫生）+ 测试缺口 2 项；R1 修复后 05 标 ✔️ 完成 |
| 2026-09-08 | Codex 指出审查建议 1 的「App 直写 gateway.audit_log」绕过唯一副作用出口的接口边界（出口是 `CloudTurnGateway` 接口而非 list 对象），要求先补契约再实现 | 收回原建议；§4.3 新增**无轮次拒绝审计专用入口** `record_denial(task_id, session_id, reason)`：reason 四值枚举（user_cancelled / authorization_expired / session_mismatch / superseded_by_new_input），枚举外 fail-closed `SAFETY_CLOUD_BLOCK`；事件操作字段全零、不含任何原文；App 唯一调用方，每条清理路径恰一条，与 `revoke_task` 并行；命名对齐 `GuardedToolExecutor.record_denial` 先例。§1.4 规则 5 / §10.4 / §10.8 同步。接口签名变更 Claude 主导，Codex 镜像 00-core-interfaces Protocol 与 00-adapter-factory，测试替身同步实现 |
| 2026-09-08 | 终验（复审落地清单第二次确认）：R1 代码修复 ✓（`_followup_candidates` 三处构造均显式带 source）；record_denial 全链 ✓（Protocol + 实现逐字段全零事件 + App 四路径 reason 映射 + 四路径「恰一条」断言 + 替身实现 + usage 不变断言 + 00-* 三份镜像）；Codex 顺带完成失败路径吊销（遗留建议 2）与死代码清理（cloud_intent_types / _build_cloud_package / 死测试文件删除，遗留建议 3 大部分） | **P4 ✔️ 完成**（219 passed / ruff 通过）。残留收尾微项 2 个（不阻塞，随下轮工作）：① R1 的 source 断言未补——entity 路径回退为 3 参构造时无测试会失败，补一行断言；② `_clear_cloud_task(reason: str \| None = None)` 默认值保留「静默跳过审计」潜在路径（当前 4 个调用点均显式传 reason），建议收紧为必填参数。adapter 死配置/永假自检、`>`/`>=`、超限错误码、台账卫生继续记录 |
| 2026-09-13 | P6c 多云 Provider 最小底座（boss 指示）：GLM Key 配入通用变量被发往 DeepSeek 得 401 且误报「暂不可用」——暴露凭据错配不可防、错误分类不可辨 | 新增 modules/09-p6c-cloud-provider.md：§7 的 DeepSeekAdvisoryBackend 由通用 OpenAICompatibleAdvisoryBackend + profile 取代；§8 配置形态更新（provider/connection/policy + 迁移）；§9 传输类错误细分四码并收窄 CLOUD_UNAVAILABLE。安全骨架（§0.3/§3/§4/§6）、grant 绑定 provider（§3.4）、唯一出口（§4.3）全部不变；`PrivacyPolicy` 构造新增可选 allowed_scope（修正死配置，见 09 §5.1/§12） |
| 2026-09-14 | 云端准入拆分（boss 批准，Codex 提出——真实 P6b 运行 S06/S08：qwen3:4b 把信息充分的开放式分析题连续判 PARTIAL/VAGUE + missing_info，旧 §1.3 否决集把「信息不完整」列为云端否决项，`RETRIEVE_MORE` 永远拦在云端之前，云端零参与；`is_effectively_ready` 的本地完整度判断锁死了「强模型补足小模型」的核心价值） | §1.3 重写为**双判定**：本地就绪（`is_effectively_ready` 语义不变，继续服务本地计划/执行）与云端咨询准入（独立确定语义）分离；否决集移除「信息不完整」，改为不可绕过条件（deny/dangerous/非 normal 风险/真实工具执行态/禁用不可用/预算冷却/空任务），`CloudControlState` 新增 `has_task_text`（App 确定性设置，空任务不升级）；准入两路径——force（绕过全部模型侧判断，含 VAGUE/PARTIAL + missing_info）与 proposal（有效 READY 既有行为 + 新增 PARTIAL/ALMOST 且 intent 非 unknown）；纯 VAGUE/unknown 无 force 不自动升级。§2.5 新增 `brief_unknowns`：模型 missing_info 前 3 条逐条成 item（local_task_context/free_text/逐条限长脱敏，不合并防整段丢失），使云端可给条件化分析或经既有 §6.1 followup 受限追问。§10.1/§10.9/§11 第 8 项同步；S06/S08 原始任务文本不变，评估侧回归要求钉入 08 §2.5。无既有接口签名变更（`CloudControlState` 仅增带默认值字段，`decide()`/`prepare()` 签名不变） |
| 2026-09-14 | Codex 实现前审查二轮（3 处实现前应修 + 测试建议，全部采纳）：① `has_task_text` 默认 True 是 fail-open——遗漏字段的调用方会把空任务误判为有任务；② 否决集把 `suggested_tools`（模型输出）当 force 不可绕过项——小模型误建议一个工具即可再次锁死 `/cloud ask`，与本次要修的 missing_info 锁同类；③ 预算注释算错——`brief_unknowns` 是 1 个 label 最多 3 个 item，最坏 6+3=9 个 item 超过默认 8，合法任务包会被 PrivacyPolicy 整包拒绝 | ① 默认改 `False`（fail-closed：宁可本地追问不误发空任务），P4 主链路显式传值，既有离线调用（cloud_enabled=False）不受影响；② 否决集第 4 项改为**真实工具执行态**（`task_has_sensitive_execution_chain`，App 确定性状态；待确认计划被新输入取代规则处理，不存在并存否决态），force 路径忽略模型工具建议（咨询回合零副作用 + 回流仍强制确认），proposal 自动路径保留 `suggested_tools` 为空的保守条件——「自动升级尊重建议、用户指令不被建议锁死」；③ `max_context_items` 默认 8→12，字节上限 2048 不变（仍是真实暴露约束，item 上限只是记账）；②的矩阵对照例：第 6 例（force+tools→升级）vs 第 11 例（自动+tools→不升级）。测试建议采纳：`TaskBrief.unknowns` 钉为 `tuple[str, ...] = ()`（逐条语义 + 与既有 6 参位置构造兼容）；§10.9 端到端补 VAGUE + proposal=None 的 App 级完整链路。实施侧同步清单（Codex 属地）：`00-adapter-factory.md` 两处 8→12、四份 TOML `max_context_items = 8 → 12` |
| 2026-09-14 | 实现后审查三轮（Claude 审查 Codex 实现，6 条结论全部收口） | ① **敏感执行链字段不改代码**（Codex）：新输入先取消待确认计划，与新一轮云端咨询不并存；捕获取消前 pending 状态并传 `True` 反而会错误拦截用户显式 `/cloud ask`——已把「主链路恒 `False`、防御性保留」写进 §1.3 否决项 4；② **预算/冷却采纳契约降级**：保证范围明确为「单次云咨询任务及其续咨询 sub-turn」，不保证普通对话轮次之间共享（每轮新 `task_id`）——§1.3 否决项 6 与 §1.2 措辞同步；③ **`provider_available` 保持等于 `cloud_enabled`**：启用态 bootstrap 已校验 provider/模型/凭据，能启动即静态可用；真实网络故障只能在调用时判断，提前探测会产生一次未经授权的云端请求，不宜进决策阶段——理由写进 §1.3 否决项 5；④ **`_task_ledgers` 无界增长记录遗留，不删台账**：`revoke_task()` 后删台账会让相同 `task_id` 重入时重置已消费预算，破坏「不退款」约束；需先钉死台账生命周期语义再设计有界终态台账；⑤ **TaskBrief 映射说明**：§2.5 新增规则 6——`TaskBrief` 是概念结构，真实外发由 App 映射为 `brief_*` context item，实现侧不构造实例再拆解，且不得存在「有字段无映射」的悬空项；⑥ `[:3]` 字面量已提为 `_BRIEF_UNKNOWN_LIMIT = 3`（Codex 已修），§2.5 规则 5 同步注明。验证：`404 passed` |
| 2026-09-14 | **遗留项（不在本轮范围，需单独设计后再入约）** | ① **会话级/用户级云端限流**（跨轮预算、跨轮冷却）——本轮只保证单任务预算，不得暗中加入；② **有界终态台账 / 会话结束清理**——依赖台账生命周期语义先钉死（「不退款」约束不可破坏）；③ **`provider_available` 的真实可用性探测**——若未来要做，必须走“不产生未授权出站”的设计（如复用既有 provider 健康检查而非新增探测请求）并经接口审查；④ 上述三项均为**新需求**，须经 boss 决策后另立条目，本轮契约不承诺 |
| 2026-09-16 | **二轮（Codex 实现前审查，2 处实现阻塞）**：① 缺失/畸形值归一化为 `normal` 与「schema 不被保证」自相矛盾（fail-open）；② §10.9 把原始模型字符串直接喂给策略层，违反「解析层唯一归一化」 | **全部采纳**：① 缺失/空/非字符串/未识别统一 fail-closed 到 `sensitive`（`resolution` 相应改为 `absent` / `unrecognized`，见 `12-risk-draft-closed-set.md` §2.2）；② §10.9 加「层次纪律」（本矩阵只喂闭集值）+ 第 9/16 例改用闭集值，原始措辞覆盖移交 `12-risk-draft-closed-set.md` §4.1/§4.2 的归一化层与集成层。**一处偏离 Codex 提议**：(2) 建议「闭集外一律按 `sensitive`」会弱化现状（`_is_dangerous` 今日已识别 `"DANGEROUS"`），故策略层对危险方向保留写法宽容（`"DANGEROUS"`/`" dangerous "` 仍 `REFUSE`），其余闭集外值按 `sensitive`（`12-risk-draft-closed-set.md` §2.1.1） |
| 2026-09-16 | `risk_draft` 未闭集导致 force 上云被随机拦截（Codex 提出）：S06/S08/S10/S13 的 `/cloud ask` 统一被判 `cloud_gate_outcome="vetoed"` + `proposal_denied_reason="non_normal_risk"`，而同一指令历史 run 可正常产生 `admitted_forced → REQUEST_CLOUD`；`_INTENT_RESPONSE_SCHEMA.risk_draft` 只声明 `string`、解析器接受任意字符串，模型实际输出过 `low`/`medium`/`high` | 出 `12-risk-draft-closed-set.md`：**R1** 值域钉死闭集 `{normal, sensitive, dangerous}` + 解析层唯一归一化（旧词表 `low→normal`/`medium→sensitive`/`high→sensitive`，非空未识别 **fail-closed 到 `sensitive`**）；**R2** `risk_draft` 移出 force 不可绕过否决集（改为**仅 proposal 路径**的保守条件，与 `suggested_tools` 同一非对称处理）——该字段是模型自由输出、模型总能说 normal，不构成安全边界，留在 force 内只贡献随机性；**R3** `dangerous → REFUSE` 保留。§1.3 否决集增「适用路径」列（否决项 3 标 `仅 proposal`）、§10.1/§10.9（第 9 例翻转 + 新增第 16 例 + 子矩阵指针 + force 轮不得出现 `non_normal_risk`）/§11 第 8 项修订 + 新增第 9 项同步；08 §2.6 增同名硬性结构项。`high → sensitive`（不采纳 `high/critical → dangerous`：触发本次 bug 的取值只能是 `medium`/`high`，而它们出现在开放式分析题上，硬拒绝会让四个待修场景变成确定性失败）+ 未识别值 → `sensitive`（不采纳 `→ dangerous`：解析失败不得捏造「危险」断言，与解析层「降到最不承诺档」的既有惯例相反） |
| 2026-09-17 | **TaskBrief `brief_*` 独立 400 字节上限取消，整包 `context_byte_budget` 成为唯一字节硬边界（S07 长上下文协同，老板裁决）**：S07 任务文本约 225 个中文字符被 App 同时映射为 `brief_goal` 与 `brief_question`，两段各自超 400 字节被 `PrivacyPolicy` 整段拒绝 → `no_safe_context` → `cloud_assisted` 结构性不可达（详见 `clarifications.md` 同日已解决条目） | ① 删除 §2.5 规则 3 的「单 section ≤ 400 UTF-8 字节——超过即整段拒绝」与 `section_too_long` 语义（§2.2/§2.3.5/§2.5.3/§2.5.5/§5.3.7/§10.8/§10.9 同步），唯一字节硬边界改为整包 `context_byte_budget`，事后超限整包 fail-closed、绝不截断；② **隐私扫描一条不减**（敏感值/裸密钥/连接串/来源/类别逐项照旧），取消的只是长度维度；③ **模型提出的 free_text 仍限 1,500 字节**（措辞由「字符」改为「字节」与既有实现对齐，无行为变更）；④ 新增 §2.5 规则 7 **确定性同值去重**：`brief_goal ← current_input`、`brief_question` 仅来自非空 `proposed_question`（删除 `current_input` fallback）、两者 `strip()` 后同值即省略，只做逐字符同值去重、不做语义去重；⑤ 默认 `context_byte_budget` 2048 → **32768**（本条先定为 8192，同日二次裁决**上调为 32768、绝对上限 65536，8192 作废**，见下一行），并首次**钉死配置合法范围**：`max_context_items ∈ [1,100]`、`context_byte_budget ∈ [256,65536]`，构造期非法值 `CONFIG_ERROR`，两处校验用同一判据（原 `PrivacyPolicy` 只校验 `>= 1`，无上界）；⑥ 新增 §10.10 验收矩阵 A1–A8 + 配置范围用例 + **附带修正**（`brief_evidence`/逐条 `brief_unknowns` 与 section 共用同一 400 字节分支，>400 字节的记忆片段过去被静默整条丢弃）；⑦ project-plan/四份 TOML/08 §2.3 S07 行同步，S07 场景文本不得为迁就限制而改写 |
| 2026-09-17 | **默认整包预算由 8192 上调为 32768，绝对上限 65536，并钉死「超预算不做三件事」（老板二次裁决，Codex 经 `clarifications.md` 转达）**：8192 是 Claude 与 Codex 商定的中间值，仍偏向保守起步；老板要求按真实长上下文规模定默认，并把「预算不足时怎么办」的可选空间一次关闭，避免实现层各自发挥 | ① 默认 `context_byte_budget = 32768`，**绝对上限 65536**（合法范围仍 `[256, 65536]`，上界即绝对硬上限），**8192 作废**，§8 样例 / §2.5 规则 3 / §5.2 / §10.10 / §11 第 10 项 / §12 / project-plan / 09 §5.1 同步；② **不做字段优先级截取**——不得按 label 优先级丢弃次要 section 凑预算；③ **不做动态扩容 grant**——不得为本包放宽已签发 grant 边界或改写预算；④ **不做二次长度确认**——不得追问「是否同意发送更大的包」；用户外发确认的唯一入口仍是既有 `/cloud ask` + 完整授权 preview，超预算一律整包 fail-closed；⑤ 隐私扫描、来源校验、指纹/preview/payload 一致性**完全不变**（本次只动默认值与处置口径）；⑥ §10.10 补 A5 的负向观测（超预算轮不得产生 `authorization_required`/`authorized`/`outbound` 事件、不得创建 pending、不得新增确认交互）。实施侧同步清单（Codex 属地）：`00-adapter-factory.md` 两处默认值 + 配置样例、四份 TOML、bootstrap 两处默认值、`privacy_policy`/`authorization` 范围校验、边界测试（32768 内通过 / 32769 起整包拒绝 / 65536 上界） |
| 2026-09-17 | **「超轮次不走云端」删除，`ControlPolicy.decide()` 与 `evaluate_cloud_admission()` 去掉轮次参数**（`14-resolution-exhausted.md` §0.1/§5，S03 round1 真实 run `7707d503adc5` 触发） | 原 §1.3 第 2 步（`round_count > max_resolution_rounds` → `ASK_USER`）**不可达**（`intent_max_rounds` 校验 `1..4`，判据 `> 4`）、**位置错**（调度规则放进准入门 → 天然位于放行分支之前、无 force 豁免，与本次 R2 的非对称原则及 `11 §3.1` 第 2 步冲突）、**归因污染**（把「规则说不」记成 `not_evaluated`）。删除后：轮次事实改由 `resolution_exhausted`（Resolver 记录、App 转发、`decide()` 第 4 步 `ASK_USER`）承担；`not_evaluated` 收窄为两源；`decide()` 的 `round_count` 与 `_MAX_RESOLUTION_ROUNDS` 一并删除。**行为变更照实声明**：proposal 路径在轮次用尽时**不再**被否决（P6d 的目标即「本地卡住时由强模型补足」；「无望任务不花预算」由既有 5 项资格条件承接） |
| 2026-09-17 | **`risk_draft` 判定对象未钉死 + `sensitive` 提案被一律否决，两条自主升级臂全灭（S09 `base` 3/3、S06 `cloud_auto` 3/3 `risk_draft=sensitive` → `vetoed` + `non_normal_risk`，实际准入 0/3，目标 ≥2/3；老板裁决 A/B，Codex 经 `clarifications.md` 转达）** | **① 判定对象（裁决 A）**：`risk_draft` 判**本回合实际请求的动作**——只读分析/排查建议/架构权衡/迁移规划/回滚设计默认 `normal`，即使话题涉及生产、切流、数据库、部署或高影响系统；`sensitive` 的充分条件只有两个（本回合实际含敏感数据 / 本回合实际请求需确认的副作用）；`dangerous` 时不得建议上云。落 `12` §1.2.1/§1.3 第 6–8 条。**② `sensitive` 提案准入与强制授权（裁决 B）**：新增 **§1.3a**（准入后按因果风险分流；`sensitive` 在所有模式含 `convenient` 下必经 `AWAITING_AUTHORIZATION`，只认显式 `/cloud allow` 的用户 grant，不得 policy grant / 不得复用旧授权；授权后既有检查一条不减、preview/grant/payload 逐项一致、秘密原值不入任何落点）、**§1.3 否决项 3 删除**（`non_normal_risk` 全域不可达，枚举值保留为不可达项）、**§1.4 规则 8 + 状态机两处**（`policy_grant 可签发` 与 `同回合自动续` 均加「因果风险为 `normal`」条件）、**§3.2**（`create_policy_grant` 新增关键字参数 `escalation_risk: str = "sensitive"`，fail-closed 默认值；`create_user_grant` 签名不改）、**§5.3 规则 2/4**、**§10.9 第 16 例翻转 + 新增 17–19 例 + 端到端 `sensitive` 授权链两例**、**§11 第 9 项改口径 + 新增第 11 项**、**§12 落点三行**。**§10.9 第 9/12/13/14/15/18 例不变**（`risk_draft` 与这些路径无关）；S06/S09 场景文本**一字不改**，`expected_benefit` 阈值**不调**。同步：`10` §4.3/§7.1/§7.3/§7.4、`08` §2.5 第 6 条/§2.6、`project-plan` 决策表。落地后须重跑 S05 `0/3`、S09 `≥2/3`、S06 `cloud_auto` `≥2/3`、S11 `0/3` |
| 2026-09-17 | **Codex 复审提出四处缺口（三处影响实现）**：① 授权形态若只取自被准入候选的 `risk_draft`，则「确定性接线」只是**确定性地传递模型结论**——模型把真实敏感任务误判为 `normal` 时续咨询仍可能拿到 policy grant，与「模型输出不是安全边界」冲突；② 「文件写入」被列为 `sensitive` 充分条件，与 `07 §6.1`「`file.write` 新建基线 `normal`、覆盖才由 preflight 升险」（**该前提已于 2026-09-20 被 P7a-0 反转**：写操作基线统一 `sensitive`）直接冲突，S14 必然红；③ 「含敏感数据可进入脱敏授权预览」不完整——`free_text` 含可替换秘密仍整段拒绝 → `no_safe_context`，S12 结构性不可达；④ policy grant 防御性拒绝的**错误与审计行为未定义**（没给原因码，`AuthorizationManager` 也没有审计依赖） | **① 有效授权风险（§1.3a）**：`max(模型下界, 确定性升险)`，确定性信号**只能升险**、信号缺失即 `sensitive`；求值移到**授权时**，新增纯函数 `effective_authorization_risk()`（`12` §3.5 为权威，验收见 `12` §4.2.5 E 组）。**② 意图层风险限定（§1.3a 引用 `12` §1.2 表注）**：工作区内**新建**文件 = `normal`（**2026-09-20 追注（P7a-0）**：该结论不变——`risk_draft` 判的是请求语义；但**工具层**的写操作基线已反转为 `sensitive`、新建同样进确认链，两层互不推导，`12` §1.2 表注/§9 末行）；**覆盖/越界**由确定性 preflight 只升不降——本字段**不复制工具的动态风险**，S14「新建无需确认」不再冲突（**该句的「无需确认」已于 2026-09-20 反转**：新建现在同样确认，但**本行结论仍成立**——`risk_draft` 的「新建 = `normal`」与工具层是否确认是两层，反转改变的是后者）。**③ 含秘密文本就地替换（新增 §2.3b）**：可替换秘密就地替换为 `[已脱敏:secret]` + 另产 `secret_placeholder`，section 不再整段拒绝（取代 2026-09-06 的降级裁定）；替换后复扫、越界即整段拒绝；纯函数语义（fingerprint 稳定）；**授权门槛不变**（含秘密输入计入升险源① → ≥ `sensitive` → 强制用户授权）。**④ 防御性拒绝契约（§3.2 防线表）**：主防线在 App（非 `normal` 时根本不调用 policy grant）；冗余防线复用**既有** `CLOUD_AUTHORIZATION_REQUIRED` + `details.reason="sensitive_policy_grant_forbidden"` + `recoverable=False`，**不消耗** grant/预算/轮次/pending，`AuthorizationManager` **不写审计**（错误码表无需新增）。**§10.9 新增第 20–22 例 + 三条端到端用例**；§11 第 8 项例数 19→**22**、新增第 12/13 项；§12 四处落点同步；S12/S14 场景文本**一字不改**，阈值**不调** |
| 2026-09-18 | **Codex 复审（上轮四处补钉后）提出两处阻塞**：① 有效授权风险的第 3 个信号（`high_impact` / preflight）在云端链路**不可求值**——policy grant 发生在续咨询阶段，通常既无 `ExecutionPlan` 也未跑 preflight；照「未求值即 `sensitive`」严格实现会让该信号恒判 `sensitive`，`normal + convenient` 自动续再次不可达，硬传 `False` 又违反「不得降险」。② **新的审计原因过不了既有审计接口**——`record_denial()` 的 `reason` 是固定四值闭集，传入 `sensitive_policy_grant_forbidden` 会被 `SAFETY_CLOUD_BLOCK` 拒绝，§10.9 第 19 例与 E7 无法实现 | **① 参数收窄（§1.3a 第 2/6 点，权威见 `12` §3.5 表后注）**：`effective_authorization_risk()` 删去 `high_impact_or_preflight_raised`，**恰两个**布尔信号（payload 候选分类 / 敏感执行链）；工具计划与 preflight 是**正交链路**，由 `07` §6.3 与 `13` §2 独立承担且只升不降，真实敏感执行链本就是准入硬否决，故无缺口；**不采纳** `deterministic_risk: str | None`（那只是给不可求值的信号换类型名，反把工具计划拖进云端链路）。E3 增**参数名反向断言**。**② 正例补齐**：新增 §10.9 第 23 例（模型下界 `normal` + 两信号均 `False` → 返回 `normal` **且必须真的签出** policy grant 并同回合自动续）——只锁升险方向的矩阵会让「恒判 `sensitive`」的实现全绿。**③ 审计出口改道（§3.2）**：误调用的痕迹由 App 发**既有** `cloud_consult phase="denied"` + `denied_reason="sensitive_policy_grant_forbidden"` **事件**承担（`07` §2.2 的 `denied_reason` 新增该本地否决类取值，与 P6c 扩展同做法）；**不写 `CloudAuditEvent`**——`record_denial()` 的四值闭集与「每条清理路径**恰一条** / 终止语义」两条不变量都只适用于**任务终止**路径，而误调用之后任务还要进授权等待、还可能走通。**错误码表、`record_denial` 四值枚举、`CloudAuditEvent` reason 闭集零改动**；验收例数 22 → **23** |
| 2026-09-18 | **工具编排加固联动（`15-tool-orchestration-hardening.md`）**：本契约有三处以 `suggested_tools` 作为判定输入——§1.3 的 force 绕过清单、§1.3a 的 proposal 资格条件、§11 验收矩阵第 6/10/11 例。该字段是任意字符串数组、不受 `list_tools()` 约束，正是 S14 四连失败的根因之一 | **判定源更换**：三处一律改读 `candidate.tool_intent`（结构化草案的声明，`15` §2.4）；`suggested_tools` 降级为纯观测字段，不再是任何判定的输入。观测面对应值 `proposal_gate_result.suggested_tools_present` 改名 **`local_action_proposed`**（权威在 `10 §4.3`）。**语义与例号一格不动**——第 6 例仍是「force 忽略模型建议」、第 11 例仍是「自动路径尊重模型建议」，变的只有判定字段。准入集、授权形态、三级否决集、`effective_authorization_risk()` 的两信号参数表**零改动** |
| 2026-09-20 | **能力终端性失败早裁接入准入函数（P7a，`16-p7-practical-tools-capability-routing.md` §3.8 ①/§6.6）**：老板真实试用暴露「本地没有这个能力时，系统既不说没有、也照样把问题送去云端换回一段编造的实时数据」 | ① `evaluate_cloud_admission()` 内新增**第二个早裁**：`not_evaluated` 来源由 2 扩为 3（新增来源③）；② 该早裁 `force_cloud` 不覆盖（用户显式 `/cloud ask` 是最高指令，与第 2 步护栏的非对称逐字一致）；③ `decide()` 的 `not_evaluated` 分支**必须按来源分流**——否则能力失败会落成 `REFUSE` + 理由句「草案被标记为危险」（起草期自审发现的缺陷）；④ 本契约 §1.3 第 1/3 步与「两种来源」表述同步修订。准入集、授权形态、三级否决集、`effective_authorization_risk()` 参数表**零改动**；`risk_draft` 早裁（来源①）的判定与动作**逐字不变** |
| 2026-09-24 | **中文自然语言凭据检测漏检（安全阻塞，老板裁决，Codex 经 `clarifications.md` 提交复现）** —— ⚠️**本行的 ④ 值区判据与 §2.3c.6 缺口第 2/3 条已被下一行（同日第二轮）修订作废，实现请以第二轮为准**：输入 `我的账号密码是123456` 时授权 preview 的 `brief_goal` **原样携带 `123456`**，`contains_sensitive_value(...)` / `contains_bare_secret(...)` 实测均为 `False`、`_redact_replaceable_secrets(...)` 零替换；根因是「同一判据四份实现 + 全部锚定英文赋值式」，且 `config.sensitive_patterns` **只被 L1 读取**、脱敏链路不读它 ⇒ 配置无法补偿 | 新增 **§2.3c**（安全边界变更）：① **单一真源** `secret_scan` + 完整委托表（`guarded_executor` 降为薄包装、`privacy_policy`/`memory_hygiene`/`rule_only_backend`/`cloud_boundary` 全部委托，config 模式键**仅追加、内建恒生效**）；② 标签闭集 + 规范 ASCII 标签映射（英文取原值小写 ⇒ 既有 fingerprint 不漂移；中文映射，**不得静默丢弃占位符**，兜底 `credential` 且闭集全覆盖为测试不变式）；③ 分隔符闭集（含全角 `：`/`＝`，裸空格不是分隔符）与终止符闭集（半角 `.`/`:` 不是终止符）；④ **值区三态判据**：不可命中（无标签 / 条款含 CJK，含全角数字字母属值区形态）/ 可替换（无内部空白 ⇒ 替换整个值区）/ **不可界定**（含内部空白）；⑤ 两种处置——出站 `redact_outbound` 对不可界定命中**不做替换** ⇒ 既有规则 4 复扫自然命中 ⇒ 整段拒绝（**不新增错误码/枚举**）；本地 `redact_local` 把最大可疑区间整体替换（**不得**整段 `[已脱敏:block]`）；⑥ 占位符全链路统一 `[已脱敏:secret]`，替换作用域 = 值区（字段名保留）；⑦ §2.3b 规则 1/2/5 与残留风险段同步改写；⑧ 新增 §10.11 C1–C11、§11 第 14 项、§12 两行落点。**§2.3c.6 五个已知缺口逐条登记**（裸空格、含 CJK 的值、跨终止符延续、`账号` 类标识符、PII 不在范围）。升险源①、授权形态、三级否决集、`effective_authorization_risk()` 参数表**零改动** |
| 2026-09-24 | **通用云端链路三处缺陷（老板裁决，Codex 经 `clarifications.md` 提交）**：① `/cloud allow` 续接回合在 `_handle_request` 前段提前返回 ⇒ **绕过 `_record_turn`**（episode / recorder / topic 计数 / 项目摘要更新全不执行）⇒ 云端结论不入任何记忆，下一轮短追问找不回；② `brief_goal`/`brief_facts`/`brief_evidence` 之间**跨 section 重复**（外发上下文膨胀、preview 审阅困难）；③ 自动生成的项目摘要把用户事实**加强**（「没有明显故障」→「验证无故障」）后经 `brief_facts` 以**事实身份**外发 | ① **统一出口（§2.5 与 `06` §2.4）**：续接回合的最终回复（含 followup 子回合结果与 `_CLOUD_FALLBACK_REPLY` 兜底）与普通回合走**同一条** `_record_turn` + `_record_tool_events`；`PendingCloudAuthorization` **冻结本回合 `topic_label`/`intent_type`**（原输入与 `project_id` 已在 `LocalTaskContext`）⇒ 写回**零新增意图解析调用**；episode 的 User 段 = **原回合用户输入**（非 `/cloud allow`），Assistant 段带云端来源标记；取消/失效/跨会话短确认**不写回**（不含云端产出，与既有口径一致，照实登记为排除项）。② **§2.5 规则 8 跨 section 确定性去重**：固定优先级（goal → question → facts → project_note → evidence → attempts → unknowns）、唯一归一化口径（NFC + strip + 空白折叠，不折叠大小写）、T1 整段同值 / T2 行级同值 / T3 行级被包含（**吸收源仅限 goal 与 question**），落点在 `_with_task_brief_candidates`、`prepare()` 之前 ⇒ **真实 payload** 上生效；空 section 不生成候选（**既有实现已如此**，本条写成契约）；不做语义/相似度合并、不做模型改写。③ **§2.5 规则 9 事实权威与来源标记**：用户逐字陈述是唯一事实权威；`brief_facts` 收窄为「用户逐字陈述」⇒ 与 goal 同源恒被 T1 省略（**生产路径不再出现**）；项目摘要改由**新 label `brief_project_note`** 承载，前缀按 `manual_overrides` 分流（自动 = 本地模型推断、人工 = 用户手写），前缀为本地固定字面量且幂等；`brief_*` 不得外发 `project_id`/`session_id`/`task_id`（取消 `json.dumps(project_state)` 整体外发）；会话摘要行与逐字片段行前缀必须可区分；两处摘要提示词按固定文本收窄。同步：新增 §10.12 W1–W10、§11 第 15/16 项、§12 两行落点；`TaskBrief` 增字段 `project_note: str = ""`（带默认值，位置构造兼容），`_BRIEF_LABELS` 增 `brief_project_note`。**不做**：CLI 交互、演示机制、固定项目路由、记忆 supersedes（老板明确排除） |
| 2026-09-24 | **第二轮（Codex 编码前审查，4 处，全部采信）——本轮是上两行的修订，不是新增范围** —— ⚠️**本行 ①（值区三态判据、§2.3c.3 规则 4/5 的片段回收、§2.3c.6 第 1–3 行、§10.11 C2/C3/C4/C12 中依赖「回收 / 不可界定」的期望）已被下一行（同日第三轮）整体修订作废，实现请以第三轮为准；②③④ 三处仍有效**。**① 高｜安全承诺与「已知缺口」矛盾**：上上行的值区判据把「条款含 CJK」直接判为**不可命中**，于是 `密码是青山绿水` **原样外发**、`密码：abc，123` 只脱敏 `abc` 而残留 `123`——这与「secret 原值永不进入 payload」和五面零残留直接冲突，**不能登记为以后观察**。**② 高｜`TaskBrief` 定义内部矛盾**：上行的第 3 条要求加 `project_note: str = ""`，但 §2.5 的 dataclass **没有**该字段；同时 `known_facts` 注释仍写「结构化已知事实」、规则 1 仍允许配置/工具结果/记忆摘要进入，而规则 9 又说它只能来自本轮用户逐字输入——实现者无法判断以哪条为准。**③ 中｜`_local_task_context is None` 的写回要求不可实现**：W2 要求该兜底分支**也写回**，但同时要求 User 段用原回合输入、topic/intent 用冻结快照、pending 不保存原始输入——该状态下这些数据**没有完整来源**。**④ 中｜授权前后的双 episode 语义没钉死**：上行的首轮会先写 `User: 原输入 / Assistant: 需要输入 /cloud allow`，新契约又要求授权后写 `User: 同一个原输入 / Assistant: 云端最终答案` ⇒ 同一输入留两条 episode，检索时**授权提示会作为上下文参与**；而上行的 W1 只规定 `/cloud allow` 回合「恰好写一次」，没说前一条是否保留 | **① 值区三态判据重写（§2.3c.3 规则 4/5、§2.3c.4、§2.3c.6、§10.11 C2/C3/C4/C9/C10 + 新增 C12）**：**删除**「条款含 CJK ⇒ 非值区形态」，改为**只看**「条款是否为空 / 是否 == 占位符字面量 `[已脱敏:secret]` / 是否含内部空白」；**不采纳** Codex 建议的「识别标签后的非空 CJK 条款至少判为不可界定」——那样的代价是整段拒绝**外加**本地记忆被占位破坏，而「无内部空白的中文条款」**可以整体替换、零残留**，因此判为**可替换**既满足安全目标又破坏更小；内部空白仍走不可界定 → 出站整段拒绝（`密码：abc 123` 一类）⇒ Codex 要求的「终止符后的疑似值片段不得未经检查继续外发」由新增**规则 5 值形态片段回收**承接（`密码：abc，123` 的 `123` 一并移除，含 CJK 的中文片段不回收以防吞并正常句子）；**防误伤改由标签闭集承担、不再靠值形态**；新增「误伤的取舍」段，明确**风险不对称**（宁过度脱敏：可见、可拒绝、可回溯；绝不漏检中文口令）并**禁止**任何形态/语法豁免（含「标签前一字不是『的』」这类规则——它会把 `系统密码是…` / `数据库密码是…` 误豁免）。缺口清单相应改为「中文句式过度脱敏（已知代价，非缺口）」，**「原值永不外发」的承诺重新成立**。**② `TaskBrief` 定义与规则 1 同步（§2.5）**：dataclass **补上** `project_note: str = ""`（追加末位、带默认值 ⇒ 位置构造兼容，`known_facts` **保持第 3 位**不变名不挪位）、`known_facts` 注释改为「**仅用户逐字陈述**」、新增字段顺序与兼容性说明；**规则 1 整条重写**为**逐 section 来源表**（goal/question / constraints / known_facts / evidence / attempts / project_note 各自唯一来源 + 不得来源），并**明文作废**原「优先来自配置、工具结果、记忆系统等结构化可信来源」表述；补写 `known_facts` 在生产路径恒与 goal 同源、恒被 T1 去重、恒不进 payload 的必然性，以及「该内容应改入 evidence 或 attempts，而不是放宽本行」。**③ W2 拆分（§10.12）**：删除该分支的写回要求，改判为**状态损坏**——撤销该任务 grant、清空 pending、返回 `_CLOUD_FALLBACK_REPLY`、**不写 episode**、**不新增任何枚举值**；并写明该分支在现行状态机下**不可达**（两处 pending 创建点均在 `_local_task_context` 非空的下游），**须用定向测试**（强制 `app._local_task_context = None`）而非端到端场景覆盖；正常云端失败但 LocalTaskContext 尚在时**仍照常写回**（留给 W1）。**④ 单条 episode 不变式（§10.12 W1/W1b + 规范文本段 + §11 第 15 项 + §12 落点）**：**钉死「每任务恰好一条 episode、只在终结时写」**——产出授权 preview 的回合**不写**（判据用**事件** `phase="authorization_required"`，不用回复文本匹配；其四条副作用链均不推进 ⇒ 临时授权提示永不进入语义记忆/会话滚动摘要/项目摘要），`/cloud allow` 回合**补写唯一一条**（User 段 = 原回合输入，取自 `LocalTaskContext.input_event.text`；topic/intent 用进入等待时冻结的快照，**零新增意图解析调用**），取消/失效/不匹配/被取代**零条**（已到位的既有行为，照实钉住）；补写调用点**必须在 `/cloud allow` 路径上**，**不得**放进 `_consult_cloud` / `_complete_cloud_consultation`（与同回合直连路径共享 ⇒ 双写）；登记**两处代价与依据**——(a) 四条异常终结路径上用户的原始请求文本不入记忆（替代方案是写「原输入 + 该回合用户可见的终结回复」，**不预先实现**，留真实 run 观察后按 §10 立候选），(b) 与 **P3 口令确认路径保留两条 episode 的差异**及其理由（那里确认回合的 User 段是**占位文本**，原请求只存在于第一条 episode，丢弃即丢失；这里终结 episode 的 User 段**就是原输入**，故只保留一条以消除重复） |
| 2026-09-24 | **第三轮（Codex 编码前审查第二次回报，3 处：2 实质 + 1 文字）——本轮是「凭据识别模型」的整体替换，不是补丁**。**① 高｜「原值永不外发」仍未真正成立**：第二轮修掉了「条款含 CJK ⇒ 不命中」，但仍留一条**形态判据**——「终止符后的片段**不含 CJK** 才回收（规则 5）」——于是 `密码 abc123`（裸空格不是分隔符 ⇒ 完全不命中）与 `密码是abc，青山绿水`（CJK 后缀不回收）两处仍把原值原样外发；且「**禁止任何形态豁免**」与「CJK 后缀不回收」**自相矛盾**（后者正是形态豁免）。Codex 给出二选一：安全优先（识别标签后凡归属不明的后续片段一律出站拒绝、本地最大区间脱敏）或**收窄承诺**（只保证「符合封闭语法的凭据原值不外发」）；并明确建议前者。**② 中｜`TaskBrief` 来源表与既有规则冲突**：第二轮新写的来源表把 `question` 写成「用户任务语义」、`attempts` 写成「本轮实际执行记录」，但规则 2/7 与 `_with_task_brief_candidates` 的既有行为是——`brief_question ← 模型的 proposed_question`、`brief_attempts ← 模型的 local_attempts_summary`；实现者无法同时满足。**③ 轻微｜冻结快照载体两种说法**：§10.12 W2 写「`PendingCloudAuthorization` 冻结 topic/intent」，同节规范文本与 §12 落点又写「载体归 Codex / `LocalTaskContext`」。 | **① 采用安全优先方向，但落点比 Codex 的建议破坏更小：不做「出站整段拒绝」，改为「识别语法整体替换 + 值区上界钉死行末」**（`05` §2.3c.2/§2.3c.3/§2.3c.4/§2.3c.6、§10.11 C12 重写 + **C13 新增**、§11 第 14 项、§12 两行）：**删除**终止符闭集、片段回收、不可界定态与**一切**值形态判据；**新增边界成分**（T1 显式分隔符 / **T2 空白** / T3 紧邻非 CJK 字符）——`密码 abc123`、`密码 青山绿水`、`密码abc123` 因此命中；**值区 = 标签之后到本行末尾**（值区为空时**顺延**跳过空行取下一个非空行，只顺延一次），值区内一律不再切分、不再按形态筛选 ⇒ 「归属不明的后续片段」不存在 ⇒ **凭据类整段拒绝处置删除**（Codex 第一条建议的「出站拒绝」由此不再需要：区域有确定上界后归属已不再是未知），`密码：abc 123` / `password = two words` / `api_key=sk-…, see README` 从「拒绝」变为「原地替换、section 仍可外发」；**唯二的形态相关条件移到标签侧**（拉丁标签右边界 `tokenizer` 不命中；CJK 标签**紧随 CJK 字符**时 T3 不成立 ⇒ `密码学` 不命中，**紧随非 CJK 非空白字符时照常触发** ⇒ `密码abc123` 命中——「T3 下不触发」只指前一种情形），判断的是「标签是不是字段名」而非值的形态，方向是**收窄识别语法**，逐条登记。**唯一保留的拒绝**换成一条**与凭据判据无关**的诚实拒绝（2.3c.4 第 2 条）：**替换后剔除占位符/标签/分隔符/空白与标点后为空的 section** 整段拒绝（单行内凭据与任务挤在一起时，该 section 已无任务语义，发出去只会换来无效或编造的回答；denied 记固定原因文案，**零新增错误码/事件枚举**；用户把凭据单独成行即可正常咨询）。**照实登记的新代价**：T2 使「拉丁标签 + 空格 + 中文」的技术句式（`token 过期了` / `api_key 读不到`）被过度脱敏并进强制授权——该形态与 `password 青山绿水` **字符层面同形**、无确定性区分手段；**消解方向 = 提高标签侧选择性，禁止回收值形态判据**（§2.3c.6 第 3 行）。**三处语法边界照实登记**（§2.3c.6 第 4/5/6 行）：标签与值之间无任何边界成分的 CJK 粘写形态（`密码青山绿水`，覆盖它会把 `密码学`、`密钥管理` 判为凭据）、值出现在标签之前、值跨多行续行；三者均不依赖值形态，并说明**裸密钥检测（无标签形态）作为第二层**覆盖其中一部分。**② 采信 Codex 的口径（不重构既有云端协议）**：§2.5 规则 1 的来源表改为**声明来源与可信度**而不改构造逻辑——`goal` = `current_input`（唯一来源）、`question` = **模型候选** `proposed_question`、`attempts` = **模型候选** `local_attempts_summary`（**不可信自述，不得视为实际执行事实**，与 `brief_unknowns` 同类）、`constraints` 注明「当前实现恒为空串」；并明文写「本表不得被读成要新增/改造构造逻辑」。**③ 采信**：冻结快照载体**统一为 `LocalTaskContext`**（`PendingCloudAuthorization` 的旧说法作废），并补**读取时机**（须在进入 `_consult_cloud` 之前取出，`main.py:1239`/`1216` 会置空）；同时补入 **W1b ③ 云端挂起追问零 episode**（回复是追问不是答案），并把「直连路径仍把追问写成 Assistant 段」登记为**本轮未处理的不对称**（**该登记于 2026-09-25 作废**——见下方 2026-09-25 行，挂起回合在两条路径上都零 episode）。**接口面**：本轮**零新增签名变更**，`TaskBrief +1 字段` 仍是唯一的结构变更 |
| 2026-09-25 | **第三轮实现审查（Claude 静态审查；Codex 报 `pytest` 749 passed / `ruff` / `mypy` / `git diff --check` 通过）——本轮只做文档一致性修复，零签名变更、零契约语义变更；代码侧 1 处必改（归 Codex）** | ① **代码（归 Codex）**：`src/safety/secret_scan.py:140-142` 的**拉丁标签左边界收窄**（左邻是 `[A-Za-z0-9_]` 即跳过）**未登记、且违反 §2.3c.2 明文的「标签不要求左边界」** ⇒ `DB_PASSWORD=hunter2`、`MYSQL_ROOT_PASSWORD=…`、`AWS_SECRET_ACCESS_KEY=…`、`secret_token=abc` 全部零命中，经单一真源导致**五面一致漏检**（出站 payload/preview/审计、本地记忆、`guarded_executor`、`rule_only_backend` L1、`cloud_boundary` 复扫）；期望删除该 3 行，详见 `reviews/05-p4-cloud-advisory-review.md` 2026-09-25 节（另 1 条测试命名，不阻塞）。② **形状表第 451/466 行与 §10.9 例 22 收口**：原「section 仍可外发 / 含空格口令不再需要拒绝 / 该 section 正常进入 preparation」与本轮同批落地的 §2.3c.4 第 2 条（诚实拒绝；§2.3c.6 交付验收 ② 正是拿 `密码：abc 123` 举例）矛盾 ⇒ 改为只陈述「不再因『不可界定』被拒」，凭据独占 section 走诚实拒绝；例 22 补「除凭据外还含任务语义」限定（**S12 属前者**：`/cloud ask 排查这份配置的鉴权失败原因：api_key=…` 替换后仍有任务语义 ⇒ 正常进入、`cloud_any=true` 不变，已核对场景文件）。③ **§2.3c.3 规则 2 的顺延括注**原含「独占一行的 `密码`」，与规则 1 矛盾（T2 明文只含空格/制表，不含换行）⇒ 改为「有边界成分但值区为空」，并把「**行末裸标签 + 值在下一行**」登记为 **§2.3c.6 第 4 行 (b)**（与 `密码青山绿水` 同族：标签与值之间无边界成分），代价照实写明（`密码\nabc123` 原样外发，裸密钥层只兜一部分）；`§10.11` C13 ⑥ 补对应反向断言（**不得**断言其命中，也**不得**触发顺延）。④ **原「已登记的不对称：直连路径仍把追问写成 Assistant 段」整体作废**——挂起判据 `main.py:432-435`（`_pending_cloud.task_id == 本回合 task_id`）对两条路径同等成立 ⇒ 「挂起回合零 episode」是**两条路径共有的不变式**；`create_policy_grant` 成功的那条分支不是挂起（写**恰一条**、Assistant 段 = 云端答案）。落点：`§10.12` 抑制条件段 + 该不对称正条 + 第 15 条 ③、`06 §2.4`/§6.4 E13 ⑥/§6.5、`clarifications.md` 同轮条目下加更正块。**接口面**：零签名变更。**⑤ 修复复核（同日）**：第 1 条已修——`secret_scan.py` 的左边界收窄删除、右边界条件保留（`_is_latin_identifier_char` 仅剩右边界一处调用），四例 `.env` 形态与全部右边界非命中集逐条数据流复核通过；修复带出的新面（`.env` 式凭据行替换后**外发为壳**——诚实拒绝的剔除项剔不掉 `DB_` / `AWS_` 这类变量名前缀）已登记为 **§2.3c.6 第 10 行**，并写明**不得**用「剔除 ASCII 标识符残段」去修（会误剔 `api_key=…, see README` 一类真任务文本）。模块状态转 **✔️ 完成** |

