using Android.App;
using Android.Content;
using Android.OS;
using Microsoft.Extensions.DependencyInjection;
using PaymentMonitor.Mobile.Services.Network;

namespace PaymentMonitor.Mobile.Platforms.Android;

[Service(
    Enabled = true,
    Exported = false,
    ForegroundServiceType = global::Android.Content.PM.ForegroundService.TypeDataSync)]
public class SyncForegroundService : Service
{
    private const string ChannelId = "paymentmonitor_sync";
    private const string ChannelName = "PaymentMonitor Service";
    private const int NotificationId = 1001;

    private Timer? _timer;
    private bool _isRunning;

    public override IBinder? OnBind(Intent? intent) => null;

    public override StartCommandResult OnStartCommand(Intent? intent, StartCommandFlags flags, int startId)
    {
        StartForegroundInternal();
        StartTimer();
        return StartCommandResult.Sticky;
    }

    public override void OnCreate()
    {
        base.OnCreate();
        CreateNotificationChannel();
    }

    public override void OnDestroy()
    {
        StopTimer();
        base.OnDestroy();
    }

    private void CreateNotificationChannel()
    {
        if (Build.VERSION.SdkInt >= BuildVersionCodes.O)
        {
            var channel = new NotificationChannel(
                ChannelId,
                ChannelName,
                NotificationImportance.Low)
            {
                Description = "PaymentMonitor Sync Service"
            };
            channel.SetShowBadge(false);

            var manager = (NotificationManager?)GetSystemService(NotificationService);
            manager?.CreateNotificationChannel(channel);
        }
    }

    private void StartForegroundInternal()
    {
        var notification = BuildNotification("متصل — جارٍ المزامنة التلقائية", "متبقٍ للمزامنة: ...");

        if (Build.VERSION.SdkInt >= BuildVersionCodes.Q)
        {
            StartForeground(
                NotificationId,
                notification,
                global::Android.Content.PM.ForegroundService.TypeDataSync);
        }
        else
        {
            StartForeground(NotificationId, notification);
        }
    }

    private Notification BuildNotification(string title, string content)
    {
        var intent = new Intent(this, typeof(MainActivity));
        intent.SetFlags(ActivityFlags.SingleTop | ActivityFlags.ClearTop);

        var pendingFlags = PendingIntentFlags.UpdateCurrent;
        if (Build.VERSION.SdkInt >= BuildVersionCodes.M)
            pendingFlags |= PendingIntentFlags.Immutable;

        var pendingIntent = PendingIntent.GetActivity(this, 0, intent, pendingFlags);

        var builder = new Notification.Builder(this, ChannelId)
            .SetContentTitle("PaymentMonitor")
            .SetContentText($"{title} | {content}")
            .SetSmallIcon(global::Android.Resource.Drawable.IcDialogInfo)
            .SetOngoing(true)
            .SetContentIntent(pendingIntent);

        if (Build.VERSION.SdkInt >= BuildVersionCodes.Lollipop)
            builder.SetCategory(Notification.CategoryService);

        return builder.Build();
    }

    private void UpdateNotification(string title, string content)
    {
        var notification = BuildNotification(title, content);
        var manager = (NotificationManager?)GetSystemService(NotificationService);
        manager?.Notify(NotificationId, notification);
    }

    private void StartTimer()
    {
        if (_isRunning) return;
        _isRunning = true;

        _timer = new Timer(async _ => await SyncOnceAsync(), null, TimeSpan.Zero, TimeSpan.FromSeconds(60));
    }

    private void StopTimer()
    {
        _isRunning = false;
        _timer?.Dispose();
        _timer = null;
    }

    private async Task SyncOnceAsync()
    {
        try
        {
            var services = Microsoft.Maui.IPlatformApplication.Current?.Services;
            if (services == null) return;

            var syncService = services.GetService<ISyncService>();
            if (syncService == null) return;

            await syncService.SyncPendingTransactionsAsync();
            var pending = await syncService.GetPendingCountAsync();

            var status = pending == 0 ? "متصل — لا توجد عمليات معلقة" : $"متصل — متبقٍ: {pending}";
            UpdateNotification(status, $"آخر مزامنة: {DateTime.Now:HH:mm:ss}");
        }
        catch
        {
            UpdateNotification("غير متصل بالسيرفر", $"محاولة أخيرة: {DateTime.Now:HH:mm:ss}");
        }
    }
}