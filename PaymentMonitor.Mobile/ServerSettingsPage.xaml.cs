using PaymentMonitor.Mobile.Services.Network;

namespace PaymentMonitor.Mobile;

public partial class ServerSettingsPage : ContentPage
{
    private readonly IServerSettingsService _settingsService;

    public ServerSettingsPage(IServerSettingsService settingsService)
    {
        InitializeComponent();
        _settingsService = settingsService;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();

        var settings = await _settingsService.GetAsync();

        ServerUrlEntry.Text = settings.ServerUrl;
        ApiKeyEntry.Text = settings.ApiKey;

        StatusLabel.Text = string.Empty;
    }

    private async void OnSaveClicked(object? sender, EventArgs e)
    {
        var url = ServerUrlEntry.Text?.Trim() ?? string.Empty;
        var apiKey = ApiKeyEntry.Text?.Trim() ?? string.Empty;

        if (string.IsNullOrWhiteSpace(url))
        {
            StatusLabel.Text = "⚠ الرجاء إدخال عنوان السيرفر.";
            return;
        }

        if (!Uri.TryCreate(url, UriKind.Absolute, out _))
        {
            StatusLabel.Text = "⚠ عنوان السيرفر غير صالح.";
            return;
        }

        await _settingsService.SaveAsync(url, apiKey);

        StatusLabel.Text = "✅ تم حفظ الإعدادات.";
    }

    private async void OnTestClicked(object? sender, EventArgs e)
    {
        StatusLabel.Text = "⏳ جارٍ اختبار الاتصال...";

        var ok = await _settingsService.TestConnectionAsync();

        StatusLabel.Text = ok
            ? "✅ الاتصال بالسيرفر ناجح."
            : "❌ فشل الاتصال بالسيرفر.";
    }
}

