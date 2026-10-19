using System;

namespace PaymentMonitor.Mobile.Parsers;

public static class SmsParserTests
{
    public class TestResult
    {
        public string TestName { get; set; } = string.Empty;
        public bool Passed { get; set; }
        public string Details { get; set; } = string.Empty;
        public SmsParserResult? ParserResult { get; set; }
    }

    public static TestResult RunJeebTest()
    {
        string sample = "اضيف 6000ر.ي تحويل مشترك رص:17702ر.ي من محمد عثمان-777729263";
        var result = SmsParserFactory.Default.Parse(sample);

        bool passed = result.IsParsed
            && result.WalletName == "جيب"
            && result.TransactionType == "تحويل مشترك"
            && result.Amount == 6000m
            && result.SenderName == "محمد عثمان"
            && result.SenderPhone == "777729263"
            && result.Balance == 17702m;

        return new TestResult
        {
            TestName = "Jeeb SMS Parser Test",
            Passed = passed,
            Details = passed
                ? $"نجاح: WalletName='{result.WalletName}', TransactionType='{result.TransactionType}', Amount={result.Amount}, SenderName='{result.SenderName}', SenderPhone='{result.SenderPhone}', Balance={result.Balance}"
                : $"فشل: IsParsed={result.IsParsed}, WalletName='{result.WalletName}', TransactionType='{result.TransactionType}', Amount={result.Amount}, Balance={result.Balance}",
            ParserResult = result
        };
    }

    public static TestResult RunMobileMoneyTest()
    {
        string sample = "تم ايداع 20200.00 ر.ي الى حسابكم رقم :734160944 الرصيد:20212.59";
        var result = SmsParserFactory.Default.Parse(sample);

        bool passed = result.IsParsed
            && result.WalletName == "موبايل موني"
            && result.TransactionType == "إيداع"
            && result.Amount == 20200.00m
            && result.AccountNumber == "734160944"
            && result.Balance == 20212.59m;

        return new TestResult
        {
            TestName = "Mobile Money SMS Parser Test",
            Passed = passed,
            Details = passed
                ? $"نجاح: WalletName='{result.WalletName}', TransactionType='{result.TransactionType}', Amount={result.Amount}, AccountNumber='{result.AccountNumber}', Balance={result.Balance}"
                : $"فشل: IsParsed={result.IsParsed}, WalletName='{result.WalletName}', TransactionType='{result.TransactionType}', Amount={result.Amount}, AccountNumber='{result.AccountNumber}', Balance={result.Balance}",
            ParserResult = result
        };
    }
}

