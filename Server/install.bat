@echo off
chcp 65001 >nul
title PaymentMonitor Server - Installation
setlocal enabledelayedexpansion

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Right-click this file and choose Run as administrator.
    pause
    exit /b 1
)

set "INSTALL_DIR=C:\PaymentMonitor\Server"
set "PORT=5000"
set "TASK_NAME=PaymentMonitor Server"

echo ============================================================
echo   PaymentMonitor Server - Installation
echo   Install to: %INSTALL_DIR%
echo   Port:       %PORT%
echo ============================================================
echo.

netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING" >nul
if %errorLevel% equ 0 (
    echo WARNING: Port %PORT% already in use.
    choice /c YN /n /m "Continue anyway? [Y/N] "
    if errorlevel 2 exit /b 1
)

echo [1/6] Creating folders...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"

echo [2/6] Copying files...
xcopy "%~dp0_internal" "%INSTALL_DIR%\_internal\" /E /I /Y /Q >nul
copy /Y "%~dp0PaymentMonitor.Server.exe" "%INSTALL_DIR%\" >nul
if not exist "%INSTALL_DIR%\PaymentMonitor.Server.exe" (
    echo ERROR: PaymentMonitor.Server.exe not found.
    pause
    exit /b 1
)

echo [3/6] Configuring firewall...
netsh advfirewall firewall delete rule name="PaymentMonitor Server" >nul 2>&1
netsh advfirewall firewall add rule name="PaymentMonitor Server" dir=in action=allow protocol=TCP localport=%PORT% >nul

echo [4/6] Registering startup task...
schtasks /end    /tn "%TASK_NAME%" >nul 2>&1
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
schtasks /create /tn "%TASK_NAME%" /tr "\"%INSTALL_DIR%\PaymentMonitor.Server.exe\"" /sc onstart /ru "SYSTEM" /rl HIGHEST /f >nul
if %errorLevel% neq 0 (
    echo ERROR: Failed to register task.
    pause
    exit /b 1
)

echo [5/6] Starting server...
schtasks /run /tn "%TASK_NAME%" >nul
timeout /t 5 /nobreak >nul

echo [6/6] Opening dashboard...
for /f "delims=" %%a in ('powershell -NoProfile -Command "try { (Invoke-RestMethod -Uri 'http://localhost:%PORT%/api/network-info' -TimeoutSec 3).ip } catch { ''localhost'' }" ') do set "IP=%%a"

echo.
echo ============================================================
echo   Installation Complete!
echo   Server:     http://%IP%:%PORT%
echo   Dashboard:  http://%IP%:%PORT%/dashboard
echo   Auto-start on every Windows boot.
echo   Location:   %INSTALL_DIR%
echo ============================================================
echo.
start http://localhost:%PORT%/dashboard
pause
