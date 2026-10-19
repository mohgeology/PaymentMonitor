using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Windows.Threading;

namespace PaymentMonitor.Cashier;

public class WebSocketClient : IDisposable
{
    private ClientWebSocket? _ws;
    private CancellationTokenSource? _cts;
    private Task? _receiveTask;
    private string _serverUrl = "";
    private bool _autoReconnect = true;
    private DispatcherTimer? _heartbeatTimer;
    private DateTime _lastMessageReceived = DateTime.UtcNow;
    private bool _isReconnecting = false;

    public event Action<Transaction>? OnTransactionReceived;
    public event Action<string, ClaimedByInfo>? OnTransactionClaimed;
    public event Action<string>? OnTransactionUnassigned;
    public event Action<bool>? OnConnectionChanged;
    public event Action<string>? OnLog;

    public bool IsConnected => _ws?.State == WebSocketState.Open;

    public async Task SendAuthAsync(string token)
    {
        if (_ws == null || _ws.State != WebSocketState.Open) return;
        try
        {
            var msg = $"auth:{token}";
            var bytes = Encoding.UTF8.GetBytes(msg);
            await _ws.SendAsync(new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text, true, CancellationToken.None);
        }
        catch (Exception ex)
        {
            OnLog?.Invoke($"فشل إرسال auth: {ex.Message}");
        }
    }

    public async Task ConnectAsync(string serverUrl)
    {
        _serverUrl = serverUrl;
        _autoReconnect = true;
        await DisconnectAsync();
        _autoReconnect = true;  // DisconnectAsync قد يُطفئها — نُعيد تفعيلها

        try
        {
            var wsUrl = serverUrl.TrimEnd('/')
                .Replace("http://", "ws://")
                .Replace("https://", "wss://") + "/ws";

            _ws = new ClientWebSocket();
            _cts = new CancellationTokenSource();

            await _ws.ConnectAsync(new Uri(wsUrl), _cts.Token);

            OnConnectionChanged?.Invoke(true);
            OnLog?.Invoke($"متصل بـ {wsUrl}");

            _receiveTask = Task.Run(() => ReceiveLoopAsync(_cts.Token));
            StartHeartbeat();
        }
        catch (Exception ex)
        {
            OnConnectionChanged?.Invoke(false);
            OnLog?.Invoke($"فشل الاتصال: {ex.Message}");
            throw;
        }
    }

    private void StartHeartbeat()
    {
        StopHeartbeat();
        _lastMessageReceived = DateTime.UtcNow;

        _heartbeatTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(5)
        };
        _heartbeatTimer.Tick += async (s, e) =>
        {
            if (!_autoReconnect) return;

            // إذا مضى أكثر من 10 ثوانٍ بدون رسالة → انقطاع
            var sinceLastMsg = (DateTime.UtcNow - _lastMessageReceived).TotalSeconds;
            if (sinceLastMsg > 10)
            {
                OnLog?.Invoke($"⚠ لا توجد رسائل منذ {sinceLastMsg:F0} ثانية — إعادة الاتصال");
                StopHeartbeat();
                OnConnectionChanged?.Invoke(false);
                await TryReconnectAsync();
                return;
            }

            // إرسال ping للحفاظ على الاتصال
            try
            {
                if (_ws != null && _ws.State == WebSocketState.Open)
                {
                    var ping = Encoding.UTF8.GetBytes("ping");
                    await _ws.SendAsync(new ArraySegment<byte>(ping),
                        WebSocketMessageType.Text, true, CancellationToken.None);
                    OnLog?.Invoke("→ heartbeat sent");
                }
                else
                {
                    OnLog?.Invoke("⚠ الاتصال غير مفتوح — محاولة إعادة اتصال");
                    StopHeartbeat();
                    OnConnectionChanged?.Invoke(false);
                    await TryReconnectAsync();
                }
            }
            catch (Exception ex)
            {
                OnLog?.Invoke($"⚠ heartbeat فشل: {ex.Message} — إعادة الاتصال");
                StopHeartbeat();
                OnConnectionChanged?.Invoke(false);
                await TryReconnectAsync();
            }
        };
        _heartbeatTimer.Start();
    }

    private void StopHeartbeat()
    {
        _heartbeatTimer?.Stop();
        _heartbeatTimer = null;
    }

    private async Task TryReconnectAsync()
    {
        if (!_autoReconnect || string.IsNullOrEmpty(_serverUrl)) return;
        if (_isReconnecting) return;
        _isReconnecting = true;

        try
        {
        for (int attempt = 1; attempt <= 60; attempt++)
        {
            if (!_autoReconnect) return;

            try { await Task.Delay(5000); } catch { return; }
            if (!_autoReconnect) return;

            OnLog?.Invoke($"↻ محاولة إعادة الاتصال #{attempt}...");

            try
            {
                var wsUrl = _serverUrl.TrimEnd('/')
                    .Replace("http://", "ws://")
                    .Replace("https://", "wss://") + "/ws";

                var newWs = new ClientWebSocket();
                var newCts = new CancellationTokenSource();

                await newWs.ConnectAsync(new Uri(wsUrl), newCts.Token);

                _ws?.Dispose();
                _cts?.Dispose();
                _ws = newWs;
                _cts = newCts;

                OnConnectionChanged?.Invoke(true);
                OnLog?.Invoke("✓ تم إعادة الاتصال بنجاح");

                _lastMessageReceived = DateTime.UtcNow;
                _receiveTask = Task.Run(() => ReceiveLoopAsync(_cts.Token));
                StartHeartbeat();
                return;
            }
            catch (Exception ex)
            {
                OnLog?.Invoke($"  ✗ فشل #{attempt}: {ex.Message}");
            }
        }

        OnLog?.Invoke("✗ فشلت كل محاولات إعادة الاتصال");
        }
        finally
        {
            _isReconnecting = false;
        }
    }

    public async Task DisconnectAsync()
    {
        _autoReconnect = false;
        StopHeartbeat();
        try
        {
            _cts?.Cancel();
            if (_ws != null && _ws.State == WebSocketState.Open)
            {
                await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None);
            }
        }
        catch { }

        _ws?.Dispose();
        _ws = null;
        _cts?.Dispose();
        _cts = null;

        OnConnectionChanged?.Invoke(false);
    }

    private async Task ReceiveLoopAsync(CancellationToken ct)
    {
        var buffer = new byte[8192];
        var sb = new StringBuilder();
        var localWs = _ws;  // نسخة محلية من الاتصال

        try
        {
            while (!ct.IsCancellationRequested && localWs != null && localWs.State == WebSocketState.Open)
            {
                var result = await localWs.ReceiveAsync(new ArraySegment<byte>(buffer), ct);

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    OnLog?.Invoke("السيرفر أغلق الاتصال");
                    break;
                }

                sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));

                if (result.EndOfMessage)
                {
                    var json = sb.ToString();
                    sb.Clear();
                    ProcessMessage(json);
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            OnLog?.Invoke($"خطأ في الاستقبال: {ex.Message}");
        }

        // إذا كان الاتصال الحالي قد تغيّر — لا تفعل شيئًا
        if (localWs != _ws)
        {
            OnLog?.Invoke("حلقة استقبال قديمة انتهت (تم استبدال الاتصال)");
            return;
        }

        OnConnectionChanged?.Invoke(false);

        // إعادة الاتصال التلقائي
        if (_autoReconnect && !ct.IsCancellationRequested && !string.IsNullOrEmpty(_serverUrl))
        {
            _ = Task.Run(() => TryReconnectAsync());
        }
    }


    private void ProcessMessage(string json)
    {
        _lastMessageReceived = DateTime.UtcNow;
        try
        {
            var msg = JsonSerializer.Deserialize<WsMessage>(json);
            if (msg == null) return;

            // Phase 6B: interactive notifications
            if ((msg.Type == "transaction.new" || msg.Type == "new_transaction") && msg.Transaction != null)
            {
                OnTransactionReceived?.Invoke(msg.Transaction);
            }
            else if (msg.Type == "transaction.claimed" && !string.IsNullOrEmpty(msg.TransactionId))
            {
                var claimedBy = msg.ClaimedBy ?? new ClaimedByInfo();
                OnTransactionClaimed?.Invoke(msg.TransactionId, claimedBy);
            }
            else if (msg.Type == "transaction.unassigned" && !string.IsNullOrEmpty(msg.TransactionId))
            {
                OnTransactionUnassigned?.Invoke(msg.TransactionId);
            }
            else if (msg.Type == "welcome")
            {
                OnLog?.Invoke("متصل بالسيرفر");
            }
        }
        catch (Exception ex)
        {
            OnLog?.Invoke($"فشل تحليل الرسالة: {ex.Message}");
        }
    }

    public void Dispose()
    {
        StopHeartbeat();
        _ = DisconnectAsync();
    }
}
