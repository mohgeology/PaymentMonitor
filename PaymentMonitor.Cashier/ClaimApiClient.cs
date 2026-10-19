using System.Net.Http;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PaymentMonitor.Cashier;

public class ClaimApiClient
{
    private readonly HttpClient _http;
    private string _serverUrl;
    private string _token;

    public ClaimApiClient(string serverUrl, string token)
    {
        _serverUrl = serverUrl.TrimEnd('/');
        _token = token;
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        _http.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}");
    }

    public void UpdateToken(string token)
    {
        _token = token;
        _http.DefaultRequestHeaders.Remove("Authorization");
        _http.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}");
    }

    public async Task<ClaimResult> ClaimAsync(string transactionId)
    {
        try
        {
            var url = $"{_serverUrl}/api/transactions/{transactionId}/claim";
            var resp = await _http.PostAsync(url, null);
            var json = await resp.Content.ReadAsStringAsync();
            if (resp.IsSuccessStatusCode)
            {
                return new ClaimResult { Success = true, Message = "تم الاستلام" };
            }
            var detail = TryExtractDetail(json);
            return new ClaimResult { Success = false, Message = detail };
        }
        catch (Exception ex)
        {
            return new ClaimResult { Success = false, Message = ex.Message };
        }
    }

    public async Task<ClaimResult> DismissAsync(string transactionId)
    {
        try
        {
            var url = $"{_serverUrl}/api/transactions/{transactionId}/dismiss";
            var resp = await _http.PostAsync(url, null);
            if (resp.IsSuccessStatusCode)
                return new ClaimResult { Success = true, Message = "تم الرفض" };
            var json = await resp.Content.ReadAsStringAsync();
            return new ClaimResult { Success = false, Message = TryExtractDetail(json) };
        }
        catch (Exception ex)
        {
            return new ClaimResult { Success = false, Message = ex.Message };
        }
    }

    public async Task<LoginResult?> LoginAsync(string username, string password)
    {
        try
        {
            var url = $"{_serverUrl}/api/auth/login";
            var body = JsonSerializer.Serialize(new { username, password });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync(url, content);
            if (!resp.IsSuccessStatusCode) return null;
            var json = await resp.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<LoginResult>(json);
        }
        catch { return null; }
    }

    public async Task<ClaimResult> EndSessionAsync()
    {
        try
        {
            var url = $"{_serverUrl}/api/cashier/session/close";
            var resp = await _http.PostAsync(url, null);
            if (resp.IsSuccessStatusCode)
                return new ClaimResult { Success = true, Message = "تم إنهاء الجلسة" };
            var json = await resp.Content.ReadAsStringAsync();
            return new ClaimResult { Success = false, Message = TryExtractDetail(json) };
        }
        catch (Exception ex)
        {
            return new ClaimResult { Success = false, Message = ex.Message };
        }
    }

    public async Task<ClaimResult> LogoutAsync()
    {
        try
        {
            var url = $"{_serverUrl}/api/auth/logout";
            var resp = await _http.PostAsync(url, null);
            return new ClaimResult { Success = resp.IsSuccessStatusCode };
        }
        catch
        {
            return new ClaimResult { Success = false };
        }
    }

    public async Task<ClaimResult> OpenSessionAsync()
    {
        try
        {
            var url = $"{_serverUrl}/api/cashier/session/open";
            var body = JsonSerializer.Serialize(new { deviceId = Environment.MachineName });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync(url, content);
            if (resp.IsSuccessStatusCode)
                return new ClaimResult { Success = true, Message = "تم فتح الجلسة" };
            var json = await resp.Content.ReadAsStringAsync();
            return new ClaimResult { Success = false, Message = TryExtractDetail(json) };
        }
        catch (Exception ex)
        {
            return new ClaimResult { Success = false, Message = ex.Message };
        }
    }

    private static string TryExtractDetail(string json)
    {
        try
        {
            var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("detail", out var detail))
                return detail.GetString() ?? "خطأ غير معروف";
        }
        catch { }
        return "خطأ من السيرفر";
    }
}

public class ClaimResult
{
    public bool Success { get; set; }
    public string Message { get; set; } = "";
}

public class LoginResult
{
    [JsonPropertyName("success")]
    public bool Success { get; set; }

    [JsonPropertyName("token")]
    public string? Token { get; set; }

    [JsonPropertyName("cashier")]
    public CashierInfo? Cashier { get; set; }
}

public class CashierInfo
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("username")]
    public string? Username { get; set; }

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; set; }

    [JsonPropertyName("role")]
    public string? Role { get; set; }
}
