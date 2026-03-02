# 系统架构和数据流

## 三层架构

nanobot 采用清晰的三层架构，通过 MessageBus 解耦：

```
┌─────────────────────────────────────────────────────────┐
│                    Channel Layer                         │
│  Telegram │ Discord │ Feishu │ Slack │ WhatsApp │ ...   │
│           │         │        │       │          │        │
│  各平台 SDK/WebSocket 连接 ← 主动连接平台，无需入站端口     │
└────────────────────────┬────────────────────────────────┘
                         │ InboundMessage / OutboundMessage
                    ┌────┴────┐
                    │MessageBus│  (两个 asyncio.Queue)
                    └────┬────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                    Agent Layer                            │
│                                                          │
│  AgentLoop ─── ContextBuilder ─── MemoryStore           │
│      │              │                  │                 │
│      │         SkillsLoader        MEMORY.md             │
│      │                             HISTORY.md            │
│      │                                                   │
│  ToolRegistry ─── ReadFile, WriteFile, EditFile,        │
│      │            ListDir, Exec, WebSearch,              │
│      │            WebFetch, Message, Spawn,              │
│      │            Cron, MCP(*)                           │
│      │                                                   │
│  SubagentManager ─── 后台异步子任务                       │
│  SessionManager  ─── JSONL 会话持久化                     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                   Provider Layer                          │
│                                                          │
│  LiteLLMProvider ─── 14+ 提供商（通过 LiteLLM 路由）      │
│  CustomProvider  ─── 直连任意 OpenAI-compatible 端点       │
│  CodexProvider   ─── OpenAI Codex (OAuth + SSE 流式)      │
│                                                          │
│  ProviderSpec Registry ─── 单一事实来源（注册表驱动）       │
└─────────────────────────────────────────────────────────┘
```

## 核心数据流：完整请求-响应路径

```
用户发送消息（Telegram/Discord/Feishu/...）
    │
    ▼
Channel.start() 监听平台事件
    │
    ▼
BaseChannel._handle_message()
    ├── is_allowed(sender_id)  → 检查 allowFrom 白名单
    │   └── 未授权 → 丢弃消息，记录警告
    │
    ├── 创建 InboundMessage(channel, sender_id, chat_id, content, media)
    │
    └── bus.publish_inbound(msg)  → 放入 inbound 队列
    │
    ▼
AgentLoop.run()  ← 持续轮询 inbound 队列（1s 超时）
    │
    ├── "/stop" → _handle_stop() → 取消该 session 所有活跃任务
    ├── "/new"  → 归档记忆 → 清空 session
    ├── "/help" → 返回帮助文本
    │
    └── asyncio.create_task(_dispatch(msg))
         │
         ▼
    _dispatch(msg) ← 加全局处理锁 (_processing_lock)
         │
         ▼
    _process_message(msg)
         │
         ├── 1. SessionManager.get_or_create(session_key)
         │      session_key = "channel:chat_id" (如 "telegram:12345")
         │
         ├── 2. 检查是否需要记忆压缩
         │      unconsolidated >= memory_window → 异步触发 consolidate
         │
         ├── 3. 设置工具上下文（channel, chat_id, message_id）
         │
         ├── 4. ContextBuilder.build_messages()
         │      ├── build_system_prompt():
         │      │   ├── 读取 AGENTS.md (身份)
         │      │   ├── 读取 SOUL.md (人格)
         │      │   ├── 读取 USER.md (用户信息)
         │      │   ├── 读取 TOOLS.md (工具指南)
         │      │   ├── 读取 MEMORY.md (长期记忆)
         │      │   ├── 注入 always-on 技能内容
         │      │   └── 注入技能列表摘要
         │      ├── session.get_history(max_messages=memory_window)
         │      ├── 运行时上下文（时间、channel、chat_id）
         │      └── 用户消息（含可选的 base64 图片）
         │
         ├── 5. _run_agent_loop(messages, on_progress)
         │      │
         │      │  ┌──────── 迭代循环（最多 max_iterations 次）────────┐
         │      │  │                                                    │
         │      │  │  provider.chat(messages, tools, model, ...)       │
         │      │  │       │                                            │
         │      │  │       ▼                                            │
         │      │  │  LLMResponse                                      │
         │      │  │       │                                            │
         │      │  │  ┌────┴───────────────────────────┐               │
         │      │  │  │ has_tool_calls?                 │               │
         │      │  │  │                                 │               │
         │      │  │  │ YES:                            │ NO:           │
         │      │  │  │ ├── on_progress(text)           │ final_content │
         │      │  │  │ ├── on_progress(tool_hint)      │ = content     │
         │      │  │  │ ├── append assistant msg         │ → break      │
         │      │  │  │ ├── for each tool_call:         │               │
         │      │  │  │ │   ├── tools.execute(name,args)│               │
         │      │  │  │ │   └── append tool result      │               │
         │      │  │  │ └── continue loop               │               │
         │      │  │  └────────────────────────────────┘               │
         │      │  └────────────────────────────────────────────────────┘
         │      │
         │      └── 返回 (final_content, tools_used, messages)
         │
         ├── 6. _save_turn(session, messages, skip)
         │      ├── 截断过长的工具结果（> 500 字符）
         │      ├── 替换 base64 图片为 "[image]" 占位符
         │      └── session.messages.append(...)
         │
         ├── 7. sessions.save(session)  → 写入 JSONL 文件
         │
         └── 8. 返回 OutboundMessage(channel, chat_id, content)
              │
              ▼
    bus.publish_outbound(msg)  → 放入 outbound 队列
              │
              ▼
    ChannelManager._dispatch_outbound()  ← 持续轮询 outbound 队列
              │
              ▼
    Channel.send(msg)  → 调用平台 API 发送消息
```

## MessageBus 详解

MessageBus 是系统的"中枢神经"，极其简单（45 行代码）：

```python
class MessageBus:
    inbound: asyncio.Queue[InboundMessage]   # Channel → Agent
    outbound: asyncio.Queue[OutboundMessage]  # Agent → Channel
```

消息数据结构：

```python
@dataclass
class InboundMessage:
    channel: str           # "telegram", "discord", "feishu", ...
    sender_id: str         # 平台用户 ID
    chat_id: str           # 聊天/群组 ID
    content: str           # 消息文本
    media: list[str]       # 媒体文件路径列表
    metadata: dict         # 平台特定元数据
    session_key_override: str | None  # 可选 session key 覆盖

    @property
    def session_key(self) -> str:
        return self.session_key_override or f"{self.channel}:{self.chat_id}"

@dataclass
class OutboundMessage:
    channel: str           # 目标渠道
    chat_id: str           # 目标聊天 ID
    content: str           # 响应文本
    metadata: dict         # 元数据（含 _progress, _tool_hint 标记）
```

## Gateway 启动流程

`nanobot gateway` 命令启动时的组件编排：

```python
# cli/commands.py 中的 gateway() 函数简化逻辑

bus = MessageBus()
provider = _make_provider(config)  # 根据配置选择 Provider 实现
agent = AgentLoop(bus, provider, workspace, ...)

# Session 管理器
session_manager = SessionManager(workspace)

# Channel 管理器 - 懒加载已启用的 Channel
channel_manager = ChannelManager(config, bus)

# Cron 定时任务服务
cron_service = CronService(data_dir, on_job=agent.process_direct)

# Heartbeat 心跳服务
heartbeat = HeartbeatService(agent, channel_manager, config)

# 并行运行所有组件
await asyncio.gather(
    agent.run(),                    # Agent Loop 主循环
    channel_manager.start_all(),    # 启动所有已启用的 Channel（内部启动 outbound 分发）
    cron_service.start(),           # 定时任务调度循环
    heartbeat.start(),              # 心跳检查循环
)
```

## 并发模型

系统完全基于 **asyncio** 单线程事件循环：

- **AgentLoop.run()**: 持续消费 inbound 队列，每条消息作为独立 `asyncio.Task` 处理
- **_processing_lock**: 全局互斥锁，同一时间只处理一条消息（串行处理）
- **Channel.start()**: 各 Channel 独立维护与平台的连接
- **ChannelManager._dispatch_outbound()**: 持续消费 outbound 队列，按 channel 名路由分发（由 `start_all()` 内部启动）
- **SubagentManager**: 子代理作为独立 asyncio.Task 运行，通过 bus 报告结果
- **Memory consolidation**: 异步后台任务，不阻塞消息处理

关键设计：`_processing_lock` 确保同一时间只有一条消息在处理，避免并发写入 session 文件的问题。但这也意味着**消息是串行处理的**——这是一个重要的性能瓶颈点。

## 会话管理

```
~/.nanobot/workspace/sessions/
├── telegram:12345.jsonl      # Telegram 用户 12345 的会话
├── discord:67890.jsonl       # Discord 用户 67890 的会话
├── feishu:ou_abc123.jsonl    # 飞书用户的会话
└── cli:direct.jsonl          # CLI 模式的会话
```

JSONL 格式：
- 第 1 行：会话元数据 `{"key": "telegram:12345", "created_at": "...", "last_consolidated": 0}`
- 后续每行：一条消息 `{"role": "user/assistant/tool", "content": "...", "timestamp": "..."}`

## 关键设计决策

1. **无数据库**：所有持久化基于文件（JSON, JSONL, Markdown），简单、可移植、人类可读
2. **LiteLLM 抽象**：通过单一接口支持 15+ LLM 提供商，注册表模式消除了提供商特定分支
3. **MessageBus 解耦**：Channel 和 Agent 核心完全独立，新增 Channel 只需实现 BaseChannel
4. **子代理隔离**：后台任务有自己的工具集（无 message/spawn 工具），通过 bus 报告结果
5. **记忆压缩**：使用 LLM 工具调用来摘要旧对话历史，防止上下文无限增长
6. **MCP 集成**：外部工具作为一等公民，透明地包装为原生工具
7. **工具调用循环**：ReAct 风格的迭代——调用 LLM → 执行工具 → 注入结果 → 再次调用 LLM
