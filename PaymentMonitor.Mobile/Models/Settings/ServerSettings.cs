namespace PaymentMonitor.Mobile.Models.Settings;

public class ServerSettings
{
    public string ServerAddress { get; set; } = string.Empty;

    public int ServerPort { get; set; } = 8000;

    public string Protocol { get; set; } = "http";

    public string ApiPath { get; set; } = "api/transactions";

    public string HealthPath { get; set; } = "ping";

    public string GetBaseUrl()
    {
        var address = ServerAddress.Trim();

        if (string.IsNullOrWhiteSpace(address))
            return string.Empty;

        if (address.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
            address.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            return address.TrimEnd('/') + "/";
        }

        return $"{Protocol}://{address}:{ServerPort}/";
    }
}

