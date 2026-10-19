namespace PaymentMonitor.Mobile.Services;

public class DeviceIdentityService : IDeviceIdentityService
{
    private const string DeviceIdKey = "payment_monitor_device_id";

    public string GetDeviceId()
    {
        var existingId = Preferences.Default.Get(DeviceIdKey, string.Empty);

        if (!string.IsNullOrWhiteSpace(existingId))
            return existingId;

        var newId = Guid.NewGuid().ToString("N");

        Preferences.Default.Set(DeviceIdKey, newId);

        return newId;
    }
}
