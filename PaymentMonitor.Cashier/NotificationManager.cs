using System.Collections.Concurrent;

namespace PaymentMonitor.Cashier;

public class NotificationManager
{
    private readonly ConcurrentDictionary<string, NotificationWindow> _activeWindows = new();
    private readonly AppSettings _settings;
    private readonly ClaimApiClient _api;

    public NotificationManager(AppSettings settings, ClaimApiClient api)
    {
        _settings = settings;
        _api = api;
    }

    public void Show(Transaction tx)
    {
        if (string.IsNullOrEmpty(tx.Id)) return;

        // إذا كانت النافذة معروضة بالفعل لهذه المعاملة → تجاهل
        if (_activeWindows.ContainsKey(tx.Id)) return;

        var wnd = new NotificationWindow(
            tx,
            _api,
            _settings.NotificationDurationSeconds,
            _settings.NotificationFlashSeconds,
            (w) => _activeWindows.TryRemove(tx.Id, out _)
        );

        _activeWindows[tx.Id] = wnd;
        wnd.Show();
    }

    public void CloseByTransactionId(string transactionId, string? reason = null)
    {
        if (_activeWindows.TryRemove(transactionId, out var wnd))
        {
            try
            {
                wnd.Dispatcher.Invoke(() => wnd.Close());
            }
            catch { }
        }
    }

    public void CloseAll()
    {
        foreach (var kvp in _activeWindows.ToArray())
        {
            try { kvp.Value.Dispatcher.Invoke(() => kvp.Value.Close()); } catch { }
        }
        _activeWindows.Clear();
    }
}
