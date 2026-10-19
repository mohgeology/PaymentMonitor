using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.OS;
using AndroidX.Core.App;
using PaymentMonitor.Mobile.Platforms.Android;

namespace PaymentMonitor.Mobile;

[Activity(Theme = "@style/Maui.SplashTheme", MainLauncher = true, LaunchMode = LaunchMode.SingleTop, ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
public class MainActivity : MauiAppCompatActivity
{
    public static MainActivity? CurrentActivity { get; private set; }

    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        CurrentActivity = this;

        RequestNotificationPermission();
        StartSyncService();
    }

    private void RequestNotificationPermission()
    {
        if (OperatingSystem.IsAndroidVersionAtLeast(33))
        {
            if (CheckSelfPermission("android.permission.POST_NOTIFICATIONS") != Permission.Granted)
            {
                RequestPermissions(new[] { "android.permission.POST_NOTIFICATIONS" }, 9001);
            }
        }
    }

    private void StartSyncService()
    {
        try
        {
            var intent = new Intent(this, typeof(SyncForegroundService));
            if (OperatingSystem.IsAndroidVersionAtLeast(26))
                StartForegroundService(intent);
            else
                StartService(intent);
        }
        catch
        {
            // ignore
        }
    }

    protected override void OnResume()
    {
        base.OnResume();
        CurrentActivity = this;
    }

    protected override void OnDestroy()
    {
        base.OnDestroy();
        if (CurrentActivity == this)
        {
            CurrentActivity = null;
        }
    }

    public override void OnRequestPermissionsResult(int requestCode, string[] permissions, Permission[] grantResults)
    {
        if (OperatingSystem.IsAndroidVersionAtLeast(23))
        {
            base.OnRequestPermissionsResult(requestCode, permissions, grantResults);
        }

        try
        {
            // Forward to SmsPermissionService handler
            PaymentMonitor.Mobile.Platforms.Android.SmsPermissionService.NotifyRequestPermissionsResult(requestCode, permissions, grantResults);
        }
        catch
        {
            // ignore
        }
    }
}
