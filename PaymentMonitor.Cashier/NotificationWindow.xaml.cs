using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace PaymentMonitor.Cashier;

public partial class NotificationWindow : Window
{
    private readonly Transaction _transaction;
    private readonly ClaimApiClient _api;
    private readonly DispatcherTimer _timer;
    private readonly int _durationSeconds;
    private readonly int _flashSeconds;
    private int _remaining;
    private bool _flashing = false;
    private readonly Action<NotificationWindow>? _onClosed;

    public NotificationWindow(Transaction tx, ClaimApiClient api,
                              int durationSeconds = 10,
                              int flashSeconds = 3,
                              Action<NotificationWindow>? onClosed = null)
    {
        InitializeComponent();
        _transaction = tx;
        _api = api;
        _durationSeconds = durationSeconds;
        _flashSeconds = flashSeconds;
        _onClosed = onClosed;
        _remaining = durationSeconds;

        PopulateData();

        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timer.Tick += Timer_Tick;
        _timer.Start();

        UpdatePosition();
    }

    private void PopulateData()
    {
        WalletText.Text = _transaction.WalletName ?? "—";
        TypeText.Text = _transaction.TransactionType ?? "—";
        AmountText.Text = $"{_transaction.Amount:N0} {_transaction.Currency}";
        SenderText.Text = string.IsNullOrEmpty(_transaction.SenderName) ? "—" : _transaction.SenderName;
        ReferenceText.Text = string.IsNullOrEmpty(_transaction.ReferenceNumber) ? "—" : _transaction.ReferenceNumber;
        TimerText.Text = _durationSeconds.ToString();
    }

    private void UpdatePosition()
    {
        var workArea = SystemParameters.WorkArea;
        const int margin = 20;

        // افتراضي: أسفل يمين
        Left = workArea.Right - Width - margin;
        Top = workArea.Bottom - Height - margin;
    }

    private void Timer_Tick(object? sender, EventArgs e)
    {
        _remaining--;
        TimerText.Text = _remaining.ToString();

        // Progress bar
        var percent = (double)_remaining / _durationSeconds;
        ProgressFill.Width = 380 * percent;

        // Flash في آخر N ثوانٍ
        if (_remaining <= _flashSeconds && _remaining > 0 && !_flashing)
        {
            _flashing = true;
            StartFlash();
        }

        if (_remaining <= 0)
        {
            _timer.Stop();
            Close();
        }
    }

    private void StartFlash()
    {
        var anim = new DoubleAnimation
        {
            From = 1.0,
            To = 0.4,
            Duration = TimeSpan.FromMilliseconds(400),
            AutoReverse = true,
            RepeatBehavior = RepeatBehavior.Forever
        };
        HeaderText.BeginAnimation(OpacityProperty, anim);
    }

    private async void ClaimButton_Click(object sender, RoutedEventArgs e)
    {
        _timer.Stop();
        ClaimButton.IsEnabled = false;
        DismissButton.IsEnabled = false;
        StatusText.Text = "جارٍ المطالبة...";
        StatusText.Foreground = new SolidColorBrush(System.Windows.Media.Color.FromRgb(0x66, 0x66, 0x66));

        var result = await _api.ClaimAsync(_transaction.Id);

        if (result.Success)
        {
            StatusText.Text = "✅ تم ربط العملية بك";
            StatusText.Foreground = new SolidColorBrush(System.Windows.Media.Color.FromRgb(0x2E, 0x7D, 0x32));
            await Task.Delay(700);
            Close();
        }
        else
        {
            StatusText.Text = $"❌ {result.Message}";
            StatusText.Foreground = new SolidColorBrush(System.Windows.Media.Color.FromRgb(0xC6, 0x28, 0x28));

            // إذا سبقك أحد، أغلق بعد 2 ثانية
            if (result.Message.Contains("Already claimed") || result.Message.Contains("already"))
            {
                await Task.Delay(2000);
                Close();
            }
            else
            {
                ClaimButton.IsEnabled = true;
                DismissButton.IsEnabled = true;
            }
        }
    }

    private async void DismissButton_Click(object sender, RoutedEventArgs e)
    {
        _timer.Stop();
        ClaimButton.IsEnabled = false;
        DismissButton.IsEnabled = false;

        await _api.DismissAsync(_transaction.Id);
        Close();
    }

    protected override void OnClosed(EventArgs e)
    {
        _timer?.Stop();
        _onClosed?.Invoke(this);
        base.OnClosed(e);
    }
}
