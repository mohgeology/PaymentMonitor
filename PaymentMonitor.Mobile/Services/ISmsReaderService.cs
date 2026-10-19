using System.Collections.Generic;
using System.Threading.Tasks;

namespace PaymentMonitor.Mobile.Services;

public class RawSmsMessage
{
    public string Address { get; set; } = string.Empty;
    public string Body { get; set; } = string.Empty;
    public long DateMillis { get; set; }
}

public interface ISmsReaderService
{
    Task<List<RawSmsMessage>> GetMessagesAsync(long startMillis, long endMillis);
}

