# 聊天渠道系统详解

## 架构概述

Channel 系统采用经典的**策略模式** —— 所有渠道实现相同的 `BaseChannel` 接口：

```
channels/
├── base.py        # BaseChannel ABC (132 行)
├── manager.py     # ChannelManager 编排器 (245 行)
├── telegram.py    # Telegram (503 行)
├── discord.py     # Discord WebSocket (301 行)
├── feishu.py      # 飞书 WebSocket (759 行)
├── mochat.py      # Mochat Socket.IO (895 行) ← 最大
├── slack.py       # Slack Socket Mode (281 行)
├── dingtalk.py    # 钉钉 Stream (247 行)
├── email.py       # Email IMAP/SMTP (408 行)
├── whatsapp.py    # WhatsApp via Bridge (148 行)
├── qq.py          # QQ botpy (132 行)
└── matrix.py      # Matrix E2EE (682 行)
```

## BaseChannel 接口

```python
class BaseChannel(ABC):
    name: str = "base"              # 渠道标识符

    def __init__(self, config: Any, bus: MessageBus):
        self.config = config        # 渠道配置（对应 XxxConfig）
        self.bus = bus              # MessageBus 引用
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """连接到聊天平台并开始监听消息"""

    @abstractmethod
    async def stop(self) -> None:
        """停止渠道并清理资源"""

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """通过此渠道发送消息"""

    def is_allowed(self, sender_id: str) -> bool:
        """检查发送者是否在白名单中（空列表 = 允许所有人）"""

    async def _handle_message(self, sender_id, chat_id, content, media, metadata, session_key):
        """处理入站消息：检查权限 → 创建 InboundMessage → 发布到 bus"""
```

## ChannelManager

```python
class ChannelManager:
    """编排所有已启用的 Channel"""

    def __init__(self, config: Config, bus: MessageBus):
        self.config = config
        self.channels: dict[str, BaseChannel] = {}
        self._init_channels()  # 按 enabled 字段惰性导入并实例化渠道

    async def start_all(self):
        """启动 outbound 分发任务并并行启动所有 Channel"""
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        await asyncio.gather(*[self._start_channel(name, ch) for name, ch in self.channels.items()])
```

## 各渠道实现详解

### Telegram (`telegram.py`, 503 行)

**SDK**: `python-telegram-bot[socks]`

**连接方式**: HTTP 长轮询 (`polling`)

**特性**:
- 支持 SOCKS5/HTTP 代理 (`proxy` 配置)
- 语音消息自动转文字（通过 Groq Whisper）
- 图片/文档作为 media 传递
- `reply_to_message` 选项：回复时引用原消息
- Markdown 格式化输出
- 长消息自动分片

**Session Key**: `telegram:{chat_id}`（同一聊天共享 session）

### Discord (`discord.py`, 301 行)

**SDK**: 无第三方 SDK，**原生 WebSocket** 实现

**连接方式**: WebSocket (`wss://gateway.discord.gg`)

**特性**:
- 完整的 Gateway v10 协议实现
- Intent 控制 (`intents: 37377` = GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT)
- 心跳 (heartbeat) 维持连接
- Resume 断线重连
- 支持 DM 和群组消息
- 自动处理 @mention 去除

**Session Key**: `discord:{channel_id}`

### Feishu/飞书 (`feishu.py`, 759 行)

**SDK**: `lark-oapi`

**连接方式**: WebSocket 长连接

**特性**:
- 支持单聊和群聊
- 群聊中支持 @mention 触发
- 消息反应 (react_emoji，默认 THUMBSUP)
- 富文本消息解析（包含 @、链接、图片等元素）
- 图片下载（通过 Feishu API 获取 image_key 对应的文件）
- 支持 encrypt_key 和 verification_token

**Session Key**: `feishu:{chat_id}`（群聊共享 session）

### DingTalk/钉钉 (`dingtalk.py`, 247 行)

**SDK**: `dingtalk-stream`

**连接方式**: DingTalk Stream Mode（SDK 管理的长连接）

**特性**:
- 支持单聊和群聊
- 群聊自动处理 @mention
- Markdown 格式化输出
- 通过 staff_id 控制白名单

**Session Key**: `dingtalk:{conversation_id}`

### Slack (`slack.py`, 281 行)

**SDK**: `slack-sdk` (Socket Mode)

**连接方式**: Slack Socket Mode (`xapp-` token)

**特性**:
- Socket Mode（无需公网 URL）
- 支持 DM 和 Channel 消息
- `reply_in_thread`: 默认在线程中回复
- `react_emoji`: 处理中添加 emoji 反应（默认 "eyes"）
- `group_policy`: "mention" / "open" / "allowlist" 三种群组策略
- DM 策略可独立配置

**Session Key**: `slack:{thread_ts 或 channel_id}`

### WhatsApp (`whatsapp.py`, 148 行)

**SDK**: 无直接 SDK，通过 **Node.js Bridge** 间接连接

**连接方式**: WebSocket (`ws://localhost:3001`) 连接到 Bridge 进程

**特性**:
- 需要单独运行 `bridge/` 下的 Node.js 进程
- Bridge 使用 @whiskeysockets/baileys（非官方 WhatsApp API）
- QR 码扫描登录（通过 `nanobot channels login`）
- 支持共享 token 认证 (`bridge_token`)
- 手机号白名单 (`allow_from`)

**架构**:
```
Python (whatsapp.py) ←WebSocket→ Node.js Bridge ←WhatsApp Web Protocol→ WhatsApp
```

### Email (`email.py`, 408 行)

**SDK**: 标准库 `imaplib` + `smtplib`

**连接方式**: IMAP 轮询（`poll_interval_seconds` 默认 30s）+ SMTP 发送

**特性**:
- IMAP SSL/TLS 支持
- SMTP TLS/SSL 支持
- 可选自动回复 (`auto_reply_enabled`)
- 邮件正文截断 (`max_body_chars: 12000`)
- 发件人白名单
- `consent_granted` 字段：显式用户授权标记
- 标记已读 (`mark_seen`)

**Session Key**: `email:{sender_address}`

### QQ (`qq.py`, 132 行)

**SDK**: `qq-botpy`

**连接方式**: SDK 管理的 WebSocket

**特性**:
- QQ 官方机器人 SDK
- 支持群聊和 C2C（点对点）消息
- 通过 openid 控制白名单

**Session Key**: `qq:{group_openid 或 user_openid}`

### Matrix (`matrix.py`, 682 行)

**SDK**: `matrix-nio[e2e]`

**连接方式**: Matrix Sync API (长轮询)

**特性**:
- **端到端加密 (E2EE)** 支持（可选，默认开启）
- 支持 DM 和群组（room）
- `group_policy`: "open" / "mention" / "allowlist" 三种策略
- `allow_room_mentions`: 是否响应 @room 全体提醒
- 媒体上传/下载 (`max_media_bytes: 20MB`)
- HTML 格式化输出（使用 `mistune` + `nh3` 渲染）
- 可选依赖（`pip install nanobot-ai[matrix]`）

**Session Key**: `matrix:{room_id}`

### Mochat (`mochat.py`, 895 行)

**SDK**: `python-socketio`

**连接方式**: Socket.IO

**特性**:
- Claw IM 平台集成（这是项目名 "类 claw" 的由来）
- Socket.IO 连接，支持 msgpack 序列化
- 复杂的群组/提及策略
- 会话 (sessions) 和面板 (panels) 概念
- 延迟回复模式 (`reply_delay_mode`)
- 自动重连（指数退避）
- Watch API 轮询新消息

**Session Key**: `mochat:{session_id}`

## 连接方式对比

| 渠道 | 连接方向 | 协议 | 需要公网 | 需要额外进程 |
|---|---|---|---|---|
| Telegram | 出站 (轮询) | HTTP Long Polling | 否 | 否 |
| Discord | 出站 | WebSocket | 否 | 否 |
| Feishu | 出站 | WebSocket | 否 | 否 |
| DingTalk | 出站 | Stream Mode | 否 | 否 |
| Slack | 出站 | Socket Mode | 否 | 否 |
| WhatsApp | 入站 (本地) | WebSocket | 否 | **是** (Node.js Bridge) |
| Email | 出站 (轮询) | IMAP/SMTP | 否 | 否 |
| QQ | 出站 | WebSocket | 否 | 否 |
| Matrix | 出站 (轮询) | HTTP Sync API | 否 | 否 |
| Mochat | 出站 | Socket.IO | 否 | 否 |

**重要特点**: 除了 WhatsApp Bridge 监听 3001 端口（可通过 `BRIDGE_PORT` 覆盖）外，所有 Channel 都是**主动向外连接**的，**不需要公网 IP 或入站端口映射**。

## 消息处理流程（各渠道通用）

```
平台事件到达
    │
    ▼
渠道特定的事件处理（解析消息内容、发送者 ID、媒体等）
    │
    ▼
BaseChannel._handle_message(sender_id, chat_id, content, media, metadata)
    │
    ├── is_allowed(sender_id)
    │   ├── allowFrom 为空 → 允许所有人
    │   ├── sender_id 在 allowFrom 中 → 允许
    │   ├── sender_id 包含 "|" → 按 "|" 分割后逐段检查
    │   └── 未匹配 → 拒绝，记录 WARNING
    │
    └── bus.publish_inbound(InboundMessage(...))
```

## 进度和工具提示消息

Agent 处理消息期间会通过 MessageBus 发送中间状态：

```python
OutboundMessage(
    channel="telegram", chat_id="12345",
    content="searching for information...",
    metadata={
        "_progress": True,    # 这是进度消息
        "_tool_hint": False,  # 不是工具调用提示
    }
)
```

ChannelManager 根据配置决定是否转发：
- `channels.send_progress: true` → 转发文本进度
- `channels.send_tool_hints: false` → 不转发工具调用提示（如 `web_search("query")`）

各 Channel 的 `send()` 方法通常会对 progress 消息做特殊处理（如 Telegram 编辑已发送消息，Feishu 添加 emoji 反应等）。

## 添加新渠道

1. 在 `config/schema.py` 中添加 `XxxConfig(Base)` 配置类
2. 在 `ChannelsConfig` 中添加字段
3. 创建 `channels/xxx.py`，实现 `BaseChannel`
4. 在 `ChannelManager` 中注册（懒加载映射表）

关键实现要点：
- `start()`: 连接到平台 → 设置消息回调 → `self._running = True`
- `stop()`: 断开连接 → 清理资源 → `self._running = False`
- `send()`: 处理 progress 消息和最终响应的区别 → 调用平台 API 发送
- 消息解析: 提取纯文本、处理 @mention、下载媒体文件
