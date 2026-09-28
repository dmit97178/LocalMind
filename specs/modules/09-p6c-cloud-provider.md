# 09-p6c-cloud-provider — 多云 Provider 最小底座模块契约

> 状态：👀 验收中（代码审查通过 2026-09-14，见 specs/reviews/p6c-review.md；§11.4 真实 provider 验收待跑：**任一**真实 provider 的凭据就绪后按 §9.2 手动执行 S10_forced_cloud → S06/S08（P6d 起追加 08 §2.6 定向观测集），完成即标 ✔️）
> 阶段：P6 增补项（P6c 多云 Provider 最小底座），服务于「P6 云端测试可使用用户自购平台」；与 08 §7 的「P6c 证据驱动调整闭环」（流程条款，非代码）并行不悖。
> 性质：编码前必读。
> 前序依赖：`05-p4-cloud-advisory.md`、`00-core-interfaces.md`、`00-error-contract.md`、`00-adapter-factory.md`、`07-p6a-observability-cli.md`、`08-p6b-evaluation-loop.md`。
> 起草：2026-09-13（Claude）。触发事件：用户将 GLM Key 配入 `LOCALMIND_CLOUD_API_KEY` 后被原样发送到 DeepSeek 端点并得到 HTTP 401，且 401 被显示为「云端服务暂不可用」——当前配置无法防止 provider 与凭据错配，错误分类也无法区分根因。

---

## 0. 目标、范围与不变量

### 0.1 本契约解决的两个实际问题

1. **provider 与凭据错配不可防**：`create_cloud_advisory_backend()` 与 `DeepSeekAdvisoryBackend` 只支持 DeepSeek，凭据统一读 `LOCALMIND_CLOUD_API_KEY`——任何平台的 Key 配入该变量都会被无条件发给 `api_base` 指向的端点，HTTP 401 才暴露错配，且用户看到的是误导性的「暂不可用」。
2. **错误分类不可辨**：所有传输异常（含 401/403/404/429/5xx/timeout）统一映射 `CLOUD_UNAVAILABLE`，用户与评估记录都无法区分「凭据无效」「模型/端点配置错误」「限流」「网络故障」。

### 0.2 本契约做什么

1. 引入 **provider profile** 概念与封闭注册表：首批内置 `deepseek`、`glm`，另支持 `custom_openai`（用户配置 HTTPS api_base 与 model）。
2. 引入通用 **`OpenAICompatibleAdvisoryBackend`**：统一承载 Bearer 鉴权、请求、超时、响应提取与 `AdvisoryResult` 解析；DeepSeek/GLM 优先经 profile 复用，不新增专用适配器。
3. **provider 专属凭据**（`LOCALMIND_DEEPSEEK_API_KEY` / `LOCALMIND_GLM_API_KEY` / `LOCALMIND_CUSTOM_OPENAI_API_KEY`）：禁止把一个通用 Key 无条件发给任意 provider。
4. **错误分类**：按 §6 映射表细分稳定错误码，同步收窄 `CLOUD_UNAVAILABLE` 语义。
5. 配置新形态与**旧配置兼容迁移**（`backend` → `provider` 一次性映射，见 §5.3）。
6. 验收：使用真实 GLM 跑通 S10，并重跑 S06、S08 云端变体（§9.3）。

### 0.3 明确排除（本契约不做）

- GUI 设置页；Windows Credential Manager / macOS Keychain / Linux Secret Service 等系统凭据库**实现**（仅预留 loader 接缝，§4.4）。
- provider 自动选择、多 provider 同任务协作、自动故障切换、多 provider 并行。
- 动态安装第三方 provider 代码 / 配置任意注册 provider。
- 专家模型与自进化相关改动。
- `AdvisoryResult` 结构、P4 安全链路（PrivacyPolicy / AuthorizationManager / CloudBoundary / SideEffectGateway）的任何语义变更。
- `allowed_scope` 取值链路的重构（§5.2 仅把它归入明确的配置归属）。

### 0.4 不变量（安全不回退）

1. **控制权与安全骨架不动**：PrivacyPolicy、AuthorizationManager、CloudBoundary、SideEffectGateway、`record_denial` 的职责、签名与检查顺序全部保持；provider/profile 只是「哪个端点、哪个凭据」的替换，不引入任何旁路。
2. **provider/profile 变化不得绕过重新授权**：`AuthorizationGrant.provider` 绑定语义（05 §3.4「provider 变化 → 失效」）不变；活动 provider 由 bootstrap 一次性解析，进程内不可变。
3. **custom_openai 不得成为任意出站或 SSRF 通道**：§2.4 的 URL 白名单规则是硬边界。
4. **云端返回仍只是建议**：入站 `check_response`、本地重解、执行强制确认不因 provider 不同而分叉；所有 provider 输出统一 `AdvisoryResult`。
5. **provider 特有配置不得进入外发 payload**：请求体封闭集见 §3.3；`model` 是请求参数，不是 payload 内容，更不是授权边界。
6. **凭据不扩散**：Key、Authorization header、原始响应不得进入日志、事件、审计和异常详情（§6.3）。

---

## 1. 概念边界（钉死）

| 概念 | 含义 | 例子 | 关键规则 |
|---|---|---|---|
| **provider_id** | 稳定字符串标识，是 grant、`CloudRequestPackage`、`CloudAuditEvent` 与 `App.cloud_provider` 绑定的值 | `"deepseek"` / `"glm"` / `"custom_openai"` / `"noop"` | **不等于 Python 类名**，不随实现重构变化；必须是注册表白名单成员 |
| **provider profile** | provider_id + 该 provider 的连接事实（端点、路径、默认模型、凭据变量名）；代码白名单资产 | glm profile：`api_base="https://open.bigmodel.cn/api/paas/v4"` | 普通配置**不得**覆盖其安全相关字段（§2.3） |
| **backend implementation** | 实现 `CloudAdvisoryBackend` 的 Python 类 | `OpenAICompatibleAdvisoryBackend` / `NoopCloudAdvisoryBackend` | 一个实现可服务多个 provider；对 Core 不可见；`provider` 字段值与类名无关 |
| **model** | 发给活动 provider 的模型名，连接级参数 | `"glm-4.7-flash"` / `"deepseek-v4-flash"` | **模型不得选择 provider**；provider 只由用户配置决定（§1.2） |
| **credential** | provider 专属凭据材料；v1 来自环境变量，经 credential loader 读取 | `LOCALMIND_GLM_API_KEY` 的值 | 与 profile 一一对应（`credential_env`）；绝不跨 provider 发送（§4） |

### 1.1 provider 单一真源

活动 provider 的**唯一判定来源**是 `[cloud_advisory].provider`（兼容期旧键 `backend` 一次性映射，§5.3）。以下全部从同一解析结果派生，不得存在第二来源：

- `App.cloud_provider`（进而派生 grant.provider、package.provider、`CloudAuditEvent.provider`、`PendingCloudAuthorization.provider`）；
- 适配器的端点（api_base + completion_path）与凭据变量（credential_env）。

禁止从 `model` 名、环境变量内容、探测结果或模型输出**反推** provider。

### 1.2 模型不得选择 provider

模型输出（`IntentCandidate` / `ConsultationProposal`）不含 provider 选择权；ControlPolicy、PrivacyPolicy、AuthorizationManager 均以 bootstrap 解析的活动 provider_id 为准。配置中的 `connection.model` 只决定请求体里的 `"model"` 字段值，不参与路由。

### 1.3 provider 切换与授权失效

- 活动 provider 在**进程生命周期内唯一且不可变**（bootstrap 解析一次；同一任务内 provider 固定由此保证）。
- provider 切换 = 配置变更 + 重启：内存态（grant、pending、`LocalTaskContext`）不跨进程存活，天然清零。
- 防御性兜底不变：任何携带旧 provider_id 的 grant 对新活动 provider 无效——`AuthorizationManager.validate()` 的 provider 绑定校验（05 §3.2/§3.4）必须拒绝并抛 `CLOUD_AUTHORIZATION_EXPIRED`；该行为有专项测试（§9.1 第 7 条）。
- 切换后首次外发必须走完整授权交互（AWAITING_AUTHORIZATION → 新 grant），无任何「同 provider 记忆」。
- **边界注记**：`custom_openai` 的 `connection.api_base` / `model` 变更**不是** provider 切换——provider_id 不变，授权边界以 provider_id 为准（grant 不感知端点细节）。当前这无实际风险（grant 不跨进程存活，端点变更必然伴随重启清零）；但若未来实现 grant 跨进程持久化，此注记即为缺口预告：届时需把端点指纹纳入 grant 绑定或另行评估，不得默认「同 provider_id 即可复用 grant」。

---

## 2. Provider Profile 与注册表

### 2.1 CloudProviderProfile（字段钉死，防膨胀）

```python
@dataclass(frozen=True)
class CloudProviderProfile:
    provider_id: str        # 稳定标识（§1）
    api_base: str           # HTTPS base URL，不带尾随 "/"
    completion_path: str    # 固定 "/chat/completions"（v1 三 profile 相同，仍单列以便未来兼容非默认路径的 provider）
    default_model: str      # connection.model 缺省时使用；custom_openai 为空串（必配）
    credential_env: str     # 专属凭据环境变量名
    openai_compatible: bool # 能力标记：可由 OpenAICompatibleAdvisoryBackend 服务
```

**本期明确延期的字段**（不得顺手实现）：rate limit / 配额参数、organization 或 API 版本等附加 header、鉴权方式变体（非 Bearer）、`response_format` 等请求参数开关、每 provider 系统提示词、定价/计量、健康检查端点。需要时按契约变更流程增补。

### 2.2 内置 profile（代码白名单）

| provider_id | api_base | completion_path | default_model | credential_env | 说明 |
|---|---|---|---|---|---|
| `deepseek` | `https://api.deepseek.com` | `/chat/completions` | `deepseek-v4-flash` | `LOCALMIND_DEEPSEEK_API_KEY` | 官方 api_base；`deepseek-chat` 已被官方弃用（2026-09-13 核对） |
| `glm` | `https://open.bigmodel.cn/api/paas/v4` | `/chat/completions` | `glm-4.7-flash` | `LOCALMIND_GLM_API_KEY` | 智谱 OpenAI 兼容端点，`Authorization: Bearer <key>` 直用 API Key |
| `custom_openai` | （由 `[cloud_advisory.connection].api_base` 提供） | `/chat/completions` | （空，必配） | `LOCALMIND_CUSTOM_OPENAI_API_KEY` | 见 §2.4 |

> 缺省模型为当前平台文档有效值（2026-09-13 核对：智谱对话补全文档、DeepSeek 模型文档；原值 `glm-4-flash` / `deepseek-chat` 已不在现行枚举或已弃用）。`glm` 取免费档 flash 作为底座缺省；验收 run 在 eval 模板显式指定 model，不依赖该缺省。default_model 只是便利缺省，不是推荐模型声明；平台改版导致的过时值按普通缺陷修复（改 profile 常量），不构成契约变更。

### 2.3 注册表与白名单规则

- `CloudProviderRegistry`：封闭的代码级字典（provider_id → profile），`resolve(provider_id) -> CloudProviderProfile`，未知 id 抛 `CONFIG_ERROR`。位置在 adapter 层（建议 `src/adapters/cloud_profiles.py`，命名 Codex 定）；**Core 不 import**——Core 只见 provider_id 字符串与 `CloudAdvisoryBackend` 实例。
- 配置可覆盖的范围**仅限**：`connection.model`、`connection.request_timeout_seconds`、`[cloud_advisory.policy].allowed_scope`、`custom_openai` 的 `connection.api_base`。
- 内置 profile 的 `api_base`、`completion_path`、`credential_env` 为**安全相关字段，配置不可覆盖**——它们决定「数据发往哪里、用哪个凭据」，属于云端边界的一部分。
- 注册表不做动态插件、不做配置注册、不做自动发现。新增 provider = 改代码白名单 + 本契约变更（新增内置 provider 是需求/安全边界变更，走 Claude 审查）。
- `openai_compatible` 标志的消费规则：v1 三个内置 profile 均为 `true` 且唯一云端适配器是 OpenAICompatibleAdvisoryBackend，该标志暂无分支效果；但工厂选择适配器时必须以它为判据——未来出现 `openai_compatible=false` 的 profile 而代码中没有对应专用适配器时，必须 `CONFIG_ERROR`，**禁止**静默落回 OpenAI 兼容适配器（防误路由到不兼容端点）。

### 2.4 custom_openai 的 api_base 校验（硬边界）

`custom_openai` 的 `api_base` 在**构造期**（无论 enabled）校验，违反任一条即 `CONFIG_ERROR`：

1. scheme 必须为 `https`（明文 http 拒绝）；
2. 禁止 URL 携带 userinfo（`user:pass@`）、query（`?`）、fragment（`#`）；
3. host 非空；host 为 **IP 字面量**时拒绝：loopback（127.0.0.0/8、::1、0.0.0.0）、私网（10.0.0.0/8、172.16.0.0/12、192.168.0.0/16）、链路本地（169.254.0.0/16、fe80::/10）、ULA（fc00::/7）；
4. host 为**域名**时拒绝 `localhost`（任意大小写与尾点变体）及 `.localhost` / `.local` / `.internal` 后缀域名；
5. 端口不限（https 默认 443）；路径前缀允许（如 `/v1`）；归一化：strip 尾随 `/`。

**已知残留（记录在案，v1 不处理）**：域名不做事前 DNS 解析——解析结果指向私网地址的域名（内网 DNS 场景）不被第 3 条拦截。本项目运行在用户本人机器、凭据由用户本人配置，该残留可接受；若未来出现多用户/托管形态，需按安全边界变更流程补解析期校验。

**与本地 ModelBackend 的职责分离**：loopback HTTP 属于本地模型后端（Ollama 等，P1 的 loopback 规则）；云端建议链路一律 HTTPS 公网端点。两套地址校验互不通用——不得以 `custom_openai` 名义接入本地推理服务（想用本地模型请配 `[model_backend]`），也不得让 ModelBackend 的 loopback 例外外溢到云端链路。

**重定向与本节的关系**：以上校验针对初始配置端点；出站过程中的 HTTP 重定向一律禁用（§3.3）——重定向目标是绕过本节校验的通道，不是需要支持的特性。

---

## 3. OpenAICompatibleAdvisoryBackend（通用适配器）

### 3.1 职责与构造

实现既有 `CloudAdvisoryBackend.advise(request: CloudRequestPackage) -> AdvisoryResult`（接口签名不变）。统一负责：Bearer 鉴权、请求组装、超时、响应提取、`AdvisoryResult` 解析、错误分类（§6）。

```python
class CloudCredentialLoader(Protocol):
    """凭据读取接缝（§4）。实现位置在 adapter 层，Core 不感知。"""
    def exists(self, profile: CloudProviderProfile) -> bool:
        """启动期/自检期存在性检查：只回答对应凭据（按 §4.1 回退链）是否存在（非空），
        不得返回、记录或缓存值内容。"""
        ...
    def get(self, profile: CloudProviderProfile) -> str:
        """读取凭据值；仅在 advise() 实际外发前调用。缺失时抛 CLOUD_CREDENTIAL_MISSING（§4.2/§6.1）。"""
        ...

class OpenAICompatibleAdvisoryBackend(CloudAdvisoryBackend):
    def __init__(
        self,
        profile: CloudProviderProfile,
        model: str,                                   # 非空（工厂已解析 default_model）
        request_timeout_seconds: float,
        transport: CloudTransport | None = None,      # 既有注入接缝保留，默认 urllib 实现
        credential_loader: CloudCredentialLoader | None = None,  # None → EnvCredentialLoader
    ) -> None: ...
```

- 构造期**不得读取或校验任何凭据**（保持 05 §7 确立的规则，现在适用于所有 provider）——`enabled=false` 时任何**合法配置的** provider 无需凭据即可 bootstrap（非法 provider 或非法连接配置仍按 §5.2 矩阵报错）；启动期/自检期只调 `credential_loader.exists(profile)`（只判存在，不返回/传播值），Key 值仅在 `advise()` 实际外发前经 `credential_loader.get(profile)` 读取——「启动期只查存在」与「凭据仅 advise 期读取」两条规则经 `exists` / `get` 双方法同时成立，互不牺牲。
- `model` / `request_timeout_seconds` 由工厂从 connection 配置解析后传入；适配器不再接收 config dict，也不接收 `max_turns`（预算唯一归 AuthorizationManager——现适配器存储但从不使用 `max_turns`/`allowed_scope` 的死配置一并移除）。
- 请求 URL = `profile.api_base + profile.completion_path`；仅 `custom_openai` 的 api_base 来自配置（§2.4）。

### 3.2 DeepSeek / GLM 复用，专用适配器收紧

DeepSeek 与 GLM **必须**经 profile 复用本适配器，不再保留 `DeepSeekAdvisoryBackend`（删除，不留双实现；配置层迁移见 §5.3）。仅当未来 provider 协议确实不兼容（非 OpenAI chat-completions 形态）时，才新增专用适配器类，且必须先经本契约变更（接口意图归 Claude）。

### 3.3 请求与响应形态（封闭集）

请求体（在既有 §4.1 边界字段断言之上，字段封闭）：

```json
{
  "model": "<connection.model 或 profile.default_model>",
  "temperature": 0.1,
  "messages": [
    {"role": "system", "content": "<固定 JSON 输出协议> + <package.allowed_scope>"},
    {"role": "user", "content": "<JSON: {allowed_scope, context[]}>"}
  ]
}
```

- **`temperature` 固定 `0.1`**：GLM 官方文档 temperature 取值为 (0,1) 开区间（`0` 不合法），DeepSeek 支持 0–2；`0.1` 是跨平台合法且近确定的取值。不做成 profile 能力字段（本阶段过重，§2.1 延期清单不变）。
- **system message = 固定 JSON 输出协议（代码级常量，provider 无关）+ `package.allowed_scope`**。响应被强制按 `AdvisoryResult` 解析，但请求侧若不声明输出格式，真实模型大概率返回自由文本 → 被误判 `CLOUD_PARSE_ERROR`（DeepSeek JSON 输出文档同样要求在提示词中声明 JSON 并给示例）。协议四要素钉死（精确措辞 Codex 定，中文，不含任何 provider 名）：
  1. 只输出一个 JSON 对象，不要 Markdown、围栏或任何解释性文字；
  2. 字段清单与类型：`analysis`（字符串，必填）、`suggested_tools`（字符串数组或 null）、`risks`（字符串数组）、`requires_local_validation`（布尔，恒输出 `true`——`check_response` 本就强制 true，05 §6.3）、`needs_more_info`（布尔）、`requested_context_categories`（字符串数组）、`followup_question`（字符串）；
  3. 最小示例（单行）：`{"analysis": "<对候选上下文的分析建议>", "suggested_tools": null, "risks": [], "requires_local_validation": true, "needs_more_info": false, "requested_context_categories": [], "followup_question": ""}`；
  4. 不引入 `response_format` 等结构化开关（§2.1 延期项）——协议提示是唯一手段。
- 自定义 header 仅 `Authorization: Bearer <credential>` 与 `Content-Type: application/json`；不提供任何配置化 header 映射、请求模板、响应模板或可执行代码（§0.4/§2.3）。
- 本地边界字段断言保留：payload 序列化前断言不含 `task_id`/`session_id`/`provider`/`purpose`/`grant_id`/`turn`/`fingerprint`，失败视为 `SAFETY_CLOUD_BLOCK` 不发网络（05 §4.1 现状延续）。
- **重定向一律禁用（出站边界的一部分，§2.4）**：云端 POST 不自动跟随任何 3xx。Python 默认 redirect 处理会为 3xx 构造新请求并复制 `Authorization` 等非内容 header——合法公网端点返回 `302 Location: https://127.0.0.1/…` 即可绕过 §2.4 校验并把 Key 转发到另一主机。默认 urllib transport 必须禁用 redirect 处理（`HTTPRedirectHandler.redirect_request` 返回 None → 3xx 以 `HTTPError` 冒泡）；任意 3xx → `CLOUD_ENDPOINT_INVALID`（§6.1）。「逐跳重验 URL + 跨域剥离 header」方案更厚且与固定端点设计不符，不采用；本规则约束任何 transport 实现（含注入替身）。
- 响应提取维持现状：`choices[0].message.content` 必须为 JSON 且含 `analysis` 字符串；结构不合法 → `CLOUD_PARSE_ERROR`（§6）。
- **围栏容忍（新增，GLM 兼容性）**：content 为 ` ```json …``` ` 围栏包裹时剥围栏后解析；其余解析仍严格，不做启发式修复。
- `stream` / `tools` / `response_format` 等参数本契约不引入。

---

## 4. 凭据边界

### 4.1 provider 专属凭据（v1 = 环境变量）

| provider_id | 主变量 | 兼容回退 |
|---|---|---|
| `deepseek` | `LOCALMIND_DEEPSEEK_API_KEY` | 主变量缺失时回退 `LOCALMIND_CLOUD_API_KEY`（仅限 deepseek，迁移期规则，§4.3） |
| `glm` | `LOCALMIND_GLM_API_KEY` | 无 |
| `custom_openai` | `LOCALMIND_CUSTOM_OPENAI_API_KEY` | 无 |

`EnvCredentialLoader` 按上表实现两个方法：`exists(profile)` 只做存在性判定（变量 strip 后非空即存在，供 bootstrap / 环境自检调用，§5.2/§9.3）；`get(profile)` 仅在 `advise()` 实际外发前调用（§3.1）。存在性检查与值读取在接缝上分离——启动期**不返回、缓存或传播**凭据值（`exists()` 内部读取环境变量做非空判定，但值不进入返回值之外的任何位置）。

### 4.2 凭据缺失与错配的行为（fail-closed）

- **bootstrap 期缺失**（enabled=true）：`CONFIG_ERROR`（recoverable=False），user_message 点名 provider 与变量：`"云端咨询已启用，但未配置 glm 的 API Key：请设置 LOCALMIND_GLM_API_KEY。"` 不创建后端、不启动 App。
- **advise 期缺失**（运行中环境变化兜底）：抛 `CLOUD_CREDENTIAL_MISSING`（recoverable=False），user_message 同上风格；走既有云端失败路径（本地降级 + 审计），绝不发送。
- **错配的表现形式就是缺失**：系统不校验 Key「属于哪个 provider」（无格式指纹/前缀嗅探，明确不做）；GLM Key 只配在旧变量而 `provider="glm"` 时 → GLM 专属变量缺失 → 4.2 第一条 fail-closed 提示设置 `LOCALMIND_GLM_API_KEY`。错配 Key 到达错误端点的通道被专属变量机制从结构上切断：glm 的请求永远只携带 `LOCALMIND_GLM_API_KEY` 的值，反之亦然（§9.1 第 2 条测试钉死）。

### 4.3 旧变量迁移（仅 deepseek，时间盒）

既有合法用户（DeepSeek Key 在 `LOCALMIND_CLOUD_API_KEY`）不得突然失效：`provider="deepseek"` 且专属变量缺失时回退读旧变量；专属变量存在时**优先生效**。`glm` / `custom_openai` 无任何回退（此前从未工作过，无既有配置可保）。该回退是迁移期规则，**P7 开始时删除**（列入 §10 Codex 待办与 P7 清单）。

### 4.4 产品化预留（本阶段只留接缝）

`CloudCredentialLoader` 是唯一凭据读取接缝：产品化后替换为 Windows Credential Manager / macOS Keychain / Linux Secret Service 实现时，只改 loader 实现与工厂注入，**不改** `OpenAICompatibleAdvisoryBackend`、App、grant/审计语义。loader 返回值仅进入 Authorization header，**不得保存到任何实例字段或持久化位置**——只作为单次请求的局部变量存在——也不得进入任何日志/事件/审计/异常（§6.3）。本阶段不实现任何系统凭据库。

### 4.5 provider_available 的准确语义（本阶段钉死）

`CloudControlState.provider_available` 的取值规则与现值一致（`App` 以 `cloud_enabled` 装配），但其**语义**钉死为：

> 「安装级云端前提完整」——`enabled=true`、活动 provider 为注册表成员且 profile 解析成功、连接配置有效、启动期凭据存在性检查已通过。它表示**可以发起云端尝试**，**不代表远端健康**；真实可用性由首次调用的结果与 §6 错误分类呈现（与 08 §3.2「环境自检只查存在性、真实可用性由调用结果判定」同口径）。

不新增 health_check / 网络探测（08 决策表 2026-09-10 条维持）；ControlPolicy 对该字段的消费方式不变。

---

## 5. 配置与迁移

### 5.1 新配置形态（权威示例）

```toml
[cloud_advisory]
enabled = false                       # true 时 provider 必须为注册表内非 noop 成员
provider = "noop"                     # noop | deepseek | glm | custom_openai（兼容期接受旧键 backend，§5.3）
privacy_mode = "balanced"             # strict | balanced | convenient
max_turns_per_task = 3                # 授权预算（AuthorizationManager）——不属 provider 连接配置
max_context_items = 12                 # 2026-09-14 由 8 上调（05 契约 §8：brief_unknowns 逐条 item 化，最坏 6+3=9）；合法范围 1..100
context_byte_budget = 32768             # 2026-09-17 由 2048 上调，同日二次裁决定 32768（05 契约 §8/§2.5 规则 3：TaskBrief 的唯一字节硬边界）；合法范围 256..65536，65536 为绝对硬上限
cooldown_seconds = 300
grant_ttl_seconds = 600

[cloud_advisory.connection]
model = ""                            # 留空 = profile.default_model；custom_openai 必填
request_timeout_seconds = 60          # > 0，构造期校验，非法 CONFIG_ERROR
# api_base = "https://..."            # 仅 provider = "custom_openai" 时允许（§2.4）；内置 provider 出现即 CONFIG_ERROR

[cloud_advisory.policy]
allowed_scope = "仅提供分析建议，不生成执行命令或计划"
```

键归属规则：

- `provider` / `enabled` / 预算与隐私键 → `[cloud_advisory]` 根（现状不变）。
- `[cloud_advisory.connection]` = 「连到哪、用哪个模型、等多久」。
- `[cloud_advisory.policy]` = 「外发政策声明」。`allowed_scope` 的**生效链路**本契约接通：bootstrap 读该键传入 `PrivacyPolicy` 构造（新增可选参数，默认现固定值）→ `build_package` 使用之。这是对 P4 现状的修正——现适配器存储并校验配置 `allowed_scope` 却从不使用、`PrivacyPolicy` 内硬编码同值（死配置）；P6c 使配置真实生效，grant/fingerprint 语义不受影响（allowed_scope 不参与指纹）。
- **不采纳用户建议中的 `[cloud_advisory.policy].max_turns`**：预算唯一真源是既有的 `max_turns_per_task`（AuthorizationManager 消费），第三个名字只会制造两源漂移。

### 5.2 校验矩阵

| enabled | provider 解析值 | bootstrap 行为 |
|:---:|---|---|
| false | 缺省 / `noop` | `NoopCloudAdvisoryBackend`；不读任何 Key（连存在性检查也不做） |
| false | 内置 / custom_openai | provider 解析与连接配置校验照常执行（**校验与能力分离**——配置错误仍在启动期 fail-fast，含 custom_openai URL 规则）；**注入 `NoopCloudAdvisoryBackend()`**——不构造具备真实外发能力的对象（关闭云端必须是能力层 fail-closed，不依赖调用方永远正确）；loader 的 `exists` / `get` 均不调用 |
| true | 缺省 / `noop` | `CONFIG_ERROR`（沿用「enabled 需非 noop 后端」规则，键名随 provider） |
| true | 内置 / custom_openai | 连接配置校验（model 解析非空、timeout 合法、custom_openai 必配 api_base+model）→ **凭据存在性检查**（经 `credential_loader.exists(profile)`，按 §4.1 回退链，不传播值）→ 构造 |

非法 provider 字符串（非注册表成员）在任何 enabled 下均 `CONFIG_ERROR`。

### 5.3 旧配置迁移（兼容期 = 至 P7 开始）

| 旧键 | 迁移规则 |
|---|---|
| `[cloud_advisory].backend = "noop"` | 映射 `provider = "noop"` |
| `[cloud_advisory].backend = "deepseek"` | 映射 `provider = "deepseek"` |
| `[cloud_advisory].backend` 为其他值 | `CONFIG_ERROR`（现状一致） |
| `provider` 与 `backend` 同时存在 | 一致（归一化后相同）→ 接受；**不同 → `CONFIG_ERROR`**（两真源冲突必须报错，不得静默择一） |
| `[cloud_advisory].config.model` | 映射 `[cloud_advisory.connection].model`（新键存在时旧键忽略） |
| `[cloud_advisory].config.request_timeout_seconds` | 映射 `connection.request_timeout_seconds`（同上） |
| `[cloud_advisory].config.allowed_scope` | 映射 `[cloud_advisory.policy].allowed_scope`（同上） |
| `[cloud_advisory].config.max_turns` | **忽略并废弃**（从不生效的死键；预算真源 `max_turns_per_task`） |
| `[cloud_advisory].config.api_base` | 仅 `custom_openai` 接受（映射 `connection.api_base`）；内置 provider 下与 profile.api_base 归一化（strip 尾 `/`）比较——**相同 → 接受并忽略；不同 → `CONFIG_ERROR`**（静默改道官方端点/代理都是出站边界变化，必须显式处理） |

迁移为纯启动期行为，不写回文件、不产生运行时事件。既有配置效果核对：`config/default.toml`（noop）与 `config/eval.example.toml`（deepseek + 官方 api_base + deepseek-chat）迁移后行为与现状逐项一致；唯一行为变化是 §4 的凭据变量体系（现配 `LOCALMIND_CLOUD_API_KEY` + deepseek 经兼容回退继续工作）。

**仓库模板 `config/cloud_advisory.example.toml` 是已知例外**：其旧值 `api_base = "https://api.deepseek.com/v1"`（官方文档别名）与 deepseek profile 的 `https://api.deepseek.com` 不匹配 → 按上表规则报 `CONFIG_ERROR`。不为「同主机别名」开静默归一口子——api_base 决定数据去向，改道必须显式，别名归一表还会造成 profile 字段膨胀（§2.1 延期项）。处置：该模板由 Codex 按新形态重写（§10 第 7 条，删除 api_base）；复刻了旧模板的用户收到 `CONFIG_ERROR` 后，删除该键即回到官方端点（错误信息须点名这条出路）。

---

## 6. 错误分类

### 6.1 稳定错误码（新增 4 个，收窄 1 个，保留 1 个）

不为每个 HTTP 状态建子类；按「用户可行动的根因」归类：

| 触发（判定顺序自上而下） | code | recoverable | user_message（模板，`{provider}` 为 provider_id） |
|---|---|:---:|---|
| HTTP 401 / 403 | `CLOUD_AUTH_INVALID`（新增） | false | 「云端凭据无效或无权限，请检查 {provider} 的 API Key。」 |
| HTTP 3xx（重定向已禁用，§3.3——以 `HTTPError` 冒泡） | `CLOUD_ENDPOINT_INVALID`（同 4xx 行） | false | 同端点错误模板 |
| HTTP 404 及其余 4xx（408、429 除外） | `CLOUD_ENDPOINT_INVALID`（新增） | false | 「云端模型或服务地址配置有误，请检查 provider 与 connection.model。」 |
| HTTP 429 | `CLOUD_RATE_LIMITED`（新增） | true | 「云端请求达到限流或配额上限，请稍后再试。」 |
| HTTP 408 / 5xx / 传输超时 / URLError（DNS、连接失败、TLS） | `CLOUD_UNAVAILABLE`（语义收窄） | true | 「云端服务暂不可用。」 |
| 响应结构不合法（含围栏剥离后仍无法解析） | `CLOUD_PARSE_ERROR`（保留） | true | 「云端返回格式异常。」 |
| 凭据缺失（loader 在 advise 期） | `CLOUD_CREDENTIAL_MISSING`（新增） | false | 「未配置 {provider} 的 API Key，请设置 {credential_env}。」 |

- `CLOUD_UNAVAILABLE` 收窄后不再覆盖 401/403/404/429——用户不再把凭据错配看成「暂不可用」。
- 新码全部走 `LocalMindError`（不新增异常子类，遵守 00-error-contract「不需要更多子类」原则）；`message` 为英文技术描述，`recoverable` 语义按 00-error-contract（凭据/端点类重试无意义 → false）。
- 其余未知 `LocalMindError` 传播规则不变（00-error-contract §4：`advise()` 抛 `LocalMindError`）。

### 6.2 App 层 denied_reason 映射（联动 07 §2.2）

`_consult_cloud` 的异常分支按 code 映射 `cloud_consult.denied_reason`（封闭集扩展，07 已同步）：

| code | denied_reason |
|---|---|
| `CLOUD_AUTH_INVALID` / `CLOUD_CREDENTIAL_MISSING` | `"auth"` |
| `CLOUD_ENDPOINT_INVALID` | `"endpoint"` |
| `CLOUD_RATE_LIMITED` | `"rate_limited"` |
| 其余（`CLOUD_UNAVAILABLE` / `CLOUD_PARSE_ERROR` / 其他 `LocalMindError`） | `"unavailable"` |

本地否决类（`disabled` / `no_safe_context` / 取消 / 超时 / 错会话）不变。降级事件（`degradation cloud→local_only`）与本地收敛路径不变。

### 6.3 脱敏不变量（错误与日志通道）

异常 `message` / `details` 可含：HTTP 状态码、provider_id、请求 URL（host+path；userinfo 本就被 §2.4 禁止）。**不得含**：凭据原值、Authorization header 值、响应体原文、`context_items` 内容、`allowed_scope` 之外的 payload 字段。该约束同样约束 transport 实现的异常包装（现状 `_unavailable_error` 的 `f"{error}"` 内插需改为白名单字段拼接，Codex 实现时注意 `str(HTTPError)` 含 URL 的现状是可接受的，响应体不可接受）。测试以「假 Key 全文扫描」钉死（§9.1 第 8 条）。

---

## 7. 注册与工厂

### 7.1 create_cloud_advisory_backend（决策表）

```python
def create_cloud_advisory_backend(config: dict) -> CloudAdvisoryBackend:
    # 1. 解析 provider（provider 真源 + backend 兼容映射 + 冲突检查，§5.3；未知 → CONFIG_ERROR）
    # 2. registry.resolve(provider_id) → profile
    # 3. 连接配置校验与 model 解析（含 custom_openai URL 规则，§2.4/§5.2）——enabled 与否都执行（校验与能力分离）
    # 4. enabled=true → 凭据存在性检查（credential_loader.exists(profile)，§4.1/§5.2）
    # 5. enabled=false → return NoopCloudAdvisoryBackend()（占位建议、零外发能力；App.cloud_provider 仍为解析出的 provider_id）
    # 6. enabled=true → return OpenAICompatibleAdvisoryBackend(profile, model, timeout)
```

- `App.cloud_provider` = 解析后的 provider_id（替换现状 `_backend_type(config, "cloud_advisory", "backend")`；语义对齐 §1.1 单一真源）。
- `bootstrap()` 新增校验顺序遵守 §5.2 矩阵；`enabled=true + noop` 矛盾规则保留（键名更新）。
- Core 仍不含任何 `if provider == ...` 分支；分支只存在于工厂（00-adapter-factory 规则不变）。
- `PrivacyPolicy` 构造新增可选 `allowed_scope`（默认现固定值）——接口签名变更，Claude 已裁定，Codex 镜像 00-adapter-factory §3.2。

### 7.2 第一版明确不做（重复钉死）

动态第三方代码插件、自动 provider 选择、多 provider 并行/协作、故障切换、provider 健康探测。`enabled=true` 时配置完整有效是唯一通过路径；`enabled=false` 一律注入 `NoopCloudAdvisoryBackend`（运行时不存在具备真实外发能力的云端对象——能力层 fail-closed），配置校验照常执行、凭据检查不执行，不因缺 Key 失败。

---

## 8. 安全不变量复查清单（对照 0.4，编码后逐条断言）

1. PrivacyPolicy / AuthorizationManager / CloudBoundary / SideEffectGateway 零改动（diff 审查项；`PrivacyPolicy` 构造新增可选参数除外）。
2. grant 绑定 provider 的失效行为有跨 provider 测试（§9.1 第 7 条）。
3. custom_openai 出站面 = §2.4 五条 URL 规则 + §3.3 请求封闭集 + 重定向禁用，测试逐条覆盖（§9.1 第 6/12 条）。
4. 所有 provider 的响应都经 `check_response` 入站检查后才会进入回流（gateway 顺序不变，测试回归覆盖）。
5. 请求体不含 provider 特有配置：`model` 只出现在 OpenAI 请求体字段，不进 `context_items`、不进授权/审计语义；system message 的 JSON 输出协议为 provider 无关代码常量（§3.3）。
6. 凭据隔离矩阵：每个 provider 的请求只携带自己的 loader 返回值（§9.1 第 2 条）。
7. `enabled=false` 时运行时不存在具备真实外发能力的云端对象（一律 Noop 注入），且 loader 全程未被调用（§9.1 第 4 条）。

---

## 9. 测试与验收

### 9.1 单元测试（全部离线：fake transport + monkeypatch env；进 pytest 必跑集）

1. **profile 选择正确**：`provider=deepseek` → deepseek profile（api_base/credential_env/default_model）；`provider=glm` → glm profile；工厂决策表（§5.2 矩阵）逐格断言。
2. **凭据隔离**：GLM Key 永不发送到 DeepSeek，反之亦然——fake transport 捕获 Authorization header，断言其值恒等于活动 provider 专属变量的值；交叉配置（GLM env 存在 + provider=deepseek + deepseek env 存在）断言 deepseek 请求不含 GLM 值。
3. **缺 Key fail-closed**：enabled=true 且专属变量缺失 → bootstrap `CONFIG_ERROR`（消息点名变量）；advise 期 loader 返回缺失 → `CLOUD_CREDENTIAL_MISSING`，不发网络、走本地降级。
4. **disabled 无外发能力、不读 Key**：enabled=false 下（环境变量全空）bootstrap 成功，注入的是 `NoopCloudAdvisoryBackend`（断言未构造 `OpenAICompatibleAdvisoryBackend`）；loader 的 `exists` / `get` 全程未被调用（注入 spy loader）；环境变量**存在**真实形态 Key 时同样注入 Noop——即便未来代码误调 `advise()` 也只得到占位建议、零网络请求。
5. **错误映射**（fake transport 注入）：401/403 → `CLOUD_AUTH_INVALID`；404 与 400 → `CLOUD_ENDPOINT_INVALID`；429 → `CLOUD_RATE_LIMITED`；408/500/503/timeout/URLError → `CLOUD_UNAVAILABLE`；非 JSON/缺 choices/缺 analysis → `CLOUD_PARSE_ERROR`；`recoverable` 标志按 §6.1。
6. **custom_openai 校验**：非 HTTPS、userinfo、query、fragment、localhost 变体、`.local`/`.internal` 后缀、私网/loopback IP 字面量逐一拒绝；合法 `https://host/v1` + model 通过；内置 provider 配 `connection.api_base` → `CONFIG_ERROR`。
7. **provider 切换使旧 grant 无效**：以 `provider="deepseek"` 签发的 grant，构造 `provider="glm"` 的 package 走 `validate()` → `CLOUD_AUTHORIZATION_EXPIRED`；pending 授权不跨 provider 复用。
8. **凭据不泄漏**：以含唯一标记的假 Key 跑完整 consult 流程（含失败路径），断言事件 JSONL、`CloudAuditEvent`、异常 `message`/`user_message`/`details`、以及（开启时）转录中均不出现该标记字符串与 `"Bearer "` 拼接值。
9. **迁移回归**：旧形态（`backend="deepseek"` + `config.*`）bootstrap 成功且行为映射正确（model/timeout/scope 生效、api_base 与 profile 一致时接受）；`provider` 与 `backend` 冲突 → `CONFIG_ERROR`；旧 `config.max_turns` 被忽略；deepseek 兼容回退（仅旧变量存在时可用、glm 无回退）。
10. **既有回归**：P4（05 §10）/ P5 / P6a / P6b 运行器测试全量保持绿；`run_p4.py` 演示脚本与 08 §3.2 环境自检改走 profile 凭据链后行为不回退。
11. **JSON 输出协议在请求中**：fake transport 捕获请求体，断言 system message 含「仅输出 JSON」指令、`AdvisoryResult` 字段清单与最小示例（§3.3）；协议文本为 provider 无关常量——不含 provider_id、不含凭据相关内容；`temperature == 0.1`；loader `exists()` 在启动期被调用且不改变请求体。
12. **重定向禁用**：本地回环 socket 服务器返回 `302 Location: …` 时（对任意 provider 配置），默认 transport 只发出一次请求、不产生第二次请求、`Authorization` 未被转发，适配器抛 `CLOUD_ENDPOINT_INVALID`；fake transport 注入 3xx 同样映射 `CLOUD_ENDPOINT_INVALID`（§3.3/§6.1）。

### 9.2 真实平台验收（显式启用，绝不进默认 pytest）

- 前置：**任选一个真实 provider 就绪**——其 `credential_env` 已设置（如 `LOCALMIND_GLM_API_KEY` / `LOCALMIND_DEEPSEEK_API_KEY`，按 §4.1 profile），`config/eval.example.toml` 切至该 provider 且 model 显式指定（如 `glm-4.7-flash`）。**验收对象是「底座 + 一个真实平台」的全链路，不是某个具体平台**：本契约的判据 provider 无关，provider 差异只体现在 `run_meta.config_snapshot.cloud_provider`（§9.3）；**不得**因平台更换而放宽或改写本节判据。
- 步骤（运行器按场景文件 stem **完整名**匹配，短 ID 会报 `scenario not found`）：`python scripts/run_p6_scenarios.py --scenario S10_forced_cloud --transcript` 真实跑通——S10 结构断言（`/cloud ask` → 云端链路触发 → 授权 → 本地回流）通过；随后 `--scenario S06_value_reasoning --variant both` 与 `--scenario S08_arch_tradeoff_value --variant both`（cloud_assisted 走该 provider，`local_reintegrate` 断言必须通过）。**2026-09-15 P6d 起追加**：按 08 §2.6 跑定向观测集（S05 / S09 / S11 的 base 各 3 run + S06 `cloud_auto` 3 run），观测验收性质与不进 pytest 的约定同 08 §2.6。
- **底座验收与语义结论分离**：S10（强制上云）是 P6c 底座的**阻塞验收**——它直接检验 GLM 全链路（profile 解析 → 授权 → 出站 → 响应解析 → 本地回流）。S06/S08 的通过还依赖本地意图收敛（是否真的请求云端——此前真实运行曾停在 RETRIEVE_MORE 未达云端）与本地回流质量，**不由底座单独决定**：S06/S08 必须运行并产出报告与 pair 评审产物；其语义结论失败时按 08 §7 证据驱动调整流程处理，不直接判 P6c 底座实现失败。
- 结果人工评审，按 08 §2.3 两级重复（首轮每变体 1 run 只立候选）；报告可按 run_meta 的 provider 标识区分 provider 代次（§9.3）。
- 不同 provider 的 run **不得**并为一对评审（G2 pair 的 A/B 是 local_only vs cloud_assisted，provider 必须同代次）。
- 单元测试一律不触网；真实 API 验证只通过评估运行器手动执行，pytest 集合不依赖任何真实云端或真实 Key。

### 9.3 评估记录联动（08 已同步两处）

- run_meta 的 `config_snapshot` 增加 `cloud_provider`（封闭枚举字符串，非敏感，可落盘）。
- 环境自检的凭据存在性检查改按活动 provider 的 `credential_env`（含 deepseek 兼容回退）判定。

---

## 10. Codex 待办（00-* 工程契约同步清单 + 实现清单）

> 按协作规范，00-* 归 Codex 维护；以下为本契约要求的同步项。接口意图（签名、语义）以本契约为准，Codex 落地为工程细节；实现细节如需偏离，先在 `specs/clarifications.md` 提出再动手。

**00-error-contract.md**
1. 新增 `CLOUD_AUTH_INVALID` / `CLOUD_ENDPOINT_INVALID` / `CLOUD_RATE_LIMITED` / `CLOUD_CREDENTIAL_MISSING` 四码（含义、recoverable、user_message 按 §6.1）。
2. `CLOUD_UNAVAILABLE` 语义收窄为「传输失败与 5xx」（表格行与 §4 `advise()` 传播规则同步）。

**00-core-interfaces.md**
3. §5 `CloudAdvisoryBackend` 实现清单更新：`NoopCloudAdvisoryBackend` / `OpenAICompatibleAdvisoryBackend`；移除 `DeepSeekAdvisoryBackend` 与从未实现的 `QianwenAdvisoryBackend` 条目。

**00-adapter-factory.md**
4. `create_cloud_advisory_backend()` 重写（§7.1 决策表）；`[cloud_advisory]` 配置结构换新形态（§5.1）并附 §5.3 迁移规则；bootstrap 校验顺序（§5.2 矩阵）。
5. `App` 构造说明中 `cloud_provider` 来源改为「解析后的 provider_id」；`PrivacyPolicy` 构造签名新增可选 `allowed_scope`（默认现值）。
6. `CloudProviderProfile` / `CloudProviderRegistry` / `CloudCredentialLoader` / `EnvCredentialLoader` 的文件位置与命名（建议 `src/adapters/cloud_profiles.py`、`src/adapters/openai_compat_adapter.py`，Codex 定）；Loader 镜像 §3.1 修订后的 `exists` + `get` 双方法签名。

**配置与脚本**
7. `config/default.toml`、`config/ollama.example.toml`、`config/eval.example.toml`、`config/cloud_advisory.example.toml` 更新为新形态（eval 模板按 §9.2 预置 glm + 显式 `glm-4.7-flash`；cloud_advisory 模板删除旧 `api_base`，规避 §5.3 `/v1` 例外；涉及缺省模型的同步为 §2.2 当前值）；`.env.example` 增加三个专属变量（移除或标注弃用 `LOCALMIND_CLOUD_API_KEY`，注明仅 deepseek 兼容回退）。
8. `scripts/run_p4.py`、`scripts/run_p6_scenarios.py` 的凭据自检/演示 Key 改走 profile.credential_env 链（§9.1 第 10 条）。

**测试与实现**
9. `tests/test_deepseek_adapter.py` 迁移为通用适配器参数化测试（deepseek/glm/custom_openai 三 profile）；新增 §9.1 全部用例。
10. 删除 `src/adapters/deepseek_adapter.py`（行为由通用适配器 + deepseek profile 承载）。
11. P7 待办登记：删除 deepseek 的 `LOCALMIND_CLOUD_API_KEY` 兼容回退（§4.3 时间盒）。

---

## 11. 验收标准（Done 定义）

1. §9.1 十二项测试全部存在且通过；全量 pytest 与 ruff 绿（不低于 P6b 现有基线）。
2. 迁移验证：仓库四份 config 与「旧变量 + deepseek」组合按 §5.3 迁移后行为正确。
3. 错配演练：GLM Key 仅配旧变量 + `provider="glm"` → 启动即 `CONFIG_ERROR` 且提示设置 `LOCALMIND_GLM_API_KEY`（演示或测试断言）。
4. 真实 GLM（阻塞项与观察项分离）：S10_forced_cloud 通过（**底座阻塞验收**）；S06_value_reasoning 与 S08_arch_tradeoff_value 双变体**必须运行并产出报告 / pair 评审产物**——其语义结论不作为底座 Done 条件，失败按 08 §7 证据驱动调整闭环处理（意图收敛质量与回流质量属于 P6 整体，不属于 provider 底座）。
5. 泄漏扫描：假 Key 标记不出现在任何事件/审计/错误/转录通道（§9.1 第 8 条）。
6. 安全零回退：§8 清单逐项核对通过；P4 安全链路 diff 为零（`PrivacyPolicy` 构造参数除外）。

---

## 12. 决策表

| 日期 | 裁决 | 理由 |
|---|---|---|
| 2026-09-13 | 新增 4 个稳定错误码而非按 HTTP 状态建码族；`CLOUD_UNAVAILABLE` 收窄不拆分「网络 vs 5xx」 | 用户可行动的根因只有四类（凭据/端点/限流/传输）；urllib 对 DNS/拒连/TLS 的区分不可靠，按不可靠信号拆码只会让映射表说谎 |
| 2026-09-13 | 凭据错配不做 Key 格式/前缀嗅探；错配的表现形式就是「专属变量缺失」 | Key 格式无稳定规范、嗅探必然误报；专属变量机制从结构上切断错配通道，fail-closed 提示足以引导用户 |
| 2026-09-13 | deepseek 保留 `LOCALMIND_CLOUD_API_KEY` 兼容回退（P7 删除）；glm/custom_openai 无回退 | 「既有配置不突然失效」只对曾合法工作的组合成立；对从未支持过的 provider 提供回退等于重建通用 Key 通道 |
| 2026-09-13 | 内置 provider 的 legacy `api_base` 与 profile 不一致时 `CONFIG_ERROR` 而非静默忽略 | api_base 决定数据去向（出站边界）；静默改道（代理↔官方）必须显式暴露 |
| 2026-09-13 | `max_turns` 不入新配置形态；预算唯一真源保持 `max_turns_per_task` | 现适配器的 `max_turns` 是存储即弃的死配置；引入第三名字会制造两源漂移 |
| 2026-09-13 | `[cloud_advisory.policy].allowed_scope` 引入并接通生效链路（PrivacyPolicy 构造新增可选参数） | 修正 P4 死配置（配置值被校验却从不使用、PrivacyPolicy 硬编码同值）；不接通的配置键是谎言；不影响 grant/fingerprint 语义 |
| 2026-09-13 | custom_openai 拒绝 loopback/私网/本地域名；DNS→私网解析残留明确记录不做 | 云端建议链路的信任/审计语义以外部服务为前提，本地推理属 ModelBackend 职责；用户本机自配凭据场景下解析期校验收益低、复杂度高，留待形态变化（多用户/托管）时按安全变更流程补 |
| 2026-09-13（实现前审查） | `temperature` 固定 `0.1`（原 0）；缺省模型更新为 `glm-4.7-flash` / `deepseek-v4-flash` | GLM 文档 temperature 取值 (0,1) 开区间，`0` 不合法；两平台旧缺省模型已弃用/不在现行枚举（Codex 引证官方文档核对）。0.1 跨平台合法且近确定；不做成 profile 能力字段（本阶段过重） |
| 2026-09-13（实现前审查） | system message 增加固定、provider 无关的 JSON 输出协议（仅 JSON / 字段清单 / 最小示例），不启用 `response_format` | 请求只发上下文却强制解析含 `analysis` 的 JSON，真实模型大概率自由文本 → 误判 `CLOUD_PARSE_ERROR`；提示词声明格式 + 给示例是 OpenAI 兼容各家的通行要求；协议是代码常量，不违反「provider 特有配置不进 payload」 |
| 2026-09-13（实现前审查） | `CloudCredentialLoader` 增 `exists()`；bootstrap/自检只调 `exists()`，`get()` 仅 advise 期 | 原单 `get()` 接缝使「启动期只查存在」与「凭据仅 advise 期读取」两条规则不可同时实现；两个能力本就是不同操作，接缝上分离而非放松任何一条 |
| 2026-09-13（实现前审查） | Done 拆分：S10 为底座阻塞验收；S06/S08 必须运行出报告、语义结论进 08 §7 调整闭环 | S06/S08 的通过还依赖本地意图收敛（曾真实停于 RETRIEVE_MORE 未达云端）与回流质量，绑进 provider 底座的 Done 会让验收长期不可判、把 P6 整体问题记到 provider 头上 |
| 2026-09-13（实现前审查） | 错误表 4xx 行补「429 除外」；迁移核对补 `cloud_advisory.example.toml`（其 `/v1` 旧值报 CONFIG_ERROR，模板同步重写不开静默归一口子）；运行器命令用完整场景 ID、`--first-round` 必带 `--all` | 表序笔误会把 429 先吞进端点错误；同主机别名也属改道，必须显式；后两项按运行器实际行为修正文档命令 |
| 2026-09-13（实现前审查 II） | 云端 POST 一律禁用自动重定向，任意 3xx → `CLOUD_ENDPOINT_INVALID` | urllib 默认 redirect 会复制 `Authorization` 到重定向目标，`302 → https://127.0.0.1/…` 即可绕过 §2.4 URL 校验并泄漏 Key；禁用比「逐跳重验 URL + 跨域剥离 header」更薄，且与固定端点设计一致——重定向不是需要支持的特性 |
| 2026-09-13（实现前审查 II） | `enabled=false` 一律注入 `NoopCloudAdvisoryBackend`（不再构造真实适配器）；连接配置校验照常执行 | 关闭云端必须是能力层 fail-closed，不能依赖调用方永远正确；校验与能力分离——配置错误仍在启动期暴露，但运行时不存在可外发对象。Noop 的占位建议（`云端咨询暂未启用。`）与禁用态语义天然一致 |
| 2026-09-13 | 适配器构造期不读 Key（延续 05 §7），bootstrap 期仅对 enabled=true 做凭据存在性检查 | 两者不矛盾：前者保证 disabled 可启动，后者把「配置了云但没配 Key」的失败从首次云端调用提前到启动，且消息可点名变量 |
| 2026-09-13 | 解析响应容忍 ```json 围栏 | GLM 实测常以围栏包裹 JSON；剥围栏是响应形态归一，不是启发式修复；避免首个真实 GLM run 死于解析 |
| 2026-09-13 | 不新增 provider 健康检查；`provider_available` 语义钉死为「安装级前提完整、可发起尝试」 | 08 决策表 2026-09-10 条（无网络探测）维持；真实可用性由首次调用与错误分类呈现 |
| 2026-09-13 | 禁止 `provider` 与 `backend` 并存冲突（不同即 CONFIG_ERROR） | 两配置源长期并存必然漂移；兼容映射一次性、可预测、P7 移除 |
