using System;

namespace PaymentMonitor.Mobile.Parsers;

public class SmsParserResult
{
    public string WalletName { get; set; } = string.Empty;
    public string TransactionType { get; set; } = string.Empty;
    public decimal Amount { get; set; }
    public string Currency { get; set; } = string.Empty;
    public string? SenderName { get; set; }
    public string? SenderPhone { get; set; }
    public string? AccountNumber { get; set; }
    public string? ReferenceNumber { get; set; }
    public decimal? Balance { get; set; }
    public string OriginalMessage { get; set; } = string.Empty;
    public bool IsParsed { get; set; }
    public DateTime ParsedAt { get; set; } = DateTime.Now;

    public static SmsParserResult Failed(string originalMessage, string walletName = "")
    {
        return new SmsParserResult
        {
            WalletName = walletName,
            OriginalMessage = originalMessage,
            IsParsed = false,
            ParsedAt = DateTime.Now
        };
    }
}

