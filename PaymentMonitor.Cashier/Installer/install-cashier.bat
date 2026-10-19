@echo off
chcp 65001 >nul
title PaymentMonitor Cashier - Installation

echo.
echo ============================================================
echo   PaymentMonitor Cashier - Installation
echo ============================================================
echo.

set "SOURCE=%~dp0"
set "TARGET=%LOCALAPPDATA%\PaymentMonitor.Cashier\App"

echo [1/5] Creating installation folder...
if not exist "%TARGET%" mkdir "%TARGET%"
echo     ^> %TARGET%
echo.

echo [2/5] Copying application files...
xcopy "%SOURCE%App\*" "%TARGET%\" /E /I /Y /Q >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy files.
    pause
    exit /b 1
)
echo     ^> Copied
echo.

echo [3/5] Adding startup shortcut...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\PaymentMonitor Cashier.lnk"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%\PaymentMonitor.Cashier.exe'; $sc.WorkingDirectory = '%TARGET%'; $sc.Description = 'PaymentMonitor Cashier'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo     ^> Startup shortcut added
) else (
    echo     [Warning] Failed to add startup shortcut
)
echo.

echo [4/5] Adding desktop shortcut...
set "DESKTOP=%USERPROFILE%\Desktop"
set "DTSHORTCUT=%DESKTOP%\PaymentMonitor Cashier.lnk"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%DTSHORTCUT%'); $sc.TargetPath = '%TARGET%\PaymentMonitor.Cashier.exe'; $sc.WorkingDirectory = '%TARGET%'; $sc.Description = 'PaymentMonitor Cashier'; $sc.Save()"

if exist "%DTSHORTCUT%" (
    echo     ^> Desktop shortcut added
) else (
    echo     [Warning] Failed to add desktop shortcut
)
echo.

echo [5/5] Starting application...
start "" "%TARGET%\PaymentMonitor.Cashier.exe"
echo     ^> Application is running
echo.

echo ============================================================
echo   Installation complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Look for the app icon in the system tray
echo   2. Right-click the icon
echo   3. Select "Network Settings"
echo   4. Enter server URL (example: http://192.168.1.70:5000)
echo   5. Click "Test Connection" then "Save and Reconnect"
echo.
pause
