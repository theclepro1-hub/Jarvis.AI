param(
    [string]$RemoteUrl = "",
    [string]$Branch = "main",
    [string]$CommitMessage = "",
    [string]$RepoRoot = "",
    [switch]$CreateTag
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) {
    Write-Host "[git] $Message" -ForegroundColor Cyan
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

function Read-AppVersion([string]$Root) {
    $brandingPath = Join-Path $Root "jarvis_ai\branding.py"
    $version = Read-PyConstant -Path $brandingPath -Name "APP_VERSION" -Fallback ""
    if (-not [string]::IsNullOrWhiteSpace($version)) {
        return $version
    }
    return "0.0.0"
}

function Invoke-Git {
    param(
        [string[]]$GitArgs,
        [switch]$AllowFailure,
        [switch]$Silent
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $rawOutput = & $script:GitExecutable @GitArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    $output = @()
    foreach ($item in @($rawOutput)) {
        $text = if ($null -eq $item) { "" } else { [string]$item }
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            $output += ($text.TrimEnd() -split "`r?`n")
        }
    }

    if (-not $Silent -and $output) {
        $output | ForEach-Object { Write-Host $_ }
    }

    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $details = ($output | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = "(git returned no additional output)"
        }
        throw "git $($GitArgs -join ' ') failed with exit code $exitCode`nRepo: $((Get-Location).Path)`n$details"
    }
    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output = @($output)
    }
}

function Get-GitConfigValue([string]$Name) {
    $local = Invoke-Git -GitArgs @("config", "--get", $Name) -AllowFailure -Silent
    if ($local.ExitCode -eq 0) {
        $value = ($local.Output | Out-String).Trim()
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }

    $global = Invoke-Git -GitArgs @("config", "--global", "--get", $Name) -AllowFailure -Silent
    if ($global.ExitCode -eq 0) {
        $value = ($global.Output | Out-String).Trim()
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    return ""
}

function Ensure-GitIdentity() {
    $userName = Get-GitConfigValue "user.name"
    if ([string]::IsNullOrWhiteSpace($userName)) {
        $userName = $env:GITHUB_ACTOR
    }
    if ([string]::IsNullOrWhiteSpace($userName)) {
        $userName = $env:USERNAME
    }
    if ([string]::IsNullOrWhiteSpace($userName)) {
        $userName = "JarvisAI2 Release Bot"
    }

    $userEmail = Get-GitConfigValue "user.email"
    if ([string]::IsNullOrWhiteSpace($userEmail)) {
        $safeUser = [regex]::Replace(($userName -replace '\s+', '-').ToLowerInvariant(), '[^a-z0-9._-]', '')
        if ([string]::IsNullOrWhiteSpace($safeUser)) {
            $safeUser = "jarvisai2-release"
        }
        $userEmail = "$safeUser@users.noreply.github.com"
    }

    $localName = ((Invoke-Git -GitArgs @("config", "--get", "user.name") -AllowFailure -Silent).Output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($localName)) {
        Step "Set local git user.name to $userName"
        Invoke-Git -GitArgs @("config", "user.name", $userName) | Out-Null
    }

    $localEmail = ((Invoke-Git -GitArgs @("config", "--get", "user.email") -AllowFailure -Silent).Output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($localEmail)) {
        Step "Set local git user.email to $userEmail"
        Invoke-Git -GitArgs @("config", "user.email", $userEmail) | Out-Null
    }
}

function Ensure-GitBranch([string]$TargetBranch) {
    $hasCommit = (Invoke-Git -GitArgs @("rev-parse", "--verify", "HEAD") -AllowFailure -Silent).ExitCode -eq 0
    if ($hasCommit) {
        Step "Switch branch to $TargetBranch"
        Invoke-Git -GitArgs @("checkout", "-B", $TargetBranch) | Out-Null
        return
    }

    Step "Prepare first branch $TargetBranch"
    Invoke-Git -GitArgs @("symbolic-ref", "HEAD", "refs/heads/$TargetBranch") | Out-Null
}

function Test-RemoteBranchExists([string]$BranchName) {
    $probe = Invoke-Git -GitArgs @("ls-remote", "--heads", "origin", $BranchName) -AllowFailure -Silent
    if ($probe.ExitCode -ne 0) {
        return $false
    }
    return -not [string]::IsNullOrWhiteSpace((($probe.Output | Out-String).Trim()))
}

function Remove-RepoContents([string]$Path) {
    Get-ChildItem -LiteralPath $Path -Force | Where-Object { $_.Name -ne ".git" } | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }
}

function Copy-RepoContents([string]$Source, [string]$Destination) {
    Get-ChildItem -LiteralPath $Source -Force | Where-Object { $_.Name -ne ".git" } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Publish-IntoExistingRemoteBranch {
    param(
        [string]$SourceRoot,
        [string]$RemoteUrl,
        [string]$TargetBranch,
        [string]$Message,
        [string]$Version,
        [bool]$ShouldCreateTag
    )

    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("jarvisai2-publish-" + [guid]::NewGuid().ToString("N"))
    Step "Clone remote branch $TargetBranch into temp workspace"
    Invoke-Git -GitArgs @("clone", "--depth", "1", "--branch", $TargetBranch, $RemoteUrl, $tempDir) | Out-Null

    Push-Location $tempDir
    try {
        Ensure-GitIdentity
        Step "Sync bundle files into temp workspace"
        Remove-RepoContents $tempDir
        Copy-RepoContents $SourceRoot $tempDir

        Step "Stage synced files"
        Invoke-Git -GitArgs @("add", "-A") | Out-Null

        $status = ((Invoke-Git -GitArgs @("status", "--short") -AllowFailure -Silent).Output | Out-String).Trim()
        $hasChanges = -not [string]::IsNullOrWhiteSpace($status)
        if ($hasChanges) {
            Step "Commit synced changes"
            Invoke-Git -GitArgs @("commit", "-m", $Message) | Out-Null
            Step "Push branch $TargetBranch"
            Invoke-Git -GitArgs @("push", "origin", $TargetBranch) | Out-Null
        } else {
            Step "Remote branch already matches bundle"
        }

        if ($ShouldCreateTag) {
            $tagName = "v$Version"
            $existingTag = ((Invoke-Git -GitArgs @("tag", "-l", $tagName) -AllowFailure -Silent).Output | Out-String).Trim()
            if (-not $existingTag) {
                Step "Create tag $tagName"
                Invoke-Git -GitArgs @("tag", $tagName) | Out-Null
            } else {
                Step "Tag $tagName already exists locally"
            }

            $remoteTag = ((Invoke-Git -GitArgs @("ls-remote", "--tags", "origin", $tagName) -AllowFailure -Silent).Output | Out-String).Trim()
            if ([string]::IsNullOrWhiteSpace($remoteTag)) {
                Step "Push tag $tagName"
                Invoke-Git -GitArgs @("push", "origin", $tagName) | Out-Null
            } else {
                Step "Tag $tagName already exists on remote"
            }
        }
    } finally {
        Pop-Location
        try {
            Remove-Item -LiteralPath $tempDir -Recurse -Force
        } catch {
        }
    }
}

function Test-RemoteRepositoryExists([string]$Url) {
    if ([string]::IsNullOrWhiteSpace($Url)) {
        return
    }
    $probe = Invoke-Git -GitArgs @("ls-remote", "--heads", $Url) -AllowFailure -Silent
    if ($probe.ExitCode -eq 0) {
        return
    }

    $details = ($probe.Output | Out-String).Trim()
    if ($details -match "repository not found" -or $details -match "not found") {
        throw "GitHub репозиторий не найден: $Url`nПроверьте slug репозитория в jarvis_ai\\release_meta.py или передайте правильный RemoteUrl."
    }
    if ($details -match "authentication failed" -or $details -match "could not read from remote repository" -or $details -match "permission denied") {
        throw "Не удалось авторизоваться в GitHub для репозитория: $Url`nПроверьте GitHub логин, токен или SSH-ключ."
    }
}

$gitCmd = Get-Command git -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $gitCmd) {
    throw "git is not installed or not available in PATH."
}
$script:GitExecutable = $gitCmd.Source

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $root = Resolve-Path (Join-Path $scriptDir "..")
} else {
    $root = Resolve-Path $RepoRoot
}
Set-Location $root

$version = Read-AppVersion $root
if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
    $CommitMessage = "release: v$version"
}

if (-not (Test-Path (Join-Path $root ".git"))) {
    Step "Initialize isolated git repository"
    Invoke-Git -GitArgs @("init") | Out-Null
}

Ensure-GitIdentity
Ensure-GitBranch $Branch

$originUrl = ""
$originLookup = Invoke-Git -GitArgs @("remote", "get-url", "origin") -AllowFailure -Silent
if ($originLookup.ExitCode -eq 0) {
    $originUrl = ($originLookup.Output | Out-String).Trim()
}

if (-not [string]::IsNullOrWhiteSpace($RemoteUrl)) {
    Test-RemoteRepositoryExists $RemoteUrl
    if ($originUrl) {
        Step "Update origin remote"
        Invoke-Git -GitArgs @("remote", "set-url", "origin", $RemoteUrl) | Out-Null
    } else {
        Step "Add origin remote"
        Invoke-Git -GitArgs @("remote", "add", "origin", $RemoteUrl) | Out-Null
    }
}

Step "Stage files"
Invoke-Git -GitArgs @("add", "-A") | Out-Null

$status = ((Invoke-Git -GitArgs @("status", "--short") -AllowFailure -Silent).Output | Out-String).Trim()
$hasChanges = -not [string]::IsNullOrWhiteSpace($status)
if ($hasChanges) {
    Step "Commit changes"
    Invoke-Git -GitArgs @("commit", "-m", $CommitMessage) | Out-Null
} else {
    Step "Nothing to commit"
}

$originCheck = Invoke-Git -GitArgs @("remote", "get-url", "origin") -AllowFailure -Silent
if ($originCheck.ExitCode -ne 0) {
    Write-Warning "Origin remote is not configured. Commit is ready locally, but push was skipped."
    exit 0
}

$originUrl = ($originCheck.Output | Out-String).Trim()
Test-RemoteRepositoryExists $originUrl

if (Test-RemoteBranchExists $Branch) {
    Publish-IntoExistingRemoteBranch -SourceRoot $root -RemoteUrl $originUrl -TargetBranch $Branch -Message $CommitMessage -Version $version -ShouldCreateTag $CreateTag.IsPresent
    Step "Git publish flow completed"
    exit 0
}

Step "Push branch $Branch"
Invoke-Git -GitArgs @("push", "-u", "origin", $Branch) | Out-Null

if ($CreateTag) {
    $tagName = "v$version"
    $existingTag = ((Invoke-Git -GitArgs @("tag", "-l", $tagName) -AllowFailure -Silent).Output | Out-String).Trim()
    if (-not $existingTag) {
        Step "Create tag $tagName"
        Invoke-Git -GitArgs @("tag", $tagName) | Out-Null
    } else {
        Step "Tag $tagName already exists"
    }

    $remoteTag = ((Invoke-Git -GitArgs @("ls-remote", "--tags", "origin", $tagName) -AllowFailure -Silent).Output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($remoteTag)) {
        Step "Push tag $tagName"
        Invoke-Git -GitArgs @("push", "origin", $tagName) | Out-Null
    } else {
        Step "Tag $tagName already exists on remote"
    }
}

Step "Git publish flow completed"
