using System;
using System.Text.RegularExpressions;

namespace PaymentMonitor.Mobile.Parsers;

public class JeebSmsParser : ISmsParser
{
    public string WalletName => "جيب";

    // Pattern 1: Classic format with spaces
    // e.g.: اضيف 6000ر.ي تحويل مشترك رص:17702ر.ي من محمد عثمان-777729263
    private static readonly Regex ClassicTransferPattern = new(
        @"[أا]ضيف\s+(?<amount>[\d,]+(?:\.\d+)?)\s*(?<currency>ر\.?ي|ريال)?\s+(?<type>[^\r\n]+?)\s+رص\s*:?\s*(?<balance>[\d,]+(?:\.\d+)?)\s*(?:ر\.?ي|ريال)?\s+من\s+(?<sender>[^-–\r\n]+?)\s*[-–]\s*(?<phone>\d+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    // Pattern 2: Compact format without spaces between amount and currency/type
    // e.g.: 238750 ر.ي\nمشتريات رص1370668.6ري\nمن 325764 م17896515239653
    // Amount is on its own first, then type + balance compact, then sender + reference
    private static readonly Regex CompactPattern = new(
        @"(?<amount>[\d,]+(?:\.\d+)?)\s*(?<currency>ر\.?ي|ريال|YER)\s*[\r\n]+\s*(?<type>[^\d\r\n]+?)رص\s*:?\s*(?<balance>[\d,]+(?:\.\d+)?)(?:ر\.?ي|ريال|ري)?\s*[\r\n]+\s*من\s+(?<sender>[^\d\r\n]+?)\s*(?<ref>\d{10,})",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    // Pattern 4: POS Payment (points of sale)
    // e.g.:
    // اضيف 274800ر.ي
    // مشتريات رص:
    // 357213.6ر.ي
    // من 218245 م:
    // 17914731004141
    private static readonly Regex PosPaymentPattern = new(
        @"[أا]ضيف\s+(?<amount>[\d,]+(?:\.\d+)?)\s*ر\.?ي\s+(?<type>مشتريات|تحويل[^\r\n]*|سحب|[إا]يداع|شراء)\s+رص\s*:?\s*[\r\n]+\s*(?<balance>[\d,]+(?:\.\d+)?)\s*ر\.?ي\s+من\s+(?<sender>\d+)\s+م\s*:\s*[\r\n]+\s*(?<ref>\d+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase | RegexOptions.Singleline
    );

    // Pattern 3: General without sender
    // e.g.: اضيف 5000ر.ي ايداع رص:15000ر.ي
    private static readonly Regex GeneralPattern = new(
        @"[أا]ضيف\s+(?<amount>[\d,]+(?:\.\d+)?)\s*(?<currency>ر\.?ي|ريال)?\s+(?<type>[^\r\n]+?)\s+رص\s*:?\s*(?<balance>[\d,]+(?:\.\d+)?)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    public bool CanParse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return false;

        if (!string.IsNullOrWhiteSpace(sender))
        {
            var s = sender.Trim().ToLowerInvariant();
            if (s.Contains("jeeb") || s.Contains("جيب"))
                return true;
        }

        var normalized = SmsParserHelper.NormalizeDigits(message);
        // Classic indicators
        if ((normalized.Contains("اضيف") || normalized.Contains("أضيف")) && normalized.Contains("رص"))
            return true;
        if (normalized.Contains("جيب") || normalized.Contains("تحويل مشترك"))
            return true;
        // Compact format: amount + ر.ي on line, then type + رص on next line, then من on next line
        if (Regex.IsMatch(normalized, @"[\d,]+\s*(?:ر\.?ي|ريال|YER)[\r\n]", RegexOptions.None)
            && normalized.Contains("رص") && normalized.Contains("من"))
            return true;

        return false;
    }

    public SmsParserResult Parse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return SmsParserResult.Failed(message ?? string.Empty, WalletName);

        var normalized = SmsParserHelper.NormalizeDigits(message);

        // Try POS payment pattern first
        var match = PosPaymentPattern.Match(normalized);
        if (match.Success)
        {
            return new SmsParserResult
            {
                WalletName = WalletName,
                TransactionType = match.Groups["type"].Value.Trim(),
                Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
                Currency = "ر.ي",
                Balance = SmsParserHelper.ParseDecimal(match.Groups["balance"].Value),
                SenderName = match.Groups["sender"].Value.Trim(),
                ReferenceNumber = match.Groups["ref"].Value.Trim(),
                OriginalMessage = message,
                IsParsed = true,
                ParsedAt = DateTime.Now
            };
        }

        // Try compact multi-line pattern first (new format)
        match = CompactPattern.Match(normalized);
        if (match.Success)
        {
            return new SmsParserResult
            {
                WalletName = WalletName,
                TransactionType = match.Groups["type"].Value.Trim().TrimEnd('ر', '.', 'ي', ' '),
                Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
                Currency = NormalizeCurrency(match.Groups["currency"].Value),
                Balance = SmsParserHelper.ParseDecimal(match.Groups["balance"].Value),
                SenderName = match.Groups["sender"].Value.Trim(),
                ReferenceNumber = match.Groups["ref"].Success ? match.Groups["ref"].Value.Trim() : null,
                OriginalMessage = message,
                IsParsed = true,
                ParsedAt = DateTime.Now
            };
        }

        // Try classic transfer pattern (with sender name-phone)
        match = ClassicTransferPattern.Match(normalized);
        if (match.Success)
        {
            return new SmsParserResult
            {
                WalletName = WalletName,
                TransactionType = match.Groups["type"].Value.Trim(),
                Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
                Currency = NormalizeCurrency(match.Groups["currency"].Value),
                Balance = SmsParserHelper.ParseDecimal(match.Groups["balance"].Value),
                SenderName = match.Groups["sender"].Value.Trim(),
                SenderPhone = match.Groups["phone"].Value.Trim(),
                OriginalMessage = message,
                IsParsed = true,
                ParsedAt = DateTime.Now
            };
        }

        // Try general pattern (no sender)
        match = GeneralPattern.Match(normalized);
        if (match.Success)
        {
            return new SmsParserResult
            {
                WalletName = WalletName,
                TransactionType = match.Groups["type"].Value.Trim(),
                Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
                Currency = NormalizeCurrency(match.Groups["currency"].Value),
                Balance = SmsParserHelper.ParseDecimal(match.Groups["balance"].Value),
                OriginalMessage = message,
                IsParsed = true,
                ParsedAt = DateTime.Now
            };
        }

        return SmsParserResult.Failed(message, WalletName);
    }

    private static string NormalizeCurrency(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "ر.ي";
        var v = raw.Trim();
        if (v.Contains("ر") || v.Contains("ريال")) return "ر.ي";
        return v;
    }
}

