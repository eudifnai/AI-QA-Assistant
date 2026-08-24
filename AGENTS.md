# AGENTS.md

## 1. 项目定位

本项目是“本地 AI QA 助手”，不是传统多人 Web 测试管理平台。优先满足单机、本地优先、隐私可控、可审计和可插拔。

核心闭环：

`需求导入 → AI 分析 → 测试点/用例生成 → 测试执行 → 报告与失败归因`

## 2. 固定技术边界

- 后端、AI 编排、文档解析、测试执行统一使用 Python 3.12。
- API 使用 FastAPI；数据校验使用 Pydantic v2。
- 业务数据库使用 SQLite + SQLModel + Alembic。
- 桌面端使用 Electron；界面使用 Vue 3 + TypeScript + Element Plus。
- Python 依赖由 `uv` 管理；前端依赖由 `pnpm` 管理。
- 首期不得引入微服务、Kubernetes、Kafka、RabbitMQ、Celery、Redis 或远程 PostgreSQL。
- 长任务必须运行在独立 Worker 进程，不得阻塞 FastAPI 事件循环。
- 本地 API 仅绑定 `127.0.0.1`，不得默认监听局域网。

## 3. 代码结构规则

- `backend/app/api`：接口层，只做参数校验、权限/令牌检查、调用应用服务。
- `backend/app/application`：用例编排，不直接依赖具体 UI。
- `backend/app/domain`：领域模型、状态机和业务规则。
- `backend/app/infrastructure`：数据库、模型 Provider、文件、向量库、外部工具适配器。
- `backend/app/workers`：长任务、测试执行、取消、超时、进度上报。
- `frontend/src`：Vue 页面、组件、状态和 API Client。
- `tests`：单元、集成、端到端测试；测试目录结构尽量映射生产代码。

禁止：

- 在 FastAPI 路由中堆积业务逻辑。
- 在 Vue 组件中直接拼接后端 URL 或绕过统一 API Client。
- 在业务代码中直接绑定某个具体大模型 SDK。
- 将 API Key、Token、密码写入仓库、SQLite 明文配置或日志。
- 捕获 `Exception` 后静默忽略。

## 4. 工作方式

每个任务按以下顺序执行：

1. 阅读相关 PRD、架构和当前代码。
2. 明确目标、非目标、影响范围、验收标准和风险。
3. 给出小步实施计划；跨 5 个以上文件或涉及数据迁移时必须先计划。
4. 优先写或更新测试，再实现最小改动。
5. 运行最小相关测试，再运行完整质量门禁。
6. 检查 diff、异常路径、日志、配置兼容性和文档同步。
7. 总结实际改动、验证结果、未完成项和残余风险。

未经明确要求，不进行大范围重构，不更换既定技术栈，不添加生产依赖。

## 5. 质量门禁

Python 变更至少运行：

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy backend
uv run pytest -q
```

前端变更至少运行：

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

涉及桌面集成时增加：

```bash
pnpm electron:package
```

无法执行某项命令时，必须说明原因和替代验证，不得声称已通过。

## 6. 测试要求

- 新增领域规则必须有单元测试。
- 新增 API 必须有成功、参数错误、业务失败和异常恢复测试。
- 长任务必须覆盖：开始、进度、成功、失败、取消、超时和进程崩溃恢复。
- 文件导入必须覆盖：不支持格式、超大文件、损坏文件、路径穿越和重复导入。
- LLM 结果必须通过 Pydantic Schema 校验；解析失败需要重试或降级路径。
- Protobuf 测试必须覆盖版本不匹配、未知字段和解码失败。
- 修复 Bug 时先添加可复现的回归测试。

## 7. 状态与错误规范

任务状态统一为：

`pending | queued | running | passed | failed | error | cancelled | timeout`

错误响应至少包含：

- `code`：稳定的机器错误码。
- `message`：面向用户的中文说明。
- `detail`：可选调试信息，不包含密钥和敏感内容。
- `trace_id`：用于关联日志。

## 8. 安全与隐私

- 密钥通过操作系统凭据库管理；Python 侧优先使用 `keyring`。
- 日志默认脱敏 Authorization、Cookie、Token、手机号、邮箱和自定义敏感字段。
- 外部命令必须使用参数数组，禁止拼接不可信 Shell 字符串。
- 用户文件只在工作空间和应用数据目录内处理。
- AI 外发前展示模型类型和数据范围；本地模式不得隐式调用云模型。
- 数据删除必须同时处理原文件、数据库记录、缓存和向量索引。

## 9. 文档同步

出现以下变化时必须更新 `docs/`：

- 用户可见行为、设置或流程变化。
- API、数据库或任务状态变化。
- 新增依赖、环境变量、外部工具或系统要求。
- 打包、安装和升级方式变化。

## 10. 完成定义

任务只有同时满足以下条件才可标记完成：

- 验收标准满足。
- 相关测试通过。
- lint、类型检查和构建通过，或明确记录无法运行的原因。
- 无调试代码、临时文件和明文密钥。
- 错误处理、日志和取消路径已考虑。
- 文档已同步。
- 最终 diff 已自审，无无关改动。
