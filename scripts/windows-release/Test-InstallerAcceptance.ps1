#Requires -Version 7.4

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$modulePath = Join-Path $PSScriptRoot "InstallerAcceptance.psm1"
Import-Module -Name $modulePath -Force

function Assert-True {
    param(
        [Parameter(Mandatory)]
        [bool]$Condition,
        [Parameter(Mandatory)]
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Throws {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Action,
        [Parameter(Mandatory)]
        [string]$ExpectedMessage
    )
    try {
        & $Action
    }
    catch {
        if ($_.Exception.Message -notlike "*$ExpectedMessage*") {
            throw "异常消息不匹配：$($_.Exception.Message)"
        }
        return
    }
    throw "预期操作失败，但操作成功完成。"
}

function New-ReleaseFixture {
    param([Parameter(Mandatory)][string]$Root)

    $artifactDirectory = Join-Path $Root "squirrel.windows/x64"
    [System.IO.Directory]::CreateDirectory($artifactDirectory) | Out-Null
    $files = @(
        "AI-QA-Assistant-Setup.exe",
        "AIQAAssistant-0.1.0-full.nupkg",
        "RELEASES"
    )
    foreach ($name in $files) {
        [System.IO.File]::WriteAllText(
            (Join-Path $artifactDirectory $name),
            "fixture:$name",
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    $squirrelRelativePaths = @(
        $files | ForEach-Object { "squirrel.windows/x64/$_" }
    )
    $sbomPath = Join-Path $Root "ai-qa-assistant.cdx.json"
    [System.IO.File]::WriteAllText(
        $sbomPath,
        '{"bomFormat":"CycloneDX","specVersion":"1.6","components":[{"type":"library","name":"fixture","version":"1.0.0"}]}',
        [System.Text.UTF8Encoding]::new($false)
    )
    $metadataArtifactPaths = $squirrelRelativePaths + @("ai-qa-assistant.cdx.json")
    $metadataArtifacts = @(
        foreach ($relativePath in $metadataArtifactPaths) {
            $path = Join-Path $Root $relativePath
            [ordered]@{
                path = $relativePath
                sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                bytes = (Get-Item -LiteralPath $path).Length
            }
        }
    )
    $metadataPath = Join-Path $Root "RELEASE-METADATA.json"
    $metadata = [ordered]@{
        schema_version = 1
        app = [ordered]@{ name = "AI QA Assistant"; version = "0.1.0" }
        target = [ordered]@{ platform = "win32"; arch = "x64"; format = "squirrel.windows" }
        signing = [ordered]@{ mode = "unsigned_internal_candidate"; verification = "not_applicable_internal_candidate" }
        sbom = [ordered]@{
            format = "CycloneDX"
            spec_version = "1.6"
            path = "ai-qa-assistant.cdx.json"
            sha256 = (Get-FileHash -LiteralPath $sbomPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        artifacts = $metadataArtifacts
    }
    [System.IO.File]::WriteAllText(
        $metadataPath,
        ($metadata | ConvertTo-Json -Depth 8),
        [System.Text.UTF8Encoding]::new($false)
    )
    $relativePaths = $squirrelRelativePaths + @("ai-qa-assistant.cdx.json", "RELEASE-METADATA.json")
    $manifestLines = foreach ($relativePath in $relativePaths) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $Root $relativePath) -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relativePath"
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $Root "SHA256SUMS.txt"),
        (($manifestLines -join [Environment]::NewLine) + [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false)
    )
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ai-qa-installer-module-test-$([guid]::NewGuid().ToString('N'))"
try {
    New-ReleaseFixture -Root $testRoot

    $release = Get-VerifiedReleaseArtifacts -ArtifactRoot $testRoot
    Assert-True -Condition ($release.Artifacts.Count -eq 5) -Message "应验证三个 Squirrel 制品和两份发布记录。"
    Assert-True -Condition ($release.Version -eq "0.1.0") -Message "应从 full.nupkg 解析版本。"
    Assert-True -Condition ($release.SetupPath.EndsWith("AI-QA-Assistant-Setup.exe")) -Message "应定位 Setup.exe。"
    Assert-True -Condition ($release.SigningMode -eq "unsigned_internal_candidate") -Message "应识别未签名内部候选。"

    $databasePath = Join-Path $testRoot "smoke.db"
    [System.IO.File]::WriteAllText($databasePath, "sqlite")
    $smoke = [pscustomobject]@{
        status = "ready"
        app_version = "0.1.0"
        api_host = "127.0.0.1"
        database_path = $databasePath
        database_bytes = 6
    }
    Assert-InstalledApplicationSmokeEvidence -Smoke $smoke -ExpectedVersion "0.1.0"
    $errorSmoke = [pscustomobject]@{
        status = "error"
        message = "本地后端在完成启动前退出。"
    }
    Assert-Throws -Action {
        Assert-InstalledApplicationSmokeProcessResult -Smoke $errorSmoke -ExitCode 1 -ExpectedVersion "0.1.0"
    } -ExpectedMessage "安装后应用启动失败：本地后端在完成启动前退出。"
    $progressSmoke = [pscustomobject]@{ status = "electron_ready" }
    Assert-Throws -Action {
        Assert-InstalledApplicationSmokeProcessResult -Smoke $progressSmoke -ExitCode 2 -ExpectedVersion "0.1.0"
    } -ExpectedMessage "安装后应用异常退出，退出码 2"
    $smoke.api_host = "0.0.0.0"
    Assert-Throws -Action {
        Assert-InstalledApplicationSmokeEvidence -Smoke $smoke -ExpectedVersion "0.1.0"
    } -ExpectedMessage "就绪证据校验失败"

    $smokeTemporaryDirectory = Join-Path $testRoot "smoke-temporary"
    $smokeEvidenceDirectory = Join-Path $testRoot "smoke-evidence"
    $smokePaths = New-InstalledApplicationSmokePaths `
        -EvidenceDirectory $smokeEvidenceDirectory `
        -TemporaryDirectory $smokeTemporaryDirectory `
        -Identifier "fixed-evidence"
    Assert-True `
        -Condition ($smokePaths.TemporaryRoot -eq [System.IO.Path]::GetFullPath($smokeTemporaryDirectory)) `
        -Message "生命周期脚本应记录传给 Electron TEMP/TMP 的受控临时根。"
    Assert-True `
        -Condition ($smokePaths.TemporaryPath -eq (Join-Path $smokeTemporaryDirectory "ai-qa-acceptance-fixed-evidence.json")) `
        -Message "应用只能接收系统临时目录中的绝对证据路径。"
    Assert-True `
        -Condition ($smokePaths.EvidencePath -eq (Join-Path $smokeEvidenceDirectory "ai-qa-acceptance-fixed-evidence.json")) `
        -Message "生命周期脚本应把最终证据归档到调用者指定目录。"
    Assert-True `
        -Condition ((Test-Path -LiteralPath $smokeTemporaryDirectory -PathType Container) -and (Test-Path -LiteralPath $smokeEvidenceDirectory -PathType Container)) `
        -Message "证据路径构造应提前创建临时目录和归档目录。"

    $installedRoot = Join-Path $testRoot "installed-app"
    $installedVersion = Join-Path $installedRoot "app-0.1.0"
    [System.IO.Directory]::CreateDirectory($installedVersion) | Out-Null
    foreach ($relativePath in @(
        ".dead",
        "Update.exe",
        "app-0.1.0/squirrel.exe",
        "app-0.1.0/v8_context_snapshot.bin",
        "app-0.1.0/vk_swiftshader_icd.json",
        "app-0.1.0/vk_swiftshader.dll"
    )) {
        $path = Join-Path $installedRoot $relativePath
        [System.IO.File]::WriteAllText($path, "residue")
    }
    $installedApplication = [pscustomobject]@{
        InstallRoot = $installedRoot
        VersionDirectory = $installedVersion
        ExecutablePath = Join-Path $installedVersion "ai-qa-assistant.exe"
        UpdatePath = Join-Path $installedRoot "Update.exe"
    }
    $uninstallState = Get-SquirrelUninstallState -InstalledApplication $installedApplication
    Assert-True -Condition (-not $uninstallState.Removed) -Message "应识别仍存在的 Squirrel 墓碑目录。"
    Assert-True `
        -Condition ($uninstallState.ResiduePaths.Count -eq 6) `
        -Message "应记录六个允许的 Electron/Squirrel 墓碑文件。"
    [System.IO.File]::WriteAllText((Join-Path $installedVersion "user-content.txt"), "unexpected")
    Assert-Throws -Action {
        Get-SquirrelUninstallState -InstalledApplication $installedApplication | Out-Null
    } -ExpectedMessage "未识别残留"
    Remove-Item -LiteralPath (Join-Path $installedVersion "user-content.txt") -Force
    Remove-Item -LiteralPath $installedRoot -Recurse -Force
    $removedState = Get-SquirrelUninstallState -InstalledApplication $installedApplication
    Assert-True -Condition $removedState.Removed -Message "安装根目录消失后应识别为完全清理。"

    $evidenceDirectory = Join-Path $testRoot "evidence"
    $validation = Invoke-InstallerAcceptance -ArtifactRoot $testRoot -Mode Validate -EvidenceDirectory $evidenceDirectory
    Assert-True -Condition ($validation.Evidence.status -eq "passed") -Message "Validate 模式应成功。"
    Assert-True -Condition ($validation.Evidence.completed_at -ne $null) -Message "验收证据应包含完成时间。"
    Assert-True -Condition (@(Get-ChildItem -LiteralPath $evidenceDirectory -File).Count -eq 1) -Message "每次验收只能生成一份汇总证据。"
    Assert-Throws -Action {
        Invoke-InstallerAcceptance -ArtifactRoot $testRoot -Mode Validate -RequireSignedArtifacts -EvidenceDirectory $evidenceDirectory | Out-Null
    } -ExpectedMessage "发布元数据未声明 PFX 签名"

    [System.IO.File]::AppendAllText($release.SetupPath, "tampered")
    Assert-Throws -Action {
        Get-VerifiedReleaseArtifacts -ArtifactRoot $testRoot | Out-Null
    } -ExpectedMessage "SHA-256 不匹配"

    Remove-Item -LiteralPath $testRoot -Recurse -Force
    New-ReleaseFixture -Root $testRoot
    Add-Content -LiteralPath (Join-Path $testRoot "SHA256SUMS.txt") -Value ("0" * 64 + "  ../outside.exe")
    Assert-Throws -Action {
        Get-VerifiedReleaseArtifacts -ArtifactRoot $testRoot | Out-Null
    } -ExpectedMessage "越界路径"

    Remove-Item -LiteralPath (Join-Path $testRoot "squirrel.windows/x64/RELEASES") -Force
    Assert-Throws -Action {
        Get-VerifiedReleaseArtifacts -ArtifactRoot $testRoot | Out-Null
    } -ExpectedMessage "制品缺失"
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}

Write-Output "Windows 安装验收模块测试通过。"
