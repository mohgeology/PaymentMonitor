using PaymentMonitor.Mobile.Services.Storage;

namespace PaymentMonitor.Mobile.Services.Network;

public class SyncService : ISyncService
{
    private readonly ITransactionQueue _queue;
    private readonly IServerApiClient _serverApiClient;

    public SyncService(
        ITransactionQueue queue,
        IServerApiClient serverApiClient)
    {
        _queue = queue;
        _serverApiClient = serverApiClient;
    }

    public async Task<bool> SyncPendingTransactionsAsync(
        CancellationToken cancellationToken = default)
    {
        var pendingTransactions = await _queue.GetPendingAsync();

        if (pendingTransactions.Count == 0)
            return true;

        var allSucceeded = true;

        foreach (var transaction in pendingTransactions)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                var result = await _serverApiClient.SendTransactionAsync(
                    transaction,
                    cancellationToken);

                if (result.Success || result.Duplicate)
                {
                    await _queue.MarkSyncedAsync(transaction.Id);
                }
                else
                {
                    await _queue.MarkFailedAsync(transaction.Id);
                    allSucceeded = false;
                }
            }
            catch
            {
                await _queue.MarkFailedAsync(transaction.Id);
                allSucceeded = false;
            }
        }

        return allSucceeded;
    }

    public Task<int> GetPendingCountAsync()
    {
        return _queue.GetPendingCountAsync();
    }
}
