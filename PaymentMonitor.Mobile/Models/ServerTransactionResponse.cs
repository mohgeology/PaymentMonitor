namespace PaymentMonitor.Mobile.Models;

public class ServerTransactionResponse
{
    public bool Success { get; set; }
    public bool Duplicate { get; set; }
    public string? Message { get; set; }
    public string? TransactionId { get; set; }
}
