$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $root ".venv\\Scripts\\python.exe"
$pyiMakeSpec = Join-Path $root ".venv\\Scripts\\pyi-makespec.exe"
$distDir = Join-Path $root "dist"
$oneFileDistDir = Join-Path $root "dist_onefile"
$buildDir = Join-Path $root "build\\pyinstaller"
$oneFileBuildDir = Join-Path $root "build\\pyinstaller_onefile"
$releaseDir = Join-Path $root "build\\release"
$installerDir = Join-Path $root "build\\installer"
$versionInfoFile = Join-Path $root "build\\pyinstaller\\version_info.txt"
$iconPath = Join-Path $root "assets\\icons\\jarvis_unity.ico"
$sttModelRef = "small"
$modelCacheDir = Join-Path $root "build\\model_cache\\faster-whisper"
$buildStamp = Get-Date -Format "yyyyMMdd_HHmmss"

function Remove-Or-Fallback {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$FallbackPath
    )

    if (!(Test-Path $Path)) {
        return $Path
    }

    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $Path
    } catch {
        Write-Host "PATH_LOCK_FALLBACK $Path -> $FallbackPath"
        return $FallbackPath
    }
}

function Resolve-LocalSTTModelPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ModelRef,
        [Parameter(Mandatory = $true)]
        [string]$CacheDir
    )

    $pythonScript = @"
from pathlib import Path

from core.voice.faster_whisper_runtime import (
    load_faster_whisper_model,
    preseed_faster_whisper_model,
    resolve_local_faster_whisper_model,
)

cache_dir = Path(r'''$CacheDir''')
cache_dir.mkdir(parents=True, exist_ok=True)
resolved = preseed_faster_whisper_model("$ModelRef", cache_dir)
if resolved is None:
    load_faster_whisper_model("$ModelRef", cache_dir, device="cpu", compute_type="int8")
resolved = resolve_local_faster_whisper_model("$ModelRef", cache_dir)
print(resolved or "")
"@

    $nativeErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $resolvedPath = ($pythonScript | & $venvPython - 2>$null)
    $pythonExit = $LASTEXITCODE
    $ErrorActionPreference = $nativeErrorActionPreference
    if ($pythonExit -ne 0) {
        return ""
    }
    $resolvedPath = "$resolvedPath".Trim()
    return $resolvedPath
}

function Write-ChecksumFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArtifactPath
    )

    if (!(Test-Path $ArtifactPath)) {
        return $null
    }

    $artifact = Get-Item -LiteralPath $ArtifactPath
    $hash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumPath = "$ArtifactPath.sha256.txt"
    $checksumContent = "SHA256 $hash $($artifact.Name)"
    Set-Content -LiteralPath $checksumPath -Value $checksumContent -Encoding UTF8
    return $checksumPath
}

function Assert-ChecksumFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArtifactPath
    )

    $checksumPath = "$ArtifactPath.sha256.txt"
    if (!(Test-Path $checksumPath)) {
        throw "Checksum sidecar missing: $checksumPath"
    }
    return $checksumPath
}

function Assert-NativeSuccess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Step
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Assert-TextContains {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [string]$Needle,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if ($Text -notlike "*$Needle*") {
        throw "$Label is missing required marker: $Needle"
    }
}

function Patch-PyInstallerSpec {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SpecPath
    )

    $pythonScript = @"
from pathlib import Path

spec_path = Path(r'''$SpecPath''')
content = spec_path.read_text(encoding="utf-8")
hook_import = "from PyInstaller.utils.hooks import collect_all"
toc_import = "from PyInstaller.building.datastruct import TOC"
if toc_import not in content:
    content = content.replace(hook_import, hook_import + "\n" + toc_import)

filter_line = 'a.datas = TOC([entry for entry in a.datas if "QtQuick\\\\Controls\\\\designer" not in str(entry[0]).replace("/", "\\\\") and "QtQuick\\\\Controls\\\\designer" not in str(entry[1]).replace("/", "\\\\")])'
if filter_line not in content:
    content = content.replace("pyz = PYZ(a.pure)", filter_line + "\n\npyz = PYZ(a.pure)")

spec_path.write_text(content, encoding="utf-8")
"@

    $pythonScript | & $venvPython -
    Assert-NativeSuccess -Step "PyInstaller spec patch"
}

function Invoke-PyInstallerBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SpecDir,
        [Parameter(Mandatory = $true)]
        [string]$DistPath,
        [Parameter(Mandatory = $true)]
        [string]$WorkPath,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [switch]$OneFile
    )

    New-Item -ItemType Directory -Force -Path $SpecDir | Out-Null
    $specPath = Join-Path $SpecDir "JarvisAi_Unity.spec"
    Remove-Item -LiteralPath $specPath -Force -ErrorAction SilentlyContinue

    $makeSpecArgs = @(
        "--noupx",
        "--windowed",
        "--name", "JarvisAi_Unity",
        "--icon", $iconPath,
        "--version-file", $versionInfoFile,
        "--specpath", $SpecDir,
        "--paths", $root,
        "--exclude-module", "PySide6.Qt3DAnimation",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.Qt3DExtras",
        "--exclude-module", "PySide6.Qt3DInput",
        "--exclude-module", "PySide6.Qt3DLogic",
        "--exclude-module", "PySide6.Qt3DRender",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtGraphs",
        "--exclude-module", "PySide6.QtLocation",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtNetworkAuth",
        "--exclude-module", "PySide6.QtPdf",
        "--exclude-module", "PySide6.QtPdfWidgets",
        "--exclude-module", "PySide6.QtPositioning",
        "--exclude-module", "PySide6.QtQuick3D",
        "--exclude-module", "PySide6.QtQuick3DAssetImport",
        "--exclude-module", "PySide6.QtQuick3DAssetUtils",
        "--exclude-module", "PySide6.QtQuick3DPhysics",
        "--exclude-module", "PySide6.QtRemoteObjects",
        "--exclude-module", "PySide6.QtSensors",
        "--exclude-module", "PySide6.QtSerialBus",
        "--exclude-module", "PySide6.QtSerialPort",
        "--exclude-module", "PySide6.QtHelp",
        "--exclude-module", "PySide6.QtMultimediaWidgets",
        "--exclude-module", "PySide6.QtScxml",
        "--exclude-module", "PySide6.QtSpatialAudio",
        "--exclude-module", "PySide6.QtSql",
        "--exclude-module", "PySide6.QtSvgWidgets",
        "--exclude-module", "PySide6.QtTest",
        "--exclude-module", "PySide6.QtStateMachine",
        "--exclude-module", "PySide6.QtTextToSpeech",
        "--exclude-module", "PySide6.QtVirtualKeyboard",
        "--exclude-module", "PySide6.QtWebChannel",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineQuick",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebSockets",
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-all", "av",
        "--hidden-import", "pyttsx3.drivers.sapi5",
        "--hidden-import", "win32com.client",
        "--hidden-import", "pythoncom",
        "--hidden-import", "pywintypes",
        "--add-data", "$root\\ui;ui",
        "--add-data", "$root\\assets;assets",
        "--add-data", "$modelCacheDir;assets\\models\\faster-whisper"
    )
    if ($OneFile) {
        $makeSpecArgs += "--onefile"
    }
    $makeSpecArgs += "$root\\app\\main.py"

    & $pyiMakeSpec @makeSpecArgs
    Assert-NativeSuccess -Step "$Label spec generation"
    Patch-PyInstallerSpec -SpecPath $specPath

    New-Item -ItemType Directory -Force -Path $DistPath | Out-Null
    New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null
    & $venvPython -m PyInstaller --noconfirm --clean --distpath $DistPath --workpath $WorkPath $specPath
    Assert-NativeSuccess -Step "$Label build"
}

function Write-ZipArchive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDir,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $pythonScript = @"
from pathlib import Path
import zipfile

source = Path(r'''$SourceDir''')
destination = Path(r'''$DestinationPath''')
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    destination.unlink()

with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        archive.write(path, Path(source.name) / path.relative_to(source))
"@

    $pythonScript | & $venvPython -
    Assert-NativeSuccess -Step "Portable zip archive"
}

if (!(Test-Path $venvPython)) {
    throw "Virtualenv Python not found: $venvPython"
}

$version = (& $venvPython -c "from core.version import DEFAULT_VERSION; print(DEFAULT_VERSION)").Trim()
Write-Host "RELEASE_VERSION $version"
$releaseNotesPath = Join-Path $root "docs\RELEASE_$version.md"
if (!(Test-Path $releaseNotesPath)) {
    throw "Release notes missing: $releaseNotesPath"
}
Write-Host "RELEASE_NOTES $releaseNotesPath"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $versionInfoFile) | Out-Null
$versionInfoContent = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($($version.Replace('.', ', ')), 0),
    prodvers=($($version.Replace('.', ', ')), 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'theclepro1-hub'),
          StringStruct(u'FileDescription', u'JARVIS Unity desktop assistant'),
          StringStruct(u'FileVersion', u'$version'),
          StringStruct(u'InternalName', u'JarvisAi_Unity'),
          StringStruct(u'OriginalFilename', u'JarvisAi_Unity.exe'),
          StringStruct(u'ProductName', u'JARVIS Unity'),
          StringStruct(u'ProductVersion', u'$version')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
Set-Content -LiteralPath $versionInfoFile -Value $versionInfoContent -Encoding UTF8

& $venvPython "$root\\tools\\generate_icon.py"

New-Item -ItemType Directory -Force -Path $modelCacheDir | Out-Null
Write-Host "LOCAL_STT_MODEL_PREWARM $sttModelRef"
$resolvedSttModelPath = Resolve-LocalSTTModelPath -ModelRef $sttModelRef -CacheDir $modelCacheDir
if ([string]::IsNullOrWhiteSpace($resolvedSttModelPath) -or !(Test-Path $resolvedSttModelPath)) {
    Write-Host "LOCAL_STT_MODEL_PREWARM_SKIPPED $sttModelRef"
    Write-Host "LOCAL_STT_MODEL_RUNTIME_FALLBACK $modelCacheDir"
} else {
    Write-Host "LOCAL_STT_MODEL_READY $resolvedSttModelPath"
}

$portableRuntimeRoot = Join-Path $root "build\\portable_runtime_$buildStamp"
$oneFileRuntimeRoot = Join-Path $root "build\\onefile_runtime_$buildStamp"
Remove-Item -LiteralPath $portableRuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $oneFileRuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue

$distDir = Join-Path $portableRuntimeRoot "dist"
$buildDir = Join-Path $portableRuntimeRoot "pyinstaller"
$oneFileDistDir = Join-Path $oneFileRuntimeRoot "dist"
$oneFileBuildDir = Join-Path $oneFileRuntimeRoot "pyinstaller"
$releaseDir = Remove-Or-Fallback -Path $releaseDir -FallbackPath (Join-Path $root "build\\release_fresh_$buildStamp")
$versionInfoFile = Join-Path $buildDir "version_info.txt"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $versionInfoFile) | Out-Null
Set-Content -LiteralPath $versionInfoFile -Value $versionInfoContent -Encoding UTF8
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$buildWorkDir = Join-Path $buildDir "work"
$oneFileWorkDir = Join-Path $oneFileBuildDir "work"

Invoke-PyInstallerBuild -SpecDir $buildDir -DistPath $distDir -WorkPath $buildWorkDir -Label "PyInstaller portable"

$portableDistPath = Join-Path $distDir "JarvisAi_Unity"
if (!(Test-Path $portableDistPath)) {
    throw "Portable dist folder missing: $portableDistPath"
}

$portableZip = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_portable.zip" -f $version)
$portableZip = Remove-Or-Fallback -Path $portableZip -FallbackPath (Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_portable_fresh_{1}.zip" -f $version, $buildStamp))
Write-ZipArchive -SourceDir $portableDistPath -DestinationPath $portableZip
Write-ChecksumFile -ArtifactPath $portableZip | Out-Null
Assert-ChecksumFile -ArtifactPath $portableZip | Out-Null

Invoke-PyInstallerBuild -SpecDir $oneFileBuildDir -DistPath $oneFileDistDir -WorkPath $oneFileWorkDir -Label "PyInstaller onefile" -OneFile

$oneFileExe = Join-Path $oneFileDistDir "JarvisAi_Unity.exe"
if (!(Test-Path $oneFileExe)) {
    throw "Onefile executable missing: $oneFileExe"
}
$oneFileRelease = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_onefile.exe" -f $version)
$oneFileRelease = Remove-Or-Fallback -Path $oneFileRelease -FallbackPath (Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_onefile_fresh_{1}.exe" -f $version, $buildStamp))
Copy-Item $oneFileExe $oneFileRelease -Force
Write-ChecksumFile -ArtifactPath $oneFileRelease | Out-Null
Assert-ChecksumFile -ArtifactPath $oneFileRelease | Out-Null

$programFilesX86 = ${env:ProgramFiles(x86)}
if ([string]::IsNullOrWhiteSpace($programFilesX86)) {
    $programFilesX86 = ${env:ProgramFiles}
}
$innoCompiler = Join-Path $programFilesX86 "Inno Setup 6\\ISCC.exe"
$installerRelease = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_installer.exe" -f $version)
$installerRelease = Remove-Or-Fallback -Path $installerRelease -FallbackPath (Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_installer_fresh_{1}.exe" -f $version, $buildStamp))

if (Test-Path $innoCompiler) {
    Remove-Item -LiteralPath $installerDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
    $installerScript = Join-Path $installerDir "JarvisAi_Unity.iss"
    & $venvPython "$root\\tools\\release_metadata.py" `
        --version $version `
        --release-dir $releaseDir `
        --icon-path $iconPath `
        --portable-dist-path $portableDistPath `
        --output $installerScript
    Assert-NativeSuccess -Step "Installer metadata render"
    $installerScriptContent = Get-Content -LiteralPath $installerScript -Raw -Encoding UTF8
    Assert-TextContains -Text $installerScriptContent -Needle 'AppUserModelID: "theclepro1.JarvisAiUnity"' -Label "Installer shortcut identity"
    Assert-TextContains -Text $installerScriptContent -Needle "SetupMutex=JarvisAi_Unity_setup_mutex" -Label "Installer mutex"
    Assert-TextContains -Text $installerScriptContent -Needle "CloseApplicationsFilter=JarvisAi_Unity.exe" -Label "Installer close filter"
    Assert-TextContains -Text $installerScriptContent -Needle "VersionInfoTextVersion=$version" -Label "Installer version text"
    Assert-TextContains -Text $installerScriptContent -Needle 'Type: filesandordirs; Name: "{app}"' -Label "Installer uninstall cleanup"
    & $innoCompiler /Qp $installerScript
    Assert-NativeSuccess -Step "Inno Setup installer"
    if (!(Test-Path $installerRelease)) {
        throw "Installer executable missing: $installerRelease"
    }
    Write-ChecksumFile -ArtifactPath $installerRelease | Out-Null
    Assert-ChecksumFile -ArtifactPath $installerRelease | Out-Null
    Write-Host "ASSET_OK $installerRelease"
} else {
    Write-Host "INSTALLER_SKIPPED Inno Setup compiler not found: $innoCompiler"
}

Write-Host "BUILD_OK $distDir\\JarvisAi_Unity"
Write-Host "ASSET_OK $portableZip"
Write-Host "ASSET_OK $oneFileRelease"
