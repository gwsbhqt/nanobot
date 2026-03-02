# Agent 引擎、工具、记忆、技能

## AgentLoop — 核心处理引擎

**文件**: `agent/loop.py` (484 行)

AgentLoop 是 nanobot 的心脏，实现了 **ReAct (Reasoning + Acting)** 模式的 Agent 循环。

### 初始化

```python
class AgentLoop:
    def __init__(self, bus, provider, workspace, model, max_iterations=40,
                 temperature=0.1, max_tokens=4096, memory_window=100, ...):
        self.bus = bus                    # MessageBus
        self.provider = provider          # LLMProvider
        self.workspace = workspace        # 工作区路径
        self.model = model                # 默认模型
        self.max_iterations = max_iterations  # 最大工具调用轮次
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window    # 触发记忆压缩的消息数阈值

        self.context = ContextBuilder(workspace)
        self.sessions = SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(...)

        self._processing_lock = asyncio.Lock()  # 全局消息处理锁
        self._register_default_tools()
```

### 默认工具注册

```python
def _register_default_tools(self):
    # 文件操作（可限制在 workspace 内）
    ReadFileTool, WriteFileTool, EditFileTool, ListDirTool

    # Shell 命令
    ExecTool(timeout=60, restrict_to_workspace=False)

    # Web 操作
    WebSearchTool(api_key=brave_api_key)  # Brave Search
    WebFetchTool()                         # URL 内容抓取

    # 通信
    MessageTool(send_callback=bus.publish_outbound)

    # 子代理
    SpawnTool(manager=subagents)

    # 定时任务（可选）
    CronTool(cron_service)

    # MCP 工具（懒加载，首条消息时连接）
    # connect_mcp_servers() → MCPToolWrapper → 注册到 ToolRegistry
```

### Agent 循环核心

```python
async def _run_agent_loop(self, initial_messages, on_progress):
    messages = initial_messages
    iteration = 0

    while iteration < self.max_iterations:
        iteration += 1

        # 1. 调用 LLM
        response = await self.provider.chat(
            messages=messages,
            tools=self.tools.get_definitions(),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # 2. 处理响应
        if response.has_tool_calls:
            # 发送进度（文本内容 + 工具提示）
            # 添加 assistant 消息（含 tool_calls）
            # 执行每个工具调用
            for tool_call in response.tool_calls:
                result = await self.tools.execute(tool_call.name, tool_call.arguments)
                # 添加 tool result 消息
            # 继续循环
        else:
            # 无工具调用 = 最终响应
            final_content = self._strip_think(response.content)
            break

    return final_content, tools_used, messages
```

### 关键行为

- **_strip_think()**: 移除 `<think>...</think>` 块（DeepSeek-R1 等模型的思维链）
- **_tool_hint()**: 格式化工具调用为简洁提示，如 `web_search("query")`
- **_save_turn()**: 保存对话轮次到 session，截断工具结果（>500 字符）并替换 base64 图片为占位符
- **_processing_lock**: 全局互斥锁，保证消息串行处理
- **_handle_stop()**: 取消指定 session 的所有活跃任务和子代理

---

## ContextBuilder — 上下文组装

**文件**: `agent/context.py` (161 行)

负责为每次 LLM 调用组装完整的消息列表。

### System Prompt 构建

```python
def build_system_prompt(self):
    parts = []

    # 1. 身份文件
    parts.append(read_file("AGENTS.md"))    # Agent 身份定义
    parts.append(read_file("SOUL.md"))      # Agent 人格
    parts.append(read_file("USER.md"))      # 用户信息
    parts.append(read_file("TOOLS.md"))     # 工具使用指南

    # 2. 长期记忆
    parts.append(read_file("memory/MEMORY.md"))

    # 3. Always-on 技能（完整内容）
    for skill in always_on_skills:
        parts.append(skill.content)

    # 4. 技能摘要列表（按需使用的技能）
    parts.append(format_skill_summaries(other_skills))

    return "\n\n".join(parts)
```

### 完整消息列表

```python
def build_messages(self, history, current_message, media, channel, chat_id):
    messages = []

    # 1. System prompt
    messages.append({"role": "system", "content": system_prompt})

    # 2. 历史消息
    messages.extend(history)

    # 3. 运行时上下文（时间、channel、chat_id）
    messages.append({
        "role": "user",
        "content": f"<runtime_context>time={now}, channel={channel}, chat_id={chat_id}</runtime_context>"
    })

    # 4. 当前用户消息（支持多模态）
    user_content = current_message
    if media:
        user_content = [
            {"type": "text", "text": current_message},
            *[{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
              for path in media]
        ]
    messages.append({"role": "user", "content": user_content})

    return messages
```

---

## 工具系统

### Tool 抽象基类

**文件**: `agent/tools/base.py` (103 行)

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...           # 工具名称

    @property
    @abstractmethod
    def description(self) -> str: ...    # 工具描述

    @property
    @abstractmethod
    def parameters(self) -> dict: ...    # JSON Schema 参数定义

    @abstractmethod
    async def execute(self, **kwargs) -> str: ...  # 执行并返回字符串结果

    def validate_params(self, params) -> list[str]:
        """针对 JSON Schema 验证参数，返回错误列表"""

    def to_schema(self) -> dict:
        """转换为 OpenAI function calling schema 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
```

### ToolRegistry

**文件**: `agent/tools/registry.py` (67 行)

```python
class ToolRegistry:
    _tools: dict[str, Tool] = {}

    def register(self, tool: Tool): ...
    def get(self, name: str) -> Tool | None: ...

    async def execute(self, name: str, params: dict) -> str:
        tool = self._tools[name]
        errors = tool.validate_params(params)
        if errors:
            return f"Parameter error: {'; '.join(errors)}"
        return await tool.execute(**params)

    def get_definitions(self) -> list[dict]:
        """返回所有工具的 OpenAI schema 列表"""
        return [tool.to_schema() for tool in self._tools.values()]
```

### 内置工具一览

| 工具 | 文件 | 功能 | 参数 |
|---|---|---|---|
| `read_file` | filesystem.py | 读取文件内容 | path |
| `write_file` | filesystem.py | 写入文件 | path, content |
| `edit_file` | filesystem.py | 编辑文件（查找/替换） | path, old_text, new_text |
| `list_dir` | filesystem.py | 列出目录内容 | path |
| `exec` | shell.py | 执行 Shell 命令 | command, working_dir |
| `web_search` | web.py | Brave Search 搜索 | query, count |
| `web_fetch` | web.py | 抓取 URL 内容（readability） | url, extractMode, maxChars |
| `message` | message.py | 发送消息到渠道 | content, channel, chat_id, media |
| `spawn` | spawn.py | 生成后台子代理 | task, label |
| `cron` | cron.py | 管理定时任务 | action, message, every_seconds, cron_expr, tz, at, job_id |

### ExecTool 安全措施

**文件**: `agent/tools/shell.py` (158 行)

```python
class ExecTool(Tool):
    # 命令安全检查 - 拒绝危险命令
    _DENY_PATTERNS = [
        r'\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f',   # rm -rf
        r'\bmkfs\b',
        r'\bdd\b.*\bof=/',
        r'\bchmod\s+777\b',
        r'>\s*/dev/sd',
        r'\bshutdown\b',
        r'\breboot\b',
    ]

    # 工作目录限制（可选）
    restrict_to_workspace: bool

    # 命令超时
    timeout: int = 60

    # PATH 追加
    path_append: str = ""
```

### MCP 集成

**文件**: `agent/tools/mcp.py` (100 行)

MCP (Model Context Protocol) 工具通过 `connect_mcp_servers()` 在首条消息时懒加载：

```python
async def connect_mcp_servers(mcp_servers, tool_registry, stack):
    for server_name, config in mcp_servers.items():
        if config.command:
            # stdio 模式：启动本地进程
            session = await stack.enter_async_context(
                stdio_client(config.command, config.args, config.env)
            )
        elif config.url:
            # HTTP 模式：连接远程 SSE 端点
            session = await stack.enter_async_context(
                streamablehttp_client(config.url, config.headers)
            )

        # 列出服务器上的所有工具
        tools = await session.list_tools()

        # 包装为原生 Tool 并注册
        for tool in tools:
            wrapper = MCPToolWrapper(session, tool, server_name)
            tool_registry.register(wrapper)
            # 工具名: "mcp_{server_name}_{tool_name}"
```

---

## 记忆系统

### 双层记忆架构

**文件**: `agent/memory.py` (150 行)

```
MEMORY.md  ← 长期事实记忆（LLM 维护，覆盖写入）
    "用户名是 Alice，喜欢 Python，家在北京"

HISTORY.md ← 时间戳日志（追加写入，可 grep 搜索）
    "[2024-01-15 10:30] 用户询问了 Docker 部署问题..."
    "[2024-01-15 14:00] 帮用户修复了 Python 依赖冲突..."
```

### 记忆压缩触发

当 session 中未压缩的消息数量 >= `memory_window`（默认 100）时：

```python
# 在 _process_message() 中检查
unconsolidated = len(session.messages) - session.last_consolidated
if unconsolidated >= self.memory_window:
    # 异步后台触发压缩（不阻塞当前消息处理）
    asyncio.create_task(consolidate_memory(session))
```

### 压缩过程

```python
async def consolidate(session, provider, model):
    # 1. 取出未压缩的消息
    snapshot = session.messages[session.last_consolidated:]

    # 2. 读取当前 MEMORY.md
    current_memory = read_file("memory/MEMORY.md")

    # 3. 构造压缩 prompt（含虚拟 save_memory 工具）
    messages = [
        {"role": "system", "content": "你是记忆管理助手..."},
        {"role": "user", "content": f"当前记忆:\n{current_memory}\n\n新对话:\n{format(snapshot)}"}
    ]
    tools = [{
        "type": "function",
        "function": {
            "name": "save_memory",
            "parameters": {
                "memory": "更新后的长期记忆",
                "history": "追加到 HISTORY.md 的摘要"
            }
        }
    }]

    # 4. 调用 LLM 执行压缩
    response = await provider.chat(messages, tools, model)

    # 5. 解析 save_memory 工具调用
    if response.has_tool_calls:
        args = response.tool_calls[0].arguments
        write_file("memory/MEMORY.md", args["memory"])      # 覆盖
        append_file("memory/HISTORY.md", args["history"])    # 追加

    # 6. 更新压缩指针
    # archive_all 时全部归档，指针重置为 0；常规压缩时保留 keep_count 条最近消息
    session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
```

---

## 会话管理

**文件**: `session/manager.py` (212 行)

### Session 数据结构

```python
@dataclass
class Session:
    key: str                      # "channel:chat_id"
    messages: list[dict] = []     # 消息列表
    created_at: datetime = now()
    updated_at: datetime = now()
    last_consolidated: int = 0    # 已压缩到的消息索引

    def get_history(self, max_messages: int) -> list[dict]:
        """返回未压缩的消息，对齐到 user 轮次起始"""
        unconsolidated = self.messages[self.last_consolidated:]
        recent = unconsolidated[-max_messages:]
        # 确保从 user 消息开始（跳过开头的 assistant/tool 消息）
        while recent and recent[0].get("role") != "user":
            recent.pop(0)
        return recent
```

### SessionManager

```python
class SessionManager:
    _cache: dict[str, Session] = {}  # 内存缓存

    def get_or_create(self, key: str) -> Session:
        """获取或创建 session（内存缓存 + JSONL 文件）"""

    def save(self, session: Session):
        """保存到 JSONL 文件"""

    def invalidate(self, key: str):
        """使缓存失效"""
```

### JSONL 文件格式

```jsonl
{"key": "telegram:12345", "created_at": "2024-01-15T10:00:00", "last_consolidated": 42}
{"role": "user", "content": "Hello", "timestamp": "2024-01-15T10:00:01"}
{"role": "assistant", "content": "Hi! How can I help?", "timestamp": "2024-01-15T10:00:02"}
{"role": "user", "content": "Read my config", "timestamp": "2024-01-15T10:01:00"}
{"role": "assistant", "content": null, "tool_calls": [...], "timestamp": "2024-01-15T10:01:01"}
{"role": "tool", "tool_call_id": "abc123", "name": "read_file", "content": "...", "timestamp": "..."}
```

---

## 技能系统

**文件**: `agent/skills.py` (228 行)

### 技能文件格式

```markdown
---
description: "Search GitHub repositories"
requires:
  bins: ["gh"]
  env: ["GITHUB_TOKEN"]
always: false
---

# GitHub Search Skill

When the user asks you to search GitHub...

## Usage
...
```

### 加载优先级

1. `{workspace}/skills/{name}/SKILL.md` — 用户自定义（最高优先级）
2. `nanobot/skills/{name}/SKILL.md` — 内置技能（回退）

### 注入方式

- **always: true** 的技能 → 完整内容注入到 system prompt
- **always: false** 的技能 → 仅注入 XML 摘要列表，Agent 可按需 `read_file` 读取完整 SKILL.md

### 内置技能

| 技能 | 用途 | always |
|---|---|---|
| clawhub | ClawHub 平台集成 | - |
| cron | 定时任务管理指南 | - |
| github | GitHub 操作（issue, PR） | - |
| memory | 记忆管理指南 | true |
| skill-creator | 创建新技能 | - |
| summarize | 内容摘要 | - |
| tmux | tmux 会话管理 | - |
| weather | 天气查询 | - |

---

## 子代理系统

**文件**: `agent/subagent.py` (256 行)

### 工作原理

```python
class SubagentManager:
    async def spawn(self, task: str, channel: str, chat_id: str):
        """生成一个后台子代理执行任务"""
        task = asyncio.create_task(self._run_subagent(task, channel, chat_id))

    async def _run_subagent(self, task, channel, chat_id):
        # 1. 创建独立的 ToolRegistry（无 message, spawn 工具）
        tools = ToolRegistry()
        tools.register(ReadFileTool, WriteFileTool, EditFileTool, ListDirTool)
        tools.register(ExecTool)
        tools.register(WebSearchTool, WebFetchTool)

        # 2. 运行迷你 Agent 循环（最多 15 次迭代）
        messages = [
            {"role": "system", "content": "You are a background task agent..."},
            {"role": "user", "content": task}
        ]
        for i in range(15):
            response = await self.provider.chat(messages, tools.get_definitions(), ...)
            if response.has_tool_calls:
                # 执行工具
            else:
                break

        # 3. 通过 bus 报告结果
        await self._announce_result(result, channel, chat_id)
```

### 子代理特点

- **工具受限**: 没有 `message`（不能直接发消息给用户）和 `spawn`（不能再生成子代理）
- **迭代受限**: 最多 15 次迭代（主 Agent 是 40 次）
- **结果报告**: 通过 `InboundMessage(channel="system")` 回传主 Agent，由主 Agent 摘要后发给用户

---

## Heartbeat 心跳服务

**文件**: `heartbeat/service.py` (173 行)

每 30 分钟（可配置）执行一次"主动检查"：

```
Phase 1: 决策
    ├── 读取 workspace/HEARTBEAT.md
    ├── 调用 LLM，提供虚拟 heartbeat 工具
    │   └── heartbeat(action: "skip" | "run", task: "...")
    ├── skip → 什么都不做
    └── run → 进入 Phase 2

Phase 2: 执行
    ├── agent.process_direct(task)  → 完整 Agent 循环
    └── 结果推送到最近活跃的 Channel
```

---

## Cron 定时任务

**文件**: `cron/service.py` (367 行), `cron/types.py` (60 行)

### 任务类型

- **at**: 一次性定时任务（毫秒时间戳）
- **every**: 间隔重复（毫秒间隔，CLI 通常以秒输入）
- **cron**: cron 表达式 + 时区（如 `0 9 * * MON-FRI` + `Asia/Shanghai`）

### 存储

```
~/.nanobot/cron/jobs.json
```

### CronTool

Agent 可通过工具调用管理定时任务：
- `cron(action="add", schedule={...}, task="...")` — 添加任务
- `cron(action="list")` — 列出任务
- `cron(action="remove", id="...")` — 删除任务
