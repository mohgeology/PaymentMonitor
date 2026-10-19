using Android;
using Android.App;
using Android.Content.PM;
using AndroidX.Core.App;
using AndroidX.Core.Content;
using System;
using System.Threading.Tasks;
using Android.Util;

namespace PaymentMonitor.Mobile.Platforms.Android
{
    // Android-only implementation
    public class SmsPermissionService : Services.ISmsPermissionService
    {
        const string TAG = "SmsPermissionService";
        const int ReceiveSmsRequestCode = 1001;
        const int ReadSmsRequestCode = 1002;
        static TaskCompletionSource<bool>? _receiveTcs;
        static TaskCompletionSource<bool>? _readTcs;

        public bool IsReceiveSmsGranted()
        {
            var context = global::Android.App.Application.Context;
            var granted = ContextCompat.CheckSelfPermission(context, Manifest.Permission.ReceiveSms) == (int)Permission.Granted;
            Log.Debug(TAG, $"IsReceiveSmsGranted={granted}");
            return granted;
        }

        public Task<bool> RequestReceiveSmsPermissionAsync()
        {
            var context = global::Android.App.Application.Context;
            var activity = MainActivity.CurrentActivity ?? Microsoft.Maui.ApplicationModel.Platform.CurrentActivity;
            if (activity == null)
            {
                Log.Warn(TAG, "No current activity to request permission.");
                return Task.FromResult(false);
            }

            if (IsReceiveSmsGranted())
                return Task.FromResult(true);

            if (_receiveTcs != null && !_receiveTcs.Task.IsCompleted)
                return _receiveTcs.Task;

            _receiveTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

            try
            {
                ActivityCompat.RequestPermissions(activity, new[] { Manifest.Permission.ReceiveSms }, ReceiveSmsRequestCode);
            }
            catch (Exception ex)
            {
                Log.Error(TAG, ex.ToString());
                _receiveTcs.TrySetResult(false);
            }

            return _receiveTcs.Task;
        }

        public bool IsReadSmsGranted()
        {
            var context = global::Android.App.Application.Context;
            var granted = ContextCompat.CheckSelfPermission(context, Manifest.Permission.ReadSms) == (int)Permission.Granted;
            Log.Debug(TAG, $"IsReadSmsGranted={granted}");
            return granted;
        }

        public Task<bool> RequestReadSmsPermissionAsync()
        {
            var context = global::Android.App.Application.Context;
            var activity = MainActivity.CurrentActivity ?? Microsoft.Maui.ApplicationModel.Platform.CurrentActivity;
            if (activity == null)
            {
                Log.Warn(TAG, "No current activity to request permission.");
                return Task.FromResult(false);
            }

            if (IsReadSmsGranted())
                return Task.FromResult(true);

            if (_readTcs != null && !_readTcs.Task.IsCompleted)
                return _readTcs.Task;

            _readTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

            try
            {
                ActivityCompat.RequestPermissions(activity, new[] { Manifest.Permission.ReadSms }, ReadSmsRequestCode);
            }
            catch (Exception ex)
            {
                Log.Error(TAG, ex.ToString());
                _readTcs.TrySetResult(false);
            }

            return _readTcs.Task;
        }

        // Called by MainActivity when permissions result is available
        public static void NotifyRequestPermissionsResult(int requestCode, string[] permissions, Permission[] grantResults)
        {
            bool granted = grantResults != null && grantResults.Length > 0 && grantResults[0] == Permission.Granted;

            if (requestCode == ReceiveSmsRequestCode)
            {
                Log.Debug(TAG, $"ReceiveSms permission result: granted={granted}");
                _receiveTcs?.TrySetResult(granted);
                _receiveTcs = null;
            }
            else if (requestCode == ReadSmsRequestCode)
            {
                Log.Debug(TAG, $"ReadSms permission result: granted={granted}");
                _readTcs?.TrySetResult(granted);
                _readTcs = null;
            }
        }
    }
}
