# Windows 安装与首次使用

## 1. 适用范围

本文适用于 AI QA Assistant `0.1.0` Windows x64 内部候选。当前安装器未做 Authenticode 正式签名，
不得面向不受控用户公开分发。候选状态、制品结构和已验证范围见
[`10-Windows候选发布说明.md`](./10-Windows候选发布说明.md)，版本变化见根目录
[`CHANGELOG.md`](../CHANGELOG.md)。

安装版已经内置 Electron 和 Python Sidecar，不要求用户安装 Python、Node.js、pnpm、Rust 或 `protoc`。
源码开发仍要求 Python 3.12、uv、Node.js 24 和 pnpm 11，详见根目录 `README.md`。

建议环境：

- 目标环境为 Windows 10/11 x64；GitHub hosted Windows runner 的安装生命周期已通过，同版本重复安装
  已纳入自动验收；正式签名候选的独立 VM SmartScreen 尚未验证，当前候选未生成 ARM64、MSI 或 MSIX。
- 当前用户可写的应用数据目录和至少 1 GiB 可用磁盘空间。
- 如使用本地分析，先安装并启动 Ollama；如使用云端分析，准备受信任的 OpenAI-compatible HTTPS
  endpoint 和 API Key。

## 2. 安装前校验

只从受控渠道同时取得以下文件，不要单独接收一个 Setup：

- `AI-QA-Assistant-Setup.exe`
- `AIQAAssistant-0.1.0-full.nupkg`
- `RELEASES`
- `ai-qa-assistant.cdx.json`
- `RELEASE-METADATA.json`
- `SHA256SUMS.txt`

在 PowerShell 中重新计算 Setup 哈希：

```powershell
Get-FileHash -Algorithm SHA256 .\AI-QA-Assistant-Setup.exe
```

结果必须与 `SHA256SUMS.txt` 中同一路径记录一致。若从源码候选目录验证，可运行：

```powershell
pnpm installer:validate
```

当前发布元数据必须声明 `unsigned_internal_candidate`，Setup 的签名状态应为 `NotSigned`。哈希或签名状态
与发布记录不一致时停止安装。遇到未知发布者或 SmartScreen 提示时，只能在已确认受控来源和哈希后按
组织策略决定是否继续；不要把关闭系统安全功能作为安装步骤。

## 3. 安装、启动与数据位置

1. 双击 `AI-QA-Assistant-Setup.exe`。Squirrel 以当前 Windows 用户安装应用。
2. 从开始菜单启动 “AI QA Assistant”。主导航左侧任务状态应能建立本地连接。
3. 打开“维护”，确认 API 监听为 `127.0.0.1`、数据库完整性为 `ok`，并记录数据库版本和路径。

默认业务数据位于：

```text
%APPDATA%\AI QA Assistant\data\ai_qa_assistant.db
```

数据库备份位于同一数据目录下的 `backups` 子目录。工作空间原文件仍保存在用户选择的目录，不会复制到
数据库备份。API Key 和安全变量存放在 Windows 凭据库，不在 SQLite 中。

## 4. 首次使用闭环

### 4.1 创建工作空间

1. 打开“工作空间”，填写名称。
2. 使用系统目录选择器选择本地目录，或填写绝对路径。
3. 创建后点击“打开”。删除工作空间记录只从应用最近列表移除记录，不删除本地目录或文件。

待导入的需求文档和 `.proto` 必须位于该工作空间内；路径越界会被后端拒绝。

### 4.2 配置模型

打开“设置”：

- 本地模式：选择 Ollama，填写模型名和回环服务地址，例如 `http://127.0.0.1:11434`。本地模式不会
  自动回退到云端。
- 云端模式：填写 Provider、模型和 HTTPS Base URL，确认设置级数据边界，再将 API Key 保存到系统
  凭据库。每次分析仍会展示完整 endpoint、文档版本、片段数和字符数，并要求逐次确认。

保存凭据后输入框会立即清空；应用只展示凭据是否存在，不回显值。

### 4.3 导入和分析需求

1. 打开“文档”，选择工作空间，再选择或拖入 Markdown、TXT、DOCX 或文本型 PDF。
2. 等待解析任务进入 `passed`，检查文本预览和稳定引用。PDF 只读取已有文本层，不执行 OCR。
3. 打开“分析”，选择已解析文档并发起分析。本地/云端失败不会自动切换 Provider。
4. 审阅结构化问题，逐条选择“纳入测试设计”或“不需覆盖”，再生成和编辑测试点。
5. 确认测试点后生成结构化测试用例，并在需求追踪矩阵检查覆盖状态。

### 4.4 执行接口并导出报告

1. 在“执行”创建 HTTP 环境和变量；WebSocket 与 Proto 执行复用该环境。
2. 在“Protobuf”导入单个 `.proto`，检查资产摘要并按需进行本地 JSON/Base64 编解码。
3. 分别运行 HTTP、WebSocket 或 Protobuf 请求，查看任务状态、断言和脱敏安全事件。
4. 打开“报告”查看统计和确定性失败初步归因，再通过系统保存对话框导出 JSON、Markdown 或 HTML。

报告不包含请求/响应正文、普通变量值、API Key 或 keyring 内容。“未知”归因必须人工复核。

## 5. HTTP 示例

以下示例假定被测服务在本机 `http://127.0.0.1:8000`，不是 AI QA Assistant 自身的随机端口。

在“执行”创建环境：

```text
环境名称：local-api
Base URL：http://127.0.0.1:8000
普通变量：{"TENANT":"qa"}
```

如需认证，在“安全变量”保存名称 `API_TOKEN`，然后配置：

```text
方法：GET
路径：/health?tenant={{TENANT}}
请求头：{"Authorization":"Bearer {{secret.API_TOKEN}}"}
预期 HTTP 状态码：200
JSON 路径：$.status
JSON 标量预期值："ok"
```

JSON 标量预期值必须是合法 JSON 文本，因此字符串需要包含双引号。GET、HEAD 和 OPTIONS 只有在传输
超时或服务不可用时才能进行最多三次受控尝试；非幂等方法不会自动重试。

## 6. WebSocket 示例

WebSocket 页面会把所选 HTTP/HTTPS Base URL 映射为 ws/wss。示例配置：

```text
WebSocket 路径：/events
握手请求头：{"Authorization":"Bearer {{secret.API_TOKEN}}"}
第 1 条发送消息：{"action":"subscribe"}
追加发送消息：["{\"action\":\"ping\"}"]
接收消息数：1
```

有序消息断言示例：

```json
[
  {"message_index": 0, "kind": "encoding", "path": null, "expected": "text"},
  {"message_index": 0, "kind": "json_path_equals", "path": "$.type", "expected": "\"ack\""}
]
```

可用断言类型为 `encoding`、`text_equals`、`text_contains` 和 `json_path_equals`。自动重连最多一次，且会
重放完整发送序列，可能重复触发远端副作用；只有确认目标操作可接受重复执行时才启用。

## 7. Protobuf 示例

当前只支持单个 `.proto` 和 `google/protobuf` 内置 import，不支持本地多文件 import、原生 gRPC 或
流式 RPC。示例资产：

```proto
syntax = "proto3";
package demo;

service EchoService {
  rpc Echo(EchoRequest) returns (EchoResponse);
}

message EchoRequest { string message = 1; }
message EchoResponse { bool ok = 1; string message = 2; }
```

将文件保存在工作空间内并从“Protobuf”导入。若被测服务以 HTTP POST 接收
`application/x-protobuf`，在“Proto 执行”选择资产、Service 和 Unary RPC，然后填写：

```json
{"message":"hello"}
```

字段断言：

```json
[
  {"path":"$.ok","expected_json":"true"},
  {"path":"$.message","expected_json":"\"hello\""}
]
```

`expected_json` 必须是 JSON 标量文本，并进行严格类型比较。Proto 源文件不会随网络请求发送；请求使用
导入时冻结的描述符编码。

## 8. 备份、卸载与数据保留

在“维护”点击“创建数据库备份”可生成通过 SQLite 完整性检查的一致性快照。当前版本不提供自动备份、
恢复或备份删除；在没有经过验证的恢复流程前，不要用文件覆盖正在运行的数据库。

卸载前：

1. 在“维护”创建备份并记录数据库与备份路径。
2. 如不希望保留模型 API Key，在“设置”清除凭据。
3. 在“执行”删除不再需要的 HTTP 环境，以清除该环境关联的安全变量。
4. 退出应用，再通过 Windows“已安装的应用”卸载。

当前卸载策略会移除应用文件和卸载项，但保留 `%APPDATA%\AI QA Assistant` 下的业务数据库和备份。
工作空间原文件始终由用户管理。安装生命周期会写入唯一 Windows keyring 探针，确认卸载不会删除该
系统凭据并在取证后主动清理；这证明安装器不会全局清理 Windows 凭据。应用目前也没有卸载时自动删除
凭据的路径，因此仍需在卸载前从应用显式清除不希望保留的模型 API Key 和安全变量。

## 9. 常见问题与诊断

### 应用启动后本地服务不可用

- 完全退出应用后重新启动，避免同时运行多个候选。
- 在“维护”确认 API 监听是 `127.0.0.1`；不要改为 `0.0.0.0`、局域网地址或 `localhost`。
- 若仍失败，记录应用版本、Python 版本、数据库版本、数据库完整性和安全错误码，不要复制数据库中的
  用户内容或任何凭据值到公开问题。

### 文档无法导入

- 确认文件位于当前工作空间内，格式为 `.md/.txt/.docx/.pdf` 且不超过 10 MiB。
- PDF 必须是未加密且带文本层的文件；DOCX/PDF 损坏会以稳定错误结束任务，不应导致应用退出。
- 相同工作空间内内容哈希重复会被拒绝。批量导入时单个失败不会阻止其他文件。

### 模型或凭据失败

- 本地 Ollama 地址必须为回环地址；检查模型名和 Ollama 是否已启动。
- 云端 Base URL 必须为 HTTPS；重新保存设置级同意，并在本次分析确认完整 endpoint 和数据范围。
- 凭据状态异常时在“设置”重新保存或清除 API Key。应用不会在本地与云端 Provider 之间自动回退。

### 执行任务失败或超时

- 根据稳定错误码区分目标不可用、超时、响应超限、断言失败和凭据库不可用。
- `cancelled`、`timeout`、`error` 与 `failed` 含义不同；不要把断言失败当作进程崩溃。
- WebSocket 自动重连会重放消息；Protobuf 请求必须选择与导入时 SHA-256 一致的冻结资产。
- 报告中的失败归因是本地规则初判，“未知”需要人工检查被测环境和数据。

### 安装器或升级问题

- 先重新校验 `SHA256SUMS.txt`，不要复用失败构建留下的旧 `out/make`。
- 当前候选未签名且未完成跨版本升级验收；不要用它覆盖无法恢复的唯一业务数据。
- 在正式升级门禁完成前，保留上一安装器、当前数据库备份和对应 SHA-256 清单。
