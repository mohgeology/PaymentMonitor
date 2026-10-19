from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
from pydantic import BaseModel
from datetime import datetime, timezone, date, timedelta
import sqlite3
from pathlib import Path
from typing import Optional
import socket
import sys
import json
import io
import base64
import secrets
import shutil
import subprocess
import hashlib
import hmac
try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent / "data"
else:
    BASE_DIR = Path(__file__).parent
BASE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE_DIR / "transactions.db"
SETTINGS_PATH = BASE_DIR / "settings.json"
API_KEY = ""


def load_settings():
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except:
            pass
    return {"port": 5000, "api_key": ""}


def save_settings(settings):
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


SETTINGS = load_settings()


# ============================================================
# WebSocket Manager - إدارة اتصالات الكواشير
# ============================================================
class CashierManager:
    """مدير اتصالات WebSocket للكواشير (نسخة محسّنة)."""

    def __init__(self):
        # websocket -> {cashierId, connectedAt, lastPing, remote}
        self.active_connections = {}
        self._lock = asyncio.Lock()

    @property
    def count(self):
        return len(self.active_connections)

    # للتوافق مع الكود القديم الذي يستخدم list
    def _as_list(self):
        return list(self.active_connections.keys())

    async def connect(self, websocket: WebSocket, cashier_id=None):
        await websocket.accept()
        async with self._lock:
            self.active_connections[websocket] = {
                "cashierId": cashier_id,
                "connectedAt": datetime.now(timezone.utc).isoformat(),
                "lastPing": datetime.now(timezone.utc).isoformat(),
                "remote": str(websocket.client) if websocket.client else None,
            }
        print(f"[WS] Connected (cashier={cashier_id}). Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.pop(websocket, None)
        print(f"[WS] Disconnected. Total: {len(self.active_connections)}")

    async def update_ping(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections[websocket]["lastPing"] = datetime.now(timezone.utc).isoformat()

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            await self.disconnect(websocket)
            return False

    async def broadcast(self, message: dict):
        async with self._lock:
            connections = list(self.active_connections.keys())
        if not connections:
            return
        dead = []
        sent = 0
        for ws in connections:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        print(f"[WS] Broadcast sent to {sent}/{len(connections)}")

    def stats(self):
        now = datetime.now(timezone.utc)
        result = []
        for ws, info in self.active_connections.items():
            try:
                last = datetime.fromisoformat(info["lastPing"].replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                idle = (now - last).total_seconds()
            except Exception:
                idle = None
            result.append({
                "cashierId": info.get("cashierId"),
                "connectedAt": info.get("connectedAt"),
                "lastPing": info.get("lastPing"),
                "idleSeconds": idle,
                "remote": info.get("remote"),
            })
        return result


cashier_manager = CashierManager()

# توكن الربط (يُولَّد مرة واحدة لكل جلسة)
if "connection_token" not in SETTINGS:
    SETTINGS["connection_token"] = secrets.token_hex(8)
    save_settings(SETTINGS)



def get_all_ips():
    """يعيد كل عناوين IPv4 المتاحة على الجهاز (0.0.0.0, 127.0.0.1, ثم عناوين الشبكة)."""
    import socket as sk
    ips = ["0.0.0.0", "127.0.0.1"]
    hostname = sk.gethostname()
    try:
        for info in sk.getaddrinfo(hostname, None, sk.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    try:
        s = sk.socket(sk.AF_INET, sk.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        if primary not in ips and not primary.startswith("127."):
            ips.insert(2, primary)
    except Exception:
        pass
    return ips

app = FastAPI(title="PaymentMonitor Server", docs_url="/docs")


from fastapi.staticfiles import StaticFiles
from pathlib import Path as _P
_static = _P(__file__).parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

# ============================================================
# Models
# ============================================================
class TransactionIn(BaseModel):
    id: str
    deviceId: Optional[str] = None
    walletName: Optional[str] = None
    transactionType: Optional[str] = None
    amount: float
    currency: Optional[str] = None
    senderName: Optional[str] = None
    senderPhone: Optional[str] = None
    accountNumber: Optional[str] = None
    referenceNumber: Optional[str] = None
    balance: Optional[float] = None
    smsTime: Optional[str] = None
    originalMessage: Optional[str] = None


# ============================================================
# DB
# ============================================================
def backup_db():
    """نسخة احتياطية تلقائية قبل أي migration"""
    if DB_PATH.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = DB_PATH.parent / f"transactions.db.backup-{ts}"
        shutil.copy2(DB_PATH, backup)
        print(f"[BACKUP] {backup.name}")
        return backup
    return None


def init_db():
    conn = sqlite3.connect(DB_PATH)

    # --- الجداول الحالية (لا تغيير) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            deviceId TEXT,
            walletName TEXT,
            transactionType TEXT,
            amount REAL,
            currency TEXT,
            senderName TEXT,
            senderPhone TEXT,
            accountNumber TEXT,
            referenceNumber TEXT,
            balance REAL,
            smsTime TEXT,
            originalMessage TEXT,
            receivedAt TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet ON transactions(walletName)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_received ON transactions(receivedAt)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            deviceId TEXT PRIMARY KEY,
            lastSeen TEXT,
            lastIp TEXT,
            lastWallet TEXT,
            transactionCount INTEGER DEFAULT 0
        )
    """)

    # --- جداول جديدة (Migration آمنة) ---

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cashiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            displayName TEXT,
            passwordHash TEXT NOT NULL,
            role TEXT DEFAULT 'cashier',
            isActive INTEGER DEFAULT 1,
            createdAt TEXT,
            lastSeen TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cashiers_username ON cashiers(username)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cashiers_active ON cashiers(isActive)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cashier_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashierId INTEGER NOT NULL,
            deviceId TEXT,
            openedAt TEXT,
            closedAt TEXT,
            status TEXT DEFAULT 'OPEN',
            lastActivity TEXT,
            FOREIGN KEY (cashierId) REFERENCES cashiers(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_cashier ON cashier_sessions(cashierId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON cashier_sessions(status)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transaction_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transactionId TEXT NOT NULL,
            cashierSessionId INTEGER NOT NULL,
            assignedAt TEXT,
            status TEXT DEFAULT 'ASSIGNED',
            matchedAt TEXT,
            FOREIGN KEY (transactionId) REFERENCES transactions(id),
            FOREIGN KEY (cashierSessionId) REFERENCES cashier_sessions(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assign_tx ON transaction_assignments(transactionId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assign_session ON transaction_assignments(cashierSessionId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assign_status ON transaction_assignments(status)")

    conn.commit()
    conn.close()


# نسخة احتياطية تلقائية + تهيئة
backup_db()
init_db()

try:
    from pm_reports import register_reports
    register_reports(app, DB_PATH)
except Exception as _e:
    print('[REPORTS] failed to load:', _e)


# ============================================================
# API - SMS Reception
# ============================================================
@app.get("/ping")
def ping():
    return {"status": "ok", "server": "PaymentMonitor", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/transactions")
async def receive_transaction(tx: TransactionIn, x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx.id,)).fetchone()
    if existing:
        conn.close()
        print(f"[DUPLICATE] {tx.id[:12]}...")
        return {"success": True, "duplicate": True}

    conn.execute("""
        INSERT INTO transactions
        (id, deviceId, walletName, transactionType, amount, currency,
         senderName, senderPhone, accountNumber, referenceNumber,
         balance, smsTime, originalMessage, receivedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tx.id, tx.deviceId, tx.walletName, tx.transactionType, tx.amount, tx.currency,
        tx.senderName, tx.senderPhone, tx.accountNumber, tx.referenceNumber,
        tx.balance, tx.smsTime, tx.originalMessage,
        datetime.now(timezone.utc).isoformat()
    ))
    # تحديث آخر ظهور للجهاز
    now_iso = datetime.now(timezone.utc).isoformat()
    device_id = tx.deviceId or "unknown"
    conn.execute("""
        INSERT INTO devices (deviceId, lastSeen, lastIp, lastWallet, transactionCount)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(deviceId) DO UPDATE SET
            lastSeen = excluded.lastSeen,
            lastWallet = excluded.lastWallet,
            transactionCount = transactionCount + 1
    """, (device_id, now_iso, "network", tx.walletName))

    conn.commit()
    conn.close()
    print(f"[NEW] {tx.id[:12]}... | {tx.amount} {tx.currency} | {tx.senderName or tx.walletName}")

    # إشعار فوري لكل الكواشير
    try:
        await cashier_manager.broadcast({
            "type": "transaction.new",
            "transaction": {
                "id": tx.id,
                "walletName": tx.walletName,
                "transactionType": tx.transactionType,
                "amount": tx.amount,
                "currency": tx.currency,
                "senderName": tx.senderName,
                "senderPhone": tx.senderPhone,
                "accountNumber": tx.accountNumber,
                "referenceNumber": tx.referenceNumber,
                "balance": tx.balance,
                "smsTime": tx.smsTime,
                "receivedAt": datetime.now(timezone.utc).isoformat(),
                "status": "NEW"
            },
            "notificationDuration": SETTINGS.get("notification_duration_seconds", 10),
            "flashDuration": SETTINGS.get("notification_flash_seconds", 3)
        })
    except Exception as e:
        print(f"[WS] Broadcast error: {e}")

    return {"success": True, "duplicate": False}


# ============================================================
# API - Queries
# ============================================================
@app.get("/api/transactions")
def list_transactions(
    wallet: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    include_archived: bool = False,
    limit: int = Query(default=100, le=1000),
    offset: int = 0
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if not include_archived:
        query += " AND (is_archived = 0 OR is_archived IS NULL)"
    if wallet:
        query += " AND walletName = ?"
        params.append(wallet)
    if from_date:
        query += " AND receivedAt >= ?"
        params.append(from_date)
    if to_date:
        query += " AND receivedAt <= ?"
        params.append(to_date)
    query += " ORDER BY receivedAt DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    return {"total": total, "count": len(rows), "items": rows}


@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()

    total_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    total_amount = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions").fetchone()[0]
    today_count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE receivedAt LIKE ?", (f"{today}%",)
    ).fetchone()[0]
    today_amount = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE receivedAt LIKE ?", (f"{today}%",)
    ).fetchone()[0]

    by_wallet = [dict(r) for r in conn.execute(
        "SELECT walletName, COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM transactions GROUP BY walletName ORDER BY cnt DESC"
    ).fetchall()]

    last_received = conn.execute("SELECT MAX(receivedAt) FROM transactions").fetchone()[0]

    conn.close()
    return {
        "total_count": total_count,
        "total_amount": total_amount,
        "today_count": today_count,
        "today_amount": today_amount,
        "by_wallet": by_wallet,
        "last_received": last_received,
    }


@app.get("/api/devices")
def list_devices():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM devices ORDER BY lastSeen DESC"
    ).fetchall()]
    conn.close()
    return {"devices": rows}


@app.get("/api/connection-status")
def connection_status():
    """يعيد حالة الاتصال: هل هناك جهاز اتصل خلال آخر 60 ثانية؟"""
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc)
    rows = conn.execute("SELECT deviceId, lastSeen FROM devices").fetchall()
    conn.close()
    
    connected = False
    latest = None
    for device_id, last_seen in rows:
        if last_seen:
            try:
                last_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                diff = (now - last_dt).total_seconds()
                if latest is None or diff < latest["seconds"]:
                    latest = {"deviceId": device_id, "seconds": diff, "lastSeen": last_seen}
                if diff < 120:
                    connected = True
            except:
                pass
    
    return {
        "connected": connected,
        "device_count": len(rows),
        "latest": latest
    }


def connection_info():
    """معلومات الربط للتطبيق (تظهر داخل QR)."""
    ip = get_local_ip()
    port = SETTINGS.get("port", 5000)
    return {
        "server": f"http://{ip}:{port}",
        "apiKey": SETTINGS.get("api_key", ""),
        "token": SETTINGS.get("connection_token", ""),
        "name": socket.gethostname(),
        "version": "1.0"
    }


@app.get("/api/qr-code")
def qr_code():
    """يولّد QR Code كصورة base64 تحتوي على معلومات الربط."""
    if not QR_AVAILABLE:
        raise HTTPException(status_code=500, detail="مكتبة QR غير مثبّتة")
    
    info = connection_info()
    # JSON مضغوط داخل QR
    payload = json.dumps(info, ensure_ascii=False, separators=(",", ":"))
    
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2
    )
    qr.add_data(payload)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#123B7A", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    
    return {
        "qr_base64": f"data:image/png;base64,{b64}",
        "info": info
    }


@app.post("/api/regenerate-token")
def regenerate_token():
    """يولّد توكن ربط جديد (يُلغي القديم)."""
    SETTINGS["connection_token"] = secrets.token_hex(8)
    save_settings(SETTINGS)
    return {"success": True, "token": SETTINGS["connection_token"]}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default=None)):
    """WebSocket للكواشير. يمكن تمرير ?token=xxx لربطه بكاشير محدد."""
    cashier_id = None
    if token:
        cashier_id = ACTIVE_TOKENS.get(token)

    await cashier_manager.connect(websocket, cashier_id=cashier_id)
    try:
        await websocket.send_json({
            "type": "welcome",
            "message": "Connected to PaymentMonitor Server",
            "cashierId": cashier_id,
            "authenticated": cashier_id is not None,
            "serverTime": datetime.now(timezone.utc).isoformat()
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await cashier_manager.update_ping(websocket)
                await websocket.send_json({
                    "type": "pong",
                    "time": datetime.now(timezone.utc).isoformat()
                })
            elif data.startswith("auth:"):
                t = data[5:].strip()
                cid = ACTIVE_TOKENS.get(t)

                # إذا لم يوجد في الذاكرة، ابحث في DB
                if not cid:
                    try:
                        conn = sqlite3.connect(DB_PATH)
                        row = conn.execute(
                            "SELECT cashierId FROM auth_tokens WHERE token = ?", (t,)
                        ).fetchone()
                        conn.close()
                        if row:
                            cid = row[0]
                            ACTIVE_TOKENS[t] = cid
                            print(f"[AUTH] Token restored from DB for cashier {cid}")
                    except Exception as e:
                        print(f"[AUTH] DB lookup failed: {e}")

                if cid:
                    async with cashier_manager._lock:
                        if websocket in cashier_manager.active_connections:
                            cashier_manager.active_connections[websocket]["cashierId"] = cid
                    await websocket.send_json({"type": "auth-ok", "cashierId": cid})
                    print(f"[AUTH] WebSocket authenticated as cashier {cid}")
                else:
                    await websocket.send_json({"type": "auth-fail"})
                    print(f"[AUTH] Token rejected: {t[:8]}...")
    except WebSocketDisconnect:
        await cashier_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        await cashier_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        await cashier_manager.disconnect(websocket)


@app.get("/api/cashiers/count")
def cashiers_count():
    """عدد الكواشير المتصلة."""
    return {"count": len(cashier_manager.active_connections)}


@app.get("/api/network-info")
def network_info():
    """يعيد معلومات الشبكة الحالية (بما فيها host المحدد)."""
    import socket as sk
    try:
        s = sk.socket(sk.AF_INET, sk.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"

    hostname = sk.gethostname()
    port = SETTINGS.get("port", 5000)
    current_host = SETTINGS.get("host", "0.0.0.0")
    display_ip = current_host if current_host not in ("0.0.0.0", "127.0.0.1") else local_ip

    conn = sqlite3.connect(DB_PATH)
    device_count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    last_device = conn.execute(
        "SELECT deviceId, lastSeen FROM devices ORDER BY lastSeen DESC LIMIT 1"
    ).fetchone()
    conn.close()

    return {
        "local_ip": display_ip,
        "auto_ip": local_ip,
        "current_host": current_host,
        "hostname": hostname,
        "port": port,
        "dashboard_url": "http://" + display_ip + ":" + str(port) + "/dashboard",
        "api_url": "http://" + display_ip + ":" + str(port),
        "local_dashboard_url": "http://localhost:" + str(port) + "/dashboard",
        "device_count": device_count,
        "last_device": {"deviceId": last_device[0], "lastSeen": last_device[1]} if last_device else None
    }

def update_network_settings(settings: NetworkSettings):
    """يحفظ إعدادات الشبكة الجديدة."""
    global SETTINGS
    old_port = SETTINGS.get("port", 5000)
    
    SETTINGS["port"] = settings.port
    SETTINGS["host"] = settings.host
    SETTINGS["api_key"] = settings.api_key
    save_settings(SETTINGS)
    
    return {
        "success": True,
        "message": "تم حفظ الإعدادات. أعد تشغيل السيرفر لتطبيق التغييرات.",
        "old_port": old_port,
        "new_port": settings.port,
        "restart_required": old_port != settings.port
    }


@app.get("/api/wallets")
def list_wallets():
    conn = sqlite3.connect(DB_PATH)
    rows = [r[0] for r in conn.execute(
        "SELECT DISTINCT walletName FROM transactions WHERE walletName IS NOT NULL ORDER BY walletName"
    ).fetchall()]
    conn.close()
    return {"wallets": rows}


# ============================================================
# Cashier Authentication (Phase 2)
# ============================================================
ACTIVE_TOKENS = {}  # token -> cashierId


def hash_password(password):
    """PBKDF2-HMAC-SHA256"""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${h.hex()}"


def verify_password(password, stored):
    try:
        salt, h = stored.split("$", 1)
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def extract_token(authorization):
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def require_cashier(authorization):
    token = extract_token(authorization)
    cashier_id = ACTIVE_TOKENS.get(token) if token else None

    # إذا لم يوجد في الذاكرة، ابحث في DB
    if not cashier_id and token:
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT cashierId FROM auth_tokens WHERE token = ?", (token,)
            ).fetchone()
            conn.close()
            if row:
                cashier_id = row[0]
                ACTIVE_TOKENS[token] = cashier_id
        except Exception:
            pass

    if not cashier_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return cashier_id


class LoginIn(BaseModel):
    username: str
    password: str


class CashierCreateIn(BaseModel):
    username: str
    password: str
    displayName: Optional[str] = None
    role: str = "cashier"


@app.post("/api/cashier/create")
def cashier_create(data: CashierCreateIn, authorization: str = Header(default=None)):
    """إنشاء cashier جديد. أول cashier يمكن إنشاؤه بدون مصادقة."""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM cashiers").fetchone()[0]

    if count > 0:
        token = extract_token(authorization)
        cashier_id = ACTIVE_TOKENS.get(token) if token else None
        if not cashier_id:
            conn.close()
            raise HTTPException(status_code=401, detail="Authentication required")
        row = conn.execute("SELECT role FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
        if not row or row[0] != "admin":
            conn.close()
            raise HTTPException(status_code=403, detail="Admin role required")

    existing = conn.execute("SELECT id FROM cashiers WHERE username = ?", (data.username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Username already exists")

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO cashiers (username, displayName, passwordHash, role, isActive, createdAt) VALUES (?,?,?,?,1,?)",
        (data.username, data.displayName or data.username, hash_password(data.password), data.role, now),
    )
    conn.commit()
    conn.close()
    print(f"[AUTH] Created cashier: {data.username} ({data.role})")
    return {"success": True, "username": data.username, "role": data.role}


@app.post("/api/auth/login")
def auth_login(data: LoginIn):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM cashiers WHERE username = ? AND isActive = 1", (data.username,)
    ).fetchone()
    if not row or not verify_password(data.password, row["passwordHash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS[token] = row["id"]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE cashiers SET lastSeen = ? WHERE id = ?", (now, row["id"]))

    # حفظ token في DB للاستمرارية
    try:
        conn.execute(
            "INSERT OR REPLACE INTO auth_tokens (token, cashierId, createdAt, lastSeen) VALUES (?,?,?,?)",
            (token, row["id"], now, now)
        )
    except Exception as e:
        print(f"[AUTH] token save failed: {e}")

    conn.commit()
    conn.close()
    print(f"[AUTH] Login: {data.username}")
    return {
        "success": True,
        "token": token,
        "cashier": {
            "id": row["id"],
            "username": row["username"],
            "displayName": row["displayName"],
            "role": row["role"],
        },
    }


@app.post("/api/auth/logout")
def auth_logout(authorization: str = Header(default=None)):
    token = extract_token(authorization)
    if token:
        # حذف من الذاكرة
        ACTIVE_TOKENS.pop(token, None)
        # حذف من DB
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return {"success": True}


@app.get("/api/cashier/me")
def cashier_me(authorization: str = Header(default=None)):
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Cashier not found")
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["displayName"],
        "role": row["role"],
        "isActive": row["isActive"],
    }


@app.get("/api/cashiers")
def list_cashiers():
    """قائمة الكواشير (بدون passwordHash)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT id, username, displayName, role, isActive, createdAt, lastSeen FROM cashiers ORDER BY id"
    ).fetchall()]
    conn.close()
    return {"cashiers": rows}




@app.get("/api/cashiers/active")
def cashiers_active():
    """الكواشير المتصلون حاليًا عبر WebSocket."""
    conns = cashier_manager.stats()
    online_ids = [c["cashierId"] for c in conns if c.get("cashierId")]

    result = []
    if online_ids:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(online_ids))
        rows = conn.execute(
            f"SELECT id, username, displayName, role, lastSeen FROM cashiers WHERE id IN ({placeholders})",
            online_ids
        ).fetchall()
        result = [dict(r) for r in rows]
        conn.close()

    return {
        "count": len(result),
        "total_connections": len(conns),
        "anonymous_connections": len([c for c in conns if not c.get("cashierId")]),
        "cashiers": result
    }




@app.get("/api/transactions/filter")
def tx_filter(
    status: Optional[str] = None,
    wallet: Optional[str] = None,
    device: Optional[str] = None,
    cashier_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
):
    """فلترة متقدمة للمعاملات."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    where = ["1=1"]
    params = []
    joins = ""

    if cashier_id is not None:
        joins = " LEFT JOIN transaction_assignments ta ON ta.transactionId = t.id LEFT JOIN cashier_sessions cs ON cs.id = ta.cashierSessionId"
        where.append("cs.cashierId = ?")
        params.append(cashier_id)

    if status:
        where.append("t.status = ?")
        params.append(status.upper())
    if wallet:
        where.append("t.walletName = ?")
        params.append(wallet)
    if device:
        where.append("t.deviceId = ?")
        params.append(device)
    if from_date:
        where.append("t.receivedAt >= ?")
        params.append(from_date)
    if to_date:
        where.append("t.receivedAt <= ?")
        params.append(to_date)
    if min_amount is not None:
        where.append("t.amount >= ?")
        params.append(min_amount)
    if max_amount is not None:
        where.append("t.amount <= ?")
        params.append(max_amount)

    sql = f"SELECT DISTINCT t.* FROM transactions t{joins} WHERE " + " AND ".join(where)
    sql += " ORDER BY t.receivedAt DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    count_sql = f"SELECT COUNT(DISTINCT t.id) FROM transactions t{joins} WHERE " + " AND ".join(where)
    total = conn.execute(count_sql, params[:-2]).fetchone()[0]

    conn.close()
    return {"total": total, "count": len(rows), "items": rows}




@app.get("/api/transactions/summary")
def tx_summary():
    """ملخص إحصائي للمعاملات حسب الحالة."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    by_status = [dict(r) for r in conn.execute(
        "SELECT COALESCE(status, 'NEW') AS status, COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM transactions GROUP BY COALESCE(status, 'NEW') ORDER BY cnt DESC"
    ).fetchall()]

    by_wallet = [dict(r) for r in conn.execute(
        "SELECT walletName, COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM transactions GROUP BY walletName ORDER BY cnt DESC"
    ).fetchall()]

    total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()

    return {
        "total": total,
        "by_status": by_status,
        "by_wallet": by_wallet
    }




@app.post("/api/cleanup-connections")
def cleanup_connections(max_idle_seconds: int = 300):
    """إزالة اتصالات WebSocket الخاملة."""
    import asyncio
    from datetime import datetime as _dt, timezone as _tz

    now = _dt.now(_tz.utc)
    dead = []

    async def _cleanup():
        for ws, info in list(cashier_manager.active_connections.items()):
            try:
                last = _dt.fromisoformat(info["lastPing"].replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=_tz.utc)
                idle = (now - last).total_seconds()
                if idle > max_idle_seconds:
                    await cashier_manager.disconnect(ws)
                    dead.append(ws)
            except Exception:
                pass

    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(_cleanup())
    except Exception:
        pass

    return {"success": True, "cleaned": len(dead), "max_idle": max_idle_seconds}




# ============================================================
# Phase 8.1: Archive + Reports + Excel
# ============================================================


@app.post("/api/transactions/{tx_id}/archive")
def tx_archive(tx_id: str, authorization: str = Header(default=None)):
    """أرشفة معاملة (إخفاء من القائمة النشطة)."""
    try:
        cashier_id = require_cashier(authorization)
    except HTTPException:
        cashier_id = None

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE transactions SET is_archived = 1, archived_at = ?, archived_by = ? WHERE id = ?",
        (now, cashier_id, tx_id)
    )
    conn.commit()
    conn.close()
    print(f"[ARCHIVE] tx={tx_id[:12]}...")
    return {"success": True, "transactionId": tx_id, "is_archived": True, "archivedAt": now}


@app.post("/api/transactions/{tx_id}/unarchive")
def tx_unarchive(tx_id: str, authorization: str = Header(default=None)):
    """إلغاء أرشفة معاملة."""
    require_cashier(authorization)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    conn.execute(
        "UPDATE transactions SET is_archived = 0, archived_at = NULL, archived_by = NULL WHERE id = ?",
        (tx_id,)
    )
    conn.commit()
    conn.close()
    print(f"[UNARCHIVE] tx={tx_id[:12]}...")
    return {"success": True, "transactionId": tx_id, "is_archived": False}


class ArchiveBulkIn(BaseModel):
    ids: list[str]


@app.post("/api/transactions/archive-bulk")
def tx_archive_bulk(data: ArchiveBulkIn, authorization: str = Header(default=None)):
    """أرشفة عدة معاملات دفعة واحدة."""
    try:
        cashier_id = require_cashier(authorization)
    except HTTPException:
        cashier_id = None

    if not data.ids:
        return {"success": True, "archived_count": 0}

    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" * len(data.ids))

    cur = conn.execute(
        f"UPDATE transactions SET is_archived = 1, archived_at = ?, archived_by = ? WHERE id IN ({placeholders})",
        [now, cashier_id] + data.ids
    )
    conn.commit()
    count = cur.rowcount
    conn.close()
    print(f"[ARCHIVE BULK] {count} transactions")
    return {"success": True, "archived_count": count}


@app.get("/api/transactions/archived")
def tx_archived_list(limit: int = 200, offset: int = 0):
    """قائمة المعاملات المؤرشفة."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM transactions WHERE is_archived = 1 ORDER BY archived_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()]
    total = conn.execute("SELECT COUNT(*) FROM transactions WHERE is_archived = 1").fetchone()[0]
    conn.close()
    return {"total": total, "count": len(rows), "items": rows}


@app.get("/api/stats/dashboard")
def stats_dashboard():
    """إحصائيات موسّعة للوحة الرئيسية."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    today = date.today().isoformat()
    today_like = today + "%"

    # عمليات اليوم
    today_count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE receivedAt LIKE ? AND is_archived = 0",
        (today_like,)
    ).fetchone()[0]
    today_amount = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE receivedAt LIKE ? AND is_archived = 0",
        (today_like,)
    ).fetchone()[0]

    # مؤكدة من الكاشير (اليوم)
    confirmed = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE receivedAt LIKE ? AND status IN ('CONFIRMED','ASSIGNED') AND is_archived = 0",
        (today_like,)
    ).fetchone()[0]

    # غير مُسنَدة (كل الفترة)
    unassigned = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE status = 'NEW' AND is_archived = 0"
    ).fetchone()[0]

    # مؤرشفة
    archived = conn.execute("SELECT COUNT(*) FROM transactions WHERE is_archived = 1").fetchone()[0]

    # هواتف متصلة
    phones = conn.execute(
        "SELECT COUNT(*) FROM devices WHERE lastSeen > datetime('now', '-5 minutes')"
    ).fetchone()[0]

    conn.close()
    return {
        "today_count": today_count,
        "today_amount": today_amount,
        "confirmed_count": confirmed,
        "unassigned_count": unassigned,
        "archived_count": archived,
        "phones_online": phones,
    }


@app.get("/api/cashiers/performance")
def cashiers_performance(from_date: Optional[str] = None, to_date: Optional[str] = None):
    """أداء الكواشير خلال فترة."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    where = ["t.claimedByCashierId IS NOT NULL", "t.is_archived = 0"]
    params = []

    if from_date:
        where.append("t.receivedAt >= ?")
        params.append(from_date)
    if to_date:
        where.append("t.receivedAt <= ?")
        params.append(to_date)

    sql = f"""
        SELECT c.id, c.username, c.displayName,
               COUNT(t.id) AS count,
               COALESCE(SUM(t.amount), 0) AS total
        FROM transactions t
        JOIN cashiers c ON c.id = t.claimedByCashierId
        WHERE {' AND '.join(where)}
        GROUP BY c.id
        ORDER BY count DESC
    """

    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    # غير مُسنَدة
    unassigned_where = ["status = 'NEW'", "is_archived = 0"]
    if from_date:
        unassigned_where.append("receivedAt >= ?")
    if to_date:
        unassigned_where.append("receivedAt <= ?")

    unassigned = conn.execute(
        f"SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total FROM transactions WHERE {' AND '.join(unassigned_where)}",
        params
    ).fetchone()

    conn.close()
    return {
        "cashiers": rows,
        "unassigned": {"count": unassigned["count"], "total": unassigned["total"]}
    }


@app.get("/api/export/transactions.csv")
def export_transactions_csv(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    wallet: Optional[str] = None,
    cashier_id: Optional[int] = None,
    status: Optional[str] = None,
    include_archived: bool = False,
):
    """تصدير المعاملات كملف CSV (يفتح في Excel)."""
    from fastapi.responses import Response
    import csv
    import io

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    where = ["1=1"]
    params = []

    if not include_archived:
        where.append("is_archived = 0")
    if from_date:
        where.append("receivedAt >= ?")
        params.append(from_date)
    if to_date:
        where.append("receivedAt <= ?")
        params.append(to_date)
    if wallet:
        where.append("walletName = ?")
        params.append(wallet)
    if status:
        where.append("status = ?")
        params.append(status.upper())

    if cashier_id is not None:
        where.append("claimedByCashierId = ?")
        params.append(cashier_id)

    sql = f"""
        SELECT id, receivedAt, walletName, transactionType, amount, currency,
               senderName, senderPhone, referenceNumber, deviceId,
               status, claimedByCashierId, claimedAt, is_archived
        FROM transactions
        WHERE {' AND '.join(where)}
        ORDER BY receivedAt DESC
    """

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    # كتابة CSV
    buf = io.StringIO()
    buf.write('﻿')  # BOM للعربية
    writer = csv.writer(buf)
    writer.writerow(["ID", "التاريخ", "المحفظة", "النوع", "المبلغ", "العملة",
                     "المرسل", "الهاتف", "المرجع", "الجهاز",
                     "الحالة", "رقم الكاشير", "وقت الإسناد", "مؤرشفة"])

    for r in rows:
        writer.writerow([
            r["id"], r["receivedAt"], r["walletName"], r["transactionType"],
            r["amount"], r["currency"], r["senderName"] or "",
            r["senderPhone"] or "", r["referenceNumber"] or "",
            r["deviceId"] or "", r["status"] or "NEW",
            r["claimedByCashierId"] or "", r["claimedAt"] or "",
            "نعم" if r["is_archived"] else "لا"
        ])

    content = buf.getvalue()
    filename = f"transactions-{date.today().isoformat()}.csv"

    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/reports/shift")
def shift_report(authorization: str = Header(default=None)):
    """تقرير الوردية الحالية."""
    require_cashier(authorization)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # الوردية الحالية = آخر جلسة OPEN
    current = conn.execute(
        "SELECT * FROM cashier_sessions WHERE status = 'OPEN' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    # آخر 10 ورديات
    recent = [dict(r) for r in conn.execute(
        "SELECT * FROM cashier_sessions ORDER BY id DESC LIMIT 10"
    ).fetchall()]

    conn.close()
    return {
        "current": dict(current) if current else None,
        "recent": recent,
    }




# ============================================================
# Phase 9.1: Cashiers Management
# ============================================================
class CashierUpdateIn(BaseModel):
    displayName: Optional[str] = None
    role: Optional[str] = None
    isActive: Optional[int] = None


class CashierPasswordIn(BaseModel):
    newPassword: str


def _require_admin(authorization: str):
    """يتحقق أن المستخدم admin."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT role FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    conn.close()
    if not row or row[0] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return cashier_id


@app.post("/api/cashiers")
def cashier_create_v2(data: CashierCreateIn, authorization: str = Header(default=None)):
    """إضافة كاشير جديد (admin only)."""
    _require_admin(authorization)

    username = data.username.strip()
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short (min 3 chars)")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password too short (min 6 chars)")
    if data.role not in ("admin", "cashier"):
        raise HTTPException(status_code=400, detail="Role must be admin or cashier")

    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT id FROM cashiers WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Username already exists")

    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO cashiers (username, displayName, passwordHash, role, isActive, createdAt) VALUES (?,?,?,?,1,?)",
        (username, data.displayName or username, hash_password(data.password), data.role, now)
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    print(f"[CASHIER] Created: {username} (id={new_id}, role={data.role})")
    return {"success": True, "id": new_id, "username": username, "role": data.role}


@app.put("/api/cashiers/{cashier_id}")
def cashier_update(cashier_id: int, data: CashierUpdateIn, authorization: str = Header(default=None)):
    """تعديل بيانات كاشير (admin only)."""
    _require_admin(authorization)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, username, role FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Cashier not found")

    updates = []
    params = []

    if data.displayName is not None:
        updates.append("displayName = ?")
        params.append(data.displayName)
    if data.role is not None:
        if data.role not in ("admin", "cashier"):
            conn.close()
            raise HTTPException(status_code=400, detail="Role must be admin or cashier")
        # منع تغيير آخر admin إلى cashier
        if row[2] == "admin" and data.role != "admin":
            n_admins = conn.execute("SELECT COUNT(*) FROM cashiers WHERE role = 'admin' AND isActive = 1").fetchone()[0]
            if n_admins <= 1:
                conn.close()
                raise HTTPException(status_code=400, detail="Cannot demote the last admin")
        updates.append("role = ?")
        params.append(data.role)
    if data.isActive is not None:
        # منع تعطيل آخر admin
        if row[2] == "admin" and data.isActive == 0:
            n_admins = conn.execute("SELECT COUNT(*) FROM cashiers WHERE role = 'admin' AND isActive = 1").fetchone()[0]
            if n_admins <= 1:
                conn.close()
                raise HTTPException(status_code=400, detail="Cannot disable the last admin")
        updates.append("isActive = ?")
        params.append(1 if data.isActive else 0)

    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(cashier_id)
    conn.execute(f"UPDATE cashiers SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    print(f"[CASHIER] Updated: id={cashier_id}")
    return {"success": True, "id": cashier_id}


@app.post("/api/cashiers/{cashier_id}/password")
def cashier_password(cashier_id: int, data: CashierPasswordIn, authorization: str = Header(default=None)):
    """تغيير كلمة مرور كاشير (admin only)."""
    _require_admin(authorization)

    if len(data.newPassword) < 6:
        raise HTTPException(status_code=400, detail="Password too short (min 6 chars)")

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Cashier not found")

    conn.execute("UPDATE cashiers SET passwordHash = ? WHERE id = ?", (hash_password(data.newPassword), cashier_id))
    # حذف tokens الكاشير (لتسجيل خروج إجباري)
    conn.execute("DELETE FROM auth_tokens WHERE cashierId = ?", (cashier_id,))
    conn.commit()
    conn.close()
    # حذف من الذاكرة
    for t, cid in list(ACTIVE_TOKENS.items()):
        if cid == cashier_id:
            del ACTIVE_TOKENS[t]
    print(f"[CASHIER] Password changed: id={cashier_id}")
    return {"success": True, "id": cashier_id}


@app.post("/api/cashiers/{cashier_id}/toggle")
def cashier_toggle(cashier_id: int, authorization: str = Header(default=None)):
    """تفعيل / تعطيل كاشير."""
    me = _require_admin(authorization)

    if cashier_id == me:
        raise HTTPException(status_code=400, detail="Cannot toggle yourself")

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, role, isActive FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Cashier not found")

    new_state = 0 if row[2] else 1

    # منع تعطيل آخر admin
    if row[1] == "admin" and new_state == 0:
        n_admins = conn.execute("SELECT COUNT(*) FROM cashiers WHERE role = 'admin' AND isActive = 1").fetchone()[0]
        if n_admins <= 1:
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot disable the last admin")

    conn.execute("UPDATE cashiers SET isActive = ? WHERE id = ?", (new_state, cashier_id))
    if new_state == 0:
        # حذف tokens (تسجيل خروج)
        conn.execute("DELETE FROM auth_tokens WHERE cashierId = ?", (cashier_id,))
    conn.commit()
    conn.close()

    if new_state == 0:
        for t, cid in list(ACTIVE_TOKENS.items()):
            if cid == cashier_id:
                del ACTIVE_TOKENS[t]

    print(f"[CASHIER] Toggle: id={cashier_id}, isActive={new_state}")
    return {"success": True, "id": cashier_id, "isActive": new_state}


# ============================================================
# Dashboard (HTML)
# ============================================================


@app.get("/api/available-ips")
def available_ips():
    return {
        "ips": get_all_ips(),
        "current_host": SETTINGS.get("host", "0.0.0.0"),
        "current_port": SETTINGS.get("port", 5000)
    }




@app.post("/api/restart")
def restart_server():
    """يعيد تشغيل السيرفر ذاتيًا (spawn + exit)."""
    import sys
    import os
    import threading
    import time

    def _restart():
        time.sleep(0.5)
        try:
            python = sys.executable
            script = os.path.abspath(__file__)
            subprocess.Popen(
                [python, script],
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
                close_fds=True,
            )
            print("[RESTART] Spawned new instance")
        except Exception as e:
            print(f"[RESTART] Spawn error: {e}")
        time.sleep(1)
        os._exit(0)

    threading.Thread(target=_restart, daemon=True).start()
    return {"success": True, "message": "Server restarting..."}

def session_open(data: SessionOpenIn, authorization: str = Header(default=None)):
    """فتح جلسة جديدة للكاشير الحالي."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)

    # منع جلسة مزدوجة
    existing = conn.execute(
        "SELECT id, openedAt FROM cashier_sessions WHERE cashierId = ? AND status = 'OPEN'",
        (cashier_id,)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=f"Session already open (id={existing[0]}, openedAt={existing[1]})"
        )

    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO cashier_sessions (cashierId, deviceId, openedAt, status, lastActivity) VALUES (?,?,?,'OPEN',?)",
        (cashier_id, data.deviceId, now, now)
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    print(f"[SESSION] Open: cashier={cashier_id}, session={session_id}")
    return {
        "success": True,
        "sessionId": session_id,
        "cashierId": cashier_id,
        "deviceId": data.deviceId,
        "openedAt": now,
        "status": "OPEN"
    }


@app.post("/api/cashier/session/close")
def session_close(authorization: str = Header(default=None)):
    """إغلاق الجلسة الحالية للكاشير."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)

    existing = conn.execute(
        "SELECT id FROM cashier_sessions WHERE cashierId = ? AND status = 'OPEN'",
        (cashier_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="No open session")

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE cashier_sessions SET status='CLOSED', closedAt=?, lastActivity=? WHERE id=?",
        (now, now, existing[0])
    )
    conn.commit()
    conn.close()
    print(f"[SESSION] Close: cashier={cashier_id}, session={existing[0]}")
    return {
        "success": True,
        "sessionId": existing[0],
        "closedAt": now,
        "status": "CLOSED"
    }


@app.get("/api/cashier/session/current")
def session_current(authorization: str = Header(default=None)):
    """الجلسة الحالية للكاشير (إن وجدت)."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM cashier_sessions WHERE cashierId = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
        (cashier_id,)
    ).fetchone()
    conn.close()
    if row:
        return {"session": dict(row)}
    return {"session": None}


@app.get("/api/cashier/sessions")
def list_sessions(limit: int = 50, authorization: str = Header(default=None)):
    """قائمة الجلسات (للمراجعة)."""
    require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM cashier_sessions ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()]
    conn.close()
    return {"sessions": rows}


def update_session_activity(cashier_id):
    """تحديث lastActivity للجلسة المفتوحة (يُستدعى عند كل تفاعل)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE cashier_sessions SET lastActivity = ? WHERE cashierId = ? AND status = 'OPEN'",
            (now, cashier_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass




# ============================================================
# Transaction Assignment (Phase 4)
# ============================================================
class AssignIn(BaseModel):
    cashierSessionId: Optional[int] = None


def _tx_broadcast(tx_id, status):
    """يبث تحديث حالة المعاملة للكواشير."""
    try:
        import asyncio
        asyncio.create_task(cashier_manager.broadcast({
            "type": "transaction.updated",
            "transactionId": tx_id,
            "status": status,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }))
    except Exception:
        pass


@app.post("/api/transactions/{tx_id}/assign")
def tx_assign(tx_id: str, data: AssignIn, authorization: str = Header(default=None)):
    """ربط معاملة بالجلسة الحالية للكاشير."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # التحقق من وجود المعاملة
    tx = conn.execute("SELECT id, status FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    # تحديد الجلسة
    session_id = data.cashierSessionId
    if not session_id:
        srow = conn.execute(
            "SELECT id FROM cashier_sessions WHERE cashierId = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
            (cashier_id,)
        ).fetchone()
        if not srow:
            conn.close()
            raise HTTPException(status_code=400, detail="No open session. Open a session first.")
        session_id = srow["id"]

    # التحقق من وجود الجلسة
    s = conn.execute("SELECT id, cashierId FROM cashier_sessions WHERE id = ?", (session_id,)).fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")
    if s["cashierId"] != cashier_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Session belongs to another cashier")

    now = datetime.now(timezone.utc).isoformat()

    # إضافة assignment
    conn.execute(
        "INSERT INTO transaction_assignments (transactionId, cashierSessionId, assignedAt, status) VALUES (?,?,?,'ASSIGNED')",
        (tx_id, session_id, now)
    )

    # تحديث حالة المعاملة
    conn.execute("UPDATE transactions SET status = 'ASSIGNED' WHERE id = ?", (tx_id,))

    # تحديث lastActivity للجلسة
    conn.execute("UPDATE cashier_sessions SET lastActivity = ? WHERE id = ?", (now, session_id))

    conn.commit()
    conn.close()

    _tx_broadcast(tx_id, "ASSIGNED")

    print(f"[TX] Assigned: {tx_id[:12]}... -> session {session_id}")
    return {
        "success": True,
        "transactionId": tx_id,
        "sessionId": session_id,
        "status": "ASSIGNED",
        "assignedAt": now
    }


def _tx_set_status(tx_id: str, new_status: str, authorization: str):
    """دالة مشتركة لتحديث حالة المعاملة."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tx = conn.execute("SELECT id, status FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx["status"] == new_status:
        conn.close()
        return {"success": True, "transactionId": tx_id, "status": new_status, "unchanged": True}

    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE transactions SET status = ? WHERE id = ?", (new_status, tx_id))

    # تحديث assignment المرتبط
    conn.execute(
        "UPDATE transaction_assignments SET status = ?, matchedAt = ? WHERE transactionId = ? AND status = 'ASSIGNED'",
        (new_status, now, tx_id)
    )

    # تحديث الجلسة
    srow = conn.execute(
        "SELECT id FROM cashier_sessions WHERE cashierId = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
        (cashier_id,)
    ).fetchone()
    if srow:
        conn.execute("UPDATE cashier_sessions SET lastActivity = ? WHERE id = ?", (now, srow["id"]))

    conn.commit()
    conn.close()

    _tx_broadcast(tx_id, new_status)
    print(f"[TX] {new_status}: {tx_id[:12]}... by cashier {cashier_id}")
    return {"success": True, "transactionId": tx_id, "status": new_status, "updatedAt": now}


@app.post("/api/transactions/{tx_id}/confirm")
def tx_confirm(tx_id: str, authorization: str = Header(default=None)):
    return _tx_set_status(tx_id, "CONFIRMED", authorization)


@app.post("/api/transactions/{tx_id}/reject")
def tx_reject(tx_id: str, authorization: str = Header(default=None)):
    return _tx_set_status(tx_id, "REJECTED", authorization)


@app.get("/api/transactions/status/{status}")
def tx_by_status(status: str, limit: int = 100, authorization: str = Header(default=None)):
    """قائمة المعاملات حسب الحالة."""
    require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM transactions WHERE status = ? ORDER BY receivedAt DESC LIMIT ?",
        (status.upper(), limit)
    ).fetchall()]
    conn.close()
    return {"status": status.upper(), "count": len(rows), "items": rows}


@app.get("/api/transactions/{tx_id}/assignments")
def tx_assignments(tx_id: str, authorization: str = Header(default=None)):
    """سجل assignments لمعاملة."""
    require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM transaction_assignments WHERE transactionId = ? ORDER BY id DESC",
        (tx_id,)
    ).fetchall()]
    conn.close()
    return {"transactionId": tx_id, "assignments": rows}




@app.get("/api/ws-stats")
def ws_stats():
    """إحصائيات اتصالات WebSocket الحالية."""
    conns = cashier_manager.stats()
    return {
        "active": len(conns),
        "connections": conns
    }




# ============================================================
# Interactive Notifications (Phase 6A)
# ============================================================

class UnassignIn(BaseModel):
    reason: str


def _log_claim(conn, tx_id, cashier_id, session_id, action, prev_cashier=None, reason=None):
    """تسجيل حدث في transaction_claims."""
    conn.execute(
        "INSERT INTO transaction_claims (transactionId, cashierId, cashierSessionId, action, previousCashierId, reason, createdAt) VALUES (?,?,?,?,?,?,?)",
        (tx_id, cashier_id, session_id, action, prev_cashier, reason, datetime.now(timezone.utc).isoformat())
    )


def _broadcast_async(payload):
    """يبثّ رسالة WebSocket من داخل endpoint متزامن."""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(cashier_manager.broadcast(payload))
    except Exception:
        pass


@app.post("/api/transactions/{tx_id}/claim")
def tx_claim(tx_id: str, authorization: str = Header(default=None)):
    """كاشير يطالب بمعاملة. أول من يطالب يفوز."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # فحص المعاملة
    tx = conn.execute("SELECT id, status, claimedByCashierId FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    # فحص هل مُطالَب بها مسبقًا
    if tx["claimedByCashierId"] is not None:
        # هل أنا من طالب؟
        if tx["claimedByCashierId"] == cashier_id:
            conn.close()
            return {"success": True, "alreadyYours": True, "transactionId": tx_id}
        # شخص آخر سبقك
        other = conn.execute("SELECT username, displayName FROM cashiers WHERE id = ?", (tx["claimedByCashierId"],)).fetchone()
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=f"Already claimed by {other['username'] if other else 'unknown'}"
        )

    # فحص وجود جلسة مفتوحة
    session = conn.execute(
        "SELECT id FROM cashier_sessions WHERE cashierId = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
        (cashier_id,)
    ).fetchone()

    now = datetime.now(timezone.utc).isoformat()

    # Atomic claim: WHERE claimedByCashierId IS NULL
    cur = conn.execute(
        "UPDATE transactions SET claimedByCashierId = ?, claimedAt = ?, status = 'ASSIGNED' WHERE id = ? AND claimedByCashierId IS NULL",
        (cashier_id, now, tx_id)
    )

    if cur.rowcount == 0:
        # سبقك أحد (race condition)
        conn.close()
        raise HTTPException(status_code=409, detail="Already claimed by someone else")

    # إضافة assignment (إن كانت هناك جلسة)
    if session:
        conn.execute(
            "INSERT INTO transaction_assignments (transactionId, cashierSessionId, assignedAt, status) VALUES (?,?,?,'ASSIGNED')",
            (tx_id, session["id"], now)
        )
        conn.execute("UPDATE cashier_sessions SET lastActivity = ? WHERE id = ?", (now, session["id"]))

    # تسجيل في السجل
    _log_claim(conn, tx_id, cashier_id, session["id"] if session else None, "claim")

    conn.commit()

    # جلب بيانات الكاشير للبث
    cashier = conn.execute("SELECT username, displayName FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    conn.close()

    # بث للجميع
    _broadcast_async({
        "type": "transaction.claimed",
        "transactionId": tx_id,
        "claimedBy": {
            "cashierId": cashier_id,
            "username": cashier["username"] if cashier else None,
            "displayName": cashier["displayName"] if cashier else None
        },
        "at": now
    })

    print(f"[CLAIM] tx={tx_id[:12]}... by cashier {cashier_id}")
    return {
        "success": True,
        "transactionId": tx_id,
        "claimedBy": cashier_id,
        "claimedAt": now,
        "status": "ASSIGNED"
    }


@app.post("/api/transactions/{tx_id}/dismiss")
def tx_dismiss(tx_id: str, authorization: str = Header(default=None)):
    """كاشير يرفض إشعار معاملة (يختفي عنده فقط)."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tx = conn.execute("SELECT id, dismissedBy FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    # إضافة cashier_id إلى قائمة dismissedBy (JSON)
    import json as _json
    current = []
    if tx["dismissedBy"]:
        try:
            current = _json.loads(tx["dismissedBy"])
        except Exception:
            current = []

    if cashier_id not in current:
        current.append(cashier_id)
        conn.execute("UPDATE transactions SET dismissedBy = ? WHERE id = ?", (_json.dumps(current), tx_id))

    _log_claim(conn, tx_id, cashier_id, None, "dismiss")
    conn.commit()
    conn.close()

    print(f"[DISMISS] tx={tx_id[:12]}... by cashier {cashier_id}")
    return {"success": True, "transactionId": tx_id, "dismissedBy": cashier_id}


@app.post("/api/transactions/{tx_id}/unassign")
def tx_unassign(tx_id: str, data: UnassignIn, authorization: str = Header(default=None)):
    """Admin يُلغي ملكية معاملة (يعيدها NEW)."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # التحقق من الدور
    me = conn.execute("SELECT role FROM cashiers WHERE id = ?", (cashier_id,)).fetchone()
    if not me or me["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Admin role required")

    tx = conn.execute("SELECT id, claimedByCashierId FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")

    if tx["claimedByCashierId"] is None:
        conn.close()
        raise HTTPException(status_code=400, detail="Transaction is not claimed")

    prev = tx["claimedByCashierId"]
    now = datetime.now(timezone.utc).isoformat()

    # إعادة NEW
    conn.execute(
        "UPDATE transactions SET claimedByCashierId = NULL, claimedAt = NULL, status = 'NEW' WHERE id = ?",
        (tx_id,)
    )

    # تسجيل
    _log_claim(conn, tx_id, cashier_id, None, "unassign", prev_cashier=prev, reason=data.reason)

    conn.commit()
    conn.close()

    _broadcast_async({
        "type": "transaction.unassigned",
        "transactionId": tx_id,
        "previousCashierId": prev,
        "unassignedBy": cashier_id,
        "reason": data.reason,
        "at": now
    })

    print(f"[UNASSIGN] tx={tx_id[:12]}... prev_cashier={prev} by admin {cashier_id} reason={data.reason}")
    return {
        "success": True,
        "transactionId": tx_id,
        "previousCashierId": prev,
        "status": "NEW",
        "reason": data.reason
    }


@app.get("/api/transactions/{tx_id}/claims-log")
def tx_claims_log(tx_id: str, authorization: str = Header(default=None)):
    """سجل كل المحاولات على معاملة."""
    require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM transaction_claims WHERE transactionId = ? ORDER BY id ASC",
        (tx_id,)
    ).fetchall()]
    conn.close()
    return {"transactionId": tx_id, "count": len(rows), "log": rows}


@app.get("/api/transactions/claimed-by-me")
def tx_claimed_by_me(authorization: str = Header(default=None)):
    """قائمة المعاملات التي طالب بها الكاشير الحالي."""
    cashier_id = require_cashier(authorization)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM transactions WHERE claimedByCashierId = ? ORDER BY claimedAt DESC",
        (cashier_id,)
    ).fetchall()]
    conn.close()
    return {"cashierId": cashier_id, "count": len(rows), "items": rows}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" href="/static/logo.png">
<title>PaymentMonitor - لوحة التحكم</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    background: linear-gradient(135deg, #123B7A 0%, #1B4F9C 50%, #F07C22 100%);
    min-height: 100vh; padding: 20px; color: #1a1a1a;
  }
  .container { max-width: 1500px; margin: 0 auto; }

  /* HEADER */
  header {
    background: white; border-radius: 16px; padding: 18px 24px;
    margin-bottom: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  }
  .header-top {
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 12px;
  }
  h1 { color: #123B7A; font-size: 24px; }
  .server-addr { color: #666; font-size: 12px; margin-top: 4px; font-family: monospace; }
  .pills { display: flex; gap: 8px; flex-wrap: wrap; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 12px; border-radius: 20px;
    font-size: 12px; font-weight: 600;
    background: #f0f4fa; color: #4a5568;
    border: 1px solid #e0e8f5;
  }
  .pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #4a5568; }
  .pill.green { background: #e8f5e9; color: #2e7d32; border-color: #c8e6c9; }
  .pill.green .dot { background: #4CAF50; animation: pulse 2s infinite; }
  .pill.blue { background: #e3f2fd; color: #1565c0; border-color: #bbdefb; }
  .pill.blue .dot { background: #2196F3; }
  .pill.orange { background: #fff8e1; color: #e65100; border-color: #ffe0b2; }
  .pill.orange .dot { background: #F07C22; }
  .pill.red { background: #ffebee; color: #c62828; border-color: #ffcdd2; }
  .pill.red .dot { background: #f44336; }
  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.4;} }

  .header-actions {
    display: flex; gap: 8px; align-items: center;
    margin-top: 12px; flex-wrap: wrap;
  }
  .live-indicator {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 12px; border-radius: 20px;
    font-size: 12px; font-weight: 600;
    background: #f0f4fa; color: #666;
  }
  .live-indicator .live-dot {
    width: 8px; height: 8px; border-radius: 50%; background: #999;
  }
  .live-indicator.connected { background: #e8f5e9; color: #2e7d32; }
  .live-indicator.connected .live-dot { background: #4CAF50; animation: pulse 2s infinite; }
  .live-indicator.disconnected { background: #ffebee; color: #c62828; }
  .live-indicator.disconnected .live-dot { background: #f44336; }

  .btn {
    padding: 9px 18px; border: none; border-radius: 10px;
    cursor: pointer; font-weight: 600; font-family: inherit;
    font-size: 13px; transition: all .2s;
  }
  .btn-primary { background: #F07C22; color: white; }
  .btn-primary:hover { background: #d96d15; }
  .btn-secondary { background: #e0e8f5; color: #123B7A; }
  .btn-secondary:hover { background: #d0dcf0; }
  .btn-success { background: #4CAF50; color: white; }
  .btn-success:hover { background: #3d8b40; }
  .btn-danger { background: #F44336; color: white; }
  .btn-danger:hover { background: #d32f2f; }

  /* STATS */
  .stats {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px; margin-bottom: 16px;
  }
  .stat-card {
    background: white; border-radius: 12px; padding: 18px;
    text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  }
  .stat-card .label { color: #666; font-size: 13px; margin-bottom: 6px; }
  .stat-card .value {
    font-size: 26px; font-weight: 700; color: #123B7A;
  }
  .stat-card.accent .value { color: #F07C22; }
  .stat-card.green .value { color: #4CAF50; }
  .stat-card.red .value { color: #c62828; }

  /* FILTERS */
  .filters {
    background: white; border-radius: 12px; padding: 18px 20px;
    margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  }
  .filter-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px; margin-bottom: 12px;
  }
  .filter-group { display: flex; flex-direction: column; gap: 5px; }
  .filter-group label { font-size: 12px; color: #666; font-weight: 600; }
  .filter-group input, .filter-group select {
    padding: 9px 12px; border: 1px solid #ddd; border-radius: 8px;
    font-family: inherit; font-size: 13px; background: white;
  }
  .filter-actions { display: flex; gap: 8px; flex-wrap: wrap; }

  /* CHARTS */
  .charts {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 16px; margin-bottom: 16px;
  }
  .chart-card {
    background: white; border-radius: 12px; padding: 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  }
  .chart-card h3 { color: #123B7A; margin-bottom: 14px; font-size: 16px; }
  .bar { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
  .bar-label { min-width: 100px; font-size: 13px; font-weight: 600; }
  .bar-fill {
    height: 20px;
    background: linear-gradient(90deg, #123B7A, #F07C22);
    border-radius: 10px; min-width: 4px;
  }
  .bar-value { font-size: 12px; color: #666; }
  .perf-row {
    display: flex; justify-content: space-between;
    padding: 10px 0; border-bottom: 1px solid #f0f0f0;
  }
  .perf-row:last-child { border-bottom: none; }
  .perf-name { font-weight: 600; color: #123B7A; }
  .perf-stats { color: #666; font-size: 13px; }
  .perf-amount { color: #F07C22; font-weight: 700; }
  .perf-unassigned { color: #c62828; font-weight: 600; }
  @media (max-width: 768px) { .charts { grid-template-columns: 1fr; } }

  /* TABS */
  .tabs {
    display: flex; gap: 4px; margin-bottom: 0;
    background: white; border-radius: 12px 12px 0 0; padding: 8px 8px 0;
  }
  .tab-btn {
    padding: 10px 20px; border: none; background: transparent;
    color: #666; font-weight: 600; font-size: 14px; cursor: pointer;
    border-radius: 10px 10px 0 0; font-family: inherit;
    transition: all .2s;
  }
  .tab-btn:hover { background: #f5f8ff; color: #123B7A; }
  .tab-btn.active {
    background: #123B7A; color: white;
  }
  .tab-count {
    display: inline-block; min-width: 22px; padding: 1px 7px;
    border-radius: 10px; font-size: 11px; margin-right: 4px;
    background: rgba(255,255,255,0.25);
  }
  .tab-btn:not(.active) .tab-count { background: #e0e8f5; color: #123B7A; }

  /* TABLE */
  .table-toolbar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 18px; background: white;
    border-bottom: 1px solid #f0f0f0;
  }
  .table-toolbar-info { font-size: 13px; color: #666; font-weight: 600; }
  table {
    width: 100%; background: white; border-radius: 0 0 12px 12px;
    overflow: hidden; border-collapse: collapse;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  }
  th {
    background: #123B7A; color: white; padding: 12px 8px;
    text-align: right; font-weight: 600; font-size: 13px;
  }
  td { padding: 10px 8px; border-bottom: 1px solid #eee; font-size: 13px; }
  tr:hover { background: #f5f8ff; }
  td.amount { font-weight: bold; color: #F07C22; }
  td.wallet { font-weight: 600; color: #123B7A; }
  .empty { text-align: center; padding: 40px; color: #999; }

  .status-badge {
    display: inline-block; padding: 3px 10px; border-radius: 6px;
    font-size: 11px; font-weight: 600; color: white;
  }
  .status-NEW { background: #2196F3; }
  .status-ASSIGNED { background: #FF9800; }
  .status-CONFIRMED { background: #4CAF50; }
  .status-REJECTED { background: #F44336; }
  .status-CANCELLED { background: #9E9E9E; }

  .row-checkbox { width: 16px; height: 16px; cursor: pointer; accent-color: #F07C22; }

  .btn-archive-small {
    padding: 4px 10px; background: #f5f5f5; color: #666;
    border: 1px solid #ddd; border-radius: 6px;
    cursor: pointer; font-size: 11px; font-family: inherit;
  }
  .btn-archive-small:hover { background: #ffebee; color: #c62828; border-color: #ffcdd2; }

  .highlight-new { animation: highlight 3s ease-out; }
  @keyframes highlight {
    0% { background-color: #FFF3E0; }
    50% { background-color: #FFE0B2; }
    100% { background-color: transparent; }
  }

  /* MODAL */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
    z-index: 1000; align-items: center; justify-content: center;
  }
  .modal-overlay.active { display: flex; }
  .modal-box {
    background: white; border-radius: 16px; max-width: 600px; width: 92%;
    max-height: 90vh; overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  }
  .modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 18px 24px; background: linear-gradient(135deg, #123B7A, #1B4F9C);
    border-radius: 16px 16px 0 0;
  }
  .modal-header h2 { color: white; font-size: 18px; }
  .modal-close {
    background: rgba(255,255,255,0.2); color: white; border: none;
    width: 32px; height: 32px; border-radius: 50%; cursor: pointer;
    font-size: 16px;
  }
  .modal-close:hover { background: rgba(255,255,255,0.35); }
  .modal-body { padding: 24px; }
  .network-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }
  .net-item {
    background: #f5f8ff; padding: 12px; border-radius: 10px;
    text-align: center; border: 1px solid #e0e8ff;
  }
  .net-label { color: #666; font-size: 12px; margin-bottom: 4px; }
  .net-value { color: #123B7A; font-weight: bold; font-size: 14px; word-break: break-all; }
  .copy-row { display: flex; gap: 8px; margin-top: 6px; }
  .copy-row input {
    flex: 1; padding: 10px 12px; border: 1px solid #ddd;
    border-radius: 8px; background: #f9f9f9; font-family: monospace;
    font-size: 13px; direction: ltr;
  }
  .net-settings {
    display: flex; gap: 10px; align-items: center;
    padding-top: 14px; border-top: 1px solid #eee; margin-top: 14px;
  }
  .net-settings label { font-weight: 600; color: #123B7A; font-size: 13px; }
  .net-settings input, .net-settings select {
    padding: 9px 12px; border: 1px solid #ddd; border-radius: 8px;
    font-family: inherit; font-size: 13px;
  }
  .modal-footer {
    display: flex; gap: 10px; justify-content: flex-end;
    padding: 16px 24px; border-top: 1px solid #f0f0f0;
    background: #fafafa; border-radius: 0 0 16px 16px;
  }
  .qr-img-wrap {
    background: white; padding: 16px; border-radius: 12px;
    display: inline-block; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    margin-bottom: 16px; text-align: center;
  }
  .qr-img-wrap img { width: 240px; height: 240px; display: block; }
  .qr-info {
    background: #f5f8ff; padding: 12px 16px; border-radius: 10px;
    font-size: 13px; text-align: right; margin-top: 12px;
    border: 1px solid #e0e8ff;
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <div class="header-top">
      <div>
        <h1>💰 PaymentMonitor</h1>
        <div class="server-addr" id="headerServerAddr">—</div>
      </div>
      <div class="pills">
        <div class="pill green">
          <span class="dot"></span>
          <span>السيرفر</span>
          <strong>يعمل</strong>
        </div>
        <div class="pill blue">
          <span class="dot"></span>
          <span>هواتف</span>
          <strong id="pillPhonesCount">0</strong>
        </div>
        <div class="pill orange">
          <span class="dot"></span>
          <span>كاشير نشط</span>
          <strong id="pillCashiersCount">0</strong>
        </div>
        <div class="pill red">
          <span class="dot"></span>
          <span>غير مُسنَدة</span>
          <strong id="pillUnassignedCount">0</strong>
        </div>
      </div>
    </div>
    <div class="header-actions">
      <div class="live-indicator" id="liveIndicator">
        <span class="live-dot"></span>
        <span id="liveText">جاري الاتصال...</span>
      </div>
      <button class="btn btn-primary" onclick="openQrModal()">📱 ربط التطبيق</button>
      <button class="btn btn-secondary" onclick="openSettings()">⚙ إعدادات</button>
      <button class="btn btn-success" id="loginBtn" onclick="openLoginModal()">🔑 تسجيل دخول</button>
      <button class="btn btn-secondary" id="logoutBtn" onclick="logoutDashboard()" style="display:none;">🚪 خروج</button>
      <span id="dashboardUserInfo" style="color:#123B7A; font-weight:600; font-size:13px; align-self:center;"></span>
    </div>
  </header>

  <div class="stats">
    <div class="stat-card">
      <div class="label">عمليات اليوم</div>
      <div class="value" id="statTodayCount">—</div>
    </div>
    <div class="stat-card accent">
      <div class="label">مبلغ اليوم (YER)</div>
      <div class="value" id="statTodayAmount">—</div>
    </div>
    <div class="stat-card green">
      <div class="label">مؤكدة من الكاشير</div>
      <div class="value" id="statConfirmed">—</div>
    </div>
    <div class="stat-card red">
      <div class="label">غير مُسنَدة</div>
      <div class="value" id="statUnassigned">—</div>
    </div>
  </div>

  <div class="filters">
    <div class="filter-grid">
      <div class="filter-group">
        <label>من تاريخ</label>
        <input type="date" id="fromDate">
      </div>
      <div class="filter-group">
        <label>إلى تاريخ</label>
        <input type="date" id="toDate">
      </div>
      <div class="filter-group">
        <label>المحفظة</label>
        <select id="walletFilter"><option value="">الكل</option></select>
      </div>
      <div class="filter-group">
        <label>الكاشير</label>
        <select id="cashierFilter"><option value="">الكل</option></select>
      </div>
      <div class="filter-group">
        <label>الهاتف</label>
        <input type="text" id="phoneFilter" placeholder="رقم الهاتف">
      </div>
    </div>
    <div class="filter-actions">
      <button class="btn btn-primary" onclick="loadData()">🔍 تطبيق الفلتر</button>
      <button class="btn btn-secondary" onclick="resetFilters()">↺ إعادة تعيين</button>
      <button class="btn btn-success" onclick="exportToExcel()">📥 تصدير Excel</button>
      <button class="btn btn-secondary" onclick="alert('لطباعة تقرير الوردية، استخدم Cashier')">🖨️ تقرير الوردية</button>
    </div>
  </div>

  <div class="charts">
    <div class="chart-card">
      <h3>📊 توزيع المبالغ حسب المحفظة</h3>
      <div id="walletChart"><div style="color:#999;">جاري التحميل...</div></div>
    </div>
    <div class="chart-card">
      <h3>👥 أداء الكاشير</h3>
      <div id="perfList"><div style="color:#999;">جاري التحميل...</div></div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" id="tabActive" onclick="switchTab('active')">
      الحالة <span class="tab-count" id="tabActiveCount">0</span>
    </button>
    <button class="tab-btn" id="tabArchived" onclick="switchTab('archived')">
      المؤرشفة <span class="tab-count" id="tabArchivedCount">0</span>
    </button>
    <button class="tab-btn" id="tabCashiers" onclick="switchTab('cashiers')">
      👥 الكواشير <span class="tab-count" id="tabCashiersCount">0</span>
    </button>
  </div>

  <div class="table-toolbar">
    <div class="table-toolbar-info">
      <span id="tableInfo">—</span>
    </div>
    <button class="btn btn-primary" id="bulkArchiveBtn" onclick="archiveBulk()" disabled>
      📦 أرشفة المحدد (0)
    </button>
    <button class="btn btn-success" id="addCashierBtn" onclick="openCashierModal()" style="display:none;">
      ➕ إضافة كاشير
    </button>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:40px;"><input type="checkbox" class="row-checkbox" id="selectAll" onclick="toggleSelectAll(this)"></th>
        <th>المحفظة</th>
        <th>النوع</th>
        <th>المبلغ</th>
        <th>المرسل</th>
        <th>الهاتف</th>
        <th>الوقت</th>
        <th>الحالة</th>
        <th style="width:90px;">إجراء</th>
      </tr>
    </thead>
    <tbody id="tableBody">
      <tr><td colspan="9" class="empty">جاري التحميل...</td></tr>
    </tbody>
  </table>
</div>

<!-- QR Modal -->
<div class="modal-overlay" id="qrModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2>📱 ربط التطبيق</h2>
      <button class="modal-close" onclick="closeQrModal()">✕</button>
    </div>
    <div class="modal-body" style="text-align:center;">
      <div class="qr-img-wrap"><img id="qrImage" src="" alt="QR"></div>
      <div class="qr-info">
        <div>عنوان السيرفر: <strong id="qrServer">—</strong></div>
        <div>اسم الجهاز: <strong id="qrName">—</strong></div>
      </div>
      <div style="margin-top:14px;">
        <button class="btn btn-secondary" onclick="regenerateToken()">🔄 توليد جديد</button>
      </div>
    </div>
  </div>
</div>

<!-- Settings Modal -->
<div class="modal-overlay" id="settingsModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2>🌐 إعدادات الشبكة</h2>
      <button class="modal-close" onclick="closeSettings()">✕</button>
    </div>
    <div class="modal-body">
      <div class="network-grid">
        <div class="net-item"><div class="net-label">IP المحلي</div><div class="net-value" id="netIp">—</div></div>
        <div class="net-item"><div class="net-label">المنفذ</div><div class="net-value" id="netPort">—</div></div>
        <div class="net-item"><div class="net-label">اسم الجهاز</div><div class="net-value" id="netHost">—</div></div>
        <div class="net-item"><div class="net-label">عدد الأجهزة</div><div class="net-value" id="netDevices">—</div></div>
      </div>
      <div style="margin-bottom:14px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:6px;">عنوان لوحة التحكم:</label>
        <div class="copy-row">
          <input type="text" id="dashboardUrl" readonly>
          <button class="btn btn-primary" onclick="copyToClipboard('dashboardUrl', this)">📋 نسخ</button>
        </div>
      </div>
      <div class="net-settings">
        <label>IP الاستماع:</label>
        <select id="hostInput" style="min-width:180px; direction:ltr;"></select>
        <label>المنفذ:</label>
        <input type="number" id="portInput" min="1024" max="65535" style="width:100px;">
      </div>
      <div id="networkMsg" style="margin-top:12px; font-size:13px;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeSettings()">إلغاء</button>
      <button class="btn btn-primary" onclick="saveNetworkSettings()">💾 حفظ</button>
    </div>
  </div>
</div>

<script>
// ═══════════════════════════════════════════════════════
// PaymentMonitor Dashboard JS
// ═══════════════════════════════════════════════════════
var ws = null;
var wsReconnectTimer = null;
var wsReconnectAttempts = 0;
var currentTab = 'active';
var activeData = [];
var selectedIds = new Set();

// ─── Helpers ───
function formatNum(n) {
  if (n == null) return '0';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function formatTimeOnly(iso) {
  if (!iso) return '—';
  try {
    var d = new Date(iso);
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    return hh + ':' + mm;
  } catch (e) { return '—'; }
}

function esc(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, function(c) {
    return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
  });
}

// ─── Load Data ───
function loadData() {
  var wallet = document.getElementById('walletFilter').value;
  var from = document.getElementById('fromDate').value;
  var to = document.getElementById('toDate').value;
  var cashierId = document.getElementById('cashierFilter').value;
  var phone = document.getElementById('phoneFilter').value;

  var url = '/api/transactions?limit=500';
  if (wallet) url += '&wallet=' + encodeURIComponent(wallet);
  if (from) url += '&from_date=' + from;
  if (to) url += '&to_date=' + to + 'T23:59:59';

  Promise.all([
    fetch(url).then(function(r) { return r.json(); }),
    fetch('/api/stats/dashboard').then(function(r) { return r.json(); }),
    fetch('/api/wallets').then(function(r) { return r.json(); })
  ]).then(function(results) {
    var tx = results[0];
    var stats = results[1];
    var wallets = results[2];

    // Update stats cards
    document.getElementById('statTodayCount').textContent = stats.today_count || 0;
    document.getElementById('statTodayAmount').textContent = formatNum(stats.today_amount);
    document.getElementById('statConfirmed').textContent = stats.confirmed_count || 0;
    document.getElementById('statUnassigned').textContent = stats.unassigned_count || 0;

    // Header pills
    document.getElementById('pillPhonesCount').textContent = stats.phones_online || 0;
    document.getElementById('pillUnassignedCount').textContent = stats.unassigned_count || 0;

    // Wallets dropdown
    var sel = document.getElementById('walletFilter');
    var currentWallet = sel.value;
    sel.innerHTML = '<option value="">الكل</option>' + (wallets.wallets || []).map(function(w) {
      return '<option value="' + esc(w) + '">' + esc(w) + '</option>';
    }).join('');
    sel.value = currentWallet;

    // Filter transactions
    var items = (tx.items || []).filter(function(t) {
      if (phone && String(t.senderPhone || '').indexOf(phone) === -1) return false;
      if (cashierId && String(t.claimedByCashierId || '') !== cashierId) return false;
      return true;
    });

    activeData = items;
    renderTable(items);

    // Update tab count
    document.getElementById('tabActiveCount').textContent = items.length;

    // Render chart
    renderWalletChart(stats.by_wallet || []);

    // Load performance
    loadPerformance();
    // Load cashiers list
    loadCashiersList();
    // Load archived count
    loadArchivedCount();
  }).catch(function(e) { console.error('loadData:', e); });
}

function renderTable(items) {
  var tb = document.getElementById('tableBody');
  document.getElementById('tableInfo').textContent = items.length + ' معاملة';

  if (!items || items.length === 0) {
    tb.innerHTML = '<tr><td colspan="9" class="empty">لا توجد عمليات</td></tr>';
    return;
  }

  var html = '';
  for (var i = 0; i < items.length; i++) {
    var t = items[i];
    html += '<tr id="tx-' + esc(t.id) + '">';
    var isChecked = selectedIds.has(t.id) ? ' checked' : '';
    html += '<td><input type="checkbox" class="row-checkbox" data-id="' + esc(t.id) + '"' + isChecked + '></td>';
    html += '<td class="wallet">' + esc(t.walletName || '-') + '</td>';
    html += '<td>' + esc(t.transactionType || '-') + '</td>';
    html += '<td class="amount">' + formatNum(t.amount) + ' ' + esc(t.currency || '') + '</td>';
    html += '<td>' + esc(t.senderName || '-') + '</td>';
    html += '<td>' + esc(t.senderPhone || '-') + '</td>';
    html += '<td>' + formatTimeOnly(t.receivedAt) + '</td>';
    html += '<td><span class="status-badge status-' + esc(t.status || 'NEW') + '">' + esc(t.status || 'NEW') + '</span></td>';
    html += '<td><button class="btn-archive-small" onclick="archiveOne(this)" data-id="' + esc(t.id) + '">📦</button></td>';
    html += '</tr>';
  }
  tb.innerHTML = html;
  updateBulkBtn();
}

function renderWalletChart(byWallet) {
  var el = document.getElementById('walletChart');
  if (!byWallet || byWallet.length === 0) {
    el.innerHTML = '<div style="color:#999;">لا توجد بيانات</div>';
    return;
  }
  var maxCnt = Math.max.apply(null, byWallet.map(function(w) { return w.cnt; })) || 1;
  var html = '';
  for (var i = 0; i < byWallet.length; i++) {
    var w = byWallet[i];
    var pct = (w.cnt / maxCnt) * 100;
    html += '<div class="bar">';
    html += '<div class="bar-label">' + esc(w.walletName || 'غير معروف') + '</div>';
    html += '<div class="bar-fill" style="width: ' + pct + '%"></div>';
    html += '<div class="bar-value">' + w.cnt + ' عملية — ' + formatNum(w.total) + '</div>';
    html += '</div>';
  }
  el.innerHTML = html;
}

function loadPerformance() {
  var from = document.getElementById('fromDate').value;
  var to = document.getElementById('toDate').value;
  var url = '/api/cashiers/performance';
  var params = [];
  if (from) params.push('from_date=' + from);
  if (to) params.push('to_date=' + to);
  if (params.length) url += '?' + params.join('&');

  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById('perfList');
    if (!el) return;
    var html = '';
    var cashiers = data.cashiers || [];
    for (var i = 0; i < cashiers.length; i++) {
      var c = cashiers[i];
      html += '<div class="perf-row">';
      html += '<span class="perf-name">' + esc(c.displayName || c.username) + '</span>';
      html += '<span class="perf-stats">' + c.count + ' عمليات · <span class="perf-amount">' + formatNum(c.total) + '</span></span>';
      html += '</div>';
    }
    if (data.unassigned && data.unassigned.count > 0) {
      html += '<div class="perf-row">';
      html += '<span class="perf-name perf-unassigned">غير مُسنَدة</span>';
      html += '<span class="perf-stats">' + data.unassigned.count + ' عمليات · <span class="perf-amount">' + formatNum(data.unassigned.total) + '</span></span>';
      html += '</div>';
    }
    el.innerHTML = html || '<div style="color:#999; padding:10px;">لا توجد بيانات</div>';
  }).catch(function(e) { console.error('loadPerformance:', e); });
}

function loadCashiersList() {
  fetch('/api/cashiers').then(function(r) { return r.json(); }).then(function(data) {
    var sel = document.getElementById('cashierFilter');
    if (!sel) return;
    var current = sel.value;
    sel.innerHTML = '<option value="">الكل</option>' + (data.cashiers || []).map(function(c) {
      return '<option value="' + c.id + '">' + esc(c.displayName || c.username) + '</option>';
    }).join('');
    sel.value = current;
  }).catch(function(){});
}

function loadCashiersCount() {
  fetch('/api/cashiers/active').then(function(r) { return r.json(); }).then(function(d) {
    var el = document.getElementById('pillCashiersCount');
    if (el) el.textContent = d.count || 0;
  }).catch(function(){});
}

function loadArchivedCount() {
  fetch('/api/transactions/archived?limit=1').then(function(r) { return r.json(); }).then(function(d) {
    document.getElementById('tabArchivedCount').textContent = d.total || 0;
  }).catch(function(){});
}

// ─── Archive ───
function archiveOne(btn) {
  var txId = btn.dataset.id;
  if (!confirm('أرشفة هذه المعاملة؟')) return;
  fetch('/api/transactions/' + txId + '/archive', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function() { loadData(); })
    .catch(function(e) { alert('فشل: ' + e.message); });
}

function toggleSelectAll(cb) {
  var boxes = document.querySelectorAll('.row-checkbox[data-id]');
  for (var i = 0; i < boxes.length; i++) {
    boxes[i].checked = cb.checked;
    if (cb.checked) selectedIds.add(boxes[i].dataset.id);
    else selectedIds.delete(boxes[i].dataset.id);
  }
  updateBulkBtn();
}

document.addEventListener('change', function(e) {
  if (e.target && e.target.classList && e.target.classList.contains('row-checkbox') && e.target.dataset.id) {
    if (e.target.checked) selectedIds.add(e.target.dataset.id);
    else selectedIds.delete(e.target.dataset.id);
    updateBulkBtn();
  }
});

function updateBulkBtn() {
  var count = selectedIds.size;
  var btn = document.getElementById('bulkArchiveBtn');
  if (btn) {
    btn.disabled = count === 0;
    btn.textContent = '📦 أرشفة المحدد (' + count + ')';
  }
  var selectAll = document.getElementById('selectAll');
  if (selectAll) {
    var total = document.querySelectorAll('.row-checkbox[data-id]').length;
    selectAll.checked = (total > 0 && count === total);
  }
}

function archiveBulk() {
  var ids = Array.from(selectedIds);
  if (ids.length === 0) return;
  if (!confirm('أرشفة ' + ids.length + ' معاملة؟')) return;

  fetch('/api/transactions/archive-bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: ids })
  }).then(function(r) { return r.json(); }).then(function() {
    selectedIds.clear();
    var sa = document.getElementById('selectAll');
    if (sa) sa.checked = false;
    loadData();
  }).catch(function(e) { alert('فشل: ' + e.message); });
}

// ─── Tabs ───
function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tabActive').classList.toggle('active', tab === 'active');
  document.getElementById('tabArchived').classList.toggle('active', tab === 'archived');
  document.getElementById('tabCashiers').classList.toggle('active', tab === 'cashiers');

  var bulk = document.getElementById('bulkArchiveBtn');
  var addBtn = document.getElementById('addCashierBtn');

  if (tab === 'archived') {
    bulk.style.display = 'inline-block';
    addBtn.style.display = 'none';
    loadArchived();
  } else if (tab === 'cashiers') {
    bulk.style.display = 'none';
    addBtn.style.display = 'inline-block';
    loadCashiersTab();
  } else {
    bulk.style.display = 'inline-block';
    addBtn.style.display = 'none';
    loadData();
  }
}

function loadArchived() {
  fetch('/api/transactions/archived?limit=500').then(function(r) { return r.json(); }).then(function(data) {
    var tb = document.getElementById('tableBody');
    document.getElementById('tableInfo').textContent = data.total + ' معاملة مؤرشفة';
    document.getElementById('tabArchivedCount').textContent = data.total;

    if (!data.items || data.items.length === 0) {
      tb.innerHTML = '<tr><td colspan="9" class="empty">لا توجد معاملات مؤرشفة</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < data.items.length; i++) {
      var t = data.items[i];
      html += '<tr>';
      html += '<td></td>';
      html += '<td class="wallet">' + esc(t.walletName || '-') + '</td>';
      html += '<td>' + esc(t.transactionType || '-') + '</td>';
      html += '<td class="amount">' + formatNum(t.amount) + ' ' + esc(t.currency || '') + '</td>';
      html += '<td>' + esc(t.senderName || '-') + '</td>';
      html += '<td>' + esc(t.senderPhone || '-') + '</td>';
      html += '<td>' + formatTimeOnly(t.receivedAt) + '</td>';
      html += '<td><span class="status-badge status-' + esc(t.status || 'NEW') + '">' + esc(t.status || 'NEW') + '</span></td>';
      html += '<td><button class="btn-archive-small" onclick="unarchiveOne(this)" data-id="' + esc(t.id) + '">↺</button></td>';
      html += '</tr>';
    }
    tb.innerHTML = html;
  });
}

function unarchiveOne(btn) {
  var txId = btn.dataset.id;
  if (!confirm('إلغاء أرشفة هذه المعاملة؟')) return;
  fetch('/api/transactions/' + txId + '/unarchive', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function() { loadArchived(); })
    .catch(function(e) { alert('فشل: ' + e.message); });
}

// ─── Export ───
function exportToExcel() {
  var from = document.getElementById('fromDate').value;
  var to = document.getElementById('toDate').value;
  var wallet = document.getElementById('walletFilter').value;
  var cashierId = document.getElementById('cashierFilter').value;
  var params = [];
  if (from) params.push('from_date=' + from);
  if (to) params.push('to_date=' + to);
  if (wallet) params.push('wallet=' + encodeURIComponent(wallet));
  if (cashierId) params.push('cashier_id=' + cashierId);
  var url = '/api/export/transactions.csv' + (params.length ? '?' + params.join('&') : '');
  window.open(url, '_blank');
}

// ─── Filters ───
function resetFilters() {
  document.getElementById('walletFilter').value = '';
  document.getElementById('fromDate').value = '';
  document.getElementById('toDate').value = '';
  document.getElementById('cashierFilter').value = '';
  document.getElementById('phoneFilter').value = '';
  loadData();
}

// ─── Connection Status ───
function loadConnectionStatus() {
  fetch('/api/connection-status').then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById('appStatus');
    if (!el) return;
    if (data.connected) {
      el.className = 'status-app connected';
      el.textContent = 'التطبيق متصل';
    } else {
      el.className = 'status-app disconnected';
      el.textContent = 'التطبيق غير متصل';
    }
  }).catch(function(){});
}

// ─── Network Info ───
function loadNetworkInfo() {
  fetch('/api/network-info').then(function(r) { return r.json(); }).then(function(data) {
    var ipEl = document.getElementById('netIp');
    var portEl = document.getElementById('netPort');
    var hostEl = document.getElementById('netHost');
    var devEl = document.getElementById('netDevices');
    var dashEl = document.getElementById('dashboardUrl');
    var portInput = document.getElementById('portInput');
    var hdr = document.getElementById('headerServerAddr');

    if (ipEl) ipEl.textContent = data.local_ip;
    if (portEl) portEl.textContent = data.port;
    if (hostEl) hostEl.textContent = data.hostname;
    if (devEl) devEl.textContent = data.device_count;
    if (dashEl) dashEl.value = data.dashboard_url;
    if (portInput) portInput.value = data.port;
    if (hdr) hdr.textContent = data.local_ip + ':' + data.port;

    fetch('/api/available-ips').then(function(r) { return r.json(); }).then(function(ipsData) {
      var sel = document.getElementById('hostInput');
      if (sel) {
        sel.innerHTML = ipsData.ips.map(function(ip) {
          var label = ip === '0.0.0.0' ? '0.0.0.0 (كل)' : ip === '127.0.0.1' ? '127.0.0.1 (محلي)' : ip;
          var selected = ip === ipsData.current_host ? ' selected' : '';
          return '<option value="' + ip + '"' + selected + '>' + label + '</option>';
        }).join('');
      }
    }).catch(function(){});
  }).catch(function(e) { console.error('loadNetworkInfo:', e); });
}

// ─── WebSocket ───
function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) return;
  var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var url = proto + '//' + location.host + '/ws';

  try { ws = new WebSocket(url); }
  catch (e) { console.error('WS error:', e); return; }

  ws.onopen = function() {
    wsReconnectAttempts = 0;
    updateLiveIndicator(true, 'اتصال مباشر');
  };
  ws.onmessage = function(event) {
    try { handleWsMessage(JSON.parse(event.data)); }
    catch (e) { console.error('WS parse:', e); }
  };
  ws.onclose = function() {
    updateLiveIndicator(false, 'غير متصل');
    scheduleReconnect();
  };
  ws.onerror = function(e) { console.error('WS error:', e); };
}

function scheduleReconnect() {
  if (wsReconnectTimer) return;
  var delay = Math.min(30000, 3000 * Math.pow(1.5, wsReconnectAttempts));
  wsReconnectAttempts++;
  wsReconnectTimer = setTimeout(function() {
    wsReconnectTimer = null;
    connectWebSocket();
  }, delay);
}

function updateLiveIndicator(connected, text) {
  var el = document.getElementById('liveIndicator');
  var txt = document.getElementById('liveText');
  if (!el || !txt) return;
  el.className = 'live-indicator ' + (connected ? 'connected' : 'disconnected');
  txt.textContent = text;
}

function handleWsMessage(msg) {
  if (msg.type === 'transaction.new') {
    setTimeout(loadData, 500);
  } else if (msg.type === 'transaction.claimed' || msg.type === 'transaction.updated' || msg.type === 'transaction.unassigned') {
    setTimeout(loadData, 500);
  }
}

// ─── QR Modal ───
function openQrModal() {
  document.getElementById('qrModal').classList.add('active');
  fetch('/api/qr-code').then(function(r) { return r.json(); }).then(function(data) {
    document.getElementById('qrImage').src = data.qr_base64;
    document.getElementById('qrServer').textContent = data.info.server;
    document.getElementById('qrName').textContent = data.info.name;
  }).catch(function() {});
}
function closeQrModal() {
  document.getElementById('qrModal').classList.remove('active');
}
function regenerateToken() {
  if (!confirm('توليد توكن جديد؟')) return;
  fetch('/api/regenerate-token', { method: 'POST' }).then(function() { openQrModal(); });
}

// ─── Settings Modal ───
function openSettings() {
  document.getElementById('settingsModal').classList.add('active');
  loadNetworkInfo();
}
function closeSettings() {
  document.getElementById('settingsModal').classList.remove('active');
}
function copyToClipboard(id, btn) {
  var input = document.getElementById(id);
  input.select();
  navigator.clipboard.writeText(input.value).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✅';
    setTimeout(function() { btn.textContent = orig; }, 1500);
  });
}
function saveNetworkSettings() {
  var port = parseInt(document.getElementById('portInput').value);
  var host = document.getElementById('hostInput').value || '0.0.0.0';
  var msg = document.getElementById('networkMsg');

  if (!port || port < 1024 || port > 65535) {
    msg.innerHTML = '<span style="color:#c62828;">⚠ المنفذ غير صحيح</span>';
    return;
  }
  msg.innerHTML = '<span style="color:#666;">جارٍ الحفظ...</span>';

  fetch('/api/network-settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port: port, host: host, api_key: '' })
  }).then(function(r) { return r.json(); }).then(function() {
    msg.innerHTML = '<span style="color:#2e7d32;">✅ تم الحفظ</span>';
  }).catch(function() {
    msg.innerHTML = '<span style="color:#c62828;">❌ فشل</span>';
  });
}

// ─── Init ───
document.addEventListener('click', function(e) {
  var sm = document.getElementById('settingsModal');
  var qm = document.getElementById('qrModal');
  if (e.target === sm) closeSettings();
  if (e.target === qm) closeQrModal();
});
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closeSettings(); closeQrModal(); }
});


// ═══════════════════════════════════════════════════════
// Phase 9: Cashiers Management
// ═══════════════════════════════════════════════════════
var currentToken = null;

function setCurrentToken(t) { currentToken = t; }

function openCashierModal(cashierId) {
  var modal = document.getElementById('cashierModal');
  document.getElementById('cashierMsg').innerHTML = '';

  if (cashierId) {
    document.getElementById('cashierModalTitle').textContent = '✏️ تعديل كاشير';
    document.getElementById('cashierEditId').value = cashierId;
    document.getElementById('cashierUsername').disabled = true;
    document.getElementById('passwordGroup').style.display = 'none';
    fetch('/api/cashiers').then(function(r) { return r.json(); }).then(function(d) {
      var c = (d.cashiers || []).find(function(x) { return x.id === cashierId; });
      if (c) {
        document.getElementById('cashierUsername').value = c.username;
        document.getElementById('cashierDisplayName').value = c.displayName || '';
        document.getElementById('cashierRole').value = c.role || 'cashier';
      }
    });
  } else {
    document.getElementById('cashierModalTitle').textContent = '➕ إضافة كاشير';
    document.getElementById('cashierEditId').value = '';
    document.getElementById('cashierUsername').disabled = false;
    document.getElementById('cashierUsername').value = '';
    document.getElementById('cashierDisplayName').value = '';
    document.getElementById('cashierPassword').value = '';
    document.getElementById('cashierRole').value = 'cashier';
    document.getElementById('passwordGroup').style.display = 'block';
  }
  modal.classList.add('active');
}

function closeCashierModal() {
  document.getElementById('cashierModal').classList.remove('active');
}

function saveCashier() {
  var id = document.getElementById('cashierEditId').value;
  var username = document.getElementById('cashierUsername').value.trim();
  var displayName = document.getElementById('cashierDisplayName').value.trim();
  var password = document.getElementById('cashierPassword').value;
  var role = document.getElementById('cashierRole').value;
  var msg = document.getElementById('cashierMsg');

  if (!username) { msg.innerHTML = '<span style="color:#c62828;">⚠ أدخل اسم المستخدم</span>'; return; }
  if (!id && password.length < 6) { msg.innerHTML = '<span style="color:#c62828;">⚠ كلمة المرور 6+ أحرف</span>'; return; }

  var url = id ? '/api/cashiers/' + id : '/api/cashiers';
  var method = id ? 'PUT' : 'POST';
  var body = id
    ? { displayName: displayName, role: role }
    : { username: username, password: password, displayName: displayName, role: role };

  msg.innerHTML = '<span style="color:#666;">جارٍ الحفظ...</span>';

  fetch(url, {
    method: method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + (currentToken || '')
    },
    body: JSON.stringify(body)
  }).then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
    .then(function(res) {
      if (res.ok && res.data.success) {
        msg.innerHTML = '<span style="color:#2e7d32;">✅ تم الحفظ</span>';
        setTimeout(function() { closeCashierModal(); loadCashiersTab(); }, 800);
      } else {
        msg.innerHTML = '<span style="color:#c62828;">❌ ' + (res.data.detail || 'فشل') + '</span>';
      }
    }).catch(function(e) { msg.innerHTML = '<span style="color:#c62828;">❌ ' + e.message + '</span>'; });
}

function openPasswordModal(id) {
  document.getElementById('pwdCashierId').value = id;
  document.getElementById('newPassword').value = '';
  document.getElementById('pwdMsg').innerHTML = '';
  document.getElementById('passwordModal').classList.add('active');
}

function closePasswordModal() {
  document.getElementById('passwordModal').classList.remove('active');
}

function savePassword() {
  var id = document.getElementById('pwdCashierId').value;
  var pwd = document.getElementById('newPassword').value;
  var msg = document.getElementById('pwdMsg');
  if (pwd.length < 6) { msg.innerHTML = '<span style="color:#c62828;">⚠ 6+ أحرف</span>'; return; }

  msg.innerHTML = '<span style="color:#666;">جارٍ الحفظ...</span>';
  fetch('/api/cashiers/' + id + '/password', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + (currentToken || '')
    },
    body: JSON.stringify({ newPassword: pwd })
  }).then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
    .then(function(res) {
      if (res.ok && res.data.success) {
        msg.innerHTML = '<span style="color:#2e7d32;">✅ تم التغيير</span>';
        setTimeout(closePasswordModal, 800);
      } else {
        msg.innerHTML = '<span style="color:#c62828;">❌ ' + (res.data.detail || 'فشل') + '</span>';
      }
    }).catch(function(e) { msg.innerHTML = '<span style="color:#c62828;">❌ ' + e.message + '</span>'; });
}

function toggleCashier(id) {
  if (!confirm('تبديل حالة هذا الكاشير؟')) return;
  fetch('/api/cashiers/' + id + '/toggle', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + (currentToken || '') }
  }).then(function(r) { return r.json(); }).then(function() { loadCashiersTab(); });
}

function loadCashiersTab() {
  fetch('/api/cashiers').then(function(r) { return r.json(); }).then(function(d) {
    var tb = document.getElementById('tableBody');
    var list = d.cashiers || [];
    document.getElementById('tabCashiersCount').textContent = list.length;
    document.getElementById('tableInfo').textContent = list.length + ' كاشير';
    document.getElementById('bulkArchiveBtn').style.display = 'none';
    document.getElementById('addCashierBtn').style.display = 'inline-block';

    if (list.length === 0) {
      tb.innerHTML = '<tr><td colspan="9" class="empty">لا يوجد كواشير — اضغط "➕ إضافة كاشير"</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      var statusBadge = c.isActive
        ? '<span class="status-badge status-CONFIRMED">نشط</span>'
        : '<span class="status-badge status-REJECTED">معطّل</span>';
      var roleBadge = c.role === 'admin'
        ? '<span class="status-badge" style="background:#123B7A;">مدير</span>'
        : '<span class="status-badge" style="background:#F07C22;">كاشير</span>';
      var lastSeen = c.lastSeen ? formatTimeOnly(c.lastSeen) : '—';

      html += '<tr>';
      html += '<td>' + c.id + '</td>';
      html += '<td class="wallet">' + esc(c.username) + '</td>';
      html += '<td>' + esc(c.displayName || '-') + '</td>';
      html += '<td>' + roleBadge + '</td>';
      html += '<td>' + statusBadge + '</td>';
      html += '<td>' + lastSeen + '</td>';
      html += '<td colspan="3">';
      html += '<button class="btn-archive-small" onclick="openCashierModal(' + c.id + ')" style="background:#e3f2fd; color:#1565c0; border-color:#bbdefb;">✏️ تعديل</button> ';
      html += '<button class="btn-archive-small" onclick="openPasswordModal(' + c.id + ')" style="background:#fff8e1; color:#e65100; border-color:#ffe0b2;">🔑 كلمة المرور</button> ';
      html += '<button class="btn-archive-small" onclick="toggleCashier(' + c.id + ')" style="background:#f3e5f5; color:#6a1b9a; border-color:#e1bee7;">' + (c.isActive ? '🚫 تعطيل' : '✅ تفعيل') + '</button>';
      html += '</td>';
      html += '</tr>';
    }
    tb.innerHTML = html;
  });
}


// ═══════════════════════════════════════════════════════
// Dashboard Auth
// ═══════════════════════════════════════════════════════

function initDashboardAuth() {
  // استرجاع token من localStorage
  var saved = localStorage.getItem('dashboard_token');
  var user = localStorage.getItem('dashboard_user');
  var role = localStorage.getItem('dashboard_role');
  if (saved) {
    currentToken = saved;
    updateAuthUI(user, role);
  }
}

function updateAuthUI(user, role) {
  var loginBtn = document.getElementById('loginBtn');
  var logoutBtn = document.getElementById('logoutBtn');
  var info = document.getElementById('dashboardUserInfo');

  if (currentToken) {
    loginBtn.style.display = 'none';
    logoutBtn.style.display = 'inline-block';
    if (info) info.textContent = '👤 ' + (user || '') + ' (' + (role === 'admin' ? 'مدير' : 'كاشير') + ')';
  } else {
    loginBtn.style.display = 'inline-block';
    logoutBtn.style.display = 'none';
    if (info) info.textContent = '';
  }
}

function openLoginModal() {
  document.getElementById('loginMsg').innerHTML = '';
  document.getElementById('dashLoginUser').value = '';
  document.getElementById('dashLoginPwd').value = '';
  document.getElementById('loginModal').classList.add('active');
  document.getElementById('dashLoginUser').focus();
}

function closeLoginModal() {
  document.getElementById('loginModal').classList.remove('active');
}

function doDashboardLogin() {
  var username = document.getElementById('dashLoginUser').value.trim();
  var password = document.getElementById('dashLoginPwd').value;
  var msg = document.getElementById('loginMsg');

  if (!username || !password) {
    msg.innerHTML = '<span style="color:#c62828;">⚠ أدخل بيانات الدخول</span>';
    return;
  }

  msg.innerHTML = '<span style="color:#666;">جارٍ التحقق...</span>';

  fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username, password: password })
  }).then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
    .then(function(res) {
      if (res.ok && res.data.success && res.data.token) {
        currentToken = res.data.token;
        var u = res.data.cashier.username;
        var role = res.data.cashier.role;
        localStorage.setItem('dashboard_token', res.data.token);
        localStorage.setItem('dashboard_user', u);
        localStorage.setItem('dashboard_role', role);
        updateAuthUI(u, role);
        msg.innerHTML = '<span style="color:#2e7d32;">✅ مرحبًا ' + u + '</span>';
        setTimeout(function() {
          closeLoginModal();
          if (currentTab === 'cashiers') loadCashiersTab();
        }, 800);
      } else {
        msg.innerHTML = '<span style="color:#c62828;">❌ ' + (res.data.detail || 'بيانات خاطئة') + '</span>';
      }
    }).catch(function(e) {
      msg.innerHTML = '<span style="color:#c62828;">❌ ' + e.message + '</span>';
    });
}

function logoutDashboard() {
  if (!confirm('تسجيل الخروج من لوحة التحكم؟')) return;
  fetch('/api/auth/logout', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + (currentToken || '') }
  }).catch(function(){});

  currentToken = null;
  localStorage.removeItem('dashboard_token');
  localStorage.removeItem('dashboard_user');
  localStorage.removeItem('dashboard_role');
  updateAuthUI('', '');
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && document.getElementById('loginModal').classList.contains('active')) {
    doDashboardLogin();
  }
});

loadData();
loadConnectionStatus();
initDashboardAuth();
loadNetworkInfo();
connectWebSocket();
loadCashiersCount();
setInterval(loadData, 10000);
setInterval(loadCashiersCount, 8000);
setInterval(loadConnectionStatus, 5000);
setInterval(loadNetworkInfo, 30000);
setInterval(function() {
  if (!ws || ws.readyState !== WebSocket.OPEN) connectWebSocket();
}, 15000);
</script>

<!-- Cashier Modal -->
<div class="modal-overlay" id="cashierModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2 id="cashierModalTitle">➕ إضافة كاشير</h2>
      <button class="modal-close" onclick="closeCashierModal()">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="cashierEditId" value="">

      <div style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">اسم المستخدم *</label>
        <input type="text" id="cashierUsername" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;" placeholder="مثال: ahmed">
      </div>

      <div style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">الاسم المعروض</label>
        <input type="text" id="cashierDisplayName" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;" placeholder="مثال: أحمد الحميدي">
      </div>

      <div id="passwordGroup" style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">كلمة المرور * (6+ أحرف)</label>
        <input type="password" id="cashierPassword" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;" placeholder="••••••">
      </div>

      <div style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">الدور</label>
        <select id="cashierRole" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;">
          <option value="cashier">كاشير</option>
          <option value="admin">مدير</option>
        </select>
      </div>

      <div id="cashierMsg" style="margin-top:12px; font-size:13px; min-height:20px;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeCashierModal()">إلغاء</button>
      <button class="btn btn-primary" onclick="saveCashier()">💾 حفظ</button>
    </div>
  </div>
</div>

<!-- Password Modal -->
<div class="modal-overlay" id="passwordModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2>🔑 تغيير كلمة المرور</h2>
      <button class="modal-close" onclick="closePasswordModal()">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="pwdCashierId" value="">
      <div style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">كلمة المرور الجديدة (6+ أحرف)</label>
        <input type="password" id="newPassword" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;">
      </div>
      <div id="pwdMsg" style="font-size:13px;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closePasswordModal()">إلغاء</button>
      <button class="btn btn-primary" onclick="savePassword()">💾 حفظ</button>
    </div>
  </div>
</div>


<!-- Dashboard Login Modal -->
<div class="modal-overlay" id="loginModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2>🔑 تسجيل دخول لوحة التحكم</h2>
      <button class="modal-close" onclick="closeLoginModal()">✕</button>
    </div>
    <div class="modal-body">
      <p style="margin-bottom:14px; color:#666; font-size:13px;">
        سجّل دخول كمدير لإدارة الكواشير. الجلسة تُحفظ لمدة 30 يومًا.
      </p>
      <div style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">اسم المستخدم</label>
        <input type="text" id="dashLoginUser" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;" placeholder="admin">
      </div>
      <div style="margin-bottom:12px;">
        <label style="font-weight:600; color:#123B7A; font-size:13px; display:block; margin-bottom:4px;">كلمة المرور</label>
        <input type="password" id="dashLoginPwd" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:8px; font-family:inherit;" placeholder="••••••">
      </div>
      <div id="loginMsg" style="font-size:13px; min-height:20px;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeLoginModal()">إلغاء</button>
      <button class="btn btn-primary" onclick="doDashboardLogin()">🔑 تسجيل الدخول</button>
    </div>
  </div>
</div>

</body>
</html>"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


@app.get("/", response_class=HTMLResponse)
def root():
    return '<meta http-equiv="refresh" content="0; url=/dashboard">'


# ============================================================
# Run info
# ============================================================
def get_local_ip():
    """يعيد IP الاستماع من الإعدادات، أو يكتشف تلقائيًا."""
    host = SETTINGS.get("host", "")
    if host and host not in ("0.0.0.0", "127.0.0.1"):
        return host
    # fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn
    ip = get_local_ip()
    print()
    print("=" * 60)
    print("  PaymentMonitor Server")
    print("=" * 60)
    print(f"  Dashboard:  http://{ip}:5000/dashboard")
    print(f"  Local:      http://localhost:5000/dashboard")
    print(f"  API Docs:   http://{ip}:5000/docs")
    print("=" * 60)
    print()
    port = SETTINGS.get("port", 5000)
    uvicorn.run(app, host=SETTINGS.get("host", "0.0.0.0"), port=port)
