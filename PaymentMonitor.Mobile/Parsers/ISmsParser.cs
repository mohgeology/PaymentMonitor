namespace PaymentMonitor.Mobile.Parsers;

public interface ISmsParser
{
    string WalletName { get; }
    bool CanParse(string message, string? sender = null);
    SmsParserResult Parse(string message, string? sender = null);
}

