# 聊天渠道系统详解

## 架构概述

当前仓库仅保留 **Feishu（飞书）** 渠道实现。

```
channels/
├── base.py        # BaseChannel 抽象接口
├── manager.py     # ChannelManager（仅初始化 feishu）
└── feishu.py      # FeishuChannel 实现
```

核心数据流：

```
Feishu WebSocket Event
    -> FeishuChannel._handle_message(...)
    -> MessageBus.publish_inbound(...)
    -> AgentLoop 处理
    -> MessageBus.publish_outbound(...)
    -> ChannelManager 分发
    -> FeishuChannel.send(...)
```

## BaseChannel 接口

所有渠道实现遵循统一接口：

- `start()`：建立平台连接并监听消息
- `stop()`：停止连接并清理资源
- `send()`：向平台发送消息
- `_handle_message()`：权限检查后写入 `MessageBus`

## ChannelManager（当前行为）

`nanobot/channels/manager.py` 现在只会在 `channels.feishu.enabled=true` 时加载 Feishu：

- 仅注册 `self.channels["feishu"]`
- 出站分发只会命中已启用渠道
- `send_progress` / `send_tool_hints` 规则仍生效

## FeishuChannel 关键能力

`nanobot/channels/feishu.py` 支持：

- 单聊与群聊
- 群聊 @ 触发
- 消息反应（处理中/完成态）
- 富文本解析（文本、链接、@）
- 图片下载并透传给 Agent

Session Key 约定：

- `feishu:{chat_id}`

## 配置项

见 `docs/05-config-reference.md`，当前仅保留：

- `channels.sendProgress`
- `channels.sendToolHints`
- `channels.feishu.*`

## 新增渠道的扩展位置

如需重新增加其他 IM 渠道，最小改动点：

1. 在 `config/schema.py` 增加新渠道配置模型
2. 在 `channels/` 新增实现并继承 `BaseChannel`
3. 在 `channels/manager.py` 注册初始化逻辑
4. 同步更新 docs 与 README
