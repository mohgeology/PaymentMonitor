using System.Threading.Tasks;

namespace PaymentMonitor.Mobile.Services
{
    public interface ISmsPermissionService
    {
        /// <summary>
        /// Checks and requests RECEIVE_SMS permission when needed.
        /// Returns true when permission is granted.
        /// </summary>
        Task<bool> RequestReceiveSmsPermissionAsync();

        /// <summary>
        /// Returns true if RECEIVE_SMS is already granted.
        /// </summary>
        bool IsReceiveSmsGranted();

        /// <summary>
        /// Checks and requests READ_SMS permission when needed.
        /// Returns true when permission is granted.
        /// </summary>
        Task<bool> RequestReadSmsPermissionAsync();

        /// <summary>
        /// Returns true if READ_SMS is already granted.
        /// </summary>
        bool IsReadSmsGranted();
    }
}
