# 部署和运维

## 部署方式

### 1) 直接安装运行

```bash
mise install
mise run setup
uv run nanobot onboard
uv run nanobot status
uv run nanobot gateway
```

### 2) Docker 部署

```bash
docker build -t nanobot .
docker run --rm -it \
  -v ~/.nanobot:/root/.nanobot \
  nanobot status
```

网关常驻：

```bash
docker run -d \
  --name nanobot-gateway \
  -v ~/.nanobot:/root/.nanobot \
  nanobot gateway
```

## 运行架构

Gateway 进程（单进程 asyncio）包含：

- `AgentLoop.run()`
- `ChannelManager.start_all()`（仅 Feishu）
- `ChannelManager._dispatch_outbound()`
- `CronService.start()`
- `HeartbeatService.start()`

## 网络与端口

- 默认网关端口：`18790`（若启用 gateway API）
- 渠道连接方式：Feishu 出站连接
- 无 WhatsApp bridge 依赖

## 日志

- 使用 `loguru`
- CLI 默认静默（`--logs` 可开启）
- Gateway 默认输出运行日志

## 持久化路径

| 数据 | 路径 |
|---|---|
| 配置 | `~/.nanobot/config.json` |
| 会话 | `~/.nanobot/workspace/sessions/*.jsonl` |
| 记忆 | `~/.nanobot/workspace/memory/*.md` |
| 定时任务 | `~/.nanobot/cron/jobs.json` |

## 安全建议

- API Key 建议通过环境变量注入
- 开启 `channels.feishu.allowFrom` 白名单
- 按需启用 `tools.restrictToWorkspace=true`

## 验证命令

```bash
python3 -m compileall nanobot tests
uv run pytest
```
