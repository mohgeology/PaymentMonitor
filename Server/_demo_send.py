import json, urllib.request
from datetime import datetime

base = 'http://127.0.0.1:5000'

# معاملة تجريبية نظيفة
tx = {
    'id': f'demo-{datetime.now().strftime("%H%M%S")}',
    'deviceId': 'demo-device',
    'walletName': 'أم فلوس',
    'transactionType': 'إيداع',
    'amount': 4500,
    'currency': 'YER',
    'senderName': 'أحمد الحميدي',
    'senderPhone': '770123456',
    'referenceNumber': 'DEMO-' + datetime.now().strftime("%H%M%S"),
    'smsTime': datetime.now().isoformat(),
    'originalMessage': 'تم إيداع 4500 ريال من أحمد الحميدي'
}

data = json.dumps(tx, ensure_ascii=False).encode('utf-8')
req = urllib.request.Request(
    f'{base}/api/transactions',
    data=data,
    headers={'Content-Type': 'application/json; charset=utf-8'},
    method='POST'
)

with urllib.request.urlopen(req, timeout=10) as r:
    print('Status:', r.status)
    print('Response:', r.read().decode('utf-8'))
    print('')
    print('راقب إشعار Cashier الآن...')
