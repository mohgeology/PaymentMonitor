using PaymentMonitor.Mobile.Models;
using PaymentMonitor.Mobile.Parsers;
using PaymentMonitor.Mobile.Services.Network;
using PaymentMonitor.Mobile.Services.Storage;

namespace PaymentMonitor.Mobile.Services;

public class SmsTransactionProcessor : ISmsTransactionProcessor
{
    // الأسماء الرسمية للمحافظ المعتمدة (تطابق دقيق)
    private static readonly HashSet<string> AllowedSenders = new(StringComparer.OrdinalIgnoreCase)
    {
        "Jaib",
        "MFloos",
        "6464",
    };

    private readonly ITransactionQueue _queue;
    private readonly IDeviceIdentityService _deviceIdentityService;
    private readonly ISyncService _syncService;

    public SmsTransactionProcessor(
        ITransactionQueue queue,
        IDeviceIdentityService deviceIdentityService,
        ISyncService syncService)
    {
        _queue = queue;
        _deviceIdentityService = deviceIdentityService;
        _syncService = syncService;
    }

    public async Task<bool> ProcessAsync(SmsMessageInfo sms)
    {
        if (sms == null || string.IsNullOrWhiteSpace(sms.Body))
            return false;

        // فحص أمني: فقط المرسلين المعتمدين
        var sender = (sms.Sender ?? string.Empty).Trim();
        if (!AllowedSenders.Contains(sender))
            return false;

        var result = SmsParserFactory.Default.Parse(
            sms.Body,
            sms.Sender);

        if (!result.IsParsed)
            return false;

        var transaction = new PaymentTransaction
        {
            Id = CreateTransactionId(sms),
            DeviceId = _deviceIdentityService.GetDeviceId(),

            WalletName = result.WalletName,
            TransactionType = result.TransactionType,

            Amount = result.Amount,
            Currency = result.Currency,

            SenderName = result.SenderName,
            SenderPhone = result.SenderPhone,
            AccountNumber = result.AccountNumber,
            ReferenceNumber = result.ReferenceNumber,

            Balance = result.Balance,

            SmsTime = sms.TimestampMillis > 0
                ? DateTimeOffset
                    .FromUnixTimeMilliseconds(sms.TimestampMillis)
                    .LocalDateTime
                : DateTime.Now,

            ReceivedAt = DateTime.UtcNow,

            OriginalMessage = sms.Body,

            SyncStatus = "Pending",
            RetryCount = 0
        };

        await _queue.EnqueueAsync(transaction);

        // مزامنة تلقائية فورية (بدون انتظار)
        _ = Task.Run(async () =>
        {
            try
            {
                await _syncService.SyncPendingTransactionsAsync();
            }
            catch
            {
                // تجاهل — الطابور يحتفظ بالعملية
            }
        });

        return true;
    }

    private static string CreateTransactionId(SmsMessageInfo sms)
    {
        var raw =
            $"{sms.Sender}|{sms.TimestampMillis}|{sms.Body}";

        using var sha = System.Security.Cryptography.SHA256.Create();

        var bytes = System.Text.Encoding.UTF8.GetBytes(raw);
        var hash = sha.ComputeHash(bytes);

        return Convert.ToHexString(hash).ToLowerInvariant();
    }
}



