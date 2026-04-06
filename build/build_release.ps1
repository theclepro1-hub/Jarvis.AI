$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $root ".venv\\Scripts\\python.exe"
$distDir = Join-Path $root "dist"
$oneFileDistDir = Join-Path $root "dist_onefile"
$buildDir = Join-Path $root "build\\pyinstaller"
$oneFileBuildDir = Join-Path $root "build\\pyinstaller_onefile"
$releaseDir = Join-Path $root "build\\release"
$iconPath = Join-Path $root "assets\\icons\\jarvis_unity.ico"
$version = (& $venvPython -c "from core.updates.update_service import UpdateService; print(UpdateService().current_version)").Trim()

if (!(Test-Path $venvPython)) {
    throw "Virtualenv Python not found: $venvPython"
}

& $venvPython "$root\\tools\\generate_icon.py"

if (Test-Path $distDir) {
    Remove-Item -Recurse -Force $distDir
}
if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
}
if (Test-Path $oneFileDistDir) {
    Remove-Item -Recurse -Force $oneFileDistDir
}
if (Test-Path $oneFileBuildDir) {
    Remove-Item -Recurse -Force $oneFileBuildDir
}
if (Test-Path $releaseDir) {
    Remove-Item -Recurse -Force $releaseDir
}
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

& $venvPython -m PyInstaller `
    --noconfirm `
    --noupx `
    --windowed `
    --name "JarvisAi_Unity" `
    --icon $iconPath `
    --distpath $distDir `
    --workpath $buildDir `
    --paths $root `
    --collect-all PySide6 `
    --collect-all vosk `
    --add-data "$root\\ui;ui" `
    --add-data "$root\\assets;assets" `
    "$root\\app\\main.py"

$portableZip = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_portable.zip" -f $version)
Compress-Archive -Path (Join-Path $distDir "JarvisAi_Unity") -DestinationPath $portableZip -Force

& $venvPython -m PyInstaller `
    --noconfirm `
    --noupx `
    --windowed `
    --onefile `
    --name "JarvisAi_Unity" `
    --icon $iconPath `
    --distpath $oneFileDistDir `
    --workpath $oneFileBuildDir `
    --paths $root `
    --collect-all PySide6 `
    --collect-all vosk `
    --add-data "$root\\ui;ui" `
    --add-data "$root\\assets;assets" `
    "$root\\app\\main.py"

$oneFileExe = Join-Path $oneFileDistDir "JarvisAi_Unity.exe"
$oneFileRelease = Join-Path $releaseDir ("JarvisAi_Unity_{0}_windows_onefile.exe" -f $version)
Copy-Item $oneFileExe $oneFileRelease -Force

Write-Host "BUILD_OK $distDir\\JarvisAi_Unity"
Write-Host "ASSET_OK $portableZip"
Write-Host "ASSET_OK $oneFileRelease"
