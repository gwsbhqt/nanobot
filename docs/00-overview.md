# Nanobot 系统全景概览

## 一句话定义

**nanobot** 是一个超轻量级的个人 AI 助手框架（核心代码约 4000 行），将多个 LLM 后端与多个聊天平台桥接在一起，通过统一的 Agent Loop 提供工具调用、记忆管理、定时任务等能力。

## 项目基本信息

| 项目 | 值 |
|---|---|
| PyPI 包名 | `nanobot-ai` |
| 版本 | `0.1.4.post3` |
| 协议 | MIT |
| Python | >= 3.11 |
| 构建系统 | Hatchling |
| CLI 入口 | `nanobot` (Typer) |
| 配置路径 | `~/.nanobot/config.json` |
| 工作区 | `~/.nanobot/workspace/` |

## 技术栈一览

| 层级 | 技术 |
|---|---|
| 语言 | Python 3.11+ |
| LLM 路由 | LiteLLM（主路径）+ 自定义直连 |
| 配置/校验 | Pydantic v2 + pydantic-settings |
| CLI | Typer |
| TUI/输出 | Rich + prompt-toolkit |
| 定时调度 | croniter |
| MCP 协议 | mcp >= 1.26.0 |
| WhatsApp 桥接 | Node.js 20 + TypeScript + @whiskeysockets/baileys |
| 代码检查 | ruff |
| 测试 | pytest + pytest-asyncio |
| 容器化 | Docker (uv/Python 3.12), docker-compose |

## 支持的 LLM 提供商（17 个）

**网关型（可路由任意模型）：**
OpenRouter, AiHubMix, SiliconFlow（硅基流动）, VolcEngine（火山引擎）

**标准提供商：**
Anthropic, OpenAI, DeepSeek, Gemini, Zhipu AI（智谱）, DashScope（通义千问）, Moonshot（Kimi）, MiniMax, Groq

**OAuth 提供商：**
OpenAI Codex, GitHub Copilot

**本地部署：**
vLLM（兼容任何 OpenAI-compatible 本地服务）

**自定义：**
Custom（任意 OpenAI-compatible 端点，绕过 LiteLLM）

## 支持的聊天渠道（10 个）

| 渠道 | 协议 | 特殊依赖 |
|---|---|---|
| Telegram | python-telegram-bot + 长轮询 | Groq Whisper 语音转文字 |
| Discord | 原生 WebSocket | 无 |
| Feishu（飞书） | lark-oapi SDK WebSocket 长连接 | 无 |
| DingTalk（钉钉） | dingtalk-stream SDK | 无 |
| Slack | slack-sdk Socket Mode | 无 |
| WhatsApp | WebSocket 连接 Node.js 桥接进程 | bridge/ (Baileys) |
| Email | IMAP 轮询 + SMTP 发送 | 无 |
| QQ | qq-botpy SDK | 无 |
| Matrix | matrix-nio + E2EE | 可选依赖 `[matrix]` |
| Mochat | python-socketio Socket.IO | 无 |

## 两种运行模式

### CLI 模式（`nanobot agent`）
单次交互或交互式对话。适合开发调试。

```bash
nanobot agent                  # 交互式 REPL
nanobot agent -m "Hello"       # 单次对话
```

### Gateway 模式（`nanobot gateway`）
长驻进程，同时运行所有已启用的 Channel + Agent Loop + Cron + Heartbeat。适合生产部署。

```bash
nanobot gateway                # 启动常驻网关
```

## 快速启动

```bash
# 1. 安装
pip install nanobot-ai
# 或
uv pip install nanobot-ai

# 2. 初始化配置
nanobot onboard

# 3. 交互式测试
nanobot agent

# 4. 查看状态
nanobot status

# 5. 启动网关（生产模式）
nanobot gateway
```

## 核心 CLI 命令

| 命令 | 用途 |
|---|---|
| `nanobot onboard` | 初始化 `~/.nanobot/config.json` 和工作区 |
| `nanobot agent` | CLI 交互模式 |
| `nanobot agent -m "..."` | 单次对话 |
| `nanobot gateway` | 启动常驻网关 |
| `nanobot status` | 查看配置和 API key 状态 |
| `nanobot cron add/list/remove` | 管理定时任务 |
| `nanobot provider login <name>` | OAuth 登录（codex/copilot）|
| `nanobot channels login` | WhatsApp QR 码扫描 |

## 目录结构

```
nanobot/
├── nanobot/                    # 主 Python 包
│   ├── __main__.py             # python -m nanobot 入口
│   ├── cli/
│   │   └── commands.py         # Typer CLI（1096 行，最大文件之一）
│   ├── agent/                  # 核心 Agent 引擎
│   │   ├── loop.py             # AgentLoop - 核心处理引擎
│   │   ├── context.py          # ContextBuilder - 上下文组装
│   │   ├── memory.py           # MemoryStore - 双层记忆
│   │   ├── skills.py           # SkillsLoader - 技能加载
│   │   ├── subagent.py         # SubagentManager - 子代理
│   │   └── tools/              # 工具系统
│   │       ├── base.py         # Tool 抽象基类
│   │       ├── registry.py     # ToolRegistry - 动态注册
│   │       ├── filesystem.py   # 文件操作工具
│   │       ├── shell.py        # Shell 命令执行
│   │       ├── web.py          # Web 搜索/抓取
│   │       ├── message.py      # 消息发送工具
│   │       ├── spawn.py        # 子代理生成
│   │       ├── cron.py         # 定时任务工具
│   │       └── mcp.py          # MCP 协议集成
│   ├── providers/              # LLM 提供商
│   │   ├── base.py             # LLMProvider 抽象基类
│   │   ├── registry.py         # ProviderSpec 注册表（单一事实来源）
│   │   ├── litellm_provider.py # LiteLLM 多提供商路由
│   │   ├── custom_provider.py  # 直连 OpenAI-compatible
│   │   ├── openai_codex_provider.py  # Codex OAuth + SSE
│   │   └── transcription.py    # Groq Whisper 语音转文字
│   ├── channels/               # 聊天渠道适配器
│   │   ├── base.py             # BaseChannel 抽象基类
│   │   ├── manager.py          # ChannelManager 编排器
│   │   ├── telegram.py         # Telegram
│   │   ├── discord.py          # Discord
│   │   ├── feishu.py           # 飞书
│   │   ├── dingtalk.py         # 钉钉
│   │   ├── slack.py            # Slack
│   │   ├── whatsapp.py         # WhatsApp（需 Node.js 桥接）
│   │   ├── email.py            # Email (IMAP/SMTP)
│   │   ├── qq.py               # QQ
│   │   ├── matrix.py           # Matrix (E2EE)
│   │   └── mochat.py           # Mochat/Claw IM
│   ├── bus/                    # 消息总线
│   │   ├── events.py           # InboundMessage / OutboundMessage
│   │   └── queue.py            # MessageBus (async 队列)
│   ├── session/
│   │   └── manager.py          # Session + SessionManager (JSONL)
│   ├── config/
│   │   ├── schema.py           # Pydantic 配置 Schema
│   │   └── loader.py           # 配置文件加载
│   ├── cron/
│   │   ├── service.py          # CronService 定时任务
│   │   └── types.py            # CronJob 数据类型
│   ├── heartbeat/
│   │   └── service.py          # HeartbeatService 心跳
│   ├── utils/
│   │   └── helpers.py          # 工具函数
│   ├── templates/              # 引导模板文件
│   │   ├── AGENTS.md           # Agent 身份定义
│   │   ├── SOUL.md             # Agent 人格
│   │   ├── USER.md             # 用户信息
│   │   ├── TOOLS.md            # 工具使用指南
│   │   ├── HEARTBEAT.md        # 心跳任务定义
│   │   └── memory/MEMORY.md    # 初始记忆
│   └── skills/                 # 内置技能
│       ├── clawhub/            # ClawHub 集成
│       ├── cron/               # 定时任务技能
│       ├── github/             # GitHub 操作
│       ├── memory/             # 记忆管理
│       ├── skill-creator/      # 技能创建器
│       ├── summarize/          # 内容摘要
│       ├── tmux/               # tmux 会话管理
│       └── weather/            # 天气查询
├── bridge/                     # Node.js WhatsApp 桥接
│   ├── src/
│   │   ├── whatsapp.ts         # Baileys WhatsApp 客户端
│   │   ├── server.ts           # WebSocket 桥接服务器
│   │   └── index.ts            # 入口
│   ├── package.json
│   └── tsconfig.json
├── tests/                      # 测试套件（15 个文件）
├── Dockerfile                  # 单镜像构建
├── docker-compose.yml          # 两服务编排
├── pyproject.toml              # 项目元数据和依赖
└── README.md                   # 项目文档（1089 行）
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [01-architecture.md](./01-architecture.md) | 系统架构和数据流 |
| [02-providers.md](./02-providers.md) | LLM 提供商系统详解 |
| [03-channels.md](./03-channels.md) | 聊天渠道系统详解 |
| [04-agent-core.md](./04-agent-core.md) | Agent 引擎、工具、记忆、技能 |
| [05-config-reference.md](./05-config-reference.md) | 配置参考手册 |
| [06-deployment.md](./06-deployment.md) | 部署和运维 |
| [07-extension-guide.md](./07-extension-guide.md) | 二次开发扩展指南 |
