#Requires -Version 7.4

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$FilePath
)

$ErrorActionPreference = "Stop"
$requiredVariables = @(
    "AI_QA_ARTIFACT_SIGNING_ENDPOINT",
    "AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME",
    "AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME"
)
foreach ($name in $requiredVariables) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Artifact Signing 配置不完整：缺少 $name。"
    }
}

$resolvedFile = (Resolve-Path -LiteralPath $FilePath -ErrorAction Stop).Path
$extension = [System.IO.Path]::GetExtension($resolvedFile).ToLowerInvariant()
if ($extension -notin @(".exe", ".dll", ".node")) {
    throw "Artifact Signing 不支持该文件类型：$resolvedFile"
}

Import-Module ArtifactSigning -MinimumVersion "0.1.8" -ErrorAction Stop
$params = @{
    Endpoint = $env:AI_QA_ARTIFACT_SIGNING_ENDPOINT
    CodeSigningAccountName = $env:AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME
    CertificateProfileName = $env:AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME
    Files = $resolvedFile
    FileDigest = "SHA256"
    TimestampRfc3161 = "http://timestamp.acs.microsoft.com"
    TimestampDigest = "SHA256"
    ExcludeEnvironmentCredential = $true
    ExcludeWorkloadIdentityCredential = $true
    ExcludeManagedIdentityCredential = $true
    ExcludeSharedTokenCacheCredential = $true
    ExcludeVisualStudioCredential = $true
    ExcludeVisualStudioCodeCredential = $true
    ExcludeAzurePowerShellCredential = $true
    ExcludeAzureDeveloperCliCredential = $true
    ExcludeInteractiveBrowserCredential = $true
    Timeout = 600
}
Invoke-ArtifactSigning @params
