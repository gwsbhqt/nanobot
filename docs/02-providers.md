# LLM 提供商系统详解

## 架构概述

Provider 系统采用**注册表驱动**架构，核心是 `ProviderSpec` 数据类和 `PROVIDERS` 元组：

```
providers/
├── base.py              # LLMProvider ABC, LLMResponse, ToolCallRequest
├── registry.py          # ProviderSpec 定义 + PROVIDERS 注册表
├── litellm_provider.py  # LiteLLMProvider（14+ 提供商）
├── custom_provider.py   # CustomProvider（直连 OpenAI-compatible）
├── openai_codex_provider.py  # OpenAICodexProvider（OAuth + SSE）
└── transcription.py     # GroqTranscriptionProvider（语音转文字）
```

## 抽象基类

```python
# providers/base.py

class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...

@dataclass
class LLMResponse:
    content: str | None           # 文本响应
    has_tool_calls: bool          # 是否包含工具调用
    tool_calls: list[ToolCallRequest]  # 工具调用列表
    finish_reason: str            # stop, tool_calls, error, length
    usage: dict | None            # token 用量 {prompt_tokens, completion_tokens, total_tokens}
    reasoning_content: str | None # 思维链内容（DeepSeek-R1, Kimi 等）

@dataclass
class ToolCallRequest:
    id: str              # 工具调用 ID（9 字符字母数字，Mistral 兼容）
    name: str            # 工具名称
    arguments: dict      # 工具参数
```

## 三种 Provider 实现

### 1. LiteLLMProvider（主路径，覆盖 14+ 提供商）

**文件**: `litellm_provider.py` (280 行)

通过 `litellm.acompletion()` 统一调用，LiteLLM 内部处理各提供商的 HTTP 协议差异。

**关键方法**:
- `_resolve_model()`: 根据 ProviderSpec 为模型名添加前缀（如 `deepseek-chat` → `deepseek/deepseek-chat`）
- `_setup_env(api_key, api_base, model)`: 设置提供商所需的环境变量（如 `ANTHROPIC_API_KEY`）
- `_apply_cache_control()`: 为 Anthropic 注入 prompt caching 标记
- `_sanitize_messages()`: 清理非标准消息字段
- `_parse_response()`: 统一解析 LiteLLM 响应为 `LLMResponse`

**调用链**:
```
chat(messages, tools, model, ...)
  │
  ├── _resolve_model(model)      → 添加 litellm 前缀
  ├── _setup_env(api_key, api_base, model) → 设置环境变量
  ├── _sanitize_messages(msgs)   → 清理消息格式
  ├── _apply_cache_control(msgs, tools)  → Anthropic 缓存
  │
  ├── litellm.acompletion(
  │     model=resolved_model,
  │     messages=sanitized,
  │     tools=tools,
  │     api_key=key,
  │     api_base=base,
  │     extra_headers=headers,
  │     **model_overrides,
  │   )
  │
  └── _parse_response(response)  → LLMResponse
```

**非流式**: LiteLLMProvider 使用单次 `await acompletion(...)` 获取完整响应，不做流式传输。

### 2. CustomProvider（直连 OpenAI-compatible）

**文件**: `custom_provider.py` (53 行)

使用 `openai.AsyncOpenAI` 客户端直连任意 OpenAI-compatible 端点，**完全绕过 LiteLLM**。

适用场景：LM Studio、llama.cpp、Ollama、自建代理等。

```python
self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)
response = await self._client.chat.completions.create(**kwargs)
```

### 3. OpenAICodexProvider（OAuth + SSE 流式）

**文件**: `openai_codex_provider.py` (312 行)

完全自定义实现，使用 `httpx` 进行 HTTP 调用：

- **API 端点**: `https://chatgpt.com/backend-api/codex/responses`（Responses API，非 Chat Completions）
- **认证**: OAuth 通过 `oauth_cli_kit.get_token()`，无 API key
- **流式**: SSE (Server-Sent Events) 全流式传输
- **格式转换**: 需要在 Chat Completions 格式和 Responses API 格式之间双向转换

**关键转换**:
- `_convert_messages()`: Chat format → Responses API input items
- `_convert_tools()`: OpenAI function schema → Codex flat format
- `_iter_sse()` / `_consume_sse()`: SSE 事件流解析

**SSE 事件类型**:
- `response.output_text.delta` → 文本流
- `response.function_call_arguments.delta` → 工具调用参数流
- `response.output_item.added/done` → 输出项生命周期
- `response.completed` → 响应完成

## ProviderSpec 注册表

**文件**: `registry.py` (462 行)

每个提供商通过一个 `ProviderSpec` 冻结数据类描述：

```python
@dataclass(frozen=True)
class ProviderSpec:
    name: str                    # 配置字段名, 如 "dashscope"
    keywords: tuple[str, ...]    # 模型名关键词匹配, 如 ("qwen", "dashscope")
    env_key: str                 # LiteLLM 环境变量名, 如 "DASHSCOPE_API_KEY"
    display_name: str            # 显示名称
    litellm_prefix: str          # 模型名前缀, 如 "dashscope" → "dashscope/{model}"
    skip_prefixes: tuple         # 避免重复前缀的前缀列表
    env_extras: tuple            # 额外环境变量, 如 ("MOONSHOT_API_BASE", "{api_base}")
    is_gateway: bool             # 是否为网关型（可路由任意模型）
    is_local: bool               # 是否为本地部署
    detect_by_key_prefix: str    # 通过 API key 前缀检测, 如 "sk-or-"
    detect_by_base_keyword: str  # 通过 API base URL 关键词检测
    default_api_base: str        # 默认 API 基地址
    strip_model_prefix: bool     # 是否在重新前缀前先剥离模型名中的提供商前缀
    model_overrides: tuple       # 特定模型的参数覆盖
    is_oauth: bool               # 是否使用 OAuth（无 API key）
    is_direct: bool              # 是否直连（绕过 LiteLLM）
    supports_prompt_caching: bool  # 是否支持 Anthropic 风格的 prompt caching
```

## 完整提供商注册表

`PROVIDERS` 元组的**顺序决定匹配优先级和回退顺序**：

| # | name | 类型 | litellm_prefix | 匹配关键词 | 特殊行为 |
|---|---|---|---|---|---|
| 1 | custom | Direct | (无) | (无) | 绕过 LiteLLM |
| 2 | openrouter | Gateway | `openrouter` | openrouter | `sk-or-*` key 检测, prompt caching |
| 3 | aihubmix | Gateway | `openai` | aihubmix | strip_model_prefix=True |
| 4 | siliconflow | Gateway | `openai` | siliconflow | 硅基流动 |
| 5 | volcengine | Gateway | `volcengine` | volcengine, volces, ark | 火山引擎 |
| 6 | anthropic | Standard | (无) | anthropic, claude | prompt caching, LiteLLM 原生 |
| 7 | openai | Standard | (无) | openai, gpt | LiteLLM 原生 |
| 8 | openai_codex | OAuth | (无) | openai-codex, codex | 独立 Provider 实现 |
| 9 | github_copilot | OAuth | `github_copilot` | github_copilot, copilot | OAuth 设备流 |
| 10 | deepseek | Standard | `deepseek` | deepseek | |
| 11 | gemini | Standard | `gemini` | gemini | |
| 12 | zhipu | Standard | `zai` | zhipu, glm, zai | 镜像 ZHIPUAI_API_KEY |
| 13 | dashscope | Standard | `dashscope` | qwen, dashscope | 通义千问 |
| 14 | moonshot | Standard | `moonshot` | moonshot, kimi | kimi-k2.5 强制 temp=1.0 |
| 15 | minimax | Standard | `minimax` | minimax | |
| 16 | vllm | Local | `hosted_vllm` | vllm | 需自行提供 api_base |
| 17 | groq | Auxiliary | `groq` | groq | 主要用于 Whisper 语音转文字 |

## Provider 匹配算法

`Config._match_provider()` 实现了三阶段匹配（`config/schema.py:336`）：

```
阶段 1: 强制指定
  如果 agents.defaults.provider != "auto"，直接使用指定的 provider

阶段 2: 模型名精确前缀匹配（优先级最高）
  如果模型名包含 "/" 前缀，匹配 spec.name
  例如: "deepseek/deepseek-chat" → 前缀 "deepseek" → 匹配 name="deepseek"

  ★ 这一步防止了 "github-copilot/...codex" 错误匹配到 openai_codex

阶段 3: 关键词匹配（按 PROVIDERS 注册顺序）
  遍历 PROVIDERS，检查模型名是否包含 spec.keywords 中的任何关键词
  例如: "claude-3-opus" → 包含 "claude" → 匹配 anthropic

阶段 4: 回退
  遍历 PROVIDERS，返回第一个有 api_key 的提供商
  网关型优先（在注册表中排序靠前）
  OAuth 提供商永远不作为回退
```

## Provider 实例化

`_make_provider()` 工厂函数（`cli/commands.py:202`）：

```python
def _make_provider(config) -> LLMProvider:
    provider_name = config.get_provider_name()

    if provider_name == "openai_codex":
        return OpenAICodexProvider(...)      # OAuth + SSE
    elif provider_name == "custom":
        return CustomProvider(api_key, api_base, ...)  # 直连
    else:
        return LiteLLMProvider(              # LiteLLM 多提供商
            api_key=config.get_api_key(),
            api_base=config.get_api_base(),
            provider_name=provider_name,
            extra_headers=config.get_provider().extra_headers,
        )
```

## 模型名解析示例

| 用户配置 model | 匹配 provider | _resolve_model() 输出 | 实际调用 |
|---|---|---|---|
| `claude-3-opus` | anthropic | `claude-3-opus` (无前缀) | litellm → Anthropic API |
| `gpt-4o` | openai | `gpt-4o` (无前缀) | litellm → OpenAI API |
| `deepseek-chat` | deepseek | `deepseek/deepseek-chat` | litellm → DeepSeek API |
| `kimi-k2.5` | moonshot | `moonshot/kimi-k2.5` + temp=1.0 | litellm → Moonshot API |
| `qwen-max` | dashscope | `dashscope/qwen-max` | litellm → DashScope API |
| `anthropic/claude-3` | openrouter (如配) | `openrouter/anthropic/claude-3` | litellm → OpenRouter API |
| `anthropic/claude-3` | aihubmix (如配) | `openai/claude-3` (strip前缀) | litellm → AiHubMix API |

## Prompt Caching

仅 Anthropic 和 OpenRouter 支持（`supports_prompt_caching=True`）：

```python
def _apply_cache_control(messages, tools):
    # 在 system message 的 content block 上注入：
    {"cache_control": {"type": "ephemeral"}}

    # 在最后一个 tool 定义上注入：
    {"cache_control": {"type": "ephemeral"}}
```

效果：Anthropic API 会缓存标记了 `cache_control` 的 prompt 部分，降低后续请求的 token 消耗。

## 语音转文字

`GroqTranscriptionProvider`（`transcription.py`）通过 Groq 的 Whisper API 进行语音转文字：

```python
# API: https://api.groq.com/openai/v1/audio/transcriptions
# 模型: whisper-large-v3
# 格式: audio/ogg → text
```

目前仅 Telegram Channel 使用此功能，将语音消息转换为文本后再发给 Agent。

## 错误处理

所有 Provider 的错误处理策略一致：
- 捕获异常 → 返回 `LLMResponse(content="Error: ...", finish_reason="error")`
- **不会崩溃进程**，只会向用户返回错误消息
- Codex Provider 特殊处理 HTTP 429 → "ChatGPT usage quota exceeded"
- Codex Provider SSL 失败 → 自动降级 `verify=False` 重试一次

## 添加新提供商

只需两步：

1. 在 `registry.py` 的 `PROVIDERS` 元组中添加一个 `ProviderSpec` 条目
2. 在 `config/schema.py` 的 `ProvidersConfig` 中添加一个字段

环境变量设置、模型名前缀、配置匹配、状态显示全部从注册表自动派生。
