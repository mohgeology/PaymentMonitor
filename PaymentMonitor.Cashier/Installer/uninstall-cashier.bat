@echo off
chcp 65001 >nul
title PaymentMonitor Cashier - Uninstallation

echo.
echo ============================================================
echo   PaymentMonitor Cashier - Uninstallation
echo ============================================================
echo.

echo [1/4] Stopping application...
taskkill /F /IM PaymentMonitor.Cashier.exe >nul 2>&1
echo     ^> Stopped
echo.

echo [2/4] Removing startup shortcut...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\PaymentMonitor Cashier.lnk"
if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo     ^> Removed
) else (
    echo     ^> Not found
)
echo.

echo [3/4] Removing desktop shortcut...
set "DTSHORTCUT=%USERPROFILE%\Desktop\PaymentMonitor Cashier.lnk"
if exist "%DTSHORTCUT%" (
    del "%DTSHORTCUT%"
    echo     ^> Removed
) else (
    echo     ^> Not found
)
echo.

echo [4/4] Removing application files...
set "TARGET=%LOCALAPPDATA%\PaymentMonitor.Cashier"

set /p REMOVE_SETTINGS="Remove settings too? (y/n): "
if /i "%REMOVE_SETTINGS%"=="y" (
    rmdir /S /Q "%TARGET%" 2>nul
    echo     ^> Everything removed
) else (
    rmdir /S /Q "%TARGET%\App" 2>nul
    echo     ^> App removed (settings kept)
)
echo.

echo ============================================================
echo   Uninstallation complete!
echo ============================================================
echo.
pause
