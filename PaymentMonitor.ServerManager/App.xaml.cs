using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Forms;
using WpfMessageBox = System.Windows.MessageBox;
using WpfMessageBoxButton = System.Windows.MessageBoxButton;
using WpfMessageBoxImage = System.Windows.MessageBoxImage;
using WpfMessageBoxResult = System.Windows.MessageBoxResult;

namespace PaymentMonitor.ServerManager;

public partial class App : System.Windows.Application
{
    private NotifyIcon? _trayIcon;
    private ServerProcessManager? _serverManager;
    private AppSettings _settings = new();
    private System.Windows.Threading.DispatcherTimer? _monitorTimer;

    private static readonly string AppFolder =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PaymentMonitor.ServerManager");

    private static readonly string SettingsPath =
        Path.Combine(AppFolder, "settings.json");

    private static readonly string LogPath =
        Path.Combine(AppFolder, "server-log.txt");

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        Directory.CreateDirectory(AppFolder);
        LoadSettings();

        if (string.IsNullOrEmpty(_settings.ServerFolder))
        {
            // أول تشغيل: عرض الإعدادات
            ShowSettings();
            if (string.IsNullOrEmpty(_settings.ServerFolder))
            {
                WpfMessageBox.Show(
                    "لم يتم إعداد السيرفر. أغلق التطبيق وأعد فتحه لاحقًا.",
                    "PaymentMonitor Server Manager",
                    WpfMessageBoxButton.OK, WpfMessageBoxImage.Warning);
                Shutdown();
                return;
            }
        }

        _serverManager = new ServerProcessManager(_settings);
        _serverManager.OnStatusChanged += OnStatusChanged;
        _serverManager.OnLog += OnLog;

        SetupTrayIcon();
        StartMonitor();

        _ = _serverManager.StartAsync();
    }

    private void LoadSettings()
    {
        try
        {
            if (File.Exists(SettingsPath))
            {
                var json = File.ReadAllText(SettingsPath);
                var s = JsonSerializer.Deserialize<AppSettings>(json);
                if (s != null) _settings = s;
            }
        }
        catch { }
    }

    private void SaveSettings()
    {
        try
        {
            var json = JsonSerializer.Serialize(_settings, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(SettingsPath, json);
        }
        catch { }
    }

    private void AutoDetectDefaults()
{
    _settings.ServerFolder = Path.Combine(AppContext.BaseDirectory, "..", "PaymentMonitor.Server");
    if (!Directory.Exists(_settings.ServerFolder))
        _settings.ServerFolder = @"F:\PaymentMonitor\PaymentMonitor.Server";
    SaveSettings();
}

    private Icon CreateServerIcon()
    {
        try
        {
            var bmp = new Bitmap(32, 32);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);

                // خلفية دائرية زرقاء داكنة
                using (var bgBrush = new SolidBrush(Color.FromArgb(18, 59, 122)))
                {
                    g.FillEllipse(bgBrush, 0, 0, 31, 31);
                }

                // 3 خطوط بيضاء (سيرفر)
                using (var whitePen = new Pen(Color.White, 2.2f))
                {
                    g.DrawLine(whitePen, 8, 10, 23, 10);
                    g.DrawLine(whitePen, 8, 16, 23, 16);
                    g.DrawLine(whitePen, 8, 22, 23, 22);
                }

                // نقطة خضراء (حالة: يعمل)
                using (var greenBrush = new SolidBrush(Color.FromArgb(76, 175, 80)))
                {
                    g.FillEllipse(greenBrush, 23, 23, 8, 8);
                }

                // حدود خفيفة
                using (var borderPen = new Pen(Color.FromArgb(240, 124, 34), 1.5f))
                {
                    g.DrawEllipse(borderPen, 0, 0, 31, 31);
                }
            }

            var hIcon = bmp.GetHicon();
            return Icon.FromHandle(hIcon);
        }
        catch
        {
            return SystemIcons.Application;
        }
    }

    private void SetupTrayIcon()
    {
        _trayIcon = new NotifyIcon
        {
            Icon = CreateServerIcon(),
            Visible = true,
            Text = "PaymentMonitor Server"
        };

        var menu = new ContextMenuStrip();
        menu.Items.Add("🌐 فتح لوحة التحكم", null, (s, e) => OpenDashboard());
        menu.Items.Add("📱 ربط التطبيق (QR)", null, (s, e) => ShowQr());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("⚙ إعدادات الشبكة", null, (s, e) => ShowSettings());
        menu.Items.Add("📊 حالة السيرفر", null, (s, e) => ShowStatus());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("🔄 إعادة تشغيل السيرفر", null, async (s, e) => await RestartServer());
        menu.Items.Add("⏹ إيقاف السيرفر", null, async (s, e) => await StopServer());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("📁 فتح مجلد السجلات", null, (s, e) => OpenLogFolder());
        menu.Items.Add("❌ خروج", null, (s, e) => ExitApp());

        _trayIcon.ContextMenuStrip = menu;
        _trayIcon.DoubleClick += (s, e) => OpenDashboard();
    }

    private void StartMonitor()
    {
        _monitorTimer = new System.Windows.Threading.DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(10)
        };
        _monitorTimer.Tick += async (s, e) =>
        {
            if (_serverManager == null) return;

            var responding = await _serverManager.IsServerRespondingAsync();
            if (!responding && !_serverManager.IsRunning)
            {
                OnLog("السيرفر لا يستجيب — محاولة إعادة التشغيل");
                await _serverManager.StartAsync();
            }
        };
        _monitorTimer.Start();
    }

    private void OpenDashboard()
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = $"http://127.0.0.1:{_settings.Port}/dashboard",
                UseShellExecute = true
            });
        }
        catch { }
    }

    private async void ShowQr()
    {
        if (!_serverManager!.IsRunning && !await _serverManager.IsServerRespondingAsync())
        {
            WpfMessageBox.Show("السيرفر غير مشغّل. الرجاء تشغيله أولًا.",
                "PaymentMonitor", WpfMessageBoxButton.OK, WpfMessageBoxImage.Warning);
            return;
        }
        var wnd = new QrWindow(_settings.Port);
        wnd.Show();
    }

    private void ShowSettings()
    {
        if (string.IsNullOrEmpty(_settings.ServerFolder) || string.IsNullOrEmpty(_settings.PythonPath))
        {
            AutoDetectDefaults();
        }

        var wnd = new SettingsWindow(_settings);
        var result = wnd.ShowDialog();

        if (result == true && wnd.SavedSettings != null)
        {
            _settings = wnd.SavedSettings;
            SaveSettings();

            // إعادة تشغيل السيرفر بالإعدادات الجديدة
            _ = Task.Run(async () =>
            {
                await _serverManager!.StopAsync();
                await _serverManager.KillProcessOnPortAsync();
                _serverManager = new ServerProcessManager(_settings);
                _serverManager.OnStatusChanged += OnStatusChanged;
                _serverManager.OnLog += OnLog;
                await _serverManager.StartAsync();
            });
        }
    }

    private void ShowStatus()
    {
        var status = _serverManager!.IsRunning
            ? $"🟢 يعمل على المنفذ {_settings.Port}"
            : "🔴 متوقف";

        var localIp = _serverManager.GetLocalIp();
        var dashboard = $"http://{localIp}:{_settings.Port}/dashboard";

        WpfMessageBox.Show(
            $"حالة السيرفر: {status}\n\n" +
            $"عنوان السيرفر: http://{localIp}:{_settings.Port}\n" +
            $"لوحة التحكم: {dashboard}\n\n" +
            $"مجلد السيرفر:\n{_settings.ServerFolder}\n\n" +
            $"Python:\n{_settings.PythonPath}",
            "PaymentMonitor - حالة السيرفر",
            WpfMessageBoxButton.OK, WpfMessageBoxImage.Information);
    }

    private async Task RestartServer()
    {
        if (_serverManager == null) return;
        await _serverManager.StopAsync();
        var killed = await _serverManager.KillProcessOnPortAsync();
        OnLog("Restart: external python processes killed on port = " + killed);
        await Task.Delay(800);
        await _serverManager.StartAsync();
    }

    private async Task StopServer()
    {
        if (_serverManager == null) return;
        var result = WpfMessageBox.Show(
            "هل تريد إيقاف السيرفر؟",
            "PaymentMonitor", WpfMessageBoxButton.YesNo, WpfMessageBoxImage.Question);

        if (result == WpfMessageBoxResult.Yes)
        {
            await _serverManager.StopAsync();
        }
    }

    private void OpenLogFolder()
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = AppFolder,
                UseShellExecute = true
            });
        }
        catch { }
    }

    private void OnStatusChanged(string status)
    {
        Current.Dispatcher.Invoke(() =>
        {
            if (_trayIcon != null)
            {
                var text = "PaymentMonitor Server — " + status;
                if (text.Length > 63) text = text.Substring(0, 63);
                _trayIcon.Text = text;
            }
        });
    }

    private void OnLog(string message)
    {
        try
        {
            var line = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}";
            File.AppendAllText(LogPath, line + Environment.NewLine);
            Debug.WriteLine(line);
        }
        catch { }
    }

    private async void ExitApp()
    {
        try
        {
            if (_serverManager != null)
            {
                await _serverManager.StopAsync();
            }
            _monitorTimer?.Stop();
            _trayIcon!.Visible = false;
            _trayIcon.Dispose();
        }
        catch { }

        Shutdown();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        try
        {
            _serverManager?.StopAsync().Wait(3000);
            _trayIcon?.Dispose();
        }
        catch { }
        base.OnExit(e);
    }
}
