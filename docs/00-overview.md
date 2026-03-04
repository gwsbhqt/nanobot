# Nanobot 系统全景概览

## 一句话定义

nanobot 是一个轻量个人 AI 助手框架：通过统一 Agent Loop，把 LLM 能力接入到 Feishu 渠道，并提供工具调用、记忆压缩、定时任务等能力。

## 项目基本信息

| 项目 | 值 |
|---|---|
| PyPI 包名 | `nanobot-ai` |
| 版本 | `0.1.4.post3` |
| Python | `>=3.11` |
| CLI 入口 | `nanobot` |
| 配置路径 | `~/.nanobot/config.json` |
| 工作区 | `~/.nanobot/workspace/` |

## 技术栈

| 层级 | 技术 |
|---|---|
| LLM 路由 | LiteLLM + OpenRouter |
| 配置 | Pydantic v2 + pydantic-settings |
| CLI | Typer + Rich + prompt-toolkit |
| 渠道 | Feishu (`lark-oapi`) |
| 调度 | croniter |
| 工具协议 | MCP (`mcp>=1.26.0`) |
| 测试 | pytest + pytest-asyncio |

## 当前能力边界

- LLM Provider：仅 `openrouter`
- IM 渠道：仅 `feishu`
- 持久化：文件系统（JSON/JSONL/Markdown）
- 运行模式：`nanobot agent` / `nanobot gateway`

## 核心 CLI 命令

| 命令 | 用途 |
|---|---|
| `nanobot onboard` | 初始化配置与工作区 |
| `nanobot agent` | CLI 交互模式 |
| `nanobot agent -m "..."` | 单次对话 |
| `nanobot gateway` | 启动常驻网关 |
| `nanobot status` | 查看模型与 provider 状态 |
| `nanobot channels status` | 查看飞书渠道状态 |
| `nanobot cron add/list/remove` | 管理定时任务 |

## 目录结构

```
nanobot/
├── nanobot/
│   ├── cli/
│   │   └── commands.py
│   ├── agent/
│   │   ├── loop.py
│   │   ├── context.py
│   │   ├── memory.py
│   │   └── tools/
│   ├── providers/
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── litellm_provider.py
│   ├── channels/
│   │   ├── base.py
│   │   ├── manager.py
│   │   └── feishu.py
│   ├── bus/
│   ├── config/
│   ├── cron/
│   ├── heartbeat/
│   ├── session/
│   ├── templates/
│   └── skills/
├── docs/
├── tests/
└── pyproject.toml
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [01-architecture.md](./01-architecture.md) | 系统架构与数据流 |
| [02-providers.md](./02-providers.md) | OpenRouter Provider 细节 |
| [03-channels.md](./03-channels.md) | Feishu 渠道实现 |
| [04-agent-core.md](./04-agent-core.md) | Agent / Tool / Memory |
| [05-config-reference.md](./05-config-reference.md) | 配置字段说明 |
| [06-deployment.md](./06-deployment.md) | 部署与运维 |
| [07-extension-guide.md](./07-extension-guide.md) | 扩展开发指南 |
