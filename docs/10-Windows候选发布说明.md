# Windows 内部候选发布说明

## 1. 候选状态

当前版本为 `0.1.0` Windows x64 内部候选。它已包含 Electron 应用、独立 Python Sidecar、Alembic
迁移和冻结 Protobuf 编译器，并在开发机当前用户配置文件完成真实安装、首次启动和卸载回归；但尚未
进行 Authenticode 签名，也未在干净虚拟机完成安装或跨版本升级验收。
不得将本候选标记为正式稳定版或面向不受控用户公开分发。

## 2. 生成制品

运行：

```bash
pnpm electron:make
```

输出位于 `frontend/out/make/squirrel.windows/x64/`：

- `AI-QA-Assistant-Setup.exe`：Squirrel.Windows 每用户安装器。
- `AIQAAssistant-0.1.0-full.nupkg`：完整更新包。
- `RELEASES`：Squirrel 更新元数据。
- 上级 `frontend/out/make/ai-qa-assistant.cdx.json`：CycloneDX 1.6 SBOM，覆盖 Python 与 pnpm
  锁文件中的源码、运行和构建依赖。
- 上级 `frontend/out/make/RELEASE-METADATA.json`：版本、目标、签名模式、SBOM 摘要和制品摘要；
  不包含证书路径或口令。
- 上级 `frontend/out/make/SHA256SUMS.txt`：上述五项文件的 SHA-256 清单。

make 会重新构建前端和 Sidecar、校验 Electron 官方 ZIP，然后按固定顺序生成安装器、SBOM、发布元数据
与校验清单。失败时不得沿用旧 `out/make` 目录声称构建成功。

## 3. 完整性检查

发布或复制制品前，按 `SHA256SUMS.txt` 重新计算每个文件的 SHA-256。Windows 可使用：

```powershell
Get-FileHash -Algorithm SHA256 .\frontend\out\make\squirrel.windows\x64\AI-QA-Assistant-Setup.exe
```

SHA-256 只能发现传输或存储篡改，不能证明发布者身份。当前 Setup 的预期签名状态是 `NotSigned`；若签名
状态与发布记录不符，或清单不匹配，必须停止验证和分发。

## 4. 已验证范围

- Forge make 在 Windows x64 成功退出。
- Setup.exe、full.nupkg、RELEASES 同时生成。
- 确定性 CycloneDX 1.6 SBOM 和脱敏发布元数据已生成。
- SHA-256 清单覆盖三个 Squirrel 制品、SBOM 和发布元数据并重新计算一致。
- full.nupkg 内含 Electron resources 下的完整 Python Sidecar。
- package 候选可启动，并在重定向 Electron `userData` 中自动创建和迁移 SQLite 数据库。
- package 候选通过受限环境变量生成最终 `ready` 证据，证据不包含会话令牌，应用随后正常退出。
- Setup.exe 在开发机当前用户完成安装、Sidecar/Alembic/renderer 就绪、回环 API 取证和卸载；
  卸载后用户数据库保留，安装根由门禁清理完成。

当前仍未验证干净 VM、SmartScreen、重复安装、跨版本升级或系统凭据库保留。

## 5. 自动化安装验收

无系统变更的本地检查：

```powershell
pnpm installer:test
pnpm installer:validate
```

`Validate` 会拒绝路径越界、清单重复、制品缺失或 SHA-256 不匹配，并生成一份临时 JSON 汇总证据。
它还会校验 SBOM 格式及发布元数据中的版本、目标、签名模式和 SBOM 摘要。元数据声明 `pfx` 时，
即使未显式传参也会强制验证 Setup 和 full.nupkg 内全部 `.exe/.dll/.node` 的 Authenticode 签名及
时间戳；任一文件无效都停止分发。可用 `pnpm installer:validate:signed` 强制要求签名候选。
生命周期模式会真实安装和卸载应用，通常只应在一次性 Windows VM/runner 中执行，并且必须显式确认系统变更：

```powershell
pwsh -NoProfile -File scripts/windows-release/Invoke-InstallerAcceptance.ps1 `
  -Mode Lifecycle `
  -AllowSystemChanges
```

该模式通过受限的专用环境变量启动已安装 EXE。应用只有在 Sidecar 安全握手、Alembic 迁移、数据库创建和 renderer
加载均完成后，才向系统临时目录原子写入不含令牌和端口、且固定包含 `api_host=127.0.0.1` 的 `ready`
证据；随后脚本调用 Squirrel 卸载并确认主程序与卸载项消失、用户数据库按当前策略保留。Squirrel 固定
墓碑残留会被精确白名单取证并由测试脚本清理，任意未知残留都会失败。传入
`-PreviousArtifactRoot <上一候选 out/make>` 时还会
执行跨版本升级并确认数据库路径保持一致；未传入时升级阶段固定记录为 `skipped`。
验收模式启动失败时不会打开需要人工关闭的模态对话框，而会原子写入不含会话令牌的错误证据并以
非零状态退出，生命周期脚本据此报告具体启动错误；就绪证据完成后会先停止 Sidecar，再强制结束专用
验收进程，避免无交互 runner 被 Electron 退出钩子挂起。外部进程超过默认 180 秒仍会被终止并报告
最后一个安全状态。脚本还会把受控证据根显式注入子进程的 `TEMP/TMP`，确保 PowerShell/.NET 与
Electron/Node 在干净 runner 上使用同一个临时目录边界。

当前开发机已执行 `Validate`、package EXE 冒烟和当前用户 Setup 生命周期；最终证据状态为 `passed`，
安装根、进程和卸载项已清理，319,488 字节用户数据库保留。GitHub Windows runner 已配置生命周期门禁，
但在实际干净 runner 工作流成功完成前，不得勾选
“干净环境启动成功”。`0.1.0` 是首个公开版本，没有上一稳定安装包，因此本次跨版本阶段记为
`skipped / not applicable`；不得声称升级已经验证，也不得用同版本或人工伪造制品替代。正式发布后
必须归档可回滚的 `0.1.0` 制品，作为下一版本的强制升级基线。验收 JSON 默认只存在于临时 runner，
不上传包含本机路径和制品哈希的文件。
对已经推送到 GitHub 的候选引用，可从 Actions 界面通过 `workflow_dispatch` 手动重跑同一质量工作流；
默认选择 `internal`，仅用于未签名内部候选；正式候选必须选择 `formal`。后者在 PFX/口令 Secret
缺失时立即失败，并在构建后以 `-RequireSignedArtifacts` 强制验证 Authenticode 和可信时间戳。
当前未提交 working tree 仍不能通过该入口直接验证。
`codex/release-*` 候选分支的 push 会自动运行相同门禁，可用于合并 `main` 前的干净 runner 验证。
成功的非 PR Windows Job 会生成 `windows-release-candidate-<run_id>` artifact，保留 90 天，内容
仅限 Setup、full.nupkg、RELEASES、SBOM、脱敏发布元数据和 SHA-256 清单，不包含生命周期 JSON、
PFX、口令或 runner 本机路径。下一版本手动运行时填写该正整数 `previous_run_id`，工作流会从当前
仓库下载对应候选，完成哈希校验后传入 `-PreviousArtifactRoot` 执行真实升级生命周期。

## 6. 受控 PFX 签名

本地或受控 runner 只通过进程环境注入证书，不把证书或口令写入仓库、`.env`、SQLite、SBOM、发布
元数据或日志：

```powershell
$env:AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE = "C:\secure\release.pfx"
$env:AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD = "<从凭据系统注入>"
$env:AI_QA_WINDOWS_SIGN_TIMESTAMP_SERVER = "http://timestamp.digicert.com" # 可省略
pnpm electron:make
pnpm installer:validate:signed
```

证书路径和口令必须同时存在；证书必须是已存在的 `.pfx/.p12`，时间戳 URL 只允许 HTTP/HTTPS，且
签名失败不能降级成成功候选。构建子进程会把口令映射给 `@electron/windows-sign` 的标准环境变量，
Forge 配置对象和 SBOM 子进程都不接收口令字段。CI 可选 Secret 名为
`AI_QA_WINDOWS_SIGN_PFX_BASE64` 和 `AI_QA_WINDOWS_SIGN_PFX_PASSWORD`；缺少两者时继续生成明确标记的
未签名内部候选，只配置其中之一则失败。临时 PFX 位于 runner 临时目录并在 `always()` 步骤删除。

当前仓库和本机没有受控正式证书，所以本节说明的是已测试的签名入口和门禁，不代表当前 `0.1.0` 制品
已经签名。

## 7. 下一发布门禁

1. 在受控 CI 配置正式 PFX 证书 Secret，通过 `workflow_dispatch` 选择 `formal`，生成候选并观察
   签名/时间戳门禁实际通过；不得以默认 `internal` 的绿色结果替代正式发布证据。
2. 在 Windows 干净虚拟机快照中校验 SHA-256 后安装，完成首次启动和核心健康检查。
3. `0.1.0` 首次发布的跨版本阶段记录为不适用；归档其可回滚制品，并从下一版本开始强制执行
   上一稳定版升级、Alembic 数据迁移和用户数据保留。
4. 卸载后核对应用文件、用户数据库、备份和操作系统凭据的预期保留/删除范围。
5. 基于现有 `CHANGELOG.md` 和 `docs/11-Windows安装与首次使用.md` 完成正式签名版本的发布说明、
   可回滚制品和签名证书轮换/吊销预案。

## 8. 已知限制

- 安装器未签名，Windows 可能显示未知发布者或 SmartScreen 警告。
- 目前只生成 Windows x64 Squirrel 制品，没有 MSI、MSIX、macOS 或 Linux 安装包。
- 版本仍为 `0.1.0`，尚未建立跨版本升级基线。
- 前端主包仍有大于 500 kB 的构建警告，不影响本次安装器生成，但后续应按页面拆分优化加载体积。
- `pnpm audit --audit-level high` 仍报告 Forge 官方兼容的 `@electron/packager 18` 传递依赖
  `extract-zip 2.0.1` 的一项 high 风险；审计建议的 `2.0.2` 尚未发布。当前构建在解压前校验
  Electron 官方 ZIP 的固定 SHA-256，并仅限内部候选使用；正式发布前必须升级到 Forge 支持的修复版本
  或完成等效修复与专项安全验证。
