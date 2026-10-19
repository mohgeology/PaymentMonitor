============================================================
  PaymentMonitor Cashier - Installation Guide
============================================================

Requirements:
-------------
- Windows 10/11 (64-bit)
- No .NET Runtime needed (bundled inside)

Installation Steps:
-------------------
1. Copy the "PaymentMonitor Cashier" folder to the cashier PC.

2. Open the folder and run: install-cashier.bat

3. The app will start automatically as a small icon in the system tray.

4. Right-click the icon -> Network Settings.

5. Enter the server URL, for example:
   http://192.168.1.70:5000

6. Click "Test Connection" to verify.

7. Click "Save and Reconnect".

8. Done! You will receive notifications automatically.

Uninstallation:
---------------
Run: uninstall-cashier.bat

Notes:
------
- The app starts automatically when Windows starts.
- No window or browser needed.
- Runs in background in system tray.
- Balloon notifications appear when a new transaction arrives.
- Sound alert included.

Support:
--------
Open the dashboard on the server:
http://SERVER-IP:5000/dashboard
