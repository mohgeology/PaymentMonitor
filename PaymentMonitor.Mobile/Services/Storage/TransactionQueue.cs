using System.Text.Json;
using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.Services.Storage;

public class TransactionQueue : ITransactionQueue
{
    private readonly SemaphoreSlim _lock = new(1, 1);

    private string QueueFilePath =>
        Path.Combine(FileSystem.AppDataDirectory, "payment_transactions.json");

    public async Task EnqueueAsync(PaymentTransaction transaction)
    {
        await _lock.WaitAsync();

        try
        {
            var transactions = await LoadAsync();

            var exists = transactions.Any(x =>
                string.Equals(x.Id, transaction.Id, StringComparison.OrdinalIgnoreCase));

            if (!exists)
            {
                transactions.Add(transaction);
                await SaveAsync(transactions);
            }
        }
        finally
        {
            _lock.Release();
        }
    }

    public async Task<List<PaymentTransaction>> GetPendingAsync()
    {
        await _lock.WaitAsync();

        try
        {
            var transactions = await LoadAsync();

            return transactions
                .Where(x => x.SyncStatus == "Pending" ||
                            x.SyncStatus == "Failed")
                .OrderBy(x => x.ReceivedAt)
                .ToList();
        }
        finally
        {
            _lock.Release();
        }
    }

    public async Task MarkSyncedAsync(string transactionId)
    {
        await UpdateStatusAsync(transactionId, "Synced", true);
    }

    public async Task MarkFailedAsync(string transactionId)
    {
        await _lock.WaitAsync();

        try
        {
            var transactions = await LoadAsync();

            var transaction = transactions.FirstOrDefault(x =>
                string.Equals(x.Id, transactionId, StringComparison.OrdinalIgnoreCase));

            if (transaction != null)
            {
                transaction.SyncStatus = "Failed";
                transaction.RetryCount++;
                await SaveAsync(transactions);
            }
        }
        finally
        {
            _lock.Release();
        }
    }

    public async Task<int> GetPendingCountAsync()
    {
        var transactions = await GetPendingAsync();
        return transactions.Count;
    }

    private async Task UpdateStatusAsync(
        string transactionId,
        string status,
        bool setSyncedDate)
    {
        await _lock.WaitAsync();

        try
        {
            var transactions = await LoadAsync();

            var transaction = transactions.FirstOrDefault(x =>
                string.Equals(x.Id, transactionId, StringComparison.OrdinalIgnoreCase));

            if (transaction != null)
            {
                transaction.SyncStatus = status;

                if (setSyncedDate)
                    transaction.SyncedAt = DateTime.UtcNow;

                await SaveAsync(transactions);
            }
        }
        finally
        {
            _lock.Release();
        }
    }

    private async Task<List<PaymentTransaction>> LoadAsync()
    {
        if (!File.Exists(QueueFilePath))
            return new List<PaymentTransaction>();

        try
        {
            var json = await File.ReadAllTextAsync(QueueFilePath);

            if (string.IsNullOrWhiteSpace(json))
                return new List<PaymentTransaction>();

            return JsonSerializer.Deserialize<List<PaymentTransaction>>(json)
                   ?? new List<PaymentTransaction>();
        }
        catch
        {
            return new List<PaymentTransaction>();
        }
    }

    private async Task SaveAsync(List<PaymentTransaction> transactions)
    {
        var options = new JsonSerializerOptions
        {
            WriteIndented = true
        };

        var json = JsonSerializer.Serialize(transactions, options);

        var directory = Path.GetDirectoryName(QueueFilePath);

        if (!string.IsNullOrWhiteSpace(directory))
            Directory.CreateDirectory(directory);

        await File.WriteAllTextAsync(QueueFilePath, json);
    }
}
