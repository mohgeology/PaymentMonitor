using Android.Content;
using Android.Provider;
using Android.Telephony;
using PaymentMonitor.Mobile.Services;

namespace PaymentMonitor.Mobile.Platforms.Android;

[BroadcastReceiver(
    Enabled = true,
    Exported = true,
    Label = "PaymentMonitor SMS Receiver")]
[global::Android.App.IntentFilter(
    new[] { "android.provider.Telephony.SMS_RECEIVED" },
    Priority = (int)IntentFilterPriority.HighPriority)]
public class SmsReceiver : BroadcastReceiver
{
    public override void OnReceive(Context? context, Intent? intent)
    {
        if (intent?.Action != "android.provider.Telephony.SMS_RECEIVED")
            return;

        var messages = Telephony.Sms.Intents.GetMessagesFromIntent(intent);

        if (messages == null || messages.Length == 0)
            return;

        var sender = messages[0]?.OriginatingAddress ?? string.Empty;

        var body = string.Join(
            string.Empty,
            messages
                .Where(x => x != null)
                .Select(x => x?.MessageBody ?? string.Empty));

        var timestamp = messages[0]?.TimestampMillis ?? 0;

        var info = new SmsMessageInfo
        {
            Sender = sender,
            Body = body,
            TimestampMillis = timestamp
        };

        // Keep the existing UI/event notification.
        SmsReceiveHelper.RaiseSmsReceived(info);

        // Process and queue the transaction.
        var processor =
            Microsoft.Maui.IPlatformApplication.Current?
                .Services
                .GetService<ISmsTransactionProcessor>();

        if (processor == null)
            return;

        var pendingResult = GoAsync();

        _ = Task.Run(async () =>
        {
            try
            {
                await processor.ProcessAsync(info);
            }
            catch
            {
                // SMS reception must not crash because of processing errors.
            }
            finally
            {
                pendingResult?.Finish();
            }
        });
    }
}





