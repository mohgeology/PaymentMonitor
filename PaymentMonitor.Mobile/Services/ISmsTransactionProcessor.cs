using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.Services;

public interface ISmsTransactionProcessor
{
    Task<bool> ProcessAsync(SmsMessageInfo sms);
}
