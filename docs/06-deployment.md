# 部署和运维

## 部署方式

### 1. 直接安装运行

```bash
# 安装
pip install nanobot-ai
# 或使用 uv
uv pip install nanobot-ai

# 如需 Matrix E2EE 支持
pip install nanobot-ai[matrix]

# 如需 WhatsApp Bridge
cd bridge && npm install && npm run build

# 初始化
nanobot onboard

# 编辑配置
vim ~/.nanobot/config.json

# 启动
nanobot gateway
```

### 2. Docker 部署

**Dockerfile 结构**（单文件，非多阶段）:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# 系统依赖
RUN apt-get install -y curl ca-certificates gnupg git
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
RUN apt-get install -y nodejs

# Python 依赖（两步，利用 Docker layer cache）
COPY pyproject.toml .
RUN uv pip install --system --no-cache .

# 源码
COPY . .
RUN uv pip install --system --no-cache .

# WhatsApp Bridge
WORKDIR /app/bridge
RUN npm install && npm run build

EXPOSE 18790
ENTRYPOINT ["nanobot"]
CMD ["status"]
```

**docker-compose.yml**:

```yaml
services:
  nanobot-gateway:
    build: .
    command: gateway
    ports:
      - "18790:18790"
    volumes:
      - ~/.nanobot:/root/.nanobot
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "1"
          memory: 1G
        reservations:
          cpus: "0.25"
          memory: 256M

  nanobot-cli:
    build: .
    command: status
    volumes:
      - ~/.nanobot:/root/.nanobot
    profiles:
      - cli  # 按需启动: docker-compose --profile cli run nanobot-cli
```

**Docker 操作命令**:

```bash
# 构建
docker build -t nanobot .

# 启动 gateway
docker-compose up -d nanobot-gateway

# 查看日志
docker-compose logs -f nanobot-gateway

# 运行 CLI 命令
docker-compose --profile cli run nanobot-cli agent -m "Hello"
docker-compose --profile cli run nanobot-cli status

# 停止
docker-compose down
```

## 运行架构

Gateway 模式下的进程/组件：

```
nanobot gateway (单进程, asyncio 事件循环)
    │
    ├── AgentLoop.run()              ← 消息处理主循环
    │   ├── inbound 队列轮询 (1s 超时)
    │   ├── 消息处理 (加全局锁, 串行)
    │   └── 子代理任务池
    │
    ├── ChannelManager.start_all()   ← 并行启动所有 Channel
    │   ├── Telegram (HTTP 长轮询)
    │   ├── Discord (WebSocket)
    │   ├── Feishu (WebSocket)
    │   ├── Slack (Socket Mode)
    │   └── ... (按配置启用)
    │
    ├── ChannelManager._dispatch_outbound() ← outbound 消息分发（由 start_all 内部启动）
    │
    ├── CronService.start()          ← 定时任务调度
    │
    └── HeartbeatService.start()     ← 30 分钟心跳
```

## 端口和网络

| 端口 | 用途 | 方向 |
|---|---|---|
| 3001 | WhatsApp Bridge WebSocket (`BRIDGE_PORT`) | 入站（本地） |
| (无) | 所有 Channel 连接 | 出站 |

**重要**: 除 WhatsApp Bridge 外，nanobot 不需要任何入站端口。所有 Channel 都是主动向外连接的。

## 日志系统

使用 `loguru` 进行日志记录：

- **Gateway 模式**: 日志默认开启，输出到 stderr
- **CLI 模式**: 日志默认关闭（`--logs` flag 开启）

日志控制:
```python
logger.enable("nanobot")   # 启用日志
logger.disable("nanobot")  # 禁用日志
```

**格式**: 文本格式（非结构化 JSON），包含时间戳、级别、模块名、消息。

## 数据持久化

nanobot **完全无数据库**，所有数据基于文件系统：

| 数据类型 | 存储位置 | 格式 |
|---|---|---|
| 配置 | `~/.nanobot/config.json` | JSON |
| 会话 | `workspace/sessions/*.jsonl` | JSONL (追加) |
| 长期记忆 | `workspace/memory/MEMORY.md` | Markdown (覆盖) |
| 历史日志 | `workspace/memory/HISTORY.md` | Markdown (追加) |
| 定时任务 | `~/.nanobot/cron/jobs.json` | JSON |
| 命令历史 | `~/.nanobot/history/cli_history` | 文本 |
| 自定义技能 | `workspace/skills/*/SKILL.md` | Markdown |
| 引导文件 | `workspace/*.md` | Markdown |

**备份策略**: 备份 `~/.nanobot/` 目录即可完整恢复。

## 安全注意事项

### API Key 管理

- API Key 存储在 `~/.nanobot/config.json` **明文**中
- Docker 部署通过 volume mount 传入
- **无 secrets manager 集成**
- 建议：生产环境通过环境变量注入敏感信息

### 访问控制

每个 Channel 支持 `allowFrom` 白名单：
- 空列表 = 允许所有人
- 非空列表 = 仅允许列表中的用户 ID

### Shell 命令安全

ExecTool 有基本的危险命令检测：
- 拒绝 `rm -rf`, `mkfs`, `dd of=/dev`, `chmod 777`, `shutdown`, `reboot`
- 可选 `restrictToWorkspace: true` 限制命令执行范围

### 文件访问

- `restrictToWorkspace: false`（默认）: 工具可以访问文件系统上的任何文件
- `restrictToWorkspace: true`: 工具只能访问 workspace 目录

## 已知的运维空白

以下是当前系统**缺失**的生产级功能，二次开发时需要考虑：

### 1. 无 CI/CD
没有 GitHub Actions、GitLab CI 或其他 CI/CD 配置。建议添加：
- ruff lint
- pytest
- docker build
- PyPI 发布

### 2. 无健康检查端点
- docker-compose 没有配置 `healthcheck`
- 没有 HTTP `/health` 端点
- 建议：在 gateway 添加简单的 HTTP health check

### 3. 无结构化日志
- loguru 输出为文本格式
- 不利于日志聚合（ELK/Loki/CloudWatch）
- 建议：添加 JSON 日志格式选项

### 4. 无 Metrics/Monitoring
- 无 Prometheus metrics
- 无 OpenTelemetry 集成
- 无 Sentry 错误追踪
- 建议：添加基础 metrics（请求计数、延迟、token 用量、错误率）

### 5. 无速率限制
- 完全依赖上游 Provider 的限流
- 无本地请求速率控制
- 无 token 用量预算

### 6. 无多实例支持
- 文件基础持久化不支持并发写入
- 无分布式锁
- 单进程架构
- 建议：如需水平扩展，需引入数据库和分布式消息队列

### 7. 消息串行处理
- `_processing_lock` 使消息串行处理
- 同一时间只处理一条消息
- 如果一个 LLM 调用耗时 30 秒，其他用户消息要排队等待
- 建议：改为 per-session 锁或引入并发处理

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_heartbeat_service.py

# Docker smoke test
./tests/test_docker.sh
```

测试覆盖：
- CLI 命令（CliRunner mock）
- 心跳服务
- 定时任务
- 记忆压缩
- 工具参数验证
- Channel（Email, Matrix）
- Docker 构建和启动
