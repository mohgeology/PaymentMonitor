using System;
using System.Threading.Tasks;
using Microsoft.Maui.Controls;
using PaymentMonitor.Mobile.Services;
using PaymentMonitor.Mobile.Services.Network;
using PaymentMonitor.Mobile.ViewModels;

namespace PaymentMonitor.Mobile;

public partial class MainPage : ContentPage
{
    private IDispatcherTimer? _syncTimer;
	private bool _permissionRequestedOnce = false;

	public MainPage()
	{
		InitializeComponent();

		var services = GetServiceProvider();
		var vm = services?.GetService(typeof(MainViewModel)) as MainViewModel;
		BindingContext = vm ?? new MainViewModel();

		if (BindingContext is MainViewModel mvm)
		{
			var permissionService = services?.GetService(typeof(ISmsPermissionService)) as ISmsPermissionService;
			if (permissionService != null && permissionService.IsReceiveSmsGranted())
			{
				mvm.SmsPermissionStatus = "مفعلة";
			}
		}
	}

	protected override async void OnAppearing()
        {
                base.OnAppearing();

                if (BindingContext is not MainViewModel)
                {
                        var services = GetServiceProvider();
                        if (services?.GetService(typeof(MainViewModel)) is MainViewModel vm)
                        {
                                BindingContext = vm;
                        }
                }

                await CheckAndRequestSmsPermissionAsync();
                await RefreshStatusAsync();
                StartSyncTimer();
        }

        protected override void OnDisappearing()
        {
                base.OnDisappearing();
                StopSyncTimer();
        }

        private void StartSyncTimer()
        {
                if (_syncTimer != null)
                        return;

                _syncTimer = Dispatcher.CreateTimer();
                _syncTimer.Interval = TimeSpan.FromSeconds(60);
                _syncTimer.Tick += async (s, e) =>
                {
                        try
                        {
                                var services = GetServiceProvider();
                                var syncService = services?.GetService(typeof(ISyncService)) as ISyncService;
                                if (syncService != null)
                                {
                                        await syncService.SyncPendingTransactionsAsync();
                                        await RefreshStatusAsync();
                                }
                        }
                        catch
                        {
                                // تجاهل
                        }
                };
                _syncTimer.Start();
        }

        private void StopSyncTimer()
        {
                _syncTimer?.Stop();
                _syncTimer = null;
        }

        private async Task RefreshStatusAsync()
        {
                if (BindingContext is not MainViewModel vm)
                        return;

                var services = GetServiceProvider();
                var syncService = services?.GetService(typeof(ISyncService)) as ISyncService;
                var settingsService = services?.GetService(typeof(IServerSettingsService)) as IServerSettingsService;

                if (syncService == null)
                        return;

                // 1. عدد العمليات المعلقة
                try
                {
                        vm.PendingCount = await syncService.GetPendingCountAsync();
                }
                catch
                {
                        // تجاهل
                }

                // 2. حالة الخادم
                if (settingsService != null)
                {
                        try
                        {
                                var connected = await settingsService.TestConnectionAsync();
                                vm.ServerStatus = connected ? "متصل" : "غير متصل";
                        }
                        catch
                        {
                                vm.ServerStatus = "غير متصل";
                        }
                }

                // 3. حالة المزامنة
                if (vm.PendingCount == 0)
                {
                        vm.SyncStatus = "لا توجد عمليات معلقة";
                }
                else
                {
                        vm.SyncStatus = $"في انتظار الاتصال ({vm.PendingCount})";
                }
        }

	private async Task CheckAndRequestSmsPermissionAsync()
	{
		if (BindingContext is not MainViewModel vm)
			return;

		var services = GetServiceProvider();
		var permissionService = services?.GetService(typeof(ISmsPermissionService)) as ISmsPermissionService;
		if (permissionService == null)
			return;

		// 1. Check whether RECEIVE_SMS is already granted
		if (permissionService.IsReceiveSmsGranted())
		{
			vm.SmsPermissionStatus = "مفعلة";
			return;
		}

		// 2. If not granted, request once at startup; do not re-request repeatedly if user denied
		if (!_permissionRequestedOnce)
		{
			_permissionRequestedOnce = true;
			vm.SmsPermissionStatus = "جارٍ الطلب...";
			var granted = await permissionService.RequestReceiveSmsPermissionAsync();
			vm.SmsPermissionStatus = granted ? "مفعلة" : "غير مفعلة";
		}
		else
		{
			vm.SmsPermissionStatus = "غير مفعلة";
		}
	}
    private async void OnSyncClicked(object? sender, EventArgs e)
    {
        if (BindingContext is not MainViewModel vm)
            return;

        var services = GetServiceProvider();
        var syncService = services?.GetService(typeof(ISyncService)) as ISyncService;

        if (syncService == null)
        {
            await DisplayAlertAsync("خطأ", "خدمة المزامنة غير متوفرة.", "حسنًا");
            return;
        }

        vm.SyncStatus = "جارٍ المزامنة...";

        try
        {
            var success = await syncService.SyncPendingTransactionsAsync();

            vm.PendingCount = await syncService.GetPendingCountAsync();
            vm.ServerStatus = success ? "متصل" : "غير متصل";

            if (vm.PendingCount == 0)
            {
                vm.SyncStatus = "المزامنة ناجحة — لا توجد عمليات معلقة";
            }
            else
            {
                vm.SyncStatus = success
                    ? $"المزامنة ناجحة — متبقٍ: {vm.PendingCount}"
                    : $"فشل جزئي — متبقٍ: {vm.PendingCount}";
            }

            await DisplayAlertAsync("المزامنة", vm.SyncStatus, "حسنًا");

            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            vm.SyncStatus = "فشلت المزامنة";
            await DisplayAlertAsync("خطأ", ex.Message, "حسنًا");
        }
    }

    private async void OnServerSettingsClicked(object? sender, EventArgs e)
    {
        var services = GetServiceProvider();
        if (services?.GetService(typeof(ServerSettingsPage)) is ServerSettingsPage page)
        {
            await Navigation.PushAsync(page);
        }
    }

    private static IServiceProvider? GetServiceProvider()
	{
		return IPlatformApplication.Current?.Services
			?? Application.Current?.Handler?.MauiContext?.Services;
	}
}








