param()

$ErrorActionPreference = "Stop"

function Step([string]$Message) {
    Write-Host "[bundle-2.0] $Message" -ForegroundColor Cyan
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

function Copy-ProjectItem([string]$Source, [string]$DestinationRoot) {
    if (-not (Test-Path $Source)) {
        return
    }
    $name = Split-Path $Source -Leaf
    $target = Join-Path $DestinationRoot $name
    Copy-Item $Source $target -Recurse -Force
}

function Remove-BundleJunk([string]$BundlePath) {
    if (-not (Test-Path $BundlePath)) {
        return
    }

    Get-ChildItem -Path $BundlePath -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "__pycache__" } |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }

    Get-ChildItem -Path $BundlePath -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -eq ".pyc" -or
            $_.Extension -eq ".pyo" -or
            $_.Name -eq ".DS_Store"
        } |
        ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        }

    foreach ($dirName in @("build", "dist", "_installer_out")) {
        Get-ChildItem -Path $BundlePath -Recurse -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $dirName } |
            ForEach-Object {
                Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$brandingPath = Join-Path $root "jarvis_ai\branding.py"
$version = Read-PyConstant -Path $brandingPath -Name "APP_VERSION" -Fallback "0.0.0"
$bundlePrefix = Read-PyConstant -Path $brandingPath -Name "APP_RELEASE_BUNDLE_PREFIX" -Fallback "JARVIS_AI_2_v"
$bundleRoot = Join-Path $scriptDir "github_bundle"
$bundleDir = Join-Path $bundleRoot ($bundlePrefix + $version)
$currentBundleName = Split-Path $bundleDir -Leaf

if (-not (Test-Path $bundleRoot)) {
    New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null
}

Get-ChildItem $bundleRoot -Directory -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -ne $currentBundleName
} | ForEach-Object {
    Step "Remove legacy bundle $($_.FullName)"
    Remove-Item $_.FullName -Recurse -Force
}

Step "Prepare bundle folder $bundleDir"
if (Test-Path $bundleDir) {
    Remove-Item $bundleDir -Recurse -Force
}
New-Item -ItemType Directory -Path $bundleDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleDir "publish_tools") -Force | Out-Null

$topLevelItems = @(
    ".github",
    "assets",
    "jarvis_ai",
    "scripts",
    "tests",
    "release",
    ".gitignore",
    "README.md",
    "ARCHITECTURE.md",
    "jarvis.py",
    "jarvis.spec",
    "JarvisAI.iss",
    "build_release.ps1",
    "build_release.bat",
    "ONE_CLICK_PUBLISH.bat",
    "pyproject.toml",
    "pytest.ini",
    "requirements.txt",
    "TASKS.md",
    "updates.json",
    "CHANGELOG.md"
)

foreach ($item in $topLevelItems) {
    Copy-ProjectItem (Join-Path $root $item) $bundleDir
}

$publishItems = @(
    "README.md",
    "Build-And-Prepare.bat",
    "Publish-One-Click.bat",
    "Commit-And-Push.bat",
    "Commit-And-Release.bat",
    "build_and_prepare.ps1",
    "prepare_github_bundle.ps1",
    "commit_and_push.ps1",
    "publish_one_click.ps1"
)

foreach ($item in $publishItems) {
    Copy-ProjectItem (Join-Path $scriptDir $item) (Join-Path $bundleDir "publish_tools")
}

Remove-BundleJunk -BundlePath $bundleDir
Step "Bundle ready: $bundleDir"
