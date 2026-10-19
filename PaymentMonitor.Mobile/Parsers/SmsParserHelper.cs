using System.Globalization;
using System.Text;

namespace PaymentMonitor.Mobile.Parsers;

public static class SmsParserHelper
{
    public static string NormalizeDigits(string input)
    {
        if (string.IsNullOrEmpty(input))
            return input;

        var sb = new StringBuilder(input.Length);
        foreach (var ch in input)
        {
            if (ch >= '\u0660' && ch <= '\u0669') // Arabic-Indic digits ٠-٩
                sb.Append((char)('0' + (ch - '\u0660')));
            else if (ch >= '\u06F0' && ch <= '\u06F9') // Eastern Arabic-Indic digits ۰-۹
                sb.Append((char)('0' + (ch - '\u06F0')));
            else
                sb.Append(ch);
        }
        return sb.ToString();
    }

    public static decimal ParseDecimal(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return 0m;

        var clean = NormalizeDigits(value).Replace(",", "").Replace(" ", "").Trim();
        if (decimal.TryParse(clean, NumberStyles.Any, CultureInfo.InvariantCulture, out var result))
            return result;

        return 0m;
    }
}

