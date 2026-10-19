using System.Text.Json.Serialization;

namespace PaymentMonitor.Cashier;

public class Transaction
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("walletName")]
    public string WalletName { get; set; } = "";

    [JsonPropertyName("transactionType")]
    public string TransactionType { get; set; } = "";

    [JsonPropertyName("amount")]
    public decimal Amount { get; set; }

    [JsonPropertyName("currency")]
    public string Currency { get; set; } = "";

    [JsonPropertyName("senderName")]
    public string? SenderName { get; set; }

    [JsonPropertyName("senderPhone")]
    public string? SenderPhone { get; set; }

    [JsonPropertyName("accountNumber")]
    public string? AccountNumber { get; set; }

    [JsonPropertyName("referenceNumber")]
    public string? ReferenceNumber { get; set; }

    [JsonPropertyName("balance")]
    public decimal? Balance { get; set; }

    [JsonPropertyName("smsTime")]
    public string? SmsTime { get; set; }

    [JsonPropertyName("receivedAt")]
    public string? ReceivedAt { get; set; }

    // Phase 6B
    [JsonPropertyName("status")]
    public string? Status { get; set; }

    [JsonPropertyName("claimedByCashierId")]
    public int? ClaimedByCashierId { get; set; }

    [JsonPropertyName("claimedAt")]
    public string? ClaimedAt { get; set; }
}

public class WsMessage
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = "";

    [JsonPropertyName("transaction")]
    public Transaction? Transaction { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }

    // Phase 6B
    [JsonPropertyName("transactionId")]
    public string? TransactionId { get; set; }

    [JsonPropertyName("status")]
    public string? Status { get; set; }

    [JsonPropertyName("claimedBy")]
    public ClaimedByInfo? ClaimedBy { get; set; }

    [JsonPropertyName("notificationDuration")]
    public int? NotificationDuration { get; set; }

    [JsonPropertyName("flashDuration")]
    public int? FlashDuration { get; set; }

    [JsonPropertyName("reason")]
    public string? Reason { get; set; }

    [JsonPropertyName("previousCashierId")]
    public int? PreviousCashierId { get; set; }
}

public class ClaimedByInfo
{
    [JsonPropertyName("cashierId")]
    public int CashierId { get; set; }

    [JsonPropertyName("username")]
    public string? Username { get; set; }

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; set; }
}
