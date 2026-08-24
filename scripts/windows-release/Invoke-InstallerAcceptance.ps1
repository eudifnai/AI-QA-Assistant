#Requires -Version 7.4

[CmdletBinding()]
param(
    [Parameter()]
    [string]$ArtifactRoot = (Join-Path $PSScriptRoot "../../frontend/out/make"),
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

$ErrorActionPreference = "Stop"
Import-Module -Name (Join-Path $PSScriptRoot "InstallerAcceptance.psm1") -Force

$arguments = @{
    ArtifactRoot = $ArtifactRoot
    Mode = $Mode
    EvidenceDirectory = $EvidenceDirectory
    AllowSystemChanges = $AllowSystemChanges
    RequireSignedArtifacts = $RequireSignedArtifacts
    TimeoutSeconds = $TimeoutSeconds
}
if (-not [string]::IsNullOrWhiteSpace($PreviousArtifactRoot)) {
    $arguments.PreviousArtifactRoot = $PreviousArtifactRoot
}

$result = Invoke-InstallerAcceptance @arguments
$result | ConvertTo-Json -Depth 8
