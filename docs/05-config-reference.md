# 配置参考手册

## 配置来源

nanobot 使用 `pydantic-settings`，支持两种来源：

1. `~/.nanobot/config.json`
2. `NANOBOT_` 前缀环境变量（`__` 表示层级）

支持 camelCase 与 snake_case 键名。

## 当前配置结构（简化）

```jsonc
{
  "agents": {
    "defaults": {
      "workspace": ".nanobot/workspace",
      "provider": "openrouter",
      "model": "google/gemini-3.1-flash-lite-preview", // 兼容字段
      "simpleModel": "google/gemini-2.5-flash-lite-preview-09-2025",
      "complexModel": "google/gemini-3.1-flash-lite-preview",
      "modelRouting": "auto", // auto | simple | complex
      "maxTokens": 8192,
      "temperature": 0.1,
      "maxToolIterations": 40,
      "memoryWindow": 100,
      "reasoningEffort": null
    }
  },
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-...",
      "apiBase": null,
      "proxy": null,
      "extraHeaders": null
    }
  },
  "channels": {
    "sendProgress": true,
    "sendToolHints": false,
    "feishu": {
      "enabled": false,
      "appId": "",
      "appSecret": "",
      "encryptKey": "",
      "verificationToken": "",
      "allowFrom": [],
      "reactEmoji": "THUMBSUP"
    }
  },
  "gateway": {
    "host": "0.0.0.0",
    "port": 18790,
    "heartbeat": {
      "enabled": true,
      "intervalS": 1800
    }
  },
  "tools": {
    "restrictToWorkspace": false,
    "web": {
      "proxy": null,
      "search": {
        "apiKey": "",
        "maxResults": 5
      }
    },
    "exec": {
      "timeout": 60,
      "pathAppend": ""
    },
    "mcpServers": {}
  }
}
```

## 双模型路由

- `modelRouting = "auto"`：默认先用 `simpleModel`，需要时自动升级到 `complexModel`
- `modelRouting = "simple"`：始终用 `simpleModel`
- `modelRouting = "complex"`：始终用 `complexModel`

## Provider 匹配

当前仅支持 `openrouter`，可设置：

- `agents.defaults.provider = "openrouter"`（推荐）
- `agents.defaults.provider = "auto"`（也会回落到 openrouter）

## 代理（翻墙）配置

- 默认不走代理（`providers.openrouter.proxy = null`，`tools.web.proxy = null`）
- 需要翻墙时，在配置里手动设置代理地址（如 `http://127.0.0.1:7890` 或 `socks5://127.0.0.1:7890`）
- `providers.openrouter.proxy`：用于 LLM 请求（OpenRouter）
- `tools.web.proxy`：用于 `web_search` / `web_fetch` 工具请求

## 常用环境变量

```bash
NANOBOT_PROVIDERS__OPENROUTER__API_KEY=sk-or-...
NANOBOT_PROVIDERS__OPENROUTER__PROXY=http://127.0.0.1:7890
NANOBOT_AGENTS__DEFAULTS__SIMPLE_MODEL=google/gemini-2.5-flash-lite-preview-09-2025
NANOBOT_AGENTS__DEFAULTS__COMPLEX_MODEL=google/gemini-3.1-flash-lite-preview
NANOBOT_AGENTS__DEFAULTS__MODEL_ROUTING=auto
NANOBOT_TOOLS__WEB__PROXY=http://127.0.0.1:7890
NANOBOT_CHANNELS__FEISHU__ENABLED=true
NANOBOT_CHANNELS__FEISHU__APP_ID=cli_xxx
NANOBOT_CHANNELS__FEISHU__APP_SECRET=xxx
```

## 配置文件路径

- `~/.nanobot/config.json`
- `~/.nanobot/workspace/`
- `~/.nanobot/workspace/sessions/`
- `~/.nanobot/workspace/memory/MEMORY.md`
- `~/.nanobot/cron/jobs.json`
