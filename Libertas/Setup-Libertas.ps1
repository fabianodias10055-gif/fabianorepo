<#
    Setup-Libertas.ps1
    -------------------
    One-shot setup for the Libertas Unreal Engine 5.7 C++ project on Windows.

    It performs, in order:
      1. Installs the required Visual Studio 2022 components from .vsconfig
         (installs VS Community if none is present, or adds missing components
         to an existing install).
      2. Locates Unreal Engine 5.7.
      3. Generates the Visual Studio project files for Libertas.
      4. Builds the LibertasEditor target (Development | Win64).

    Run it by double-clicking Setup-Libertas.bat (which elevates to admin).
    You can also run it directly from an ADMIN PowerShell:
        powershell -ExecutionPolicy Bypass -File .\Setup-Libertas.ps1

    Nothing here is destructive; it only installs tooling and builds the project.
#>

$ErrorActionPreference = 'Stop'
$ProjectDir  = $PSScriptRoot
$UProject    = Join-Path $ProjectDir 'Libertas.uproject'
$VsConfig    = Join-Path $ProjectDir '.vsconfig'
$EngineVer   = '5.7'

function Write-Step($msg)  { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg"   -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "  [!] $msg"    -ForegroundColor Yellow }

Write-Host "Libertas setup - Unreal Engine $EngineVer" -ForegroundColor White
Write-Host "Project: $ProjectDir"

if (-not (Test-Path $UProject)) {
    throw "Libertas.uproject not found next to this script. Run it from inside the Libertas project folder."
}

# --------------------------------------------------------------------------
# 1. Visual Studio 2022 components
# --------------------------------------------------------------------------
Write-Step 'Visual Studio 2022 components'

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsInstaller = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vs_installer.exe'
$installedPath = $null
if (Test-Path $vswhere) {
    $installedPath = & $vswhere -latest -products * -property installationPath 2>$null | Select-Object -First 1
}

if ($installedPath -and (Test-Path $installedPath)) {
    Write-Ok "Visual Studio found at: $installedPath"
    Write-Host "  Adding any missing components from .vsconfig (a VS Installer window may appear)..."
    Start-Process -FilePath $vsInstaller -ArgumentList @(
        'modify', '--installPath', "`"$installedPath`"",
        '--config', "`"$VsConfig`"", '--passive', '--norestart', '--norestart'
    ) -Wait
    Write-Ok "Visual Studio components ensured."
} else {
    Write-Warn2 "No Visual Studio install detected - downloading the VS 2022 Community bootstrapper."
    $bootstrapper = Join-Path $env:TEMP 'vs_community.exe'
    Write-Host "  Downloading from https://aka.ms/vs/17/release/vs_community.exe ..."
    Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vs_community.exe' -OutFile $bootstrapper
    Write-Host "  Installing (this downloads several GB and can take a while)..."
    Start-Process -FilePath $bootstrapper -ArgumentList @(
        '--config', "`"$VsConfig`"", '--passive', '--norestart', '--wait'
    ) -Wait
    Write-Ok "Visual Studio 2022 Community installed with the required components."
}

# --------------------------------------------------------------------------
# 2. Locate Unreal Engine 5.7
# --------------------------------------------------------------------------
Write-Step "Locating Unreal Engine $EngineVer"

$EngineDir = $null
$regKeys = @(
    "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$EngineVer",
    "HKLM:\SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\$EngineVer"
)
foreach ($k in $regKeys) {
    try {
        $val = (Get-ItemProperty -Path $k -ErrorAction Stop).InstalledDirectory
        if ($val -and (Test-Path $val)) { $EngineDir = $val; break }
    } catch { }
}
if (-not $EngineDir) {
    $guess = "C:\Program Files\Epic Games\UE_$EngineVer"
    if (Test-Path $guess) { $EngineDir = $guess }
}

if (-not $EngineDir) {
    Write-Warn2 "Unreal Engine $EngineVer was not found."
    Write-Warn2 "Install it via the Epic Games Launcher (Unreal Engine > Library > +), then re-run this script."
    Write-Host  "Visual Studio setup above is already done." -ForegroundColor White
    Read-Host "`nPress Enter to close"
    return
}
Write-Ok "Unreal Engine found at: $EngineDir"

$UBT   = Join-Path $EngineDir 'Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe'
$BuildBat = Join-Path $EngineDir 'Engine\Build\BatchFiles\Build.bat'

# --------------------------------------------------------------------------
# 3. Generate Visual Studio project files
# --------------------------------------------------------------------------
Write-Step 'Generating Visual Studio project files'
if (Test-Path $UBT) {
    & $UBT -projectfiles -project="`"$UProject`"" -game -progress
    Write-Ok "Generated Libertas.sln"
} else {
    Write-Warn2 "UnrealBuildTool not found at $UBT - skipping project file generation."
}

# --------------------------------------------------------------------------
# 4. Build the editor
# --------------------------------------------------------------------------
Write-Step 'Building LibertasEditor (Development | Win64)'
if (Test-Path $BuildBat) {
    & $BuildBat LibertasEditor Win64 Development -project="`"$UProject`"" -waitmutex
    Write-Ok "Build finished."
} else {
    Write-Warn2 "Build.bat not found at $BuildBat - skipping build."
}

Write-Host "`nAll done. Double-click Libertas.uproject to open the editor," -ForegroundColor Green
Write-Host "or open Libertas.sln in Visual Studio and press F5." -ForegroundColor Green
Read-Host "`nPress Enter to close"
