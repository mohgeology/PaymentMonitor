using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Android.Provider;
using Android.Util;
using PaymentMonitor.Mobile.Services;

namespace PaymentMonitor.Mobile.Platforms.Android;

public class SmsReaderService : ISmsReaderService
{
    const string TAG = "SmsReaderService";

    public Task<List<RawSmsMessage>> GetMessagesAsync(long startMillis, long endMillis)
    {
        return Task.Run(() =>
        {
            var list = new List<RawSmsMessage>();

            try
            {
                var context = global::Android.App.Application.Context;
                var contentResolver = context.ContentResolver;
                if (contentResolver == null)
                {
                    Log.Warn(TAG, "ContentResolver is null");
                    return list;
                }

                // Query SMS Inbox strictly within [startMillis, endMillis]
                var uri = global::Android.Net.Uri.Parse("content://sms/inbox")!;
                const string colAddress = "address";
                const string colBody = "body";
                const string colDate = "date";

                string[] projection = new[]
                {
                    colAddress,
                    colBody,
                    colDate
                };

                string selection = $"{colDate} >= ? AND {colDate} <= ?";
                string[] selectionArgs = new[] { startMillis.ToString(), endMillis.ToString() };
                string sortOrder = $"{colDate} DESC";

                using var cursor = contentResolver.Query(uri, projection, selection, selectionArgs, sortOrder);
                if (cursor != null && cursor.MoveToFirst())
                {
                    int addressIndex = cursor.GetColumnIndex(colAddress);
                    int bodyIndex = cursor.GetColumnIndex(colBody);
                    int dateIndex = cursor.GetColumnIndex(colDate);

                    do
                    {
                        string address = addressIndex >= 0 ? (cursor.GetString(addressIndex) ?? string.Empty) : string.Empty;
                        string body = bodyIndex >= 0 ? (cursor.GetString(bodyIndex) ?? string.Empty) : string.Empty;
                        long date = dateIndex >= 0 ? cursor.GetLong(dateIndex) : 0;

                        list.Add(new RawSmsMessage
                        {
                            Address = address,
                            Body = body,
                            DateMillis = date
                        });
                    } while (cursor.MoveToNext());
                }

                Log.Debug(TAG, $"GetMessagesAsync: found {list.Count} SMS in range [{startMillis}, {endMillis}]");
            }
            catch (Exception ex)
            {
                Log.Error(TAG, $"Error reading SMS inbox: {ex}");
            }

            return list;
        });
    }
}

