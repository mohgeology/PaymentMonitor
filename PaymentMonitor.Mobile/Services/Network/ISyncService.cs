using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.Services.Network;

public interface ISyncService
{
    Task<bool> SyncPendingTransactionsAsync(
        CancellationToken cancellationToken = default);

    Task<int> GetPendingCountAsync();
}
