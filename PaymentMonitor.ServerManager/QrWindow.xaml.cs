using System.Net.Http;
using System.Windows;
using System.Windows.Media.Imaging;

namespace PaymentMonitor.ServerManager;

public partial class QrWindow : Window
{
    private readonly int _port;

    public QrWindow(int port)
    {
        InitializeComponent();
        _port = port;
        Loaded += async (s, e) => await LoadQrAsync();
    }

    private async Task LoadQrAsync()
    {
        StatusText.Text = "⏳ جارٍ التحميل...";
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            var url = $"http://localhost:{_port}/api/qr-code";
            var res = await http.GetAsync(url);

            if (!res.IsSuccessStatusCode)
            {
                StatusText.Text = $"❌ فشل الاتصال (HTTP {(int)res.StatusCode})";
                return;
            }

            var json = await res.Content.ReadAsStringAsync();

            // استخراج base64 يدويًا (بدون مكتبة JSON)
            var base64Key = "\"qr_base64\":\"";
            var startIdx = json.IndexOf(base64Key);
            if (startIdx < 0)
            {
                StatusText.Text = "❌ QR غير متوفر";
                return;
            }
            startIdx += base64Key.Length;
            var endIdx = json.IndexOf('"', startIdx);
            var base64 = json.Substring(startIdx, endIdx - startIdx);

            // إزالة البادئة data:image/png;base64,
            var commaIdx = base64.IndexOf(',');
            if (commaIdx >= 0)
                base64 = base64.Substring(commaIdx + 1);

            var bytes = Convert.FromBase64String(base64);
            var image = new BitmapImage();
            using (var ms = new System.IO.MemoryStream(bytes))
            {
                image.BeginInit();
                image.CacheOption = BitmapCacheOption.OnLoad;
                image.StreamSource = ms;
                image.EndInit();
            }
            QrImage.Source = image;

            // عنوان السيرفر
            var localIp = GetLocalIp();
            ServerUrlText.Text = $"http://{localIp}:{_port}";
            StatusText.Text = "✅ جاهز للمسح";
        }
        catch (Exception ex)
        {
            StatusText.Text = $"❌ فشل: {ex.Message}";
        }
    }

    private string GetLocalIp()
    {
        try
        {
            using var socket = new System.Net.Sockets.Socket(
                System.Net.Sockets.AddressFamily.InterNetwork,
                System.Net.Sockets.SocketType.Dgram,
                System.Net.Sockets.ProtocolType.Udp);
            socket.Connect("8.8.8.8", 80);
            return ((System.Net.IPEndPoint)socket.LocalEndPoint!).Address.ToString();
        }
        catch
        {
            return "127.0.0.1";
        }
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e)
    {
        await LoadQrAsync();
    }

    private void Close_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }
}
