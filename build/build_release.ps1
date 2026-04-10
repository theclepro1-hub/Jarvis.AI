$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $root ".venv\\Scripts\\python.exe"
$distDir = Join-Path $root "dist"
$oneFileDistDir = Join-Path $root "dist_onefile"
$buildDir = Join-Path $root "build\\pyinstaller"
$oneFileBuildDir = Join-Path $root "build\\pyinstaller_onefile"
$releaseDir = Join-Path $root "build\\release"
$installerDir = Join-Path $root "build\\installer"
$versionInfoFile = Join-Path $root "build\\pyinstaller\\version_info.txt"
$iconPath = Join-Path $root "assets\\icons\\jarvis_unity.ico"
$modelName = "vosk-model-small-ru-0.22"
$modelCacheDir = Join-Path $root "build\\model_cache"
$modelPath = Join-Path $modelCacheDir $modelName
$modelZip = Join-Path $modelCacheDir "$modelName.zip"
$modelUrl = "https://alphacephei.com/vosk/models/$modelName.zip"
$buildStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$requiredModelFiles = @(
    "am\final.mdl",
    "conf\model.conf",
    "graph\Gr.fst",
    "ivector\final.ie"
)

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

function Test-ModelSourceReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [string[]]$RequiredFiles = $requiredModelFiles
    )

    if (!(Test-Path $Path)) {
        return $false
    }

    foreach ($relativePath in $RequiredFiles) {
        if (!(Test-Path (Join-Path $Path $relativePath))) {
            return $false
        }
    }

    return $true
}

function Invoke-RetryDownload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$OutFile,
        [int]$Attempts = 3
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $OutFile
            if (!(Test-Path $OutFile)) {
                throw "download_missing"
            }
            if ((Get-Item -LiteralPath $OutFile).Length -le 0) {
                throw "download_empty"
            }
            return
        } catch {
            Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
            if ($attempt -ge $Attempts) {
                throw
            }
            Start-Sleep -Seconds 2
        }
    }
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

if (!(Test-Path $venvPython)) {
    throw "Virtualenv Python not found: $venvPython"
}

$version = (& $venvPython -c "from core.version import DEFAULT_VERSION; print(DEFAULT_VERSION)").Trim()
Write-Host "RELEASE_VERSION $version"

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

if (!(Test-ModelSourceReady -Path $modelPath)) {
    Remove-Item -Recurse -Force $modelPath -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $modelZip -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $modelCacheDir | Out-Null
    Write-Host "MODEL_DOWNLOAD $modelUrl"
    Invoke-RetryDownload -Uri $modelUrl -OutFile $modelZip
    Expand-Archive -Path $modelZip -DestinationPath $modelCacheDir -Force
    Remove-Item -LiteralPath $modelZip -Force
}

if (!(Test-ModelSourceReady -Path $modelPath)) {
    Remove-Item -Recurse -Force $modelPath -ErrorAction SilentlyContinue
    throw "Vosk model source is missing or empty: $modelPath"
}

$distDir = Remove-Or-Fallback -Path $distDir -FallbackPath (Join-Path $root "dist_fresh_$buildStamp")
$buildDir = Remove-Or-Fallback -Path $buildDir -FallbackPath (Join-Path $root "build\\pyinstaller_fresh_$buildStamp")
$oneFileDistDir = Remove-Or-Fallback -Path $oneFileDistDir -FallbackPath (Join-Path $root "dist_onefile_fresh_$buildStamp")
$oneFileBuildDir = Remove-Or-Fallback -Path $oneFileBuildDir -FallbackPath (Join-Path $root "build\\pyinstaller_onefile_fresh_$buildStamp")
$releaseDir = Remove-Or-Fallback -Path $releaseDir -FallbackPath (Join-Path $root "build\\release_fresh_$buildStamp")
$versionInfoFile = Join-Path $buildDir "version_info.txt"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $versionInfoFile) | Out-Null
Set-Content -LiteralPath $versionInfoFile -Value $versionInfoContent -Encoding UTF8
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$nativeErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $venvPython -m PyInstaller `
    --noconfirm `
    --noupx `
    --windowed `
    --name "JarvisAi_Unity" `
    --icon $iconPath `
    --version-file $versionInfoFile `
    --distpath $distDir `
    --workpath $buildDir `
    --specpath $buildDir `
    --paths $root `
    --exclude-module PySide6.Qt3DAnimation `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.Qt3DExtras `
    --exclude-module PySide6.Qt3DInput `
    --exclude-module PySide6.Qt3DLogic `
    --exclude-module PySide6.Qt3DRender `
    --exclude-module PySide6.QtCharts `
    --exclude-module PySide6.QtDataVisualization `
    --exclude-module PySide6.QtGraphs `
    --exclude-module PySide6.QtLocation `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtNetworkAuth `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtPdfWidgets `
    --exclude-module PySide6.QtPositioning `
    --exclude-module PySide6.QtQuick3D `
    --exclude-module PySide6.QtQuick3DAssetImport `
    --exclude-module PySide6.QtQuick3DAssetUtils `
    --exclude-module PySide6.QtQuick3DPhysics `
    --exclude-module PySide6.QtRemoteObjects `
    --exclude-module PySide6.QtSensors `
    --exclude-module PySide6.QtSerialBus `
    --exclude-module PySide6.QtSerialPort `
    --exclude-module PySide6.QtHelp `
    --exclude-module PySide6.QtMultimediaWidgets `
    --exclude-module PySide6.QtScxml `
    --exclude-module PySide6.QtSpatialAudio `
    --exclude-module PySide6.QtSql `
    --exclude-module PySide6.QtSvgWidgets `
    --exclude-module PySide6.QtTest `
    --exclude-module PySide6.QtStateMachine `
    --exclude-module PySide6.QtTextToSpeech `
    --exclude-module PySide6.QtVirtualKeyboard `
    --exclude-module PySide6.QtWebChannel `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineQuick `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtWebSockets `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all av `
    --collect-all vosk `
    --hidden-import pyttsx3.drivers.sapi5 `
    --hidden-import win32com.client `
    --hidden-import pythoncom `
    --hidden-import pywintypes `
    --add-data "$root\\ui;ui" `
    --add-data "$root\\assets;assets" `
    --add-data "$modelPath;assets\\models\\$modelName" `
    "$root\\app\\main.py"
$pyInstallerExit = $LASTEXITCODE
$ErrorActionPreference = $nativeErrorActionPreference
if ($pyInstallerExit -ne 0) {
    throw "PyInstaller portable failed with exit code $pyInstallerExit"
}

$portableDistPath = Join-Path $distDir "JarvisAi_Unity"
if (!(Test-Path $portableDistPath)) {
    throw "Portable dist folder missing: $portableDistPath"
}

$portableZip = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_portable.zip" -f $version)
Compress-Archive -Path $portableDistPath -DestinationPath $portableZip -Force
Write-ChecksumFile -ArtifactPath $portableZip | Out-Null
Assert-ChecksumFile -ArtifactPath $portableZip | Out-Null

$nativeErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $venvPython -m PyInstaller `
    --noconfirm `
    --noupx `
    --windowed `
    --onefile `
    --name "JarvisAi_Unity" `
    --icon $iconPath `
    --version-file $versionInfoFile `
    --distpath $oneFileDistDir `
    --workpath $oneFileBuildDir `
    --specpath $oneFileBuildDir `
    --paths $root `
    --exclude-module PySide6.Qt3DAnimation `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.Qt3DExtras `
    --exclude-module PySide6.Qt3DInput `
    --exclude-module PySide6.Qt3DLogic `
    --exclude-module PySide6.Qt3DRender `
    --exclude-module PySide6.QtCharts `
    --exclude-module PySide6.QtDataVisualization `
    --exclude-module PySide6.QtGraphs `
    --exclude-module PySide6.QtLocation `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtNetworkAuth `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtPdfWidgets `
    --exclude-module PySide6.QtPositioning `
    --exclude-module PySide6.QtQuick3D `
    --exclude-module PySide6.QtQuick3DAssetImport `
    --exclude-module PySide6.QtQuick3DAssetUtils `
    --exclude-module PySide6.QtQuick3DPhysics `
    --exclude-module PySide6.QtRemoteObjects `
    --exclude-module PySide6.QtSensors `
    --exclude-module PySide6.QtSerialBus `
    --exclude-module PySide6.QtSerialPort `
    --exclude-module PySide6.QtHelp `
    --exclude-module PySide6.QtMultimediaWidgets `
    --exclude-module PySide6.QtScxml `
    --exclude-module PySide6.QtSpatialAudio `
    --exclude-module PySide6.QtSql `
    --exclude-module PySide6.QtSvgWidgets `
    --exclude-module PySide6.QtTest `
    --exclude-module PySide6.QtStateMachine `
    --exclude-module PySide6.QtTextToSpeech `
    --exclude-module PySide6.QtVirtualKeyboard `
    --exclude-module PySide6.QtWebChannel `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineQuick `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtWebSockets `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all av `
    --collect-all vosk `
    --hidden-import pyttsx3.drivers.sapi5 `
    --hidden-import win32com.client `
    --hidden-import pythoncom `
    --hidden-import pywintypes `
    --add-data "$root\\ui;ui" `
    --add-data "$root\\assets;assets" `
    --add-data "$modelPath;assets\\models\\$modelName" `
    "$root\\app\\main.py"
$pyInstallerExit = $LASTEXITCODE
$ErrorActionPreference = $nativeErrorActionPreference
if ($pyInstallerExit -ne 0) {
    throw "PyInstaller onefile failed with exit code $pyInstallerExit"
}

$oneFileExe = Join-Path $oneFileDistDir "JarvisAi_Unity.exe"
if (!(Test-Path $oneFileExe)) {
    throw "Onefile executable missing: $oneFileExe"
}
$oneFileRelease = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_onefile.exe" -f $version)
Copy-Item $oneFileExe $oneFileRelease -Force
Write-ChecksumFile -ArtifactPath $oneFileRelease | Out-Null
Assert-ChecksumFile -ArtifactPath $oneFileRelease | Out-Null

$programFilesX86 = ${env:ProgramFiles(x86)}
if ([string]::IsNullOrWhiteSpace($programFilesX86)) {
    $programFilesX86 = ${env:ProgramFiles}
}
$innoCompiler = Join-Path $programFilesX86 "Inno Setup 6\\ISCC.exe"
$installerRelease = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_installer.exe" -f $version)

if (Test-Path $innoCompiler) {
    Remove-Item -LiteralPath $installerDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
    $installerScript = Join-Path $installerDir "JarvisAi_Unity.iss"
    $installerScriptContent = @"
[Setup]
AppId={{5E8E34A2-7D82-4B23-8B6A-2D12F795C2A9}}
AppName=JARVIS Unity
AppVersion=$version
AppVerName=JARVIS Unity $version
AppPublisher=theclepro1-hub
AppPublisherURL=https://github.com/theclepro1-hub/Jarvis.AI
AppSupportURL=https://github.com/theclepro1-hub/Jarvis.AI/issues
AppUpdatesURL=https://github.com/theclepro1-hub/Jarvis.AI/releases
DefaultDirName={autopf}\JARVIS Unity
DefaultGroupName=JARVIS Unity
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\JarvisAi_Unity.exe
UninstallDisplayName=JARVIS Unity
AppMutex=JarvisAi_Unity_22_instance_mutex
SetupMutex=JarvisAi_Unity_22_setup_mutex
CloseApplications=yes
CloseApplicationsFilter=JarvisAi_Unity.exe
RestartApplications=yes
VersionInfoCompany=theclepro1-hub
VersionInfoDescription=JARVIS Unity desktop assistant
VersionInfoProductName=JARVIS Unity
VersionInfoProductVersion=$version
VersionInfoVersion=$version.0
VersionInfoTextVersion=$version
OutputDir=$releaseDir
OutputBaseFilename=JarvisAi_Unity_$version`_windows_installer
SetupIconFile=$iconPath
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UsePreviousAppDir=yes
UsePreviousLanguage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "$portableDistPath\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Icons]
Name: "{group}\JARVIS Unity"; Filename: "{app}\JarvisAi_Unity.exe"; AppUserModelID: "theclepro1.JarvisAiUnity"
Name: "{group}\Uninstall JARVIS Unity"; Filename: "{uninstallexe}"
Name: "{autodesktop}\JARVIS Unity"; Filename: "{app}\JarvisAi_Unity.exe"; Tasks: desktopicon; AppUserModelID: "theclepro1.JarvisAiUnity"

[Run]
Filename: "{app}\JarvisAi_Unity.exe"; Description: "{cm:LaunchProgram,JARVIS Unity}"; Flags: nowait postinstall skipifsilent
"@
    Assert-TextContains -Text $installerScriptContent -Needle 'AppUserModelID: "theclepro1.JarvisAiUnity"' -Label "Installer shortcut identity"
    Assert-TextContains -Text $installerScriptContent -Needle "SetupMutex=JarvisAi_Unity_22_setup_mutex" -Label "Installer mutex"
    Assert-TextContains -Text $installerScriptContent -Needle "CloseApplicationsFilter=JarvisAi_Unity.exe" -Label "Installer close filter"
    Assert-TextContains -Text $installerScriptContent -Needle "VersionInfoTextVersion=$version" -Label "Installer version text"
    Assert-TextContains -Text $installerScriptContent -Needle 'Type: filesandordirs; Name: "{app}"' -Label "Installer uninstall cleanup"
    Set-Content -LiteralPath $installerScript -Value $installerScriptContent -Encoding UTF8
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
