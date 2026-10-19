namespace PaymentMonitor.Cashier;

public class AppSettings
{
    public string ServerUrl { get; set; } = "";
    public bool AutoConnect { get; set; } = true;
    public bool PlaySound { get; set; } = true;
    public bool ShowBalloon { get; set; } = true;

    // Phase 6B
    public int NotificationDurationSeconds { get; set; } = 10;
    public int NotificationFlashSeconds { get; set; } = 3;
    public string NotificationPosition { get; set; } = "BottomRight"; // BottomRight | BottomLeft | TopRight | TopLeft | Center
    public bool EnableInteractiveNotification { get; set; } = true;

    // Auto-Login
    public string? SavedAuthToken { get; set; } = null;
    public int SavedCashierId { get; set; } = 0;
    public string? SavedCashierName { get; set; } = null;
    public string? SavedServerUrlForToken { get; set; } = null;
}
