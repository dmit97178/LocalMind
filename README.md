# LocalMind

LocalMind 是一个本地优先的个人办公智能体。它以本地模型作为主控，通过渐进式意图理解、项目与话题记忆、安全工具执行和可选的云端协同，在终端中完成持续对话与办公任务。

当前版本聚焦两个核心方向：

- **渐进式理解**：模型可在最多四轮内部解析中检索记忆、识别缺失信息，并在必要时向用户追问。
- **本地与云端协同**：本地模型决定是否建议升级到更强的云端模型；发送前经过确定性脱敏、授权预览和用户确认，云端只提供建议，不能直接执行工具。

## 当前能力

- Ollama 本地模型或 Mock 后端
- SQLite 项目记忆、话题跟踪和关键词/向量混合检索
- DeepSeek、智谱 GLM 或自定义 OpenAI 兼容云端提供商
- 工作区内文件读取、目录浏览、文件属性和受控写入
- PDF、DOCX、XLSX、PPTX、Markdown 和纯文本读取
- 工作区文件名与文本内容搜索
- 当前时间和天气查询
- MCP 工具提供商接入底座
- 危险操作拦截、敏感操作确认、路径逃逸防护和审计事件

当前不包含通用联网搜索。专家模型调度和自进化模块也尚未启用。

## 环境要求

- Python 3.11 或更高版本
- 使用真实本地模型时需要 [Ollama](https://ollama.com/)
- Windows 是当前主要验证平台

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

准备本地模型：

```powershell
ollama pull qwen3:4b
Copy-Item config\ollama.example.toml config\local.toml
```

根据机器情况编辑 `config/local.toml` 中的模型名、上下文长度和工作区路径。`config/local.toml` 已被 Git 忽略。

## 启动

```powershell
python -m src.cli --config config\local.toml
```

不安装 Ollama 时，也可以用默认 Mock 配置检查程序是否正常启动：

```powershell
python -m src.cli --config config\default.toml
```

常用 CLI 命令：

- `/status`：显示当前项目、话题和待确认状态
- `/why`：解释最近一次决策
- `/trace on|off`：开关详细运行轨迹
- `/projects`、`/topics`：查看项目和话题
- `/switch <项目名>`：切换或创建项目
- `/cloud allow`、`/cloud deny`：批准或拒绝待发送的云端咨询
- `/quit`：保存会话摘要并退出

## 工作区文件

文件工具只能访问配置项 `tools.workspace_root` 指定的目录，默认是 `data/workspace`。需要读取或搜索的文档应先放入该目录；CLI 当前只接收文本输入，不提供文件上传控件。

## 可选云端协同

默认 Mock 配置关闭云端；`config/ollama.example.toml` 作为完整交互示例启用了 DeepSeek。使用该示例时需要提供凭据，不需要云端时可将 `cloud_advisory.enabled` 设为 `false`、`provider` 设为 `noop`。启用云端时，通过操作系统环境变量提供对应凭据：

```powershell
$env:LOCALMIND_DEEPSEEK_API_KEY = "your-key"
$env:LOCALMIND_GLM_API_KEY = "your-key"
$env:LOCALMIND_CUSTOM_OPENAI_API_KEY = "your-key"
```

只需设置实际使用的提供商变量。不要把密钥写进 TOML、源码或 Git 仓库。项目不会自动读取 `.env` 文件。

## 验证

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

## 已知限制

- 小型本地模型的理解和生成质量受模型能力与上下文窗口限制。
- 天气工具依赖 Open-Meteo 网络服务；项目没有通用网页搜索能力。
- 文档工具只读取已放入工作区的本地文件，不会修改 Office 文档。
- MCP 已具备受控接入协议和演示服务，但未宣称兼容所有第三方 MCP 服务。
- 这是命令行优先版本，尚无图形界面和文件上传入口。

## 架构文档

- [需求说明](specs/requirements.md)
- [项目计划](specs/project-plan.md)
- [模块契约](specs/modules/)
