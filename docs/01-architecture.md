# 系统架构和数据流

## 三层架构

```
┌─────────────────────────────────────────────────────────┐
│                    Channel Layer                         │
│                      Feishu                              │
└────────────────────────┬────────────────────────────────┘
                         │ InboundMessage / OutboundMessage
                    ┌────┴────┐
                    │MessageBus│
                    └────┬────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                    Agent Layer                           │
│  AgentLoop ─ ContextBuilder ─ MemoryStore               │
│  ToolRegistry ─ SessionManager ─ SubagentManager        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                   Provider Layer                         │
│         LiteLLMProvider (OpenRouter)                    │
└─────────────────────────────────────────────────────────┘
```

## 核心数据流

```text
Feishu Event
  -> FeishuChannel._handle_message(...)
  -> MessageBus.inbound
  -> AgentLoop.run()
  -> provider.chat(...)
  -> (可选)工具调用循环
  -> MessageBus.outbound
  -> ChannelManager._dispatch_outbound()
  -> FeishuChannel.send(...)
```

## MessageBus 数据结构

```python
@dataclass
class InboundMessage:
    channel: str
    sender_id: str
    chat_id: str
    content: str
    media: list[str]
    metadata: dict

@dataclass
class OutboundMessage:
    channel: str
    chat_id: str
    content: str
    media: list[str]
    metadata: dict
```

## Gateway 启动编排

`nanobot gateway` 启动时并行运行：

- `agent.run()`
- `channels.start_all()`（当前只会启动 Feishu）
- `cron.start()`
- `heartbeat.start()`

## 并发模型

- 基于 `asyncio` 单事件循环
- Agent 主处理路径由 `_processing_lock` 串行化
- 渠道层异步收发消息
- 定时任务与心跳在后台协程运行

## 会话存储

会话 key 形式：`{channel}:{chat_id}`，例如：`feishu:ou_xxx`。

数据落盘位置：`~/.nanobot/workspace/sessions/*.jsonl`
