using System;
using System.Text.RegularExpressions;

namespace PaymentMonitor.Mobile.Parsers;

public class MobileMoneySmsParser : ISmsParser
{
    public string WalletName => "موبايل موني";

    // Pattern for deposit / transfer to account:
    // e.g.: تم ايداع 20200.00 ر.ي الى حسابكم رقم :734160944 الرصيد:20212.59
    private static readonly Regex DepositPattern = new(
        @"تم\s+(?<type>[أا]يداع|تحويل|تغذية|سحب|شراء)\s+(?<amount>[\d,]+(?:\.\d+)?)\s*(?:ر\.?ي|ريال)?\s+[إا]لى\s+حسابكم\s+رقم\s*:\s*(?<account>\d+)\s+الرصيد\s*:\s*(?<balance>[\d,]+(?:\.\d+)?)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    // Fallback general pattern:
    private static readonly Regex GeneralPattern = new(
        @"تم\s+(?<type>[أا]يداع|تحويل|تغذية|سحب|شراء)\s+(?<amount>[\d,]+(?:\.\d+)?)\s*(?:ر\.?ي|ريال)?.*?(?:حسابكم\s+رقم\s*:\s*(?<account>\d+))?.*?الرصيد\s*:\s*(?<balance>[\d,]+(?:\.\d+)?)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    // Format 6464 (mobile money payments):
    // مدفوعات
    // المبلغ: 8800.0
    // المرجع: Pmt-261001-825262-2133263
    // النقطة: 900248
    private static readonly Regex Payments6464Pattern = new(
        @"مدفوعات\s*[\r\n]+\s*المبلغ\s*:\s*(?<amount>[\d,]+(?:\.\d+)?)\s*[\r\n]+\s*المرجع\s*:\s*(?<ref>\S+)\s*[\r\n]+\s*النقطة\s*:\s*(?<point>\d+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    public bool CanParse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return false;

        if (!string.IsNullOrWhiteSpace(sender))
        {
            var s = sender.Trim().ToLowerInvariant();
            if (s.Contains("mobilemoney") || s.Contains("mobile money") || s.Contains("cacbank") || s.Contains("cac bank") || s.Contains("موبايل موني"))
                return true;

            // 6464 mobile money short code
            if (s.Trim() == "6464")
                return true;
        }

        var normalized = SmsParserHelper.NormalizeDigits(message);
        return (normalized.Contains("موبايل موني") || normalized.Contains("موبايل_موني"))
            || (normalized.Contains("حسابكم رقم") && normalized.Contains("الرصيد:"));
    }

    public SmsParserResult Parse(string message, string? sender = null)
    {
        if (string.IsNullOrWhiteSpace(message))
            return SmsParserResult.Failed(message ?? string.Empty, WalletName);

        var normalized = SmsParserHelper.NormalizeDigits(message);

        var match = DepositPattern.Match(normalized);
        if (!match.Success)
        {
            match = GeneralPattern.Match(normalized);
        }
        if (!match.Success)
        {
            match = Payments6464Pattern.Match(normalized);
        }

        if (match.Success)
        {
            // نوع العملية (قد لا يكون موجودًا في نمط 6464)
            string normalizedType = "مدفوعات";
            if (match.Groups["type"].Success)
            {
                var rawType = match.Groups["type"].Value.Trim();
                normalizedType = NormalizeTransactionType(rawType);
            }

            // رقم الحساب (للنمط القديم)
            string? accountNumber = null;
            if (match.Groups["account"].Success)
                accountNumber = match.Groups["account"].Value.Trim();
            // رقم النقطة (للنمط الجديد 6464)
            else if (match.Groups["point"].Success)
                accountNumber = match.Groups["point"].Value.Trim();

            // المرجع (قد يكون ref أو لا يوجد)
            string? referenceNumber = null;
            if (match.Groups["ref"].Success)
                referenceNumber = match.Groups["ref"].Value.Trim();

            return new SmsParserResult
            {
                WalletName = WalletName,
                TransactionType = normalizedType,
                Amount = SmsParserHelper.ParseDecimal(match.Groups["amount"].Value),
                AccountNumber = accountNumber,
                ReferenceNumber = referenceNumber,
                Balance = match.Groups["balance"].Success ? SmsParserHelper.ParseDecimal(match.Groups["balance"].Value) : null,
                OriginalMessage = message,
                IsParsed = true,
                ParsedAt = DateTime.Now
            };
        }

        return SmsParserResult.Failed(message, WalletName);
    }

    private static string NormalizeTransactionType(string type)
    {
        if (type == "ايداع" || type == "إيداع")
            return "إيداع";
        if (type == "تحويل")
            return "تحويل";
        if (type == "سحب")
            return "سحب";
        return type;
    }
}

