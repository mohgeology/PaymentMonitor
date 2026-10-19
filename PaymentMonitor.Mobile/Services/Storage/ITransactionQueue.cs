using System.Text.Json;
using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.Services.Storage;

public interface ITransactionQueue
{
    Task EnqueueAsync(PaymentTransaction transaction);
    Task<List<PaymentTransaction>> GetPendingAsync();
    Task MarkSyncedAsync(string transactionId);
    Task MarkFailedAsync(string transactionId);
    Task<int> GetPendingCountAsync();
}
