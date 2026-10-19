namespace PaymentMonitor.Mobile.Services;

/// <summary>
/// Minimal interface representing an SMS gateway service.
/// This is a placeholder for future functionality and must not access
/// platform APIs, permissions, networking, or SMS at this stage.
/// </summary>
public interface ISmsGatewayService
{
    /// <summary>
    /// Returns a short status description for UI/debugging purposes.
    /// Implementations must be lightweight and side-effect free.
    /// </summary>
    string GetStatus();
}
