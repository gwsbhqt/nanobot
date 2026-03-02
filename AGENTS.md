# Nanobot Project Context

本仓库的主提示词由 `AGENTS.md` 与 `CLAUDE.md` 双文件镜像维护，二者必须始终完全一致。

## 0. 主提示词同步机制

- 修改 `AGENTS.md` 或 `CLAUDE.md` 任意一方后，必须立刻同步另一方，并在同一次变更中完成。
- 同步后必须校验两个文件完全一致（例如使用 `cmp -s AGENTS.md CLAUDE.md`）。
- 如存在多人或多代理并行编辑，先合并为单一版本，再做双文件同步，禁止保留差异。
- 主提示词内容保持角色中立，不写“这是给某个特定代理的提示词”。

## 1. 任务目标

在本仓库工作时，优先保证：
- 代码行为正确，优先对齐 `nanobot/` 真实实现
- 配置与文档同步（尤其 `docs/`）
- 不引入破坏现有 async 架构和工具协议的改动
- 变更可被其他协作者直接接手（包括人工与不同代理）

## 2. 首次进入阅读顺序

1. `docs/00-overview.md`
2. `docs/01-architecture.md`
3. 按任务读取专项文档：
   - Provider 相关：`docs/02-providers.md`
   - Channel 相关：`docs/03-channels.md`
   - Agent/Tool/Memory：`docs/04-agent-core.md`
   - 配置：`docs/05-config-reference.md`
   - 部署：`docs/06-deployment.md`
   - 扩展：`docs/07-extension-guide.md`

## 3. 核心事实（当前代码）

- 版本：`0.1.4.post3`
- 架构：Channel -> MessageBus -> AgentLoop -> Provider
- 持久化：文件系统（JSON/JSONL/Markdown），无数据库
- Provider 注册项：17
- Channel：10
- 运行模式：`nanobot agent` / `nanobot gateway`

## 4. 关键路径

- `nanobot/cli/commands.py`：CLI 与运行编排
- `nanobot/agent/loop.py`：主推理循环
- `nanobot/agent/context.py`：system prompt 组装
- `nanobot/agent/memory.py`：记忆压缩
- `nanobot/providers/registry.py`：provider 单一事实来源
- `nanobot/channels/manager.py`：渠道初始化与出站分发
- `nanobot/config/schema.py`：配置模型

## 5. 开发约束

- I/O 路径保持 async 风格
- 工具返回值保持 `str`
- 工具参数保持 JSON Schema
- 修改配置字段必须同步 `schema.py` + 文档
- 修改 Provider/Channel 必须同步对应 docs

## 6. 修改策略

- 先读再改，避免假设
- 对核心路径变更要补测试或最小可验证步骤
- 避免在文档写死易漂移数字（行数、临时实现细节）
- 若发现实现与文档冲突，以代码为准修正文档

## 7. 常用命令

```bash
uv pip install -e ".[dev]"
ruff check .
pytest
nanobot status
nanobot agent -m "hello"
```

## 8. 文档同步规则

发生以下改动时，必须更新 `docs/`：
- Provider 注册、匹配逻辑、OAuth 流程变化
- Channel 新增/删除、字段或策略变化
- AgentLoop 流程、工具协议、记忆策略变化
- 配置字段变化
- 部署结构变化（Docker/bridge/入口）
