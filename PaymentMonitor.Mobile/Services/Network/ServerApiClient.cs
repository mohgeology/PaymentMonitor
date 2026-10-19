using System.Net.Http.Json;
using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.Services.Network;

public class ServerApiClient : IServerApiClient
{
    private readonly HttpClient _httpClient;
    private readonly IServerSettingsService _settingsService;

    public ServerApiClient(
        HttpClient httpClient,
        IServerSettingsService settingsService)
    {
        _httpClient = httpClient;
        _settingsService = settingsService;
    }

    public async Task<bool> TestConnectionAsync(
        CancellationToken cancellationToken = default)
    {
        var settings = _settingsService.GetAsync().GetAwaiter().GetResult();

        var baseUrl = settings.GetBaseUrl();

        if (string.IsNullOrWhiteSpace(baseUrl))
            return false;

        var url = new Uri(
            new Uri(baseUrl),
            settings.HealthPath.TrimStart('/'));

        try
        {
            using var response = await _httpClient.GetAsync(
                url,
                cancellationToken);

            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public async Task<ServerTransactionResponse> SendTransactionAsync(
        PaymentTransaction transaction,
        CancellationToken cancellationToken = default)
    {
        if (transaction == null)
            throw new ArgumentNullException(nameof(transaction));

        var settings = _settingsService.GetAsync().GetAwaiter().GetResult();

        var baseUrl = settings.GetBaseUrl();

        if (string.IsNullOrWhiteSpace(baseUrl))
            throw new InvalidOperationException(
                "لم يتم إعداد عنوان السيرفر.");

        var url = new Uri(
            new Uri(baseUrl),
            settings.ApiPath.TrimStart('/'));

        var response = await _httpClient.PostAsJsonAsync(
            url,
            transaction,
            cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorText = await response.Content.ReadAsStringAsync(
                cancellationToken);

            throw new HttpRequestException(
                $"Server returned {(int)response.StatusCode} ({response.StatusCode}). {errorText}");
        }

        var result =
            await response.Content.ReadFromJsonAsync<ServerTransactionResponse>(
                cancellationToken: cancellationToken);

        if (result == null)
            throw new InvalidOperationException(
                "السيرفر أعاد استجابة فارغة أو غير صالحة.");

        return result;
    }
}


