# 配置参考手册

## 配置系统架构

nanobot 使用 `pydantic-settings` 管理配置，支持两种配置来源：

1. **JSON 文件**: `~/.nanobot/config.json`（主配置）
2. **环境变量**: `NANOBOT_` 前缀，嵌套用 `__` 分隔（覆盖 JSON）

配置支持 **camelCase** 和 **snake_case** 两种命名风格（双向兼容）。

## 完整配置结构

```jsonc
{
  // ========== Agent 配置 ==========
  "agents": {
    "defaults": {
      "workspace": "~/.nanobot/workspace",  // 工作区路径
      "model": "anthropic/claude-opus-4-5",  // 默认模型
      "provider": "auto",                    // "auto" 或指定提供商名
      "maxTokens": 8192,                     // 最大输出 token 数
      "temperature": 0.1,                    // 温度
      "maxToolIterations": 40,               // 最大工具调用轮次
      "memoryWindow": 100                    // 触发记忆压缩的消息数
    }
  },

  // ========== LLM 提供商 ==========
  "providers": {
    // 自定义 OpenAI-compatible 端点（绕过 LiteLLM）
    "custom": {
      "apiKey": "",
      "apiBase": null,          // 必须指定，如 "http://localhost:8080/v1"
      "extraHeaders": null
    },

    // 标准提供商（只需 apiKey）
    "anthropic": { "apiKey": "sk-ant-..." },
    "openai": { "apiKey": "sk-..." },
    "deepseek": { "apiKey": "sk-..." },
    "gemini": { "apiKey": "..." },
    "groq": { "apiKey": "gsk_..." },
    "zhipu": { "apiKey": "..." },
    "dashscope": { "apiKey": "sk-..." },
    "moonshot": { "apiKey": "sk-..." },
    "minimax": { "apiKey": "..." },

    // 网关型（可路由任意模型）
    "openrouter": { "apiKey": "sk-or-..." },
    "aihubmix": {
      "apiKey": "...",
      "apiBase": "https://aihubmix.com/v1",
      "extraHeaders": { "APP-Code": "..." }  // AiHubMix 需要 APP-Code
    },
    "siliconflow": { "apiKey": "..." },
    "volcengine": { "apiKey": "..." },

    // 本地部署
    "vllm": {
      "apiKey": "dummy",               // 可以是任意值
      "apiBase": "http://localhost:8000/v1"
    },

    // OAuth 提供商（需要 nanobot provider login）
    "openaiCodex": {},
    "githubCopilot": {}
  },

  // ========== 聊天渠道 ==========
  "channels": {
    "sendProgress": true,       // 是否发送文本进度
    "sendToolHints": false,     // 是否发送工具调用提示

    "telegram": {
      "enabled": false,
      "token": "",              // @BotFather 获取的 Bot Token
      "allowFrom": [],          // 允许的用户 ID 或用户名
      "proxy": null,            // HTTP/SOCKS5 代理 URL
      "replyToMessage": false   // 回复时是否引用原消息
    },

    "discord": {
      "enabled": false,
      "token": "",              // Discord 开发者门户的 Bot Token
      "allowFrom": [],          // 允许的用户 ID
      "gatewayUrl": "wss://gateway.discord.gg/?v=10&encoding=json",
      "intents": 37377          // GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT
    },

    "feishu": {
      "enabled": false,
      "appId": "",              // 飞书开放平台 App ID
      "appSecret": "",          // App Secret
      "encryptKey": "",         // 事件订阅加密密钥（可选）
      "verificationToken": "",  // 验证 Token（可选）
      "allowFrom": [],          // 允许的用户 open_id
      "reactEmoji": "THUMBSUP"  // 消息反应 emoji
    },

    "dingtalk": {
      "enabled": false,
      "clientId": "",           // AppKey
      "clientSecret": "",       // AppSecret
      "allowFrom": []           // 允许的 staff_id
    },

    "slack": {
      "enabled": false,
      "mode": "socket",
      "botToken": "",           // xoxb-...
      "appToken": "",           // xapp-...
      "replyInThread": true,    // 在线程中回复
      "reactEmoji": "eyes",     // 处理中的 emoji 反应
      "groupPolicy": "mention", // "mention" | "open" | "allowlist"
      "groupAllowFrom": [],     // allowlist 模式的频道 ID
      "dm": {
        "enabled": true,
        "policy": "open",       // "open" | "allowlist"
        "allowFrom": []
      }
    },

    "whatsapp": {
      "enabled": false,
      "bridgeUrl": "ws://localhost:3001",
      "bridgeToken": "",        // Bridge 认证 token
      "allowFrom": []           // 允许的手机号
    },

    "email": {
      "enabled": false,
      "consentGranted": false,  // 必须设为 true 才能访问邮箱
      "imapHost": "",
      "imapPort": 993,
      "imapUsername": "",
      "imapPassword": "",
      "imapMailbox": "INBOX",
      "imapUseSsl": true,
      "smtpHost": "",
      "smtpPort": 587,
      "smtpUsername": "",
      "smtpPassword": "",
      "smtpUseTls": true,
      "smtpUseSsl": false,
      "fromAddress": "",
      "autoReplyEnabled": true,
      "pollIntervalSeconds": 30,
      "markSeen": true,
      "maxBodyChars": 12000,
      "subjectPrefix": "Re: ",
      "allowFrom": []
    },

    "qq": {
      "enabled": false,
      "appId": "",              // 机器人 AppID
      "secret": "",             // 机器人 AppSecret
      "allowFrom": []           // 允许的 openid
    },

    "matrix": {
      "enabled": false,
      "homeserver": "https://matrix.org",
      "accessToken": "",
      "userId": "",             // @bot:matrix.org
      "deviceId": "",
      "e2eeEnabled": true,      // 端到端加密
      "syncStopGraceSeconds": 2,
      "maxMediaBytes": 20971520, // 20MB
      "allowFrom": [],
      "groupPolicy": "open",   // "open" | "mention" | "allowlist"
      "groupAllowFrom": [],
      "allowRoomMentions": false
    },

    "mochat": {
      "enabled": false,
      "baseUrl": "https://mochat.io",
      "socketUrl": "",
      "socketPath": "/socket.io",
      "socketDisableMsgpack": false,
      "socketReconnectDelayMs": 1000,
      "socketMaxReconnectDelayMs": 10000,
      "socketConnectTimeoutMs": 10000,
      "refreshIntervalMs": 30000,
      "watchTimeoutMs": 25000,
      "watchLimit": 100,
      "retryDelayMs": 500,
      "maxRetryAttempts": 0,    // 0 = 无限重试
      "clawToken": "",
      "agentUserId": "",
      "sessions": [],
      "panels": [],
      "allowFrom": [],
      "mention": {
        "requireInGroups": false
      },
      "groups": {},             // {"group_id": {"requireMention": false}}
      "replyDelayMode": "non-mention",  // "off" | "non-mention"
      "replyDelayMs": 120000
    }
  },

  // ========== 网关配置 ==========
  "gateway": {
    "host": "0.0.0.0",
    "port": 18790,
    "heartbeat": {
      "enabled": true,
      "intervalS": 1800          // 30 分钟
    }
  },

  // ========== 工具配置 ==========
  "tools": {
    "restrictToWorkspace": false, // 是否限制工具只能访问 workspace
    "web": {
      "search": {
        "apiKey": "",            // Brave Search API key
        "maxResults": 5
      }
    },
    "exec": {
      "timeout": 60,             // Shell 命令超时（秒）
      "pathAppend": ""           // 追加到 PATH
    },
    "mcpServers": {
      // stdio 模式示例
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
        "env": {},
        "toolTimeout": 30
      },
      // HTTP 模式示例
      "remote-server": {
        "url": "https://mcp.example.com/sse",
        "headers": { "Authorization": "Bearer xxx" },
        "toolTimeout": 30
      }
    }
  }
}
```

## 环境变量覆盖

所有配置项都可以通过环境变量覆盖。前缀 `NANOBOT_`，嵌套用 `__` 分隔：

```bash
# Provider API keys
NANOBOT_PROVIDERS__ANTHROPIC__API_KEY=sk-ant-...
NANOBOT_PROVIDERS__OPENAI__API_KEY=sk-...
NANOBOT_PROVIDERS__DEEPSEEK__API_KEY=sk-...

# Agent 配置
NANOBOT_AGENTS__DEFAULTS__MODEL=openai/gpt-4o
NANOBOT_AGENTS__DEFAULTS__MAX_TOKENS=16384
NANOBOT_AGENTS__DEFAULTS__TEMPERATURE=0.2

# Gateway
NANOBOT_GATEWAY__PORT=18790
NANOBOT_GATEWAY__HEARTBEAT__ENABLED=true

# Channels
NANOBOT_CHANNELS__TELEGRAM__ENABLED=true
NANOBOT_CHANNELS__TELEGRAM__TOKEN=123456:ABC-DEF...

# Tools
NANOBOT_TOOLS__WEB__SEARCH__API_KEY=BSA...
NANOBOT_TOOLS__EXEC__TIMEOUT=120
```

## 配置文件位置

| 文件/目录 | 用途 |
|---|---|
| `~/.nanobot/config.json` | 主配置文件 |
| `~/.nanobot/workspace/` | 默认工作区 |
| `~/.nanobot/workspace/sessions/` | 会话 JSONL 文件 |
| `~/.nanobot/workspace/memory/MEMORY.md` | 长期记忆 |
| `~/.nanobot/workspace/memory/HISTORY.md` | 历史日志 |
| `~/.nanobot/workspace/skills/` | 自定义技能 |
| `~/.nanobot/workspace/AGENTS.md` | Agent 身份 |
| `~/.nanobot/workspace/SOUL.md` | Agent 人格 |
| `~/.nanobot/workspace/USER.md` | 用户信息 |
| `~/.nanobot/workspace/TOOLS.md` | 工具指南 |
| `~/.nanobot/workspace/HEARTBEAT.md` | 心跳任务 |
| `~/.nanobot/cron/jobs.json` | 定时任务数据 |
| `~/.nanobot/history/cli_history` | CLI 命令历史 |

## Provider 自动匹配规则

当 `provider: "auto"` 时，系统根据模型名自动选择提供商：

| 模型名包含 | 匹配到 |
|---|---|
| `claude` | anthropic |
| `gpt` | openai |
| `deepseek` | deepseek |
| `gemini` | gemini |
| `qwen` | dashscope |
| `kimi`, `moonshot` | moonshot |
| `glm`, `zhipu` | zhipu |
| `minimax` | minimax |
| `groq` | groq |
| `openai-codex` | openai_codex |
| `copilot` | github_copilot |

如果模型名带有明确的提供商前缀（如 `deepseek/deepseek-chat`），前缀匹配优先。

## Docker 环境变量映射

在 docker-compose.yml 中，通过 `environment` 传递配置：

```yaml
services:
  nanobot-gateway:
    environment:
      - NANOBOT_PROVIDERS__ANTHROPIC__API_KEY=${ANTHROPIC_API_KEY}
      - NANOBOT_CHANNELS__TELEGRAM__ENABLED=true
      - NANOBOT_CHANNELS__TELEGRAM__TOKEN=${TELEGRAM_BOT_TOKEN}
```

或直接挂载配置文件：

```yaml
volumes:
  - ~/.nanobot:/root/.nanobot
```
