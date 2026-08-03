# AI QA Assistant

本仓库用于开发一款面向测试工程师的本地 AI 助手。产品以桌面应用运行，核心业务、AI 编排、文档处理和测试执行统一使用 Python；桌面界面采用 Tauri + Vue 3。

> Codex 使用说明：截至 2026-07-31，原 Codex App 已整合进新版 ChatGPT 桌面应用。本文档中的“Codex App”指桌面应用内的 Codex 开发模式。

## 产品目标

将“需求理解 → 风险分析 → 测试点 → 测试用例 → 接口/UI/移动端执行 → 报告归因”串成一个本地、可审计、可扩展的 QA 工作流。

## MVP 范围

1. 本地工作空间与项目管理。
2. 导入 Markdown、DOCX、PDF、HTML、图片和 `.proto` 文件。
3. 需求完整性、一致性、清晰度、可测性、可行性分析。
4. 生成结构化测试点和测试用例。
5. HTTP、WebSocket、Protobuf 测试执行。
6. 执行历史、日志、报告和 AI 失败归因。
7. 本地模型与 OpenAI-compatible 云模型切换。

## 技术栈

- 桌面端：Tauri 2、Vue 3、TypeScript、Vite、Element Plus、Pinia。
- 后端：Python 3.12、FastAPI、Pydantic v2、SQLModel、Alembic、SQLite。
- AI：统一 Provider 层、Ollama、本地/云端模型、Qdrant Local。
- 测试：pytest、httpx、websockets、protobuf、Playwright Python、Appium Python。
- 工程：uv、Ruff、mypy、pre-commit、GitHub Actions。

## 推荐阅读顺序

1. `docs/00-项目总览.md`
2. `docs/01-产品需求文档-MVP.md`
3. `docs/02-技术架构设计.md`
4. `docs/03-Codex开发流程.md`
5. `AGENTS.md`
6. `.agents/skills/` 下的可复用技能

## 开发启动顺序

```bash
# 首次安装
uv sync --all-groups
pnpm install

# 初始化本地数据库
uv run alembic upgrade head

# 终端 1：后端（固定绑定 127.0.0.1:8765）
uv run python -m backend.app.run

# 终端 2：桌面端
pnpm tauri dev
```

打开桌面窗口后，首页会显示本地 FastAPI 的健康状态和后端版本。也可以访问
`http://127.0.0.1:8765/health` 进行 HTTP 冒烟检查。

## 开发环境要求

- Python 3.12（项目通过 `.python-version` 固定，不支持 3.13）。
- uv。
- Node.js 24 和 pnpm 11。
- Rust stable 及当前平台的 Tauri 2 系统依赖。

当前 M0 骨架采用“独立启动 FastAPI + 固定开发端口”的方式。Python Sidecar、随机端口和启动令牌将在后续桌面安全切片实现；`/health` 不返回用户数据或敏感配置。

## 质量命令

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy backend
uv run pytest -q

pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm tauri build
```
