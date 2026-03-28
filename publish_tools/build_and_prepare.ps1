param(
    [switch]$CloseRunningReleaseApps = $true,
    [string]$RepoSlug = ""
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) {
    Write-Host "[publish-2.0] $Message" -ForegroundColor Cyan
}

function Read-PyConstant {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Fallback = ""
    )

    if (-not (Test-Path $Path)) {
        return $Fallback
    }
    $pattern = [regex]::Escape($Name) + '\s*=\s*"([^"]+)"'
    $match = Select-String -Path $Path -Pattern $pattern -Encoding UTF8 | Select-Object -First 1
    if ($match -and $match.Matches.Count -gt 0) {
        return $match.Matches[0].Groups[1].Value
    }
    return $Fallback
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$releaseMetaPath = Join-Path $root "jarvis_ai\release_meta.py"
if ([string]::IsNullOrWhiteSpace($RepoSlug)) {
    $RepoSlug = Read-PyConstant -Path $releaseMetaPath -Name "DEFAULT_GITHUB_REPO" -Fallback "theclepro1-hub/Jarvis.AI"
}
$buildScript = Join-Path $root "build_release.ps1"
$bundleScript = Join-Path $scriptDir "prepare_github_bundle.ps1"

if (-not (Test-Path $buildScript)) {
    throw "build_release.ps1 not found: $buildScript"
}

if (-not (Test-Path $bundleScript)) {
    throw "prepare_github_bundle.ps1 not found: $bundleScript"
}

Set-Location $root
Step "Build release artifacts"
if ($CloseRunningReleaseApps) {
    & $buildScript -RepoSlug $RepoSlug -CloseRunningReleaseApps
} else {
    & $buildScript -RepoSlug $RepoSlug
}
if ($LASTEXITCODE -ne 0) {
    throw "build_release.ps1 failed with exit code $LASTEXITCODE"
}

Step "Prepare clean GitHub bundle"
& $bundleScript
if ($LASTEXITCODE -ne 0) {
    throw "prepare_github_bundle.ps1 failed with exit code $LASTEXITCODE"
}

Step "All publish helpers completed"
