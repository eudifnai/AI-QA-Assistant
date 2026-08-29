# 变更记录

本文件记录 AI QA Assistant 的用户可见变化。版本仍处于内部候选阶段；除非发布说明明确标记，条目不代表
已经完成正式签名、干净虚拟机或公开分发验收。

## [Unreleased]

### 待完成

- 使用受控正式证书完成 Authenticode 签名与时间戳验证。
- 使用正式签名候选在独立 Windows VM 完成发布者信息和 SmartScreen 人工检查。
- 首个公开版本发布后归档可回滚制品，并把它作为下一版本跨版本升级、数据库迁移和回滚验收基线。

## [0.1.0] - 2026-08-24（内部候选）

### 新增

- 交付 Electron + Vue 3 桌面应用与独立 Python 3.12 Sidecar，本地 API 仅绑定
  `127.0.0.1`，使用每次启动生成的会话令牌。
- 交付工作空间、设置、系统凭据库、数据库诊断与一致性备份。
- 支持 Markdown、TXT、DOCX 和文本型 PDF 导入、版本、稳定引用、独立解析 Worker 与批量导入。
- 支持本地 Ollama 和显式确认后的 OpenAI-compatible 云端需求分析，以及测试点、测试用例和需求
  追踪矩阵。
- 支持 HTTP、WebSocket 和非流式 Protobuf HTTP 执行、断言、取消、超时、崩溃恢复和统一任务事件流。
- 支持工作空间级统计、确定性失败初步归因，以及脱敏 JSON、Markdown 和 HTML 报告导出。
- 生成 Windows x64 Squirrel Setup、完整 NUPKG、RELEASES、CycloneDX 1.6 SBOM、发布元数据和
  SHA-256 清单。

### 安全与隐私

- API Key 和安全变量仅写入操作系统凭据库，不写入 SQLite、Worker 参数、前端 Store 或报告。
- 本地模型只接受回环地址；云端模型只接受 HTTPS，且设置级同意和每次分析的数据范围确认缺一不可。
- HTTP、WebSocket 和 Protobuf Runner 禁用系统代理与重定向，并在持久化前脱敏已知敏感值。
- 用户文件必须位于已选工作空间内；外部命令使用参数数组，Protobuf 编译不加载工作空间 Python 代码。

### 工程与发布

- 使用 SQLite、SQLModel 和 Alembic 管理业务数据与迁移。
- 长任务在独立 `spawn` Worker 中执行，覆盖进度、成功、失败、取消、超时、崩溃和重启恢复。
- 建立 Python、前端、Electron、迁移、核心闭环及 Windows 安装生命周期自动化门禁。
- 质量工作流支持 `codex/release-*` 候选分支自动运行和 `workflow_dispatch` 手动重跑；
  `formal` 模式缺少 PFX Secret 或 Authenticode/时间戳验证失败时必须阻塞，并由回归测试固定
  关键发布门禁。
- 成功的非 PR Windows 候选会把 Setup、NUPKG、RELEASES、SBOM、发布元数据和哈希清单归档到
  GitHub Actions 90 天；后续版本可按正整数 run ID 下载上一候选并执行真实升级生命周期。
- 开发机当前用户已完成未签名 Setup 的安装、首次启动和卸载回归；卸载保留用户数据库。
- 提交 `f6c3f02` 的 GitHub hosted Windows runner 已完成未签名候选的 make、制品校验、真实安装、
  Sidecar/Alembic/renderer 首启、卸载和用户数据库保留，并归档候选制品。
- 卸载门禁精确识别 Electron 可能被短暂占用的 SwiftShader DLL 与清单文件，取证后只清理固定版本目录，
  其他未知文件或目录仍会阻塞候选发布。
- 打包态 Python Sidecar 的冷启动等待上限由 15 秒调整为 45 秒，以覆盖干净 Windows 环境的首次扫描与
  解压抖动；源码开发模式仍保持 15 秒，安装验收外层超时和失败证据保持不变。
- 安装生命周期增加同版本重复安装/再次首启，以及唯一 Windows keyring 探针的卸载保留与主动清理取证；
  探针值只通过子进程环境传递，不进入参数、日志或验收证据。
- 将 Forge 使用的 `@electron/packager` 覆盖到 `20.3.0`，统一使用 Electron 的安全解压实现；删除
  `GHSA-jmr9-qjv8-65gv` 审计豁免，high 级依赖审计恢复为零豁免阻塞。通过 pnpm 补丁将稳定版
  Forge 7.11.2 的旧回调 hook 适配到 Packager 20 的对象/Promise 接口，并由真实 Windows make 回归锁定。

### 已知限制

- 当前 Setup 未签名，只能作为受控内部候选；Windows 可能显示未知发布者或 SmartScreen 提示。
- 尚未完成正式证书签名、跨版本升级和独立 VM SmartScreen 验证。
- 当前不支持 OCR、原生/流式 gRPC、本地多文件 Proto import、批量执行、数据库恢复或自动备份。
- 前端主包仍有大于 500 kB 的构建警告。
