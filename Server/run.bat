@echo off
chcp 65001 >nul
title PaymentMonitor Server
cd /d "%~dp0"
echo.
echo ============================================================
echo   PaymentMonitor Server - Starting...
echo ============================================================
echo.
python main.py
pause