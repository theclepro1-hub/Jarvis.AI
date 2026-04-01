param(
    [switch]$SkipInstaller,
    [switch]$CloseRunningReleaseApps = $true,
    [string]$RepoSlug = ""
)

$ErrorActionPreference = "Stop"
try {
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [Console]::InputEncoding = $utf8NoBom
    [Console]::OutputEncoding = $utf8NoBom
    $OutputEncoding = $utf8NoBom
    chcp 65001 > $null
}
catch {
}

function Step([string]$Message) {
    Write-Host "[build-2.0] $Message" -ForegroundColor Cyan
}

function Warn([string]$Message) {
    Write-Warning $Message
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

function Get-Sha256([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash
}

function Get-ProcessesForPath([string]$Path) {
    if (-not $Path) { return @() }
    $normalized = [System.IO.Path]::GetFullPath($Path)
    return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -ieq $normalized)
        }
        catch {
            $false
        }
    })
}

function Assert-PathUnlocked([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path)) { return }
    $holders = @(Get-ProcessesForPath $Path)
    if ($holders.Count -eq 0) { return }

    $details = ($holders | Sort-Object Id | ForEach-Object { "$($_.ProcessName)#$($_.Id)" }) -join ", "
    throw "$Label is currently open by: $details. Close the running app and re-run build_release.ps1."
}

function Stop-ProcessesForPath([string]$Path, [string]$Label) {
    $holders = @(Get-ProcessesForPath $Path)
    if ($holders.Count -eq 0) { return }
    $details = ($holders | Sort-Object Id | ForEach-Object { "$($_.ProcessName)#$($_.Id)" }) -join ", "
    Step "Close running $Label before rebuild: $details"
    foreach ($proc in $holders) {
        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        }
        catch {
            throw "Could not close $Label process $($proc.ProcessName)#$($proc.Id): $($_.Exception.Message)"
        }
    }
    Start-Sleep -Milliseconds 350
}

function Resolve-PythonCommand {
    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return @($candidate)
        }
    }

    $pyCmd = Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyCmd) {
        return @($pyCmd.Source, "-3")
    }

    $pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pythonCmd) {
        return @($pythonCmd.Source)
    }

    throw "Python interpreter was not found. Install Python 3.11+ or adjust build_release.ps1."
}

function Update-InnoSetupVersion {
    param([string]$IssPath, [string]$Version)
    if (-not (Test-Path $IssPath)) { return }
    $content = Get-Content $IssPath -Raw -Encoding UTF8
    $newContent = $content -replace '#define MyAppVersion "[^"]+"', "#define MyAppVersion `"$Version`""
    if ($content -ne $newContent) {
        Set-Content $IssPath $newContent -Encoding UTF8 -NoNewline
        Step "Updated installer script version to $Version"
    }
}

try {
    $root = Split-Path -Parent $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($root)) {
        $root = (Get-Location).Path
    }
    Set-Location $root

    $brandingPath = Join-Path $root "jarvis_ai\branding.py"
    $releaseMetaPath = Join-Path $root "jarvis_ai\release_meta.py"
    $jarvisPy = Join-Path $root "jarvis.py"
    $specPath = Join-Path $root "jarvis.spec"
    $issPath = Join-Path $root "JarvisAI.iss"
    $changelogPath = Join-Path $root "CHANGELOG.md"
    $notesScript = Join-Path $root "scripts\sync_release_notes.py"
    $versionCheckScript = Join-Path $root "scripts\check_version_consistency.py"
    $unitChecksScript = Join-Path $root "scripts\unit_checks.py"
    $crashTestScript = Join-Path $root "scripts\crash_test.py"
    $smokeCheckScript = Join-Path $root "scripts\release_smoke_check.py"
    $updatesJsonPath = Join-Path $root "updates.json"
    $releaseDir = Join-Path $root "release"
    $distDir = Join-Path $root "dist"
    $buildDir = Join-Path $root "build"
    $installerBuildDir = Join-Path $root "_installer_out"
    $readmePath = Join-Path $root "README.md"

    if (-not (Test-Path $brandingPath)) { throw "branding.py not found in jarvis_ai." }
    if (-not (Test-Path $jarvisPy)) { throw "jarvis.py not found in project root." }
    if (-not (Test-Path $specPath)) { throw "jarvis.spec not found in project root." }
    if (-not (Test-Path $issPath)) { throw "JarvisAI.iss not found in project root." }

    if ([string]::IsNullOrWhiteSpace($RepoSlug)) {
        $RepoSlug = Read-PyConstant -Path $releaseMetaPath -Name "DEFAULT_GITHUB_REPO" -Fallback "theclepro1-hub/Jarvis.AI"
    }

    $version = Read-PyConstant -Path $brandingPath -Name "APP_VERSION" -Fallback "0.0.0"
    $exeName = Read-PyConstant -Path $brandingPath -Name "APP_EXECUTABLE_NAME" -Fallback "jarvis_ai_2.exe"
    $installerName = Read-PyConstant -Path $brandingPath -Name "APP_INSTALLER_NAME" -Fallback "JarvisAI2_Setup.exe"

    $installerBaseName = [System.IO.Path]::GetFileNameWithoutExtension($installerName)
    $portableBaseName = "JARVIS_AI_2_portable_v$version"
    $distExe = Join-Path $root ("dist\" + $exeName)
    $setupExe = Join-Path $releaseDir $installerName
    $releaseNotesPath = Join-Path $releaseDir "RELEASE_NOTES.md"
    $manifestPath = Join-Path $releaseDir "manifest.json"
    $portableStageDir = Join-Path $releaseDir ("portable\" + $portableBaseName)
    $portableZipName = "$portableBaseName.zip"
    $portableZipPath = Join-Path $releaseDir $portableZipName
    $portableStageRoot = Join-Path $releaseDir "portable"

    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    New-Item -ItemType Directory -Path $installerBuildDir -Force | Out-Null
    foreach ($staleDir in @($distDir, $buildDir)) {
        if (Test-Path $staleDir) {
            Step "Remove stale build directory: $staleDir"
            Remove-Item $staleDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($staleFile in @(
        (Join-Path $releaseDir $exeName),
        (Join-Path $releaseDir $installerName),
        $portableZipPath
    )) {
        if (Test-Path $staleFile) {
            Step "Remove stale release artifact: $staleFile"
            Remove-Item $staleFile -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path $portableStageRoot) {
        Get-ChildItem -Path $portableStageRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne $portableBaseName } |
            ForEach-Object {
                Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
    }
    Get-ChildItem -Path $releaseDir -Filter "JARVIS_AI_2_portable_v*.zip" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne $portableZipName } |
        ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        }

    Step "Detected version: $version"
    Step "Executable: $exeName"
    Step "Installer: $installerName"

    if ($CloseRunningReleaseApps) {
        Stop-ProcessesForPath -Path (Join-Path $releaseDir $exeName) -Label $exeName
        Stop-ProcessesForPath -Path (Join-Path $releaseDir $installerName) -Label $installerName
    }
    Assert-PathUnlocked -Path (Join-Path $releaseDir $exeName) -Label $exeName
    Assert-PathUnlocked -Path (Join-Path $releaseDir $installerName) -Label $installerName

    $pythonCmd = @(Resolve-PythonCommand)
    $pythonExe = $pythonCmd[0]
    $pythonPrefixArgs = @()
    if ($pythonCmd.Count -gt 1) {
        $pythonPrefixArgs = $pythonCmd[1..($pythonCmd.Count - 1)]
    }
    Step ("Python: " + ($pythonCmd -join " "))

    Update-InnoSetupVersion -IssPath $issPath -Version $version
    $env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
    $env:PYTHONWARNINGS = "ignore::RuntimeWarning"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Step "Check version consistency"
    & $pythonExe -B @pythonPrefixArgs $versionCheckScript
    if ($LASTEXITCODE -ne 0) { throw "Version consistency check failed." }

    Step "Run ruff"
    & $pythonExe -B @pythonPrefixArgs -m ruff check $jarvisPy (Join-Path $root "jarvis_ai") (Join-Path $root "scripts") (Join-Path $root "tests")
    if ($LASTEXITCODE -ne 0) { throw "Ruff check failed." }

    Step "Run pytest"
    & $pythonExe -B @pythonPrefixArgs -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Pytest failed." }

    Step "Run compileall"
    & $pythonExe -B @pythonPrefixArgs -m compileall $jarvisPy (Join-Path $root "jarvis_ai") (Join-Path $root "scripts") (Join-Path $root "tests")
    if ($LASTEXITCODE -ne 0) { throw "Python compileall check failed." }

    Step "Run unit checks"
    & $pythonExe -B @pythonPrefixArgs $unitChecksScript
    if ($LASTEXITCODE -ne 0) { throw "Unit checks failed." }

    Step "Run crash test"
    & $pythonExe -B @pythonPrefixArgs $crashTestScript
    if ($LASTEXITCODE -ne 0) { throw "Crash test failed." }

    Step "Build EXE (PyInstaller)"
    & $pythonExe -B @pythonPrefixArgs -m PyInstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    if (-not (Test-Path $distExe)) {
        throw "Missing $distExe after build."
    }

    Copy-Item $distExe (Join-Path $releaseDir $exeName) -Force
    Step "Copied $exeName into release"

    $nowUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $downloadUrl = "https://github.com/$RepoSlug/releases/download/v$version/$installerName"
    $releasePage = "https://github.com/$RepoSlug/releases/tag/v$version"

    $existingUpdates = [ordered]@{}
    if (Test-Path $updatesJsonPath) {
        try {
            $parsed = Get-Content $updatesJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($parsed) {
                foreach ($prop in $parsed.PSObject.Properties) {
                    $existingUpdates[$prop.Name] = $prop.Value
                }
            }
        }
        catch {
            Warn "updates.json could not be parsed; rebuilding from scratch."
        }
    }

    $existingUpdates["version"] = $version
    $existingUpdates["download_url"] = $downloadUrl
    $existingUpdates["release_page"] = $releasePage
    $existingUpdates["installer_name"] = $installerName
    $existingUpdates["executable_name"] = $exeName
    $existingUpdates["build_utc"] = $nowUtc
    if (-not $existingUpdates.Contains("notes") -or [string]::IsNullOrWhiteSpace([string]$existingUpdates["notes"])) {
        $existingUpdates["notes"] = "Release ${version}: shell, voice, settings and release metadata were rebuilt for the current publish cycle."
    }

    $existingUpdates | ConvertTo-Json -Depth 12 | Set-Content $updatesJsonPath -Encoding UTF8
    Step "Updated updates.json"

    if (Test-Path $notesScript) {
        Step "Sync release notes"
        & $pythonExe -B @pythonPrefixArgs $notesScript --version $version --changelog $changelogPath --updates-json $updatesJsonPath --release-notes $releaseNotesPath
        if ($LASTEXITCODE -ne 0) {
            Warn "Release notes sync failed, but build continues."
        }
        elseif (Test-Path $updatesJsonPath) {
            try {
                $syncedUpdates = Get-Content $updatesJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($syncedUpdates -and $syncedUpdates.PSObject.Properties.Name -contains "notes") {
                    $existingUpdates["notes"] = [string]$syncedUpdates.notes
                }
            }
            catch {
                Warn "Could not reload synced release notes from updates.json."
            }
        }
    }

    $installerBuilt = $false
    if (-not $SkipInstaller) {
        $isccPath = $null
        foreach ($candidate in @("iscc.exe", "ISCC.exe")) {
            $cmd = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($cmd) {
                $isccPath = $cmd.Source
                break
            }
        }

        if (-not $isccPath) {
            foreach ($candidatePath in @(
                "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                "C:\Program Files\Inno Setup 6\ISCC.exe"
            )) {
                if (Test-Path $candidatePath) {
                    $isccPath = $candidatePath
                    break
                }
            }
        }

        if ($isccPath) {
            Step "Build installer (Inno Setup)"
            & $isccPath "/DMyAppVersion=$version" "/O$installerBuildDir" "/F$installerBaseName" $issPath
            if ($LASTEXITCODE -ne 0) {
                Warn "Installer build returned an error. Check JarvisAI.iss."
            }
            else {
                $foundInstaller = Get-ChildItem -Path $installerBuildDir -Filter "*.exe" -File -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -ieq $installerName -or $_.Name -like "*$installerBaseName*" } |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 1

                if ($foundInstaller) {
                    Copy-Item $foundInstaller.FullName $setupExe -Force
                    Step "Installer ready: $setupExe"
                    $installerBuilt = $true
                }
                else {
                    Warn "Installer compiled, but output file was not found in $installerBuildDir."
                }
            }
        }
        else {
            Warn "Inno Setup (ISCC) not found. Install it or use -SkipInstaller."
        }
    }

    Copy-Item $updatesJsonPath (Join-Path $releaseDir "updates.json") -Force
    if (Test-Path $changelogPath) {
        Copy-Item $changelogPath (Join-Path $releaseDir "CHANGELOG.md") -Force
    }

    if (Test-Path $portableStageDir) {
        Remove-Item $portableStageDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $portableZipPath) {
        Remove-Item $portableZipPath -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $portableStageDir -Force | Out-Null
    Copy-Item (Join-Path $releaseDir $exeName) (Join-Path $portableStageDir $exeName) -Force
    if (Test-Path (Join-Path $releaseDir "updates.json")) {
        Copy-Item (Join-Path $releaseDir "updates.json") (Join-Path $portableStageDir "updates.json") -Force
    }
    if (Test-Path (Join-Path $releaseDir "CHANGELOG.md")) {
        Copy-Item (Join-Path $releaseDir "CHANGELOG.md") (Join-Path $portableStageDir "CHANGELOG.md") -Force
    }
    if (Test-Path $releaseNotesPath) {
        Copy-Item $releaseNotesPath (Join-Path $portableStageDir "RELEASE_NOTES.md") -Force
    }
    if (Test-Path $readmePath) {
        Copy-Item $readmePath (Join-Path $portableStageDir "README.md") -Force
    }
    Compress-Archive -Path $portableStageDir -DestinationPath $portableZipPath -Force
    Step "Portable bundle ready: $portableZipPath"

    $manifestFiles = [ordered]@{}
    $manifestFiles[$exeName] = [ordered]@{
        path = $exeName
        sha256 = Get-Sha256 (Join-Path $releaseDir $exeName)
    }
    $manifestFiles[$installerName] = [ordered]@{
        path = $installerName
        sha256 = Get-Sha256 (Join-Path $releaseDir $installerName)
        built = $installerBuilt
    }
    $manifestFiles["updates.json"] = [ordered]@{
        path = "updates.json"
        sha256 = Get-Sha256 (Join-Path $releaseDir "updates.json")
    }
    $manifestFiles["CHANGELOG.md"] = [ordered]@{
        path = "CHANGELOG.md"
        sha256 = Get-Sha256 (Join-Path $releaseDir "CHANGELOG.md")
    }
    $manifestFiles["RELEASE_NOTES.md"] = [ordered]@{
        path = "RELEASE_NOTES.md"
        sha256 = Get-Sha256 (Join-Path $releaseDir "RELEASE_NOTES.md")
    }
    $manifestFiles[$portableZipName] = [ordered]@{
        path = $portableZipName
        sha256 = Get-Sha256 $portableZipPath
        built = $true
    }

    $manifest = [ordered]@{
        version = $version
        build_utc = $nowUtc
        files = $manifestFiles
    }
    $manifest | ConvertTo-Json -Depth 12 | Set-Content $manifestPath -Encoding UTF8

    $releaseFiles = @()
    Get-ChildItem -Path $releaseDir -File -ErrorAction SilentlyContinue |
        Sort-Object Name |
        ForEach-Object {
            $releaseFiles += [ordered]@{
                name = $_.Name
                path = $_.Name
                size = [int64]$_.Length
                url = "https://github.com/$RepoSlug/releases/download/v$version/$($_.Name)"
            }
        }
    if (-not ($releaseFiles | Where-Object { $_.name -eq $installerName })) {
        $releaseFiles += [ordered]@{
            name = $installerName
            path = $installerName
            size = 0
            url = "https://github.com/$RepoSlug/releases/download/v$version/$installerName"
        }
    }
    if (-not ($releaseFiles | Where-Object { $_.name -eq $portableZipName })) {
        $releaseFiles += [ordered]@{
            name = $portableZipName
            path = $portableZipName
            size = if (Test-Path $portableZipPath) { [int64](Get-Item $portableZipPath).Length } else { 0 }
            url = "https://github.com/$RepoSlug/releases/download/v$version/$portableZipName"
        }
    }

    $existingUpdates["manifest_url"] = "https://github.com/$RepoSlug/releases/download/v$version/manifest.json"
    $existingUpdates["files"] = $releaseFiles
    $existingUpdates | ConvertTo-Json -Depth 14 | Set-Content $updatesJsonPath -Encoding UTF8
    Copy-Item $updatesJsonPath (Join-Path $releaseDir "updates.json") -Force
    $manifest.files["updates.json"]["sha256"] = Get-Sha256 (Join-Path $releaseDir "updates.json")
    $manifest | ConvertTo-Json -Depth 12 | Set-Content $manifestPath -Encoding UTF8

    Step "Run release smoke check"
    & $pythonExe -B @pythonPrefixArgs $smokeCheckScript
    if ($LASTEXITCODE -ne 0) { throw "Release smoke check failed." }

    foreach ($tempDirName in @("build", "dist", "_installer_out")) {
        $tempDir = Join-Path $root $tempDirName
        if (Test-Path $tempDir) {
            Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    $staleRootExe = Join-Path $root $exeName
    if (Test-Path $staleRootExe) {
        Remove-Item $staleRootExe -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -Path $root -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "__pycache__" } |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    Get-ChildItem -Path $root -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
        ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        }
    Step "Temporary build folders cleaned"
    Step "Release artifacts prepared in .\release"
    Write-Host "Done." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "Build failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
