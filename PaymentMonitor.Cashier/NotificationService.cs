using System.Media;

namespace PaymentMonitor.Cashier;

public static class NotificationService
{
    public static void PlaySound()
    {
        try
        {
            SystemSounds.Exclamation.Play();
        }
        catch { }
    }

    public static string FormatAmount(decimal amount)
    {
        return amount.ToString("N0");
    }

    public static string BuildBalloonTitle()
    {
        return "PaymentMonitor";
    }

    public static string BuildBalloonText(Transaction tx)
    {
        var lines = new List<string>();
        lines.Add($"تم استلام: {FormatAmount(tx.Amount)} {tx.Currency}");
        lines.Add($"المحفظة: {tx.WalletName}");
        if (!string.IsNullOrEmpty(tx.SenderName))
            lines.Add($"من: {tx.SenderName}");
        if (!string.IsNullOrEmpty(tx.ReferenceNumber))
            lines.Add($"المرجع: {tx.ReferenceNumber}");
        return string.Join("\n", lines);
    }
}
