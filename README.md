# LocalMind

LocalMind 是一个本地优先的个人办公智能体。它以本地模型作为主控，通过渐进式意图理解、项目与话题记忆、安全工具执行和受控云端协同，在终端中完成持续对话与办公任务。

当前版本聚焦两个核心方向：

- **渐进式理解**：模型可在最多四轮内部解析中检索记忆、识别缺失信息，并在必要时向用户追问。
- **本地与云端协同**：本地模型决定是否建议升级到更强的云端模型；发送前经过确定性脱敏、授权预览和用户确认，云端只提供建议，不能直接执行工具。

## 当前能力

- Ollama 本地主控模型（Mock 后端仅用于开发测试）
- 项目与话题记忆、关键词/向量混合检索，以及可选的 SQLite 持久化
- DeepSeek、智谱 GLM 或自定义 OpenAI 兼容云端提供商
- 工作区内文件读取、目录浏览、文件属性和受控写入
- PDF、DOCX、XLSX、PPTX、Markdown 和纯文本读取
- 工作区文件名与文本内容搜索
- 当前时间和天气查询
- MCP 工具提供商接入底座
- 危险操作拦截、敏感操作确认、路径逃逸防护和审计事件

联网搜索尚未启用，若要启用，参考后文联网搜索扩展说明。

## 环境要求

- Windows 10 或更高版本（当前主要验证平台）
- Python 3.11 或更高版本
- Git，用于克隆仓库和版本管理
- [Ollama](https://ollama.com/)，用于运行真实本地模型

安装前先打开 PowerShell，确认 Python 和 Git 可用：

```powershell
python --version
git --version
```

`python --version` 应显示 3.11 或更高版本。若命令不存在，请先从 [Python 官网](https://www.python.org/downloads/windows/) 安装，并在安装器中勾选 **Add Python to PATH**；Git 可从 [Git for Windows](https://git-scm.com/download/win) 安装。安装后重新打开 PowerShell 再检查版本。

## 从零开始安装

以下命令都应在项目根目录的 PowerShell 中执行。

### 1. 创建 Python 虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

这些命令依次完成：

1. 在项目内创建独立的 `.venv` Python 环境，避免污染系统 Python。
2. 激活该环境；成功后命令行开头通常会出现 `(.venv)`。
3. 升级虚拟环境里的包管理器 `pip`。

如果 PowerShell 提示禁止运行脚本，可只对当前终端临时放行，然后重新激活：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

关闭该 PowerShell 窗口后，临时策略自动失效。

### 2. 安装项目依赖

仅使用 LocalMind：

```powershell
python -m pip install -e .
```

参与开发并运行 pytest、ruff、mypy：

```powershell
python -m pip install -e ".[dev]"
```

`-e` 表示以可编辑模式安装项目，之后修改源码不需要重复安装。运行依赖包括 PDF、Word、Excel 和 PowerPoint 文档解析库；`[dev]` 额外安装测试、代码检查和类型检查工具。

可用下面的命令确认 LocalMind 能被 Python 导入：

```powershell
python -c "import src; print('LocalMind Python environment OK')"
```

## 安装和准备 Ollama

LocalMind 的正常使用形态是：Ollama 本地模型负责理解、记忆和决策，在本地能力不足且满足安全条件时请求云端模型协助。Mock 只用于开发测试，不能代替真实协同体验。

### 1. 安装 Ollama

推荐打开 [Ollama Windows 官方下载页](https://ollama.com/download/windows)，下载并运行 `OllamaSetup.exe`。也可以使用官方 PowerShell 安装命令：

```powershell
irm https://ollama.com/install.ps1 | iex
```

安装完成后重新打开 PowerShell，检查命令是否可用：

```powershell
ollama --version
```

Windows 版 Ollama 通常会在后台启动，并在 `http://localhost:11434` 提供本地 API。检查服务：

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

如果返回模型列表或空的 `models` 列表，说明服务已连通。如果连接失败，先从开始菜单启动 Ollama；仍未启动时可在单独的 PowerShell 窗口运行：

```powershell
ollama serve
```

保持该窗口运行，再回到项目窗口继续操作。

### 2. 下载本地模型

LocalMind 的示例配置使用 `qwen3:4b`：

```powershell
ollama pull qwen3:4b
ollama list
```

`ollama pull` 会下载模型，所需时间取决于网络；`ollama list` 用于确认本机已有 `qwen3:4b`。随后进行一次不经过 LocalMind 的模型冒烟测试：

```powershell
ollama run qwen3:4b "请只回答：模型已就绪"
```

能得到文本回复即表示模型可以使用。模型文件由 Ollama 管理，不需要复制到 LocalMind 项目目录。

## 配置 LocalMind

### 1. 创建本地配置

不要直接修改仓库里的示例文件，先复制一份本机配置：

```powershell
Copy-Item config\ollama.example.toml config\local.toml
New-Item -ItemType Directory -Force data\workspace
```

`config/local.toml` 和 `data/` 中的运行数据已被 Git 忽略，不会被正常提交。常用配置项：

- `model_backend.config.model`：Ollama 模型名，必须与 `ollama list` 中的名称一致。
- `model_backend.config.base_url`：Ollama 地址，本机默认是 `http://localhost:11434`。
- `model_backend.config.num_ctx`：本地模型上下文长度；越大通常占用越多内存。
- `tools.workspace_root`：文件工具允许访问的唯一工作区，默认是 `./data/workspace`。
- `memory_backend.type`：示例默认使用内存记忆；需要跨进程保留时可参考 `config/p2_sqlite.example.toml`。
- `cloud_advisory`：云端协同提供商、模型、授权和上下文预算配置。

### 2. 配置云端协同

`config/ollama.example.toml` 已同时启用 Ollama 本地主控和 DeepSeek 云端协同。默认关键配置如下：

```toml
[cloud_advisory]
enabled = true
provider = "deepseek"

[cloud_advisory.connection]
model = "deepseek-v4-flash"
request_timeout_seconds = 60
```

项目也支持 `glm` 和 `custom_openai`。普通用户只需选择一个云端提供商，并设置它对应的环境变量；不要同时配置多个 key，也不要把密钥写进 TOML、源码或 Git 仓库。

当前 PowerShell 窗口临时设置 DeepSeek key：

```powershell
$env:LOCALMIND_DEEPSEEK_API_KEY = "your-key"
```

需要保存为当前 Windows 用户的持久变量时：

```powershell
[Environment]::SetEnvironmentVariable(
    "LOCALMIND_DEEPSEEK_API_KEY",
    "your-key",
    "User"
)
```

持久变量设置后需要关闭并重新打开 PowerShell。只检查变量是否存在，不要把完整密钥打印到终端：

```powershell
if ($env:LOCALMIND_DEEPSEEK_API_KEY) { "DeepSeek key is set" } else { "DeepSeek key is missing" }
```

使用其他提供商时，对应关系为：

| `provider` | 环境变量 | 用途 |
|---|---|---|
| `deepseek` | `LOCALMIND_DEEPSEEK_API_KEY` | DeepSeek API |
| `glm` | `LOCALMIND_GLM_API_KEY` | 智谱 GLM API |
| `custom_openai` | `LOCALMIND_CUSTOM_OPENAI_API_KEY` | 自定义 OpenAI 兼容 API |

项目直接读取进程环境变量，不会自动读取 `.env` 文件。

## 首次启动

确认 Ollama 服务正在运行、`qwen3:4b` 已下载、云端 key 已设置后，启动完整的本地—云端协同 Agent：

```powershell
python -m src.cli --config config\local.toml
```

看到 `LocalMind 已启动` 后，建议按下面的顺序验证：

1. 输入 `你好，请介绍一下你自己`：验证本地主控模型能够完成普通对话。
2. 输入 `现在几点`：验证本地主控能够选择并调用只读时间工具。
3. 输入 `今天南京天气怎么样`：验证能力路由、天气工具和结果回流。
4. 输入 `/cloud ask 请比较两种复杂架构方案，并说明选择依据`：显式触发一次云端协同链路。
5. 查看终端展示的脱敏后待发送内容；确认无误后输入 `/cloud allow`，验证云端建议能回到本地主控并形成最终回答。
6. 把一个 TXT、Markdown、PDF 或 DOCX 文件放进 `data/workspace`，再问 `读取 xxx 文件并概括内容`：验证工作区与文档读取。

`/cloud ask` 只用于首次安装时明确验证云端链路。正常对话中不必每次输入该命令：本地主控会根据任务复杂度、理解状态、风险和云端可用性决定是否提出云端协同；需要外发内容时仍会显示预览并等待用户授权。

遇到敏感写入或云端外发时，LocalMind 会先展示确认信息；未确认前不会执行对应操作。

常用 CLI 命令：

- `/status`：显示当前项目、话题和待确认状态
- `/why`：解释最近一次决策
- `/trace on|off`：开关详细运行轨迹
- `/projects`、`/topics`：查看项目和话题
- `/switch <项目名>`：切换或创建项目
- `/cloud allow`、`/cloud deny`：批准或拒绝待发送的云端咨询
- `/quit`：完成会话摘要收尾并退出；内存模式下退出后不会保留

### 当前记忆模式

示例配置默认使用内存记忆。对话、会话摘要和项目状态只在本次 CLI 进程中有效，关闭终端或退出程序后会被清除；这也是当前推荐的普通使用方式，避免历史内容长期累积且缺少方便的删除入口。

项目已经提供 SQLite 持久化后端，可参考 `config/p2_sqlite.example.toml` 启用，但它目前属于可选的开发能力：历史会持续写入数据库，尚未提供类似聊天产品的会话列表、按会话删除、项目摘要回收和临时会话管理界面。启用前应了解这些限制，不要把“能够写入 SQLite”理解为完整的长期记忆管理功能。

当前的“话题”表示同一终端会话内的内容分段，不是多个可并行打开和切换的独立聊天。`/topics` 只用于查看本次会话的话题轨迹。

## 工作区文件

文件工具只能访问配置项 `tools.workspace_root` 指定的目录，默认是 `data/workspace`。需要读取或搜索的文档应先放入该目录，例如：

```powershell
Copy-Item "C:\Users\你的用户名\Desktop\报告.docx" data\workspace\
```

然后在 CLI 中输入 `读取报告.docx并概括内容`。CLI 当前只接收文本输入，不提供文件上传控件；终端里输入一个工作区外的绝对路径也不会绕过工作区边界。

## 联网搜索扩展说明

LocalMind 当前有天气查询等用途固定的联网工具，但**尚未实现通用网页搜索工具**。云端大模型协同也不等于联网搜索：云端模型是否掌握最新资料取决于提供商能力，LocalMind 目前不会把它的回答标记成“已经检索过网页”。

因此，当前版本不能通过增加一个 API key 或修改 TOML 直接获得 `web.search`。后续若接入通用搜索，建议保留统一的 `SearchProvider` 接口，让 Agent 上层只认识一个 `web.search` 工具，底层再选择 SearXNG 或托管搜索 API：

```text
用户请求
  -> LocalMind 能力路由
  -> web.search
  -> SearchProvider
       -> 自建 SearXNG
       -> 托管搜索 API
  -> 统一的标题、链接、摘要和来源时间
```

### 方案一：自建 SearXNG

[SearXNG](https://docs.searxng.org/) 是可自行部署的元搜索引擎。LocalMind 将查询发送到用户自己的 SearXNG 服务，由 SearXNG 再向其启用的搜索引擎聚合结果。

特点：

- LocalMind 不需要购买单独的搜索 API key，也不按 LocalMind 查询次数向某个 API 提供商付费。
- 搜索服务和配置由用户控制，可在本机或自己的服务器运行。
- 它并不是“完全离线搜索”：查询仍会由 SearXNG 发往所配置的上游搜索引擎。
- 用户需要安装 Docker 或 Podman、运行并维护 SearXNG，部署成本高于填写 API key。
- 不建议默认使用互联网上的随机公共实例；它们的稳定性、隐私策略和 JSON API 可用性无法由 LocalMind 保证。

官方推荐使用容器或安装脚本部署，详细步骤见 [SearXNG 容器安装文档](https://docs.searxng.org/admin/installation-docker)。LocalMind 适配器将使用 SearXNG 的 `/search` HTTP 接口，并请求 `format=json`；SearXNG 必须在 `settings.yml` 中启用 JSON 输出，否则接口可能返回 `403`。参数和返回格式见 [SearXNG Search API 文档](https://docs.searxng.org/dev/search_api)。

真正接入 LocalMind 时仍需实现以下代码，而不只是启动 SearXNG：

1. 实现 `SearXNGSearchProvider`，负责请求、超时、响应大小限制和结果解析。
2. 注册 `web.search` 工具及其能力声明，并加入配置白名单。
3. 校验 SearXNG 地址，禁止任意 URL、重定向和非预期主机造成 SSRF。
4. 搜索词外发前执行敏感信息检查，审计日志不保存完整查询原文。
5. 把不同搜索引擎的结果归一化为固定结构，再交给本地主控总结。

### 方案二：托管搜索 API

也可以接入提供 JSON 搜索接口的托管服务。用户在服务商处申请 key，LocalMind 通过对应 adapter 调用服务。

特点：

- 不需要安装和维护 Docker 服务，通常配置更简单、稳定性更高。
- 可能提供搜索时间范围、地区、语言和结果排序等附加能力。
- 免费额度、计费方式、速率限制和数据保留策略由各服务商决定，可能随时变化。
- 搜索词会发送给第三方服务，必须阅读其隐私政策，并避免提交口令、密钥和不应外发的文档内容。

接入时应为每个服务商单独实现 provider adapter，并从专属环境变量读取 API key；不能把 key 写入 `config/local.toml`。上层 `web.search` 的参数和返回结构保持不变，这样以后切换服务商不需要改 IntentResolver、ControlPolicy 或工具编排逻辑。

### 两种方案共同的安全要求

无论采用 SearXNG 还是托管 API，后续实现都应满足：

- `web.search` 明确标记为外网出站工具，不能伪装成本地检索。
- 查询必须来自用户本轮输入，不允许模型凭空拼接密钥、个人信息或整段私有文档。
- 设置连接超时、读取超时、最大响应字节数和最大结果数；超限时失败，不静默截断成误导性答案。
- 拒绝 HTTP 重定向，配置的 endpoint 必须经过确定性校验。
- 返回结果只作为外部资料，不自动视为可信事实；回答应保留来源链接。
- provider 未配置、不可达或额度耗尽时，明确告诉用户本轮没有完成联网搜索。
- 通用网页正文抓取应作为独立的 `web.fetch` 工具设计，额外处理 URL allowlist、内网地址、下载类型和正文大小，不能顺便塞进 `web.search`。

## 验证

以下命令面向开发者和交付验收，不是普通使用的启动方式：

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```

场景评估可通过以下命令运行：

```powershell
python scripts\run_p6_scenarios.py --all
python scripts\p6_report.py
```

需要排查 Python/CLI 环境、且暂时不调用任何真实模型时，才使用 Mock 配置：

```powershell
python -m src.cli --config config\default.toml
```

Mock 回复是固定测试数据，只能证明工程入口可运行，不能验证渐进式理解或本地—云端协同效果。

## 常见问题

### `python`、`git` 或 `ollama` 不是可识别的命令

安装程序尚未加入 PATH，或者当前终端没有读取到新 PATH。关闭全部 PowerShell 窗口并重新打开；仍然失败时重新安装对应程序并启用 PATH 选项。

### 无法激活 `.venv`

先执行本 README 前面的 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`。也可以不激活虚拟环境，直接使用：

```powershell
.\.venv\Scripts\python.exe -m src.cli --config config\local.toml
```

### LocalMind 报 Ollama 不可用或连接超时

依次检查：

```powershell
ollama --version
Invoke-RestMethod http://localhost:11434/api/tags
ollama list
```

第一条检查安装，第二条检查本地服务，第三条检查模型。若模型名称不同，应同步修改 `config/local.toml` 的 `model_backend.config.model`。

### 启动时报缺少 Python 模块

确认当前命令行开头有 `(.venv)`，然后重新安装依赖：

```powershell
python -m pip install -e ".[dev]"
```

### 云端模型提示缺少 API key

确认配置中的 `provider` 与环境变量匹配，并在设置持久用户变量后重新打开 PowerShell。DeepSeek、GLM、custom OpenAI 分别读取不同变量，不能混用。

### 工作区文件读取或文件搜索提示找不到文件

确认文件位于 `tools.workspace_root` 下，并从工作区根目录写相对路径。默认配置下，应把文件放在 `data/workspace`。

## 已知限制

- 小型本地模型的理解和生成质量受模型能力与上下文窗口限制。
- 天气工具依赖 Open-Meteo 网络服务；项目没有通用网页搜索能力。
- 文档工具只读取已放入工作区的本地文件，不会修改 Office 文档。
- MCP 已具备受控接入协议和演示服务，但未宣称兼容所有第三方 MCP 服务。
- 这是命令行优先版本，尚无图形界面和文件上传入口。

## 架构文档

- [需求说明](requirements.md)
- [项目报告](project-report.md)
- [模块契约](specs/modules/)
