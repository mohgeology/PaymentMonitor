using Microsoft.Maui.Storage;

namespace PaymentMonitor.Mobile.Services.Network;

public class ServerSettingsService : IServerSettingsService
{
    private const string ServerUrlKey = "server_url";
    private const string ApiKeyKey = "server_api_key";

    private static readonly HttpClient HttpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(10)
    };

    public Task<ServerSettings> GetAsync()
    {
        var url = Preferences.Default.Get(ServerUrlKey, string.Empty);
        var apiKey = Preferences.Default.Get(ApiKeyKey, string.Empty);

        return Task.FromResult(new ServerSettings(url, apiKey));
    }

    public Task SaveAsync(string serverUrl, string apiKey)
    {
        Preferences.Default.Set(ServerUrlKey, serverUrl ?? string.Empty);
        Preferences.Default.Set(ApiKeyKey, apiKey ?? string.Empty);

        return Task.CompletedTask;
    }

    public async Task<bool> TestConnectionAsync()
    {
        var settings = await GetAsync();

        if (string.IsNullOrWhiteSpace(settings.ServerUrl))
            return false;

        try
        {
            var baseUrl = settings.ServerUrl.TrimEnd('/');
            var pingUrl = $"{baseUrl}/ping";

            using var request = new HttpRequestMessage(HttpMethod.Get, pingUrl);

            if (!string.IsNullOrWhiteSpace(settings.ApiKey))
                request.Headers.Add("X-Api-Key", settings.ApiKey);

            using var response = await HttpClient.SendAsync(request);

            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }
}
