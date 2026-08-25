#Requires -Version 7.4

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-VerifiedReleaseArtifacts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ArtifactRoot
    )

    $root = (Resolve-Path -LiteralPath $ArtifactRoot).Path.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $manifestPath = Join-Path $root "SHA256SUMS.txt"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "发布制品缺失：SHA256SUMS.txt。"
    }

    $rootPrefix = "$root$([System.IO.Path]::DirectorySeparatorChar)"
    $artifacts = [System.Collections.Generic.List[object]]::new()
    $seenPaths = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line -notmatch "^(?<hash>[0-9a-fA-F]{64})  (?<path>.+)$") {
            throw "SHA256SUMS.txt 格式无效。"
        }
        $relativePath = $Matches.path.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
        if ([System.IO.Path]::IsPathRooted($relativePath)) {
            throw "SHA256SUMS.txt 包含越界路径。"
        }
        $artifactPath = [System.IO.Path]::GetFullPath((Join-Path $root $relativePath))
        if (-not $artifactPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "SHA256SUMS.txt 包含越界路径。"
        }
        if (-not $seenPaths.Add($artifactPath)) {
            throw "SHA256SUMS.txt 包含重复制品。"
        }
        if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
            throw "发布制品缺失：$relativePath。"
        }
        $actualHash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $Matches.hash.ToLowerInvariant()) {
            throw "发布制品 SHA-256 不匹配：$relativePath。"
        }
        $artifacts.Add([pscustomobject]@{
            RelativePath = $Matches.path.Replace("\", "/")
            Path = $artifactPath
            SHA256 = $actualHash
            Bytes = (Get-Item -LiteralPath $artifactPath).Length
        })
    }

    $setupArtifacts = @($artifacts | Where-Object { $_.RelativePath -match "(?i)Setup\.exe$" })
    $packageArtifacts = @($artifacts | Where-Object { $_.RelativePath -match "(?i)-full\.nupkg$" })
    $releaseArtifacts = @($artifacts | Where-Object { [System.IO.Path]::GetFileName($_.RelativePath) -eq "RELEASES" })
    $sbomArtifacts = @($artifacts | Where-Object { $_.RelativePath -eq "ai-qa-assistant.cdx.json" })
    $metadataArtifacts = @($artifacts | Where-Object { $_.RelativePath -eq "RELEASE-METADATA.json" })
    if (
        $artifacts.Count -ne 5 -or
        $setupArtifacts.Count -ne 1 -or
        $packageArtifacts.Count -ne 1 -or
        $releaseArtifacts.Count -ne 1 -or
        $sbomArtifacts.Count -ne 1 -or
        $metadataArtifacts.Count -ne 1
    ) {
        throw "Squirrel 发布制品或发布记录缺失，或集合不唯一。"
    }
    $packageName = [System.IO.Path]::GetFileName($packageArtifacts[0].Path)
    if ($packageName -notmatch "^AIQAAssistant-(?<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)-full\.nupkg$") {
        throw "无法从 Squirrel 更新包解析应用版本。"
    }
    $version = $Matches.version
    $sbom = Get-Content -LiteralPath $sbomArtifacts[0].Path -Raw | ConvertFrom-Json
    if (
        $sbom.bomFormat -ne "CycloneDX" -or
        $sbom.specVersion -ne "1.6" -or
        @($sbom.components).Count -lt 1
    ) {
        throw "发布 SBOM 必须是 CycloneDX 1.6 JSON。"
    }
    $metadata = Get-Content -LiteralPath $metadataArtifacts[0].Path -Raw | ConvertFrom-Json
    if (
        $metadata.schema_version -ne 1 -or
        $metadata.app.version -ne $version -or
        $metadata.target.platform -ne "win32" -or
        $metadata.target.format -ne "squirrel.windows"
    ) {
        throw "发布元数据与 Squirrel 制品不一致。"
    }
    if ($metadata.signing.mode -notin @("pfx", "unsigned_internal_candidate")) {
        throw "发布元数据包含未知签名模式。"
    }
    if (
        $metadata.sbom.format -ne "CycloneDX" -or
        $metadata.sbom.spec_version -ne "1.6" -or
        $metadata.sbom.path -ne "ai-qa-assistant.cdx.json" -or
        $metadata.sbom.sha256 -ne $sbomArtifacts[0].SHA256
    ) {
        throw "发布元数据中的 SBOM 记录无效。"
    }
    $recordedArtifacts = @($metadata.artifacts)
    $expectedRecordedArtifacts = @(
        $artifacts | Where-Object { $_.RelativePath -ne "RELEASE-METADATA.json" }
    )
    if ($recordedArtifacts.Count -ne $expectedRecordedArtifacts.Count) {
        throw "发布元数据中的制品集合不完整。"
    }
    foreach ($artifact in $expectedRecordedArtifacts) {
        $records = @($recordedArtifacts | Where-Object { $_.path -eq $artifact.RelativePath })
        if (
            $records.Count -ne 1 -or
            $records[0].sha256 -ne $artifact.SHA256 -or
            [long]$records[0].bytes -ne [long]$artifact.Bytes
        ) {
            throw "发布元数据中的制品摘要无效：$($artifact.RelativePath)。"
        }
    }

    [pscustomobject]@{
        ArtifactRoot = $root
        ManifestPath = $manifestPath
        SetupPath = $setupArtifacts[0].Path
        PackagePath = $packageArtifacts[0].Path
        ReleasesPath = $releaseArtifacts[0].Path
        SbomPath = $sbomArtifacts[0].Path
        MetadataPath = $metadataArtifacts[0].Path
        Version = $version
        SigningMode = $metadata.signing.mode
        Artifacts = @($artifacts)
    }
}

function Assert-ReleaseAuthenticode {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Release
    )

    if ($Release.SigningMode -ne "pfx") {
        throw "发布元数据未声明 PFX 签名，不能执行正式签名门禁。"
    }
    $temporaryRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) "ai-qa-signature-$([guid]::NewGuid().ToString('N'))"
    [System.IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($Release.PackagePath, $temporaryRoot)
        $targets = [System.Collections.Generic.List[object]]::new()
        $targets.Add([pscustomobject]@{
            Path = $Release.SetupPath
            RelativePath = "squirrel.windows/x64/$([System.IO.Path]::GetFileName($Release.SetupPath))"
        })
        foreach ($file in Get-ChildItem -LiteralPath $temporaryRoot -Recurse -File) {
            if ($file.Extension -in @(".exe", ".dll", ".node")) {
                $targets.Add([pscustomobject]@{
                    Path = $file.FullName
                    RelativePath = "full.nupkg/$($file.FullName.Substring($temporaryRoot.Length + 1).Replace('\', '/'))"
                })
            }
        }
        if ($targets.Count -lt 2) {
            throw "签名候选中未找到应用或更新包 PE 文件。"
        }

        $thumbprints = [System.Collections.Generic.HashSet[string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )
        foreach ($target in $targets) {
            $signature = Get-AuthenticodeSignature -LiteralPath $target.Path
            if (
                $signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
                $null -eq $signature.SignerCertificate
            ) {
                throw "Authenticode 签名无效：$($target.RelativePath)。"
            }
            if ($null -eq $signature.TimeStamperCertificate) {
                throw "Authenticode 签名缺少可信时间戳：$($target.RelativePath)。"
            }
            $thumbprints.Add($signature.SignerCertificate.Thumbprint) | Out-Null
        }
        return [pscustomobject]@{
            signed_file_count = $targets.Count
            signer_thumbprints = @($thumbprints | Sort-Object)
            timestamp_required = $true
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryRoot) {
            Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
        }
    }
}

function Invoke-CheckedProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,
        [Parameter()]
        [string[]]$Arguments = @(),
        [Parameter()]
        [hashtable]$Environment = @{},
        [Parameter()]
        [ValidateRange(1, 1800)]
        [int]$TimeoutSeconds = 180,
        [Parameter()]
        [switch]$AllowNonZeroExit
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $Arguments) {
        $startInfo.ArgumentList.Add($argument)
    }
    foreach ($entry in $Environment.GetEnumerator()) {
        $startInfo.Environment[$entry.Key] = [string]$entry.Value
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "无法启动外部进程。"
        }
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "外部进程执行超时：$([System.IO.Path]::GetFileName($FilePath))。"
        }
        if (-not $AllowNonZeroExit -and $process.ExitCode -ne 0) {
            throw "外部进程失败：$([System.IO.Path]::GetFileName($FilePath))，退出码 $($process.ExitCode)。"
        }
        return $process.ExitCode
    }
    finally {
        $process.Dispose()
    }
}

function Wait-ForCondition {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Condition,
        [Parameter(Mandatory)]
        [string]$TimeoutMessage,
        [Parameter()]
        [ValidateRange(1, 600)]
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $result = & $Condition
        if ($null -ne $result -and $result -ne $false) {
            return $result
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw $TimeoutMessage
}

function Get-InstalledApplication {
    param(
        [Parameter(Mandatory)]
        [string]$LocalAppDataPath,
        [Parameter(Mandatory)]
        [string]$ExpectedVersion,
        [Parameter()]
        [ValidateRange(1, 600)]
        [int]$TimeoutSeconds = 90
    )

    $installRoot = Join-Path $LocalAppDataPath "AIQAAssistant"
    Wait-ForCondition -TimeoutSeconds $TimeoutSeconds -TimeoutMessage "等待 Squirrel 安装目录超时。" -Condition {
        $versionDirectory = Join-Path $installRoot "app-$ExpectedVersion"
        $executablePath = Join-Path $versionDirectory "ai-qa-assistant.exe"
        $updatePath = Join-Path $installRoot "Update.exe"
        if (
            (Test-Path -LiteralPath $executablePath -PathType Leaf) -and
            (Test-Path -LiteralPath $updatePath -PathType Leaf)
        ) {
            return [pscustomobject]@{
                InstallRoot = $installRoot
                VersionDirectory = $versionDirectory
                ExecutablePath = $executablePath
                UpdatePath = $updatePath
            }
        }
        return $null
    }
}

function New-InstalledApplicationSmokePaths {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$EvidenceDirectory,
        [Parameter()]
        [string]$TemporaryDirectory = [System.IO.Path]::GetTempPath(),
        [Parameter()]
        [ValidatePattern("^[a-zA-Z0-9-]+$")]
        [string]$Identifier = [guid]::NewGuid().ToString("N")
    )

    $temporaryRoot = [System.IO.Path]::GetFullPath($TemporaryDirectory)
    $evidenceRoot = [System.IO.Path]::GetFullPath($EvidenceDirectory)
    [System.IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
    [System.IO.Directory]::CreateDirectory($evidenceRoot) | Out-Null
    $fileName = "ai-qa-acceptance-$Identifier.json"
    [pscustomobject]@{
        TemporaryRoot = $temporaryRoot
        TemporaryPath = Join-Path $temporaryRoot $fileName
        EvidencePath = Join-Path $evidenceRoot $fileName
    }
}

function Get-SquirrelUninstallState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$InstalledApplication
    )

    if (-not (Test-Path -LiteralPath $InstalledApplication.InstallRoot -PathType Container)) {
        return [pscustomobject]@{
            Removed = $true
            ResiduePaths = @()
        }
    }
    if (Test-Path -LiteralPath $InstalledApplication.ExecutablePath -PathType Leaf) {
        return $null
    }
    $deadMarkerPath = Join-Path $InstalledApplication.InstallRoot ".dead"
    if (-not (Test-Path -LiteralPath $deadMarkerPath -PathType Leaf)) {
        return $null
    }

    $root = [System.IO.Path]::GetFullPath($InstalledApplication.InstallRoot).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $versionDirectoryName = [System.IO.Path]::GetFileName($InstalledApplication.VersionDirectory)
    $allowedFiles = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($relativePath in @(
        ".dead",
        "Update.exe",
        "$versionDirectoryName/squirrel.exe",
        "$versionDirectoryName/v8_context_snapshot.bin"
    )) {
        $allowedFiles.Add($relativePath) | Out-Null
    }
    $residuePaths = @(
        Get-ChildItem -LiteralPath $root -Recurse -Force -File | ForEach-Object {
            $_.FullName.Substring($root.Length + 1).Replace("\", "/")
        }
    )
    $unexpectedFiles = @($residuePaths | Where-Object { -not $allowedFiles.Contains($_) })
    $unexpectedDirectories = @(
        Get-ChildItem -LiteralPath $root -Recurse -Force -Directory | ForEach-Object {
            $_.FullName.Substring($root.Length + 1).Replace("\", "/")
        } | Where-Object { $_ -ne $versionDirectoryName }
    )
    if ($unexpectedFiles.Count -ne 0 -or $unexpectedDirectories.Count -ne 0) {
        $unexpected = @($unexpectedFiles + $unexpectedDirectories)
        throw "卸载后安装目录包含未识别残留：$($unexpected -join ', ')。"
    }
    [pscustomobject]@{
        Removed = $false
        ResiduePaths = @($residuePaths)
    }
}

function Complete-SquirrelUninstall {
    param(
        [Parameter(Mandatory)]
        [object]$InstalledApplication,
        [Parameter(Mandatory)]
        [int]$TimeoutSeconds
    )

    $state = Wait-ForCondition -TimeoutSeconds $TimeoutSeconds -TimeoutMessage "等待 Squirrel 卸载完成超时。" -Condition {
        Get-SquirrelUninstallState -InstalledApplication $InstalledApplication
    }
    if (-not $state.Removed) {
        $expectedRoot = [System.IO.Path]::GetFullPath($InstalledApplication.InstallRoot)
        $resolvedRoot = (Resolve-Path -LiteralPath $InstalledApplication.InstallRoot).Path
        if (-not $resolvedRoot.Equals($expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Squirrel 残留清理目标路径不匹配。"
        }
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
        if (Test-Path -LiteralPath $resolvedRoot) {
            throw "Squirrel 墓碑残留清理失败。"
        }
    }
    return $state
}

function Invoke-InstalledApplicationSmoke {
    param(
        [Parameter(Mandatory)]
        [object]$InstalledApplication,
        [Parameter(Mandatory)]
        [string]$ExpectedVersion,
        [Parameter(Mandatory)]
        [string]$EvidenceDirectory,
        [Parameter()]
        [ValidateRange(1, 600)]
        [int]$TimeoutSeconds = 90
    )

    $smokePaths = New-InstalledApplicationSmokePaths -EvidenceDirectory $EvidenceDirectory
    try {
        try {
            $exitCode = Invoke-CheckedProcess -FilePath $InstalledApplication.ExecutablePath -Environment @{
                AI_QA_ACCEPTANCE_SMOKE_PATH = $smokePaths.TemporaryPath
                TEMP = $smokePaths.TemporaryRoot
                TMP = $smokePaths.TemporaryRoot
            } -TimeoutSeconds $TimeoutSeconds -AllowNonZeroExit
        }
        catch {
            $processMessage = $_.Exception.Message
            if (Test-Path -LiteralPath $smokePaths.TemporaryPath -PathType Leaf) {
                try {
                    $partialSmoke = Get-Content -LiteralPath $smokePaths.TemporaryPath -Raw | ConvertFrom-Json
                    if ($partialSmoke.status -eq "error") {
                        Assert-InstalledApplicationSmokeProcessResult -Smoke $partialSmoke -ExitCode 1 -ExpectedVersion $ExpectedVersion
                    }
                    $lastStatus = if ([string]::IsNullOrWhiteSpace([string]$partialSmoke.status)) {
                        "unknown"
                    }
                    else {
                        [string]$partialSmoke.status
                    }
                    throw "安装后应用未完成就绪，最后状态：$lastStatus。$processMessage"
                }
                catch {
                    if ($_.Exception.Message -like "安装后应用*") {
                        throw
                    }
                }
            }
            throw
        }
        if (-not (Test-Path -LiteralPath $smokePaths.TemporaryPath -PathType Leaf)) {
            throw "安装后应用未生成就绪证据。"
        }
        $smoke = Get-Content -LiteralPath $smokePaths.TemporaryPath -Raw | ConvertFrom-Json
        Assert-InstalledApplicationSmokeProcessResult -Smoke $smoke -ExitCode $exitCode -ExpectedVersion $ExpectedVersion
        return $smoke
    }
    finally {
        if (
            (Test-Path -LiteralPath $smokePaths.TemporaryPath -PathType Leaf) -and
            $smokePaths.TemporaryPath -ne $smokePaths.EvidencePath
        ) {
            Move-Item -LiteralPath $smokePaths.TemporaryPath -Destination $smokePaths.EvidencePath -Force
        }
    }
}

function Assert-InstalledApplicationSmokeProcessResult {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Smoke,
        [Parameter(Mandatory)]
        [int]$ExitCode,
        [Parameter(Mandatory)]
        [string]$ExpectedVersion
    )

    if ($Smoke.status -eq "error") {
        $message = [string]$Smoke.message
        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = "未知启动错误。"
        }
        throw "安装后应用启动失败：$message"
    }
    if ($ExitCode -ne 0) {
        throw "安装后应用异常退出，退出码 $ExitCode。"
    }
    Assert-InstalledApplicationSmokeEvidence -Smoke $Smoke -ExpectedVersion $ExpectedVersion
}

function Assert-InstalledApplicationSmokeEvidence {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$Smoke,
        [Parameter(Mandatory)]
        [string]$ExpectedVersion
    )

    if (
        $Smoke.status -ne "ready" -or
        $Smoke.app_version -ne $ExpectedVersion -or
        $Smoke.api_host -ne "127.0.0.1" -or
        -not (Test-Path -LiteralPath $Smoke.database_path -PathType Leaf) -or
        [long]$Smoke.database_bytes -le 0
    ) {
        throw "安装后应用就绪证据校验失败。"
    }
}

function Write-AcceptanceEvidence {
    param(
        [Parameter(Mandatory)]
        [object]$Evidence,
        [Parameter(Mandatory)]
        [string]$EvidenceDirectory
    )

    [System.IO.Directory]::CreateDirectory($EvidenceDirectory) | Out-Null
    $evidencePath = Join-Path $EvidenceDirectory "installer-acceptance-$([guid]::NewGuid().ToString('N')).json"
    [System.IO.File]::WriteAllText(
        $evidencePath,
        (($Evidence | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false)
    )
    return $evidencePath
}

function Invoke-InstallerAcceptance {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ArtifactRoot,
        [Parameter()]
        [ValidateSet("Validate", "Lifecycle")]
        [string]$Mode = "Validate",
        [Parameter()]
        [string]$PreviousArtifactRoot,
        [Parameter()]
        [string]$EvidenceDirectory = (Join-Path ([System.IO.Path]::GetTempPath()) "ai-qa-installer-acceptance"),
        [Parameter()]
        [switch]$AllowSystemChanges,
        [Parameter()]
        [switch]$RequireSignedArtifacts,
        [Parameter()]
        [ValidateRange(30, 600)]
        [int]$TimeoutSeconds = 180
    )

    if ($Mode -eq "Lifecycle" -and -not $AllowSystemChanges) {
        throw "Lifecycle 模式会安装和卸载应用，必须显式传入 -AllowSystemChanges。"
    }
    $currentRelease = Get-VerifiedReleaseArtifacts -ArtifactRoot $ArtifactRoot
    $previousRelease = if ([string]::IsNullOrWhiteSpace($PreviousArtifactRoot)) {
        $null
    }
    else {
        Get-VerifiedReleaseArtifacts -ArtifactRoot $PreviousArtifactRoot
    }
    if ($null -ne $previousRelease -and $previousRelease.Version -eq $currentRelease.Version) {
        throw "升级验收要求上一候选与当前候选版本不同。"
    }
    [System.IO.Directory]::CreateDirectory($EvidenceDirectory) | Out-Null

    $stages = [System.Collections.Generic.List[object]]::new()
    $evidence = [ordered]@{
        schema_version = 1
        mode = $Mode
        status = "running"
        started_at = [DateTimeOffset]::UtcNow.ToString("O")
        completed_at = $null
        current_version = $currentRelease.Version
        previous_version = if ($null -eq $previousRelease) { $null } else { $previousRelease.Version }
        artifacts = @($currentRelease.Artifacts)
        authenticode = $null
        stages = $stages
        user_data_retained_after_uninstall = $null
    }
    $installed = $null

    try {
        $stages.Add([pscustomobject]@{ name = "artifact_validation"; status = "passed" })
        if ($RequireSignedArtifacts -or $currentRelease.SigningMode -eq "pfx") {
            $authenticode = Assert-ReleaseAuthenticode -Release $currentRelease
            $evidence.authenticode = $authenticode
            $stages.Add([pscustomobject]@{
                name = "authenticode_validation"
                status = "passed"
                signed_file_count = $authenticode.signed_file_count
            })
        }
        else {
            $stages.Add([pscustomobject]@{
                name = "authenticode_validation"
                status = "skipped"
                reason = "未签名内部候选。"
            })
        }
        if ($Mode -eq "Validate") {
            $evidence.status = "passed"
        }
        else {
        $localAppDataPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
        $releaseToInstall = if ($null -eq $previousRelease) { $currentRelease } else { $previousRelease }
        Invoke-CheckedProcess -FilePath $releaseToInstall.SetupPath -Arguments @("--silent") -TimeoutSeconds $TimeoutSeconds | Out-Null
        $installed = Get-InstalledApplication -LocalAppDataPath $localAppDataPath -ExpectedVersion $releaseToInstall.Version -TimeoutSeconds $TimeoutSeconds
        $stages.Add([pscustomobject]@{ name = "install"; version = $releaseToInstall.Version; status = "passed" })

        $smoke = Invoke-InstalledApplicationSmoke -InstalledApplication $installed -ExpectedVersion $releaseToInstall.Version -EvidenceDirectory $EvidenceDirectory -TimeoutSeconds $TimeoutSeconds
        $stages.Add([pscustomobject]@{ name = "first_launch"; version = $releaseToInstall.Version; status = "passed"; database_path = $smoke.database_path })

        if ($null -ne $previousRelease) {
            Invoke-CheckedProcess -FilePath $currentRelease.SetupPath -Arguments @("--silent") -TimeoutSeconds $TimeoutSeconds | Out-Null
            $installed = Get-InstalledApplication -LocalAppDataPath $localAppDataPath -ExpectedVersion $currentRelease.Version -TimeoutSeconds $TimeoutSeconds
            $upgradedSmoke = Invoke-InstalledApplicationSmoke -InstalledApplication $installed -ExpectedVersion $currentRelease.Version -EvidenceDirectory $EvidenceDirectory -TimeoutSeconds $TimeoutSeconds
            if ($upgradedSmoke.database_path -ne $smoke.database_path) {
                throw "升级后用户数据库路径发生变化。"
            }
            $smoke = $upgradedSmoke
            $stages.Add([pscustomobject]@{ name = "upgrade"; from = $previousRelease.Version; to = $currentRelease.Version; status = "passed"; database_path = $smoke.database_path })
        }
        else {
            $stages.Add([pscustomobject]@{ name = "upgrade"; status = "skipped"; reason = "未提供上一候选制品目录。" })
        }

        Invoke-CheckedProcess -FilePath $installed.UpdatePath -Arguments @("--uninstall", "-s") -TimeoutSeconds $TimeoutSeconds | Out-Null
        $uninstallState = Complete-SquirrelUninstall -InstalledApplication $installed -TimeoutSeconds $TimeoutSeconds
        $userDataRetained = Test-Path -LiteralPath $smoke.database_path -PathType Leaf
        if (-not $userDataRetained) {
            throw "卸载后用户数据库未按当前保留策略留存。"
        }
        $evidence.user_data_retained_after_uninstall = $true
        $stages.Add([pscustomobject]@{
            name = "uninstall"
            status = "passed"
            user_data_retained = $true
            squirrel_residue_file_count = @($uninstallState.ResiduePaths).Count
            squirrel_residue_cleaned = (-not $uninstallState.Removed)
        })
        $evidence.status = "passed"
        }
    }
    catch {
        $evidence.status = "failed"
        $stages.Add([pscustomobject]@{ name = "failure"; status = "failed"; message = $_.Exception.Message })
        throw
    }
    finally {
        if (
            $Mode -eq "Lifecycle" -and
            $null -ne $installed -and
            (Test-Path -LiteralPath $installed.InstallRoot) -and
            (Test-Path -LiteralPath $installed.UpdatePath -PathType Leaf)
        ) {
            try {
                Invoke-CheckedProcess -FilePath $installed.UpdatePath -Arguments @("--uninstall", "-s") -TimeoutSeconds $TimeoutSeconds | Out-Null
                $cleanupState = Complete-SquirrelUninstall -InstalledApplication $installed -TimeoutSeconds $TimeoutSeconds
                $stages.Add([pscustomobject]@{
                    name = "failure_cleanup"
                    status = "passed"
                    user_data_removed = $false
                    squirrel_residue_file_count = @($cleanupState.ResiduePaths).Count
                    squirrel_residue_cleaned = (-not $cleanupState.Removed)
                })
            }
            catch {
                $stages.Add([pscustomobject]@{ name = "failure_cleanup"; status = "failed"; message = $_.Exception.Message })
            }
        }
        $evidence.completed_at = [DateTimeOffset]::UtcNow.ToString("O")
        $evidencePath = Write-AcceptanceEvidence -Evidence $evidence -EvidenceDirectory $EvidenceDirectory
        Write-Information "安装验收证据：$evidencePath" -InformationAction Continue
    }

    [pscustomobject]@{
        Evidence = $evidence
        EvidencePath = $evidencePath
    }
}

Export-ModuleMember -Function Get-VerifiedReleaseArtifacts, Invoke-InstallerAcceptance, Assert-InstalledApplicationSmokeProcessResult, Assert-InstalledApplicationSmokeEvidence, New-InstalledApplicationSmokePaths, Get-SquirrelUninstallState
