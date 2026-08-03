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

# 桌面端（自动启动并回收 FastAPI 子进程）
pnpm tauri dev
```

桌面端每次启动都会创建随机回环端口和高熵会话令牌，通过 Tauri IPC 将连接信息交给
Vue API Client；首页会显示本地 FastAPI 的健康状态和后端版本，窗口退出后后端随之停止。

如需只调试浏览器界面，可分别运行 `uv run python -m backend.app.run` 和
`pnpm --dir frontend dev:web`。此模式固定使用 `http://127.0.0.1:8765`；若配置
`AI_QA_SESSION_TOKEN`，前端还需通过 `VITE_API_SESSION_TOKEN` 提供相同令牌。

## 开发环境要求

- Python 3.12（项目通过 `.python-version` 固定，不支持 3.13）。
- uv。
- Node.js 24 和 pnpm 11。
- Rust stable 及当前平台的 Tauri 2 系统依赖。

Windows 构建 Tauri 前，需要通过 Visual Studio Installer 安装“使用 C++ 的桌面开发”工作负载。
本仓库提供 `AI-QA-Assistant.vsconfig`，可在 Installer 的“更多 → 导入配置”中直接导入，
避免只安装 Visual Studio IDE 而缺少 `link.exe`、MSVC x64 工具链和 Windows SDK。

当前源码开发版由 Tauri 使用项目 `.venv` 中的 Python 启动 FastAPI。安装包使用的独立
Python Sidecar 可执行文件及签名流程属于阶段 6 打包切片，不在源码开发启动链路中隐式下载。

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
cargo test --manifest-path frontend/src-tauri/Cargo.toml
pnpm tauri build
```
