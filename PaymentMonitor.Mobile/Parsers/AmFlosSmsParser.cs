using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace PaymentMonitor.Mobile.Parsers;

public class AmFlosSmsParser : ISmsParser
{
    public string WalletName => "أم فلوس";

    // Format 1 (multi-line):
    // تم إيداع مبلغ 9000YER
    // من: نجوی احمد
    // المرجع: 53739956
    private static readonly Regex MultiLineDepositPattern = new(
        @"تم\s+(?<type>[إا]يداع|تحويل|سحب)\s+مبلغ\s+(?<amount>[\d,]+(?:\.\d+)?)\s*(?<currency>[A-Za-z]+|ر\.?ي|ريال)?\s*[\r\n]+\s*من\s*:\s*(?<sender>[^\r\n]+?)\s*[\r\n]+\s*المرجع\s*:\s*(?<ref>\d+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    // Format 2 (single-line, reversed reference):
    // تم إيداع مبلغ 7000 YER من عبد الفتاح محمد 53734851 :المرجع
    private static readonly Regex SingleLineDepositPattern = new(
        @"تم\s+(?<type>[إا]يداع|تحويل|سحب)\s+مبلغ\s+(?<amount>[\d,]+(?:\.\d+)?)\s*(?<currency>[A-Za-z]+|ر\.?ي|ريال)?\s+من\s+(?<sender>[^\d\r\n]+?)\s+(?<ref>\d+)\s*:?\s*المرجع",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    // Format 3 (classic transfer with balance):
    // e.g.: تم استلام حوالة بمبلغ 15000 ر.ي من فلان رقم الحوالة: 123456 الرصيد: 60000 ر.ي
    private static readonly Regex TransferWithBalancePattern = new(
        @"(?:استلمت|وصلكم|تم\s+(?:تحويل|استلام حوالة))\s+(?:مبلغ\s+)?(?<amount>[\d,]+(?:\.\d+)?)\s*(?<currency>[A-Za-z]+|ر\.?ي|ريال)?\s+من\s+(?<sender>[^\d\r\n]+?)(?:\s+(?:رقم\s+الحوالة|المرجع)\s*:?\s*(?<ref>\d+))?.*?(?:الرصيد\s*:\s*(?<balance>[\d,]+(?:\.\d+)?))?",
        RegexOptions.Compiled | RegexOptions.IgnoreCase | RegexOptions.Singleline
    );

    // Extensible custom templates
    private readonly List<Func<string, SmsParserResult?>> _customTemplates = new();

    /// <summary>
    /// Register additional AmFlos message patterns when new real SMS samples are available.
    /// </summary>
    public void AddCustomTemplate(Func<string, SmsParserResult?> templateParser)
    {
        if (templateParser != null)
            _customTemplates.Add(templateParser);
    }

    public bool CanParse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return false;

        if (!string.IsNullOrWhiteSpace(sender))
        {
            var s = sender.Trim().ToLowerInvariant();
            if (s.Contains("amflos") || s.Contains("mfloos") || s.Contains("m-floos") || s.Contains("mf-loos")
                || s.Contains("أم فلوس") || s.Contains("ام فلوس")
                || s.Contains("amqi") || s.Contains("العمقي"))
                return true;
        }

        var normalized = SmsParserHelper.NormalizeDigits(message);
        if (normalized.Contains("أم فلوس") || normalized.Contains("ام فلوس"))
            return true;
        if (normalized.Contains("AmFlos", StringComparison.OrdinalIgnoreCase))
            return true;

        // Key patterns for AmFlos
        if (Regex.IsMatch(normalized, @"تم\s+[إا]يداع\s+مبلغ\s+[\d,]", RegexOptions.None)
            && (normalized.Contains("المرجع") || normalized.Contains("من:")))
            return true;

        return false;
    }

    public SmsParserResult Parse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return SmsParserResult.Failed(message ?? string.Empty, WalletName);

        var normalized = SmsParserHelper.NormalizeDigits(message);

        // Try multi-line format first
        var match = MultiLineDepositPattern.Match(normalized);
        if (match.Success)
        {
            return BuildResult(match, message);
        }

        // Try single-line format (reversed reference)
        match = SingleLineDepositPattern.Match(normalized);
        if (match.Success)
        {
            return BuildResult(match, message);
        }

        // Try transfer with balance
        match = TransferWithBalancePattern.Match(normalized);
        if (match.Success && match.Groups["amount"].Success
            && SmsParserHelper.ParseDecimal(match.Groups["amount"].Value) > 0)
        {
            return new SmsParserResult
            {
                WalletName = WalletName,
                TransactionType = NormalizeType(match.Groups["type"].Value),
                Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
                Currency = NormalizeCurrency(match.Groups["currency"].Value),
                SenderName = match.Groups["sender"].Success ? match.Groups["sender"].Value.Trim() : null,
                ReferenceNumber = match.Groups["ref"].Success ? match.Groups["ref"].Value.Trim() : null,
                Balance = match.Groups["balance"].Success ? SmsParserHelper.ParseDecimal(match.Groups["balance"].Value) : null,
                OriginalMessage = message,
                IsParsed = true,
                ParsedAt = DateTime.Now
            };
        }

        // Try custom templates
        foreach (var template in _customTemplates)
        {
            try
            {
                var result = template(normalized);
                if (result != null && result.IsParsed)
                {
                    result.OriginalMessage = message;
                    return result;
                }
            }
            catch { }
        }

        return new SmsParserResult
        {
            WalletName = WalletName,
            OriginalMessage = message,
            IsParsed = false,
            ParsedAt = DateTime.Now
        };
    }

    private SmsParserResult BuildResult(Match match, string originalMessage)
    {
        return new SmsParserResult
        {
            WalletName = WalletName,
            TransactionType = NormalizeType(match.Groups["type"].Value),
            Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
            Currency = NormalizeCurrency(match.Groups["currency"].Value),
            SenderName = match.Groups["sender"].Success ? match.Groups["sender"].Value.Trim() : null,
            ReferenceNumber = match.Groups["ref"].Success ? match.Groups["ref"].Value.Trim() : null,
            Balance = match.Groups["balance"].Success && !string.IsNullOrEmpty(match.Groups["balance"].Value)
                ? SmsParserHelper.ParseDecimal(match.Groups["balance"].Value)
                : null,
            OriginalMessage = originalMessage,
            IsParsed = true,
            ParsedAt = DateTime.Now
        };
    }

    private static string NormalizeType(string raw)
    {
        var v = raw.Trim();
        if (v == "ايداع" || v == "إيداع") return "إيداع";
        if (v == "تحويل") return "تحويل";
        if (v == "سحب") return "سحب";
        return v;
    }

    private static string NormalizeCurrency(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "YER";
        var v = raw.Trim();
        if (v.Equals("YER", StringComparison.OrdinalIgnoreCase)) return "YER";
        if (v.Contains("ر") || v.Contains("ريال")) return "ر.ي";
        return v.ToUpperInvariant();
    }
}

