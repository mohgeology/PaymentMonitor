using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Collections.ObjectModel;
using System.Windows.Input;
using Microsoft.Maui.Controls;
using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.ViewModels;

// Minimal ViewModel for the main dashboard UI.
// Contains only simple, static properties for UI binding.
public class MainViewModel : INotifyPropertyChanged
{
    public MainViewModel()
    {
        // subscribe to SMS receive events
        PaymentMonitor.Mobile.Services.SmsReceiveHelper.SmsReceived += info =>
        {
            LatestSmsSender = info.Sender;
            LatestSmsBody = info.Body;
            try
            {
                if (info.TimestampMillis > 0)
                    LatestSmsTime = DateTimeOffset.FromUnixTimeMilliseconds(info.TimestampMillis).ToLocalTime().ToString("g");
                else
                    LatestSmsTime = DateTimeOffset.Now.ToString("g");
            }
            catch
            {
                LatestSmsTime = DateTimeOffset.Now.ToString("g");
            }
            LatestMessage = LatestSmsBody;

            // Parse incoming SMS using parser layer
            try
            {
                var parseResult = PaymentMonitor.Mobile.Parsers.SmsParserFactory.Default.Parse(info.Body, info.Sender);
                LatestOperation = FormatOperationResult(parseResult);
                if (parseResult.IsParsed)
                {
                    OverallStatus = $"دفعة: {parseResult.WalletName}";
                    SmsGatewayStatus = "نشطة";
                }
                else
                {
                    OverallStatus = "رسالة غير معروفة";
                }
            }
            catch
            {
                LatestOperation = "خطأ أثناء معالجة الرسالة";
            }
        };

        ScanHistoricalSmsCommand = new Command(async () => await ScanHistoricalSmsAsync(), () => !IsScanning);
}

    public static string FormatOperationResult(PaymentMonitor.Mobile.Parsers.SmsParserResult result)
    {
        if (!result.IsParsed)
        {
            return "الحالة: غير معروف\nالرسالة المستلمة ليست عملية محفظة إلكترونية معتمدة.";
        }

        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"المحفظة: {result.WalletName}");
        sb.AppendLine($"العملية: {result.TransactionType}");

        // Format amount: preserve 2 decimal places if present in original parsed decimal
        bool hasDecimals = ((decimal.GetBits(result.Amount)[3] >> 16) & 0x7F) > 0;
        sb.AppendLine($"المبلغ: {(hasDecimals ? result.Amount.ToString("N2") : result.Amount.ToString("N0"))} ر.ي");

        if (!string.IsNullOrWhiteSpace(result.SenderName))
            sb.AppendLine($"المرسل: {result.SenderName}");

        if (!string.IsNullOrWhiteSpace(result.SenderPhone))
            sb.AppendLine($"رقم المرسل: {result.SenderPhone}");

        if (!string.IsNullOrWhiteSpace(result.AccountNumber))
            sb.AppendLine($"رقم الحساب: {result.AccountNumber}");

        if (result.Balance.HasValue)
        {
            bool balHasDecimals = ((decimal.GetBits(result.Balance.Value)[3] >> 16) & 0x7F) > 0;
            sb.Append($"الرصيد: {(balHasDecimals ? result.Balance.Value.ToString("N2") : result.Balance.Value.ToString("N0"))} ر.ي");
        }

        return sb.ToString().TrimEnd();
    }

    private string _statusText = "Ready";
    private string _serverStatus = "غير متصل";
    private string _smsGatewayStatus = "جاهزة";
    private string _syncStatus = "في انتظار الاتصال";
    private string _latestMessage = "لا توجد رسائل مستلمة حتى الآن";
    private string _deviceInfo = "هذا التطبيق يعمل كبوابة SMS";
    private string _overallStatus = "جاهزة";
    private string _latestOperation = "لا توجد عمليات حتى الآن";
    private string _contactIp = "غير متاح";
    private string _contactServer = "غير متصل";
    private string _battery = "--";
    private string _charger = "غير معروف";
    private string _latestSmsSender = string.Empty;
    private string _latestSmsBody = string.Empty;
    private string _latestSmsTime = string.Empty;
    private string _smsPermissionStatus = "غير معروف";
    private int _pendingCount = 0;

    public string AppTitle => "PaymentMonitor";
    public string Subtitle => "بوابة استقبال المدفوعات";

    public string StatusText
    {
        get => _statusText;
        set => SetProperty(ref _statusText, value);
    }

    public string ServerStatus
    {
        get => _serverStatus;
        set
        {
            if (SetProperty(ref _serverStatus, value))
            {
                OnPropertyChanged(nameof(ServerStatusColor));
            }
        }
    }

    public string SmsGatewayStatus
    {
        get => _smsGatewayStatus;
        set
        {
            if (SetProperty(ref _smsGatewayStatus, value))
            {
                OnPropertyChanged(nameof(SmsGatewayColor));
            }
        }
    }

    public string SyncStatus
    {
        get => _syncStatus;
        set
        {
            if (SetProperty(ref _syncStatus, value))
            {
                OnPropertyChanged(nameof(SyncStatusColor));
            }
        }
    }

    public string LatestMessage
    {
        get => _latestMessage;
        set => SetProperty(ref _latestMessage, value);
    }

    public string DeviceInfo
    {
        get => _deviceInfo;
        set => SetProperty(ref _deviceInfo, value);
    }

    public string OverallStatus
    {
        get => _overallStatus;
        set => SetProperty(ref _overallStatus, value);
    }

    public string LatestOperation
    {
        get => _latestOperation;
        set => SetProperty(ref _latestOperation, value);
    }

    public string ContactIp
    {
        get => _contactIp;
        set => SetProperty(ref _contactIp, value);
    }

    public string ContactServer
    {
        get => _contactServer;
        set => SetProperty(ref _contactServer, value);
    }

    public string Battery
    {
        get => _battery;
        set => SetProperty(ref _battery, value);
    }

    public string Charger
    {
        get => _charger;
        set => SetProperty(ref _charger, value);
    }

    public string LatestSmsSender
    {
        get => _latestSmsSender;
        set => SetProperty(ref _latestSmsSender, value);
    }

    public string LatestSmsBody
    {
        get => _latestSmsBody;
        set => SetProperty(ref _latestSmsBody, value);
    }

    public string LatestSmsTime
    {
        get => _latestSmsTime;
        set => SetProperty(ref _latestSmsTime, value);
    }

    public string SmsPermissionStatus
    {
        get => _smsPermissionStatus;
        set => SetProperty(ref _smsPermissionStatus, value);
    }

    public int PendingCount
    {
        get => _pendingCount;
        set
        {
            if (SetProperty(ref _pendingCount, value))
            {
                OnPropertyChanged(nameof(PendingCountDisplay));
                OnPropertyChanged(nameof(SyncStatusColor));
            }
        }
    }

    public string PendingCountDisplay => $"متبقٍ للمزامنة: {_pendingCount}";

    // Dynamic status colors (MAUI accepts Color or hex string)
    public string SmsGatewayColor => SmsGatewayStatus == "نشطة" || SmsGatewayStatus == "جاهزة"
        ? "#4CAF50"
        : "#9E9E9E";

    public string ServerStatusColor => ServerStatus == "متصل"
        ? "#4CAF50"
        : "#F44336";

    public string SyncStatusColor => SyncStatus.StartsWith("المزامنة ناجحة")
        ? "#4CAF50"
        : (PendingCount > 0 ? "#FFC107" : "#9E9E9E");

    // --- Historical SMS Scanning Properties ---
    public ObservableCollection<string> TimeRangeOptions { get; } = new()
    {
        "رسائل اليوم",
        "آخر ساعة",
        "آخر 6 ساعات",
        "آخر 24 ساعة",
        "تحديد الفترة"
    };

    private string _selectedTimeRange = "رسائل اليوم";
    public string SelectedTimeRange
    {
        get => _selectedTimeRange;
        set
        {
            if (SetProperty(ref _selectedTimeRange, value))
            {
                IsCustomRangeSelected = value == "تحديد الفترة";
            }
        }
    }

    private bool _isCustomRangeSelected;
    public bool IsCustomRangeSelected
    {
        get => _isCustomRangeSelected;
        set => SetProperty(ref _isCustomRangeSelected, value);
    }

    private DateTime _customStartDate = DateTime.Today;
    public DateTime CustomStartDate
    {
        get => _customStartDate;
        set => SetProperty(ref _customStartDate, value);
    }

    private TimeSpan _customStartTime = TimeSpan.Zero;
    public TimeSpan CustomStartTime
    {
        get => _customStartTime;
        set => SetProperty(ref _customStartTime, value);
    }

    private DateTime _customEndDate = DateTime.Today;
    public DateTime CustomEndDate
    {
        get => _customEndDate;
        set => SetProperty(ref _customEndDate, value);
    }

    private TimeSpan _customEndTime = DateTime.Now.TimeOfDay;
    public TimeSpan CustomEndTime
    {
        get => _customEndTime;
        set => SetProperty(ref _customEndTime, value);
    }

    private bool _isScanning;
    public bool IsScanning
    {
        get => _isScanning;
        set
        {
            if (SetProperty(ref _isScanning, value))
            {
                (ScanHistoricalSmsCommand as Command)?.ChangeCanExecute();
            }
        }
    }

    private int _totalScannedCount;
    public int TotalScannedCount
    {
        get => _totalScannedCount;
        set => SetProperty(ref _totalScannedCount, value);
    }

    private int _recognizedCount;
    public int RecognizedCount
    {
        get => _recognizedCount;
        set => SetProperty(ref _recognizedCount, value);
    }

    private int _unrecognizedCount;
    public int UnrecognizedCount
    {
        get => _unrecognizedCount;
        set => SetProperty(ref _unrecognizedCount, value);
    }

    private bool _hasScanResults;
    public bool HasScanResults
    {
        get => _hasScanResults;
        set => SetProperty(ref _hasScanResults, value);
    }

    private string _scanStatusMessage = string.Empty;
    public string ScanStatusMessage
    {
        get => _scanStatusMessage;
        set => SetProperty(ref _scanStatusMessage, value);
    }

    public ObservableCollection<ScannedSmsItem> ScannedOperations { get; } = new();

    public ICommand ScanHistoricalSmsCommand { get; }
public async System.Threading.Tasks.Task ScanHistoricalSmsAsync()
    {
        if (IsScanning) return;
        IsScanning = true;
        ScanStatusMessage = "جاري التحقق من الصلاحيات...";

        try
        {
            var services = Microsoft.Maui.IPlatformApplication.Current?.Services
                ?? Microsoft.Maui.Controls.Application.Current?.Handler?.MauiContext?.Services;
            var permissionService = services?.GetService(typeof(PaymentMonitor.Mobile.Services.ISmsPermissionService))
                as PaymentMonitor.Mobile.Services.ISmsPermissionService;
            var readerService = services?.GetService(typeof(PaymentMonitor.Mobile.Services.ISmsReaderService))
                as PaymentMonitor.Mobile.Services.ISmsReaderService;

            if (permissionService == null || readerService == null)
            {
                ScanStatusMessage = "خدمة قراءة الرسائل غير متوفرة على هذا الجهاز.";
                return;
            }

            // Verify READ_SMS permission
            if (!permissionService.IsReadSmsGranted())
            {
                ScanStatusMessage = "جاري طلب صلاحية قراءة الرسائل (READ_SMS)...";
                bool granted = await permissionService.RequestReadSmsPermissionAsync();
                if (!granted)
                {
                    ScanStatusMessage = "تم رفض صلاحية قراءة الرسائل (READ_SMS). يرجى منحها للمتابعة.";
                    return;
                }
            }

            // Determine time boundaries using local device time
            DateTime startLocal;
            DateTime endLocal;
            var now = DateTime.Now;

            switch (SelectedTimeRange)
            {
                case "رسائل اليوم":
                    startLocal = now.Date; // 00:00:00 today local time
                    endLocal = now;
                    break;
                case "آخر ساعة":
                    startLocal = now.AddHours(-1);
                    endLocal = now;
                    break;
                case "آخر 6 ساعات":
                    startLocal = now.AddHours(-6);
                    endLocal = now;
                    break;
                case "آخر 24 ساعة":
                    startLocal = now.AddHours(-24);
                    endLocal = now;
                    break;
                case "تحديد الفترة":
                    startLocal = CustomStartDate.Date + CustomStartTime;
                    endLocal = CustomEndDate.Date + CustomEndTime;
                    if (startLocal > endLocal)
                    {
                        (startLocal, endLocal) = (endLocal, startLocal);
                    }
                    break;
                default:
                    startLocal = now.Date;
                    endLocal = now;
                    break;
            }

            long startMillis = new DateTimeOffset(startLocal).ToUnixTimeMilliseconds();
            long endMillis = new DateTimeOffset(endLocal).ToUnixTimeMilliseconds();

            ScanStatusMessage = $"جاري البحث في الرسائل من {startLocal:yyyy/MM/dd hh:mm tt} إلى {endLocal:yyyy/MM/dd hh:mm tt}...";

            var rawMessages = await readerService.GetMessagesAsync(startMillis, endMillis);

            TotalScannedCount = rawMessages.Count;
            var recognized = new System.Collections.Generic.List<ScannedSmsItem>();

            foreach (var msg in rawMessages)
            {
                var parseResult = PaymentMonitor.Mobile.Parsers.SmsParserFactory.Default.Parse(msg.Body, msg.Address);
                if (parseResult.IsParsed)
                {
                    bool hasDecimals = ((decimal.GetBits(parseResult.Amount)[3] >> 16) & 0x7F) > 0;
                    string amtStr = (hasDecimals ? parseResult.Amount.ToString("N2") : parseResult.Amount.ToString("N0")) + " ر.ي";

                    string? balStr = null;
                    if (parseResult.Balance.HasValue)
                    {
                        bool balHasDecimals = ((decimal.GetBits(parseResult.Balance.Value)[3] >> 16) & 0x7F) > 0;
                        balStr = (balHasDecimals ? parseResult.Balance.Value.ToString("N2") : parseResult.Balance.Value.ToString("N0")) + " ر.ي";
                    }

                    var msgTime = DateTimeOffset.FromUnixTimeMilliseconds(msg.DateMillis).ToLocalTime();

                    recognized.Add(new ScannedSmsItem
                    {
                        WalletName = parseResult.WalletName,
                        TransactionType = parseResult.TransactionType,
                        Amount = parseResult.Amount,
                        FormattedAmount = amtStr,
                        SenderName = parseResult.SenderName,
                        SenderPhone = parseResult.SenderPhone,
                        AccountNumber = parseResult.AccountNumber,
                        Balance = parseResult.Balance,
                        FormattedBalance = balStr,
                        MessageTime = msgTime.DateTime,
                        FormattedTime = msgTime.ToString("yyyy/MM/dd hh:mm tt"),
                        OriginalMessage = msg.Body
                    });
                }
            }

            RecognizedCount = recognized.Count;
            UnrecognizedCount = TotalScannedCount - RecognizedCount;

            ScannedOperations.Clear();
            foreach (var item in System.Linq.Enumerable.OrderByDescending(recognized, x => x.MessageTime))
            {
                ScannedOperations.Add(item);
            }

            HasScanResults = true;
            if (TotalScannedCount == 0)
            {
                ScanStatusMessage = "اكتمل الفحص: لا توجد أي رسائل SMS في النطاق الزمني المحدد.";
            }
            else
            {
                ScanStatusMessage = $"اكتمل الفحص: تم فحص {TotalScannedCount} رسالة، والتعرف على {RecognizedCount} عملية محفظة.";
            }
        }
        catch (Exception ex)
        {
            ScanStatusMessage = $"حدث خطأ أثناء الفحص: {ex.Message}";
        }
        finally
        {
            IsScanning = false;
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    protected void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    protected bool SetProperty<T>(ref T backingField, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(backingField, value))
            return false;
        backingField = value;
        OnPropertyChanged(propertyName);
        return true;
    }
}








