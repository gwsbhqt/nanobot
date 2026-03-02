# 二次开发扩展指南

本文档是为二次开发者准备的实操指南，覆盖所有常见的扩展场景。

## 1. 添加新 LLM 提供商

**两步完成，无需修改路由逻辑。**

### 步骤 1: 添加 ProviderSpec

在 `nanobot/providers/registry.py` 的 `PROVIDERS` 元组中添加条目：

```python
# 在 PROVIDERS 元组中添加（注意位置决定优先级）
ProviderSpec(
    name="my_provider",                    # 配置字段名
    keywords=("myprovider", "mymodel"),    # 模型名匹配关键词
    env_key="MY_PROVIDER_API_KEY",         # LiteLLM 环境变量名
    display_name="My Provider",            # nanobot status 显示名
    litellm_prefix="my_provider",          # 模型名前缀: model → my_provider/model
    skip_prefixes=("my_provider/",),       # 避免双重前缀
    default_api_base="https://api.myprovider.com/v1",
),
```

### 步骤 2: 添加配置字段

在 `nanobot/config/schema.py` 的 `ProvidersConfig` 中添加：

```python
class ProvidersConfig(Base):
    # ... 现有字段 ...
    my_provider: ProviderConfig = Field(default_factory=ProviderConfig)
```

**完成！** 环境变量设置、模型名路由、配置匹配、`nanobot status` 显示全部自动派生。

### 特殊情况

如果提供商需要完全自定义的 HTTP 协议（像 Codex 那样），需要：
1. 创建新的 Provider 类（继承 `LLMProvider`）
2. 在 `cli/commands.py` 的 `_make_provider()` 中添加分支

---

## 2. 添加新聊天渠道

### 步骤 1: 添加配置

在 `nanobot/config/schema.py` 中：

```python
class MyChannelConfig(Base):
    """My channel configuration."""
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    # ... 其他配置

class ChannelsConfig(Base):
    # ... 现有字段 ...
    my_channel: MyChannelConfig = Field(default_factory=MyChannelConfig)
```

### 步骤 2: 实现 Channel

创建 `nanobot/channels/my_channel.py`：

```python
from nanobot.channels.base import BaseChannel
from nanobot.bus.events import OutboundMessage

class MyChannel(BaseChannel):
    name = "my_channel"

    async def start(self):
        """连接到平台并开始监听"""
        self._running = True
        # 连接到平台...
        while self._running:
            # 接收消息
            event = await self._receive()
            # 提取信息
            await self._handle_message(
                sender_id=event.sender,
                chat_id=event.chat,
                content=event.text,
                media=event.attachments,
            )

    async def stop(self):
        """断开连接"""
        self._running = False
        # 清理资源...

    async def send(self, msg: OutboundMessage):
        """发送消息到平台"""
        is_progress = msg.metadata.get("_progress", False)
        if is_progress:
            # 处理进度消息（如编辑已发送的消息）
            pass
        else:
            # 发送最终响应
            await self._platform_send(msg.chat_id, msg.content)
```

### 步骤 3: 注册到 ChannelManager

在 `nanobot/channels/manager.py` 的 `_init_channels()` 中按 `enabled` 条件惰性导入并实例化：

```python
if self.config.channels.my_channel.enabled:
    from nanobot.channels.my_channel import MyChannel
    self.channels["my_channel"] = MyChannel(self.config.channels.my_channel, self.bus)
```

---

## 3. 添加新工具

### 步骤 1: 实现 Tool

创建新文件或在现有文件中添加：

```python
from nanobot.agent.tools.base import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Description of what this tool does"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to process"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "minimum": 1,
                    "maximum": 100
                }
            },
            "required": ["query"]
        }

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        limit = kwargs.get("limit", 10)
        # 执行逻辑...
        return f"Results for '{query}': ..."
```

### 步骤 2: 注册工具

在 `nanobot/agent/loop.py` 的 `_register_default_tools()` 中添加：

```python
def _register_default_tools(self):
    # ... 现有注册 ...
    self.tools.register(MyTool())
```

### 关键设计约束

- `execute()` 必须返回 `str`（工具结果以文本形式注入 LLM 上下文）
- `parameters` 必须是合法的 JSON Schema（OpenAI function calling 格式）
- 工具名称必须唯一
- 参数会在执行前自动验证

---

## 4. 添加新技能

在 workspace 或内置技能目录创建 Markdown 文件：

```
workspace/skills/my-skill/SKILL.md
```

或

```
nanobot/skills/my-skill/SKILL.md
```

格式：

```markdown
---
description: "Brief description of what this skill does"
requires:
  bins: ["optional-binary"]     # 需要的命令行工具
  env: ["OPTIONAL_ENV_VAR"]     # 需要的环境变量
always: false                   # true = 始终注入 system prompt
---

# My Skill

Detailed instructions for the agent on when and how to use this skill.

## When to use
- Scenario 1
- Scenario 2

## How to use
Step by step instructions...
```

**无需修改代码**——SkillsLoader 会自动发现 SKILL.md 文件。

---

## 5. 添加 MCP 服务器

纯配置，无需代码：

```json
{
  "tools": {
    "mcpServers": {
      "my-server": {
        "command": "npx",
        "args": ["-y", "my-mcp-server"],
        "env": {"API_KEY": "xxx"},
        "toolTimeout": 30
      }
    }
  }
}
```

或 HTTP 模式：

```json
{
  "tools": {
    "mcpServers": {
      "remote": {
        "url": "https://mcp.example.com/sse",
        "headers": {"Authorization": "Bearer xxx"},
        "toolTimeout": 30
      }
    }
  }
}
```

MCP 服务器的工具会自动注册为 `mcp_{server_name}_{tool_name}`。

---

## 6. 自定义 Agent 人格

编辑 workspace 中的模板文件：

| 文件 | 用途 | 说明 |
|---|---|---|
| `AGENTS.md` | Agent 身份定义 | 角色、能力、行为规范 |
| `SOUL.md` | Agent 人格 | 语气、风格、价值观 |
| `USER.md` | 用户信息 | Agent 对用户的了解 |
| `TOOLS.md` | 工具使用指南 | 工具使用的最佳实践 |
| `HEARTBEAT.md` | 心跳任务 | 定义主动检查的任务 |

这些文件会被注入到 system prompt 中。

---

## 7. 关键扩展点速查

| 扩展需求 | 修改位置 | 复杂度 |
|---|---|---|
| 新 LLM 提供商 | `registry.py` + `schema.py` | 低（2 处） |
| 新聊天渠道 | `schema.py` + 新文件 + `manager.py` | 中（3 处） |
| 新工具 | 新文件 + `loop.py` 注册 | 低（2 处） |
| 新技能 | 新 SKILL.md 文件 | 极低（纯配置） |
| 新 MCP 服务器 | `config.json` | 极低（纯配置） |
| 自定义 Provider 协议 | 新 Provider 类 + `commands.py` | 高 |
| 修改消息处理流程 | `loop.py` | 高（核心代码） |
| 修改记忆策略 | `memory.py` | 中 |
| 修改上下文构建 | `context.py` | 中 |
| 添加数据库持久化 | `session/manager.py` | 高（架构变更） |
| 添加 HTTP API | 新增服务 | 高（需新增组件） |

---

## 8. 代码风格和约定

- **Python >= 3.11**，使用类型标注
- **asyncio 异步**: 所有 I/O 操作使用 `async/await`
- **loguru 日志**: `from loguru import logger`
- **ruff 代码检查**: `ruff check .` + `ruff format .`
- **测试**: pytest + pytest-asyncio (asyncio_mode="auto")
- **Pydantic v2**: 配置和数据校验
- **JSON Schema**: 工具参数定义
- **OpenAI 消息格式**: 内部消息统一使用 OpenAI Chat Completion 格式

---

## 9. 常见二次开发场景

### 场景 A: 接入新的国内 LLM

如果提供商兼容 OpenAI API（大多数国内提供商都是）：
1. 添加 ProviderSpec（设置正确的 `litellm_prefix` 和 `env_key`）
2. 添加 ProvidersConfig 字段
3. 在 config.json 中配置 `apiKey` 和 `apiBase`

### 场景 B: 添加 HTTP API 层（供前端调用）

当前系统没有 HTTP API，所有交互通过 Channel。如需添加：
1. 创建新的 Channel 实现（如 `HTTPChannel`），在 `start()` 中启动 HTTP 服务器
2. 接收 HTTP 请求 → 发布到 MessageBus → 等待 outbound 响应 → 返回 HTTP 响应
3. 或者直接创建独立的 HTTP 服务，使用 `agent.process_direct()` 方法

### 场景 C: 消息并行处理

当前的 `_processing_lock` 使消息串行处理。改为并行：
1. 将全局锁改为 per-session 锁
2. 或完全移除锁，改用线程安全的 session 存储
3. 注意：需要处理并发写入 JSONL 文件的问题

### 场景 D: 替换文件持久化为数据库

1. 实现新的 `SessionManager`（接口兼容）
2. 实现新的 `MemoryStore`（接口兼容）
3. 实现新的 `CronStore`
4. 在 `AgentLoop` 和 `CronService` 中注入新实现

### 场景 E: 添加多模型/多 Agent 支持

当前每个 AgentLoop 只绑定一个 Provider 和一个模型。如需多模型：
1. 允许 AgentLoop 持有多个 Provider
2. 在工具调用或路由层根据任务类型选择模型
3. 或创建多个 AgentLoop 实例，通过消息路由分配
