param(
    [switch]$UseSsh
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) {
    Write-Host "[one-click-2.0] $Message" -ForegroundColor Cyan
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
$brandingPath = Join-Path $root "jarvis_ai\branding.py"
$releaseMetaPath = Join-Path $root "jarvis_ai\release_meta.py"
$version = Read-PyConstant -Path $brandingPath -Name "APP_VERSION" -Fallback "0.0.0"
$bundlePrefix = Read-PyConstant -Path $brandingPath -Name "APP_RELEASE_BUNDLE_PREFIX" -Fallback "JARVIS_AI_2_v"
$repoSlug = Read-PyConstant -Path $releaseMetaPath -Name "DEFAULT_GITHUB_REPO" -Fallback "theclepro1-hub/Jarvis.AI"
$remoteHttps = "https://github.com/$repoSlug.git"
$remoteSsh = "git@github.com:$repoSlug.git"
$remoteUrl = if ($UseSsh) { $remoteSsh } else { $remoteHttps }

Set-Location $root

Step "Build release and prepare GitHub bundle"
& (Join-Path $scriptDir "build_and_prepare.ps1") -RepoSlug $repoSlug
if ($LASTEXITCODE -ne 0) {
    throw "build_and_prepare.ps1 failed with exit code $LASTEXITCODE"
}

$bundleDir = Join-Path $scriptDir ("github_bundle\" + $bundlePrefix + $version)
if (-not (Test-Path $bundleDir)) {
    throw "Prepared bundle was not found: $bundleDir"
}

Step "Commit, push, and publish tag"
& (Join-Path $scriptDir "commit_and_push.ps1") -RemoteUrl $remoteUrl -Branch "main" -CreateTag -RepoRoot $bundleDir
if ($LASTEXITCODE -ne 0) {
    throw "commit_and_push.ps1 failed with exit code $LASTEXITCODE"
}

Step "Open bundle folder"
$bundleRoot = Join-Path $scriptDir "github_bundle"
if (Test-Path $bundleRoot) {
    Start-Process explorer.exe $bundleRoot | Out-Null
}

Step "One-click publish done"
