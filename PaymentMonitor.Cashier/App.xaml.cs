using System.IO;
using System.Windows;
using System.Windows.Forms;
using System.Drawing;

namespace PaymentMonitor.Cashier;

public partial class App : System.Windows.Application
{
    private NotifyIcon? _trayIcon;
    private ContextMenuStrip? _trayMenu;
    private WebSocketClient? _wsClient;
    private AppSettings _settings = new();

    // Phase 6B
    private ClaimApiClient? _api;
    private NotificationManager? _notificationManager;
    private string _authToken = "";
    private int _myCashierId = 0;
    private string _myCashierName = "";

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // منع إغلاق التطبيق عند إغلاق آخر نافذة (الإعدادات)
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        _settings = SettingsService.Load();
        OnLog($"settings loaded. SavedToken present: {!string.IsNullOrEmpty(_settings.SavedAuthToken)}");
        _wsClient = new WebSocketClient();

        _wsClient.OnTransactionReceived += OnTransactionReceived;
        _wsClient.OnConnectionChanged += OnConnectionChanged;
        _wsClient.OnLog += OnLog;

        // Phase 6B: connect claimed/unassigned events
        _wsClient.OnTransactionClaimed += OnTransactionClaimed;
        _wsClient.OnTransactionUnassigned += OnTransactionUnassigned;

        SetupTrayIcon();

        OnLog($"OnStartup check: ServerUrl={_settings.ServerUrl}, SavedUrl={_settings.SavedServerUrlForToken}, TokenPresent={!string.IsNullOrEmpty(_settings.SavedAuthToken)}");

        // استرجاع token للاستخدام التلقائي (Auto-Login)
        if (!string.IsNullOrEmpty(_settings.SavedAuthToken)
            && _settings.SavedServerUrlForToken == _settings.ServerUrl)
        {
            _authToken = _settings.SavedAuthToken;
            _myCashierId = _settings.SavedCashierId;
            _myCashierName = _settings.SavedCashierName ?? "";
            OnLog($"Auto-login: restoring session for {_myCashierName}");
        }

        if (!string.IsNullOrEmpty(_settings.ServerUrl))
        {
            _ = ConnectAsync();
        }
        else
        {
            ShowBalloon("لم يتم إعداد السيرفر", "انقر على الأيقونة → إعدادات الشبكة");
        }
    }

    private void SetupTrayIcon()
    {
        if (_trayIcon == null)
        {
            _trayIcon = new NotifyIcon
            {
                Icon = SystemIcons.Information,
                Visible = true,
                Text = "PaymentMonitor Cashier"
            };
            _trayIcon.DoubleClick += (s, e) => ShowSettings();
        }

        RefreshTrayMenu();
    }

    private void RefreshTrayMenu()
    {
        if (_trayIcon == null) return;

        // إعادة إنشاء القائمة
        _trayMenu = new ContextMenuStrip();

        // معلومات الحالة
        var isLoggedIn = !string.IsNullOrEmpty(_authToken);
        var statusText = isLoggedIn
            ? $"✅ مسجل: {_myCashierName}"
            : "🔒 غير مسجل";
        var statusItem = new ToolStripMenuItem(statusText) { Enabled = false };
        _trayMenu.Items.Add(statusItem);
        _trayMenu.Items.Add(new ToolStripSeparator());

        // إعدادات الشبكة
        _trayMenu.Items.Add("⚙ إعدادات الشبكة", null, (s, e) => ShowSettings());

        // تسجيل الدخول أو الخروج
        if (isLoggedIn)
        {
            _trayMenu.Items.Add("🛑 إنهاء الجلسة", null, async (s, e) => await EndSessionAsync());
            _trayMenu.Items.Add("🔓 تسجيل الخروج", null, async (s, e) => await LogoutAsync());
        }
        else
        {
            _trayMenu.Items.Add("🔒 تسجيل الدخول", null, async (s, e) => await ShowLoginAsync());
        }

        // إعادة الاتصال
        _trayMenu.Items.Add("🔁 إعادة الاتصال", null, async (s, e) => await ConnectAsync());

        _trayMenu.Items.Add(new ToolStripSeparator());
        _trayMenu.Items.Add("❌ خروج", null, (s, e) => ExitApp());

        // استبدال القائمة
        _trayIcon.ContextMenuStrip = _trayMenu;
    }

    private async Task ConnectAsync()
    {
        if (string.IsNullOrEmpty(_settings.ServerUrl))
            return;

        try
        {
            await _wsClient!.ConnectAsync(_settings.ServerUrl);

            // Phase 6B: initialize API client after WebSocket connected
            if (string.IsNullOrEmpty(_authToken))
            {
                // نحاول تسجيل دخول تلقائي إذا كان هناك username/password محفوظ
                // (اختياري - يمكن تركه يدويًا)
            }

            // Auto-login: إذا وُجد token محفوظ، أعد استخدامه
            if (!string.IsNullOrEmpty(_authToken))
            {
                _api = new ClaimApiClient(_settings.ServerUrl, _authToken);
                _notificationManager = new NotificationManager(_settings, _api);
                OnLog($"Auto-login: using saved token for {_myCashierName}");

                // إرسال auth للـ WebSocket (بانتظار أن يصبح متصلًا)
                await TrySendAuthAsync();

                // تحديث القائمة
                RefreshTrayMenu();
            }
            else
            {
                // لا يوجد token — يحتاج تسجيل يدوي
                OnLog("No saved token — login required");
                RefreshTrayMenu();
            }
        }
        catch { }
    }


    private async Task TrySendAuthAsync()
    {
        if (_wsClient == null || string.IsNullOrEmpty(_authToken))
        {
            OnLog("TrySendAuthAsync skipped: no client or token");
            return;
        }

        // الانتظار حتى يصبح الاتصال مفتوحًا (حتى 10 ثوانٍ)
        for (int i = 0; i < 20; i++)
        {
            if (_wsClient.IsConnected)
            {
                try
                {
                    await _wsClient.SendAuthAsync(_authToken);
                    OnLog($"auth sent (attempt {i + 1})");
                    return;
                }
                catch (Exception ex)
                {
                    OnLog($"auth send failed: {ex.Message}");
                }
            }
            await Task.Delay(500);
        }
        OnLog("TrySendAuthAsync: timeout waiting for connection");
    }

    private async Task ShowLoginAsync()
    {
        // نافذة بسيطة عبر InputBox (Microsoft.VisualBasic)
        try
        {
            var username = Microsoft.VisualBasic.Interaction.InputBox(
                "اسم المستخدم:", "تسجيل الدخول - PaymentMonitor", "");

            if (string.IsNullOrEmpty(username)) return;

            var password = Microsoft.VisualBasic.Interaction.InputBox(
                "كلمة المرور:", "تسجيل الدخول - PaymentMonitor", "");

            if (string.IsNullOrEmpty(password)) return;

            if (string.IsNullOrEmpty(_settings.ServerUrl))
            {
                System.Windows.MessageBox.Show("لم يتم إعداد السيرفر أولاً", "خطأ",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var api = new ClaimApiClient(_settings.ServerUrl, "");
            var result = await api.LoginAsync(username, password);

            if (result != null && result.Success && !string.IsNullOrEmpty(result.Token))
            {
                _authToken = result.Token;
                _myCashierId = result.Cashier?.Id ?? 0;
                _myCashierName = result.Cashier?.DisplayName ?? result.Cashier?.Username ?? "admin";
                _api = new ClaimApiClient(_settings.ServerUrl, _authToken);

                // حفظ token للاستخدام التلقائي
                _settings.SavedAuthToken = _authToken;
                _settings.SavedCashierId = _myCashierId;
                _settings.SavedCashierName = _myCashierName;
                _settings.SavedServerUrlForToken = _settings.ServerUrl;
                SettingsService.Save(_settings);
                OnLog("auth saved for auto-login");

                // تحديث قائمة Tray
                RefreshTrayMenu();

                // إخبار WebSocket بالـ token
                await TrySendAuthAsync();

                _notificationManager = new NotificationManager(_settings, _api);

                // فتح جلسة تلقائيًا
                try
                {
                    await _api.OpenSessionAsync();
                }
                catch { }

                System.Windows.MessageBox.Show(
                    $"مرحبًا {result.Cashier?.DisplayName ?? username}!",
                    "تسجيل دخول ناجح",
                    MessageBoxButton.OK, MessageBoxImage.Information);
            }
            else
            {
                System.Windows.MessageBox.Show("فشل تسجيل الدخول",
                    "خطأ", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
        catch (Exception ex)
        {
            System.Windows.MessageBox.Show($"خطأ: {ex.Message}",
                "خطأ", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void ShowSettings()
    {
        var wnd = new SettingsWindow();
        var result = wnd.ShowDialog();

        if (result == true && !string.IsNullOrEmpty(wnd.SavedServerUrl))
        {
            _settings.ServerUrl = wnd.SavedServerUrl;
            _ = ConnectAsync();
        }
    }

    private void OnTransactionReceived(Transaction tx)
    {
        Current.Dispatcher.Invoke(() =>
        {
            // Phase 6B: interactive notification أولاً
            if (_settings.EnableInteractiveNotification && _notificationManager != null)
            {
                _notificationManager.Show(tx);
            }
            else
            {
                // fallback: balloon
                var title = NotificationService.BuildBalloonTitle();
                var text = NotificationService.BuildBalloonText(tx);
                if (_settings.ShowBalloon)
                    ShowBalloon(title, text);
            }

            if (_settings.PlaySound)
                NotificationService.PlaySound();
        });
    }

    // Phase 6B: عند claim من كاشير آخر → أغلق النافذة تلقائيًا
    private void OnTransactionClaimed(string transactionId, ClaimedByInfo claimedBy)
    {
        Current.Dispatcher.Invoke(() =>
        {
            if (_notificationManager == null) return;

            // إذا كنت أنا من طالب → لا تفعل شيئًا
            if (claimedBy.CashierId == _myCashierId) return;

            // شخص آخر سبقك → أغلق النافذة
            _notificationManager.CloseByTransactionId(transactionId);

            var name = claimedBy.DisplayName ?? claimedBy.Username ?? $"#{claimedBy.CashierId}";
            ShowBalloon("تم استلام العملية", $"سبقك: {name}");
        });
    }

    // Phase 6B: عند unassign → أخبر الكاشير
    private void OnTransactionUnassigned(string transactionId)
    {
        Current.Dispatcher.Invoke(() =>
        {
            if (_notificationManager != null)
            {
                _notificationManager.CloseByTransactionId(transactionId);
            }
            ShowBalloon("تم إلغاء الملكية", "أعاد المدير العملية إلى قائمة الجديدة");
        });
    }

    private void OnConnectionChanged(bool connected)
    {
        Current.Dispatcher.Invoke(async () =>
        {
            if (_trayIcon != null)
            {
                _trayIcon.Text = connected
                    ? "PaymentMonitor Cashier — متصل"
                    : "PaymentMonitor Cashier — غير متصل";
            }

            // إعادة إرسال auth تلقائيًا عند الاتصال
            if (connected && !string.IsNullOrEmpty(_authToken))
            {
                try
                {
                    await Task.Delay(500);
                    await TrySendAuthAsync();
                    OnLog("auth re-sent after reconnect");
                }
                catch (Exception ex)
                {
                    OnLog("auth re-send failed: " + ex.Message);
                }
            }
        });
    }

    private static readonly string LogPath =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PaymentMonitor.Cashier", "cashier-log.txt");

    private void OnLog(string message)
    {
        System.Diagnostics.Debug.WriteLine($"[Cashier] {message}");
        try
        {
            var line = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}";
            File.AppendAllText(LogPath, line + Environment.NewLine);
        }
        catch { }
    }

    private void ShowBalloon(string title, string text)
    {
        try
        {
            _trayIcon?.ShowBalloonTip(8000, title, text, ToolTipIcon.Info);
        }
        catch { }
    }


    private async Task EndSessionAsync()
    {
        try
        {
            if (_api != null) await _api.EndSessionAsync();
            _notificationManager?.CloseAll();
            System.Windows.MessageBox.Show("تم إنهاء الجلسة", "PaymentMonitor",
                MessageBoxButton.OK, MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            System.Windows.MessageBox.Show($"خطأ: {ex.Message}", "خطأ",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private async Task LogoutAsync()
    {
        try
        {
            if (_api != null) await _api.LogoutAsync();
            _authToken = ""; _myCashierId = 0; _myCashierName = "";
            _api = null; _notificationManager = null;
            _settings.SavedAuthToken = null;
            _settings.SavedCashierId = 0;
            _settings.SavedCashierName = null;
            SettingsService.Save(_settings);
            OnLog("auth cleared on logout");
            RefreshTrayMenu();
            System.Windows.MessageBox.Show("تم تسجيل الخروج", "PaymentMonitor",
                MessageBoxButton.OK, MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            System.Windows.MessageBox.Show($"خطأ: {ex.Message}", "خطأ",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void ExitApp()
    {
        try
        {
            _notificationManager?.CloseAll();
            _wsClient?.Dispose();
            _trayIcon!.Visible = false;
            _trayIcon.Dispose();
        }
        catch { }

        Shutdown();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _notificationManager?.CloseAll();
        _trayIcon?.Dispose();
        _wsClient?.Dispose();
        base.OnExit(e);
    }
}
