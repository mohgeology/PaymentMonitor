namespace PaymentMonitor.Mobile.Models;

public class PaymentTransaction
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string DeviceId { get; set; } = string.Empty;

    public string WalletName { get; set; } = string.Empty;
    public string TransactionType { get; set; } = string.Empty;

    public decimal Amount { get; set; }
    public string Currency { get; set; } = string.Empty;

    public string? SenderName { get; set; }
    public string? SenderPhone { get; set; }
    public string? AccountNumber { get; set; }
    public string? ReferenceNumber { get; set; }

    public decimal? Balance { get; set; }

    public DateTime SmsTime { get; set; }
    public DateTime ReceivedAt { get; set; }

    public string OriginalMessage { get; set; } = string.Empty;

    public string SyncStatus { get; set; } = "Pending";
    public int RetryCount { get; set; }

    public DateTime? SyncedAt { get; set; }
}
