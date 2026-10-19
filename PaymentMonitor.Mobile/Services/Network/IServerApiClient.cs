using PaymentMonitor.Mobile.Models;

namespace PaymentMonitor.Mobile.Services.Network;

public interface IServerApiClient
{
    Task<ServerTransactionResponse> SendTransactionAsync(
        PaymentTransaction transaction,
        CancellationToken cancellationToken = default);

    Task<bool> TestConnectionAsync(
        CancellationToken cancellationToken = default);
}
