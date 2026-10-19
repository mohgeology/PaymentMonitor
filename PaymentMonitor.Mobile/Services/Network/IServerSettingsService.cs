namespace PaymentMonitor.Mobile.Services.Network;

public interface IServerSettingsService
{
    Task<ServerSettings> GetAsync();

    Task SaveAsync(string serverUrl, string apiKey);

    Task<bool> TestConnectionAsync();
}

public record ServerSettings(
    string ServerUrl,
    string ApiKey,
    string ApiPath = "/api/transactions",
    string HealthPath = "/ping")
{
    public string GetBaseUrl()
    {
        return (ServerUrl ?? string.Empty).TrimEnd('/');
    }
}

