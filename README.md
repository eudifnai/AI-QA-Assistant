# AI QA Assistant

本仓库用于开发一款面向测试工程师的本地 AI 助手。产品以桌面应用运行，核心业务、AI 编排、文档处理和测试执行统一使用 Python；桌面界面采用 Electron + Vue 3。

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

- 桌面端：Electron、Electron Forge、Vue 3、TypeScript、Vite、Element Plus、Pinia。
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
7. `docs/10-Windows候选发布说明.md`
8. `docs/11-Windows安装与首次使用.md`

## 开发启动顺序

```bash
# 首次安装
uv sync --all-groups
pnpm install

# 初始化本地数据库
uv run alembic upgrade head

# 桌面端（自动启动并回收 FastAPI 子进程）
pnpm dev
```

拉取包含数据库变更的新版本后，也需要再次执行 `uv run alembic upgrade head`。该命令会创建工作空间
和当前业务表。当前 M1 工作空间首页支持通过系统目录选择器或输入本机绝对路径来创建工作空间，并按最近访问时间重新打开、
重命名或移除历史项目记录；记录保存在本地 SQLite 中，项目文件目录不会自动上传。删除操作只移除
助手中的记录，不会删除本地目录或文件。

“维护”页面可查看应用/Python/平台版本、本地 API 监听地址、SQLite 路径、大小、Alembic
版本、完整性、工作空间数和备份数，并可通过 SQLite 在线备份 API 创建一致性数据库副本。备份
保存在数据库同级的 `backups/` 目录，只包含业务数据库，不包含工作空间原文件或操作系统凭据；
当前不提供恢复、删除和自动备份。

“分析”页面可选择一个解析成功的文档，使用本地 Ollama 或 OpenAI-compatible 云端服务生成完整性、
一致性、清晰度、可测性和可行性五维评分。每个问题包含严重度、影响、改进建议、待确认问题和至少
一个稳定文档引用。云端模式同时要求设置级数据外发同意和每次分析的逐次确认；确认框会展示被冻结的
Provider、模型、完整 HTTPS 请求 endpoint（`base_url` 加 `/chat/completions`）、文档版本，以及本次
发送的全部稳定片段数和字符数；运行记录同时冻结 `base_url`。客户端在创建任务时提交版本、Provider、
模型、`base_url`、`input_chunk_count` 和 `input_character_count` 快照，后端发现其中任何一项与当前
上下文不一致都会拒绝任务并要求重新确认，避免确认后上下文被替换。分析输入超过 200,000 字符会被
明确拒绝，不会静默截断。

本地模式只接受 `localhost`、`127.0.0.0/8` 或 `::1` 回环地址。云端 API Key 只保存在操作系统
凭据库，由独立 Python Worker 子进程在执行时读取，不进入 SQLite、Worker 进程参数或日志。
OpenAI-compatible Provider 通过 HTTPS `/chat/completions` 发送 Bearer 凭据和 strict JSON Schema
请求，并禁止 HTTP 重定向。本地与云端均不会自动回退到另一 Provider；认证、限流、超时、服务不可用、
拒绝和无效响应都会以不含密钥的安全错误结束任务。模型结果须通过固定 Pydantic Schema 与引用归属
校验；首次失败会修复重试一次，第二次仍无效则安全失败。

分析完成后，可在同一页面逐条将待确认问题标记为“纳入测试设计”或“无需覆盖”并填写确认说明。
已接受的问题可幂等转换为测试点草稿；每个来源问题最多生成一个测试点。测试点保留来源问题 ID 和
原文引用，可编辑标题、验证目标、正向/异常/边界/状态/权限/兼容/性能类型、P0-P3 优先级、
草稿/已确认/已禁用状态及自动化候选标记。测试点生成后原确认结论锁定，避免审计依据被改写。
此转换是本地确定性操作，不会再次调用模型或外发数据。

已确认测试点可继续幂等转换为结构化测试用例草稿；每个来源测试点最多生成一个用例。用例支持编辑
标题、前置条件、P0-P3 优先级、标签、手工/API/Web/移动端自动化类型、草稿/已确认/已禁用状态，
以及一至多个“操作 + 预期结果”步骤，并可多选后批量确认或禁用。用例生成后来源测试点锁定，
转换同样完全在本地确定性执行，不会再次调用模型或外发数据。

测试点还会获得透明的自动化候选建议：异常、边界、状态、权限和性能类型建议 API 自动化；正向和
兼容性类型建议先人工评审。新测试点自动继承候选标记，新用例在候选开启时继承建议类型；已有草稿
仅展示规则编号、理由和“一键应用”，不会被后台静默覆盖，人工仍可修改最终选择。

分析页同时提供只读需求追踪矩阵，将每个分析问题的稳定原文引用、人工确认、测试点和测试用例串成
一行，并统一标记“未确认、已排除、已接受待设计、已有测试点、用例草稿、已覆盖、已禁用”。矩阵
支持覆盖汇总和状态筛选，由当前运行的冻结数据实时派生，不复制或新增业务数据。

“执行”页面已提供 M5 的首个 HTTP 闭环：可为当前工作空间创建 HTTP/HTTPS 环境，保存普通变量，并将
安全变量值写入操作系统凭据库。请求路径、请求头和 UTF-8 请求体支持 `{{NAME}}` 普通变量及
`{{secret.NAME}}` 安全变量引用；数据库与 Worker 启动参数只保存模板、环境快照和安全变量名称，不保存
展开后的安全变量值。单次请求在独立 `spawn` Worker 中执行，支持 1-60 秒请求超时、任务取消、进程
崩溃/应用重启恢复、最多 2 MiB 的文本或 Base64 二进制响应，以及状态码、耗时和脱敏响应头/响应体展示。
可配置状态码、响应头、正文包含和 JSON 路径等值断言；GET/HEAD/OPTIONS 可对超时和服务不可用进行最多
3 次受控尝试。运行记录持久化不含请求/响应正文的安全事件，并支持终态运行按冻结模板重跑。Runner 不
自动跟随重定向，也不隐式使用系统代理。

WebSocket 执行复用相同环境、普通变量和 keyring 安全变量，将 HTTP/HTTPS Base URL 映射为 ws/wss。
单次运行可按序发送最多 10 条文本消息、接收最多 20 条文本或 Base64 二进制消息，配置 5-60 秒 Ping
心跳、最多一次显式自动重连及 encoding、文本等值/包含、JSON 路径严格等值断言。任务在独立 `spawn`
Worker 中支持实时任务推送、轮询恢复、取消、总超时、崩溃/重启恢复和安全事件；断言失败进入 `failed`。连接不使用
系统代理，模板展开结果与安全变量不进入 SQLite、进程参数或日志。自动重连只用于连接超时或不可用，
并会重放完整发送序列，可能产生重复副作用；超限和断言失败不重连。批量运行仍待后续。

“Protobuf”页面可从当前工作空间选择并导入最大 1 MiB 的单个 `.proto` 文件。后端通过受限
`grpcio-tools` 子进程生成并冻结 FileDescriptorSet，数据库保存相对路径、SHA-256 和描述符，不保存
用户输入的 JSON/Base64 编解码内容。页面展示 package、service/RPC、message、enum 和字段，并可按
冻结 SHA-256 在本机完成 JSON → Protobuf Base64 与 Base64 → JSON。未知字段、无效 JSON/Base64、
解码失败和版本变化会明确拒绝。当前只允许单文件定义与 `google/protobuf` 内置类型。

“Proto 执行”页面可复用 HTTP/HTTPS 环境、普通变量及 keyring 安全变量，选择冻结资产中的非流式
Service/RPC，将请求 JSON 动态编码为 `application/x-protobuf` 并通过独立 `spawn` Worker 执行一次
HTTP POST。响应限制为 2 MiB，使用冻结描述符解码为 JSON 后执行严格类型字段等值断言；支持轮询进度、
取消、请求/总超时、进程崩溃和应用重启恢复。传输禁用系统代理与重定向，安全变量只在 Worker 内展开，
响应头和解码后的字符串字段落库前脱敏。当前不是原生 gRPC，不支持流式 RPC、本地多文件 import、批量
执行。

桌面端为当前工作空间建立统一任务事件 WebSocket，覆盖文档解析、AI 分析、HTTP、WebSocket 和 Protobuf
执行。服务端只推送任务类型、ID、状态、进度和生命周期时间戳；前端收到事件后通过原有工作空间作用域 API
刷新结果、失败原因和脱敏事件。连接使用单调序号去重，检测到序号缺口或重新连接时主动恢复当前任务，
并保留页面轮询作为容错兜底。会话令牌经过 Base64URL 编码放入 `Sec-WebSocket-Protocol`，不会进入 URL，
服务端只回选公开的 `ai-qa-task-events` 协议名。

桌面端每次启动都会创建随机回环端口和高熵会话令牌，通过 context-isolated Electron
preload 桥将连接信息交给 Vue API Client；首页会显示本地 FastAPI 的健康状态和后端版本，
窗口退出后后端随之停止。后端绑定地址只接受规范 IPv4 回环 `127.0.0.1`，通配、局域网、IPv6 和
`localhost` 别名都会在启动前被拒绝；桌面 Sidecar 还会在输出握手前复核真实 listener 地址。生产
渲染器使用受信 `app://ai-qa-assistant` 协议。

如需只调试浏览器界面，可分别运行 `uv run python -m backend.app.run` 和
`pnpm --dir frontend dev:web`。此模式固定使用 `http://127.0.0.1:8765`；若配置
`AI_QA_SESSION_TOKEN`，前端还需通过 `VITE_API_SESSION_TOKEN` 提供相同令牌。

## 开发环境要求

- Python 3.12（项目通过 `.python-version` 固定，不支持 3.13）。
- uv。
- Node.js 24 和 pnpm 11。
- pnpm 安装的 Electron 运行时；不再需要 Rust、Cargo 或 Tauri 系统依赖。
- `protobuf` 运行时与 `grpcio-tools` 由 `uv sync` 安装，不要求系统预装 `protoc`。

源码开发版由 Electron 主进程使用项目 `.venv` 中的 Python 启动 FastAPI。`pnpm backend:sidecar`
使用 PyInstaller onedir 构建独立 Python Sidecar；`pnpm electron:package` 会先构建该 Sidecar，再将其
作为 Electron resources 打入候选目录。打包态不依赖仓库或 `.venv`，业务数据库位于 Electron
`userData/data/ai_qa_assistant.db`，Sidecar 在安全握手前自动升级 Alembic，并在 Electron 会话心跳停止后退出。

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
pnpm backend:sidecar
pnpm electron:package
pnpm electron:make
pnpm installer:test
pnpm installer:validate
```

核心用户闭环可单独运行：

```bash
uv run pytest -q backend/tests/e2e/test_core_user_loop.py
```

该场景使用临时 SQLite、临时工作空间和本机回环确定性服务，串联需求导入、独立解析/分析 Worker、
测试点与用例确认、独立 HTTP 执行 Worker 和报告导出，不访问外网或系统模型凭据。

`electron:package` 会先按 `electron/checksums.json` 验证 Electron ZIP：优先使用
`AI_QA_ELECTRON_ZIP_DIR` 指定目录，否则递归查找操作系统的 Electron 下载缓存；只有文件名与
SHA-256 均匹配的 `electron-v<version>-<platform>-<arch>.zip` 才会交给 Forge，从而避免已通过校验的
镜像缓存因 URL 哈希目录不同而被重复下载。当前 Windows x64 自包含候选目录生成到
`frontend/out/AI QA Assistant-win32-x64`，内置 `resources/ai-qa-backend/ai-qa-backend.exe`，不再使用
项目 `.venv`。Forge package 候选目录不是安装器。

`electron:make` 在 Windows 上生成未签名的 Squirrel.Windows 内部安装器候选，包括 Setup.exe、
full.nupkg、RELEASES 和根级 `SHA256SUMS.txt`。`installer:validate` 只校验制品和清单，不安装应用；
Windows CI 还会在一次性 runner 中执行安装、后端迁移与首次启动、卸载及用户数据库保留验收。make
会生成 CycloneDX 1.6 SBOM、脱敏发布元数据和五项文件校验清单，并提供只经 CI Secret 注入的可选 PFX
签名入口。校验和与签名入口不能替代正式证书的实际签名结论，当前候选不得作为正式公开版本分发。详见
`docs/10-Windows候选发布说明.md`。

当前 `0.1.0` 候选已在开发机当前用户配置文件完成一次真实 Setup 生命周期：安装、Sidecar/Alembic/
renderer 就绪、`api_host=127.0.0.1`、卸载和用户数据库保留均通过。Squirrel 卸载可能留下固定墓碑文件；
门禁只允许 `.dead`、Updater 本体和对应版本目录内的 Electron/Squirrel 固定运行时文件；记录数量后
清理测试安装根，任何未知残留都失败。提交 `f6c3f02` 的 GitHub hosted Windows runner 也已完成相同安装生命周期并
归档候选。生命周期现已增加同版本重复安装/再次首启及唯一 Windows keyring 探针的卸载保留和主动清理；
该结论仍不覆盖独立 VM 的 SmartScreen、跨版本升级或正式签名验收。

安装候选前的哈希校验、首次使用闭环、HTTP/WebSocket/Protobuf 示例、诊断、备份和卸载数据范围见
`docs/11-Windows安装与首次使用.md`；版本级变化与未完成门禁见根目录 `CHANGELOG.md`。

## 当前进度

- M0 工程骨架：已完成。
- M1 工作空间：已完成创建、系统目录选择、最近列表、打开、重命名、安全删除记录和 SQLite 恢复。
- M1 设置：已完成浅色/深色主题、本地 Ollama / 云端 OpenAI-compatible 配置、
  操作系统凭据库写入/状态/清除及隐私约束。
- M1 备份与诊断：已完成 SQLite 一致性备份、完整性检查、诊断信息与桌面维护页面。
- M2 文档管线：已完成 Markdown/TXT/DOCX/PDF 系统文件选择、工作空间边界校验、SHA-256 去重、
  文档版本、独立解析 Worker、进度/取消/超时/崩溃恢复、文本预览及稳定引用片段。文本按行段、DOCX
  块或 PDF 页保存来源范围、字符偏移和稳定引用 ID；支持单次选择或拖入最多 50 个文件并逐项显示导入结果。
  PDF 只提取已有文本层，不执行 OCR。
- M2 文档管线已完成；M3 本地 Ollama、OpenAI-compatible 云端分析和问题人工确认切片已完成。
- M3 AI 分析：已完成 Provider 抽象、本地/云端五维结构化分析、稳定引用校验、一次输出修复重试、
  独立 Worker 生命周期、逐次云端外发确认、上下文快照校验、分析审计记录、待确认问题接受/拒绝，
  以及确认结果到可编辑测试点、结构化测试用例草稿的幂等转换、用例批量确认/禁用和需求追踪矩阵。
  Qdrant Local 检索索引、模型驱动的多场景扩展和测试执行仍属于后续切片。
- M4 测试设计：已完成测试点、结构化用例、需求追踪矩阵与透明自动化候选规则的最小闭环。
- M5 接口执行：已完成 HTTP 环境、普通/安全变量、独立 Worker 请求、统一实时任务推送、轮询恢复、取消/超时/崩溃恢复、
  脱敏结果、四类断言、安全重试、持久化事件和冻结模板重跑；WebSocket 已完成有序多消息发送/接收、
  Ping 心跳、最多一次受控重连、四类消息断言与完整 Worker 生命周期；Protobuf 已完成单文件资产导入、
  结构摘要、本地动态 JSON/Base64 编解码，以及非流式 RPC 的单次 HTTP
  二进制执行、字段断言和完整 Worker 生命周期；原生 gRPC、流式 RPC 和批量执行待后续。
- M6 报告与打包：已完成工作空间级结果聚合、14 日 UTC 趋势、通过率/平均时长/慢执行统计、分析与测试设计
  摘要，以及按稳定状态/错误码生成的本地确定性失败初步归因。JSON、Markdown、HTML 三种脱敏导出通过
  Electron 系统保存对话框落盘，不导出请求/响应正文、凭据值或变量值。独立 PyInstaller Sidecar、
  打包态自动迁移、用户数据目录、会话心跳回收、Forge 自包含候选目录、Squirrel 未签名安装器候选、
  SHA-256 制品清单、CycloneDX SBOM、签名配置/验证门禁、一次性 Windows runner 安装生命周期门禁、
  开发机当前用户和 GitHub hosted Windows runner 真实安装/卸载回归已完成；模型辅助复核、正式证书
  实际签名、独立 VM SmartScreen 和跨版本升级实测仍待后续。
