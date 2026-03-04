# LLM 提供商系统详解

## 架构概述

当前代码中的 LLM Provider 只保留 **OpenRouter 单端点**，走 LiteLLM 路由：

```
providers/
├── base.py              # LLMProvider 抽象、LLMResponse、ToolCallRequest
├── registry.py          # ProviderSpec 定义 + PROVIDERS 注册表（单一事实来源）
└── litellm_provider.py  # LiteLLMProvider（OpenRouter 路由）
```

核心原则：
- Provider 匹配依赖 `registry.py`
- 统一通过 `LLMResponse` 传递文本与工具调用
- 不再内置其他 LLM 端点

## 抽象接口

`LLMProvider.chat()` 统一输入输出：

- 输入：`messages`、`tools`、`model`、`temperature`、`max_tokens`
- 输出：`LLMResponse`

`LLMResponse` 关键字段：
- `content`
- `has_tool_calls`
- `tool_calls`
- `finish_reason`
- `usage`
- `reasoning_content`

## Provider 注册表（当前实现）

`nanobot/providers/registry.py` 当前仅注册 1 个 provider：

| name | 类型 | 说明 |
|---|---|---|
| `openrouter` | Gateway | 通过 LiteLLM 调 OpenRouter，支持路由上游模型 |

OpenRouter 注册项的关键配置：
- `env_key = "OPENROUTER_API_KEY"`
- `litellm_prefix = "openrouter"`
- `detect_by_key_prefix = "sk-or-"`
- `detect_by_base_keyword = "openrouter"`
- `default_api_base = "https://openrouter.ai/api/v1"`
- `supports_prompt_caching = True`

## Provider 匹配算法

`Config._match_provider()`（`nanobot/config/schema.py`）匹配顺序：

1. 强制 provider
- 如果 `agents.defaults.provider != "auto"`，优先使用指定值

2. 显式前缀匹配
- 模型名包含前缀（如 `openrouter/google/gemini-3.1-flash-lite-preview`）时优先命中

3. 关键词匹配
- 按 `PROVIDERS` 顺序匹配关键词

4. 回退匹配
- 返回第一个已配置 `api_key` 的 provider

## Provider 实例化

`nanobot/cli/commands.py::_make_provider()` 固定返回 `LiteLLMProvider`：

- 使用 `config.get_complex_model()` 做 provider 匹配
- 使用 `openrouter` 的 `apiKey/apiBase` 初始化 LiteLLM

## OpenRouter 端点接入

最小可用配置：

```json
{
  "agents": {
    "defaults": {
      "provider": "openrouter",
      "simpleModel": "google/gemini-2.5-flash-lite-preview-09-2025",
      "complexModel": "google/gemini-3.1-flash-lite-preview",
      "modelRouting": "auto"
    }
  },
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-..."
    }
  }
}
```

可选：自定义 OpenRouter 基地址（代理场景）：

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-...",
      "apiBase": "https://openrouter.ai/api/v1"
    }
  }
}
```

模型解析行为：
- `google/gemini-3.1-flash-lite-preview` → `openrouter/google/gemini-3.1-flash-lite-preview`
- `openrouter/google/gemini-3.1-flash-lite-preview` → 保持不变（不会双前缀）

## Prompt Caching

OpenRouter 路径启用 `cache_control` 注入：
- System 消息最后一个 block 注入 `{"cache_control": {"type": "ephemeral"}}`
- 最后一个 tool 定义注入同样标记

## 错误处理

Provider 层统一策略：
- 捕获异常后返回 `LLMResponse(finish_reason="error")`
- 错误以文本形式回传，不会导致网关进程崩溃
