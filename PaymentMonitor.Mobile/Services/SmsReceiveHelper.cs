using System;

namespace PaymentMonitor.Mobile.Services
{
    public class SmsMessageInfo
    {
        public string Sender { get; set; } = string.Empty;
        public string Body { get; set; } = string.Empty;
        public long TimestampMillis { get; set; }
    }

    public static class SmsReceiveHelper
    {
        public static event Action<SmsMessageInfo>? SmsReceived;

        public static void RaiseSmsReceived(SmsMessageInfo info)
        {
            SmsReceived?.Invoke(info);
        }
    }
}
