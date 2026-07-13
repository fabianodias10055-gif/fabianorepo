@echo off
REM ============================================================================
REM  Setup-Libertas.bat  -  double-click to set up the Libertas UE 5.7 project.
REM
REM  Elevates to administrator, then runs Setup-Libertas.ps1 which:
REM    1. installs the required Visual Studio 2022 components (from .vsconfig)
REM    2. finds Unreal Engine 5.7
REM    3. generates the Visual Studio project files
REM    4. builds the LibertasEditor target
REM
REM  You will see a User Account Control (UAC) prompt - click "Yes".
REM ============================================================================

echo Launching Libertas setup (an admin prompt will appear)...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0Setup-Libertas.ps1\"'"

echo.
echo A new elevated window is running the setup. You can close this window.
