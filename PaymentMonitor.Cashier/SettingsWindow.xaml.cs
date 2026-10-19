using System.Net.Http;
using System.Windows;

namespace PaymentMonitor.Cashier;

public partial class SettingsWindow : Window
{
    public string? SavedServerUrl { get; private set; }

    public SettingsWindow()
    {
        InitializeComponent();
        var settings = SettingsService.Load();
        ServerUrlBox.Text = string.IsNullOrEmpty(settings.ServerUrl)
            ? "http://192.168.1.70:5000"
            : settings.ServerUrl;
    }

    private async void TestBtn_Click(object sender, RoutedEventArgs e)
    {
        var url = ServerUrlBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(url))
        {
            StatusText.Text = "❌ الرجاء إدخال عنوان السيرفر";
            StatusText.Foreground = System.Windows.Media.Brushes.Red;
            return;
        }

        StatusText.Text = "⏳ جارٍ الاختبار...";
        StatusText.Foreground = System.Windows.Media.Brushes.Gray;

        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            var pingUrl = url.TrimEnd('/') + "/ping";
            var res = await http.GetAsync(pingUrl);

            if (res.IsSuccessStatusCode)
            {
                StatusText.Text = "✅ الاتصال بالسيرفر ناجح";
                StatusText.Foreground = System.Windows.Media.Brushes.Green;
            }
            else
            {
                StatusText.Text = $"❌ فشل: HTTP {(int)res.StatusCode}";
                StatusText.Foreground = System.Windows.Media.Brushes.Red;
            }
        }
        catch (Exception ex)
        {
            StatusText.Text = $"❌ فشل: {ex.Message}";
            StatusText.Foreground = System.Windows.Media.Brushes.Red;
        }
    }

    private void SaveBtn_Click(object sender, RoutedEventArgs e)
    {
        var url = ServerUrlBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(url))
        {
            StatusText.Text = "❌ الرجاء إدخال عنوان السيرفر";
            StatusText.Foreground = System.Windows.Media.Brushes.Red;
            return;
        }

        var settings = SettingsService.Load();
        settings.ServerUrl = url;
        SettingsService.Save(settings);

        SavedServerUrl = url;
        DialogResult = true;
        Close();
    }

    private void CloseBtn_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
