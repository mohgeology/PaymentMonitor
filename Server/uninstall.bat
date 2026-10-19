@echo off
chcp 65001 >nul
title PaymentMonitor Server - Uninstall
setlocal enabledelayedexpansion

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

set "INSTALL_DIR=C:\PaymentMonitor\Server"
set "TASK_NAME=PaymentMonitor Server"

echo Stopping and removing task...
schtasks /end /tn "%TASK_NAME%" >nul 2>&1
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

echo Removing firewall rule...
netsh advfirewall firewall delete rule name="PaymentMonitor Server" >nul 2>&1

if exist "%INSTALL_DIR%\data\transactions.db" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DT=%%I"
    set "STAMP=!DT:~0,8!_!DT:~8,6!"
    set "BACKUP=%USERPROFILE%\Desktop\PM_Backup_!STAMP!.db"
    copy "%INSTALL_DIR%\data\transactions.db" "!BACKUP!" >nul
    echo   Backup saved: !BACKUP!
)

if exist "%INSTALL_DIR%" rmdir /S /Q "%INSTALL_DIR%"
if exist "C:\PaymentMonitor" rmdir /S /Q "C:\PaymentMonitor"
echo.
echo Uninstall complete.
pause