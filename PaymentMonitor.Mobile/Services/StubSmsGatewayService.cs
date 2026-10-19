namespace PaymentMonitor.Mobile.Services;

/// <summary>
/// Temporary stub of an SMS gateway service.
/// This class is intentionally simple and MUST NOT attempt to read SMS,
/// request permissions, access Android APIs, or perform network I/O.
/// It exists only as a placeholder and to allow DI wiring during early development.
/// </summary>
public class StubSmsGatewayService : ISmsGatewayService
{
    public string GetStatus()
    {
        return "StubSmsGatewayService: placeholder (no SMS or network access).";
    }
}
