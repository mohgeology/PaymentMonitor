using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Input;
using Microsoft.Maui.Controls;

namespace PaymentMonitor.Mobile.Models;

public class ScannedSmsItem : INotifyPropertyChanged
{
    public string WalletName { get; set; } = string.Empty;
    public string TransactionType { get; set; } = string.Empty;
    public decimal Amount { get; set; }
    public string FormattedAmount { get; set; } = string.Empty;
    public string? SenderName { get; set; }
    public string? SenderPhone { get; set; }
    public string? AccountNumber { get; set; }
    public decimal? Balance { get; set; }
    public string? FormattedBalance { get; set; }
    public DateTime MessageTime { get; set; }
    public string FormattedTime { get; set; } = string.Empty;
    public string OriginalMessage { get; set; } = string.Empty;

    public bool HasSenderName => !string.IsNullOrWhiteSpace(SenderName);
    public bool HasSenderPhone => !string.IsNullOrWhiteSpace(SenderPhone);
    public bool HasAccountNumber => !string.IsNullOrWhiteSpace(AccountNumber);
    public bool HasBalance => Balance.HasValue;

    private bool _showOriginalMessage;
    public bool ShowOriginalMessage
    {
        get => _showOriginalMessage;
        set
        {
            if (_showOriginalMessage != value)
            {
                _showOriginalMessage = value;
                OnPropertyChanged();
                OnPropertyChanged(nameof(ToggleOriginalButtonText));
            }
        }
    }

    public string ToggleOriginalButtonText => ShowOriginalMessage ? "إخفاء النص الأصلي ▲" : "عرض النص الأصلي ▼";

    public ICommand ToggleOriginalCommand { get; }

    public ScannedSmsItem()
    {
        ToggleOriginalCommand = new Command(() => ShowOriginalMessage = !ShowOriginalMessage);
    }

    public event PropertyChangedEventHandler? PropertyChanged;
    protected void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}

