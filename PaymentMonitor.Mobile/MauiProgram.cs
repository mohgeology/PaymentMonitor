using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using PaymentMonitor.Mobile.ViewModels;
using PaymentMonitor.Mobile.Services;
using PaymentMonitor.Mobile.Services.Storage;
using PaymentMonitor.Mobile.Services.Network;
using PaymentMonitor.Mobile.Platforms.Android;
using PaymentMonitor.Mobile.Parsers;

namespace PaymentMonitor.Mobile;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();

        builder
            .UseMauiApp<App>()
            .ConfigureFonts(fonts =>
            {
                fonts.AddFont("OpenSans-Regular.ttf", "OpenSansRegular");
                fonts.AddFont("OpenSans-Semibold.ttf", "OpenSansSemibold");
            });

        builder.Services.AddSingleton<MainViewModel>();
        builder.Services.AddTransient<ServerSettingsPage>();
        builder.Services.AddSingleton<IDeviceIdentityService, DeviceIdentityService>();

        builder.Services.AddSingleton<ISmsGatewayService, StubSmsGatewayService>();
        builder.Services.AddSingleton<ISmsPermissionService, SmsPermissionService>();
        builder.Services.AddSingleton<SmsParserFactory>();
        builder.Services.AddSingleton<ISmsReaderService, SmsReaderService>();

        builder.Services.AddSingleton<ITransactionQueue, TransactionQueue>();
        builder.Services.AddSingleton<ISmsTransactionProcessor, SmsTransactionProcessor>();

        builder.Services.AddSingleton<IServerSettingsService, ServerSettingsService>();
        builder.Services.AddSingleton<ISyncService, SyncService>();

        builder.Services.AddHttpClient<IServerApiClient, ServerApiClient>(client =>
        {
            client.Timeout = TimeSpan.FromSeconds(30);
        });

#if DEBUG
        builder.Logging.AddDebug();
#endif

        return builder.Build();
    }
}








