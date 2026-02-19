# ShowWise Backend - Security Quick Reference

## 🚀 Quick Start (30 minutes)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Setup
python setup_secure.py
# → Creates .env
# → Initializes database
# → Creates admin user

# 3. Run
python app_db.py

# 4. Access
# http://localhost:5000
```

## 🔑 Default Passwords & Keys

### Initial Setup
- Username: (created during setup)
- Password: (12+ characters, you set)
- 2FA: Not enabled by default

### Enable 2FA
1. Login → Settings
2. Click "Enable 2FA"
3. Scan QR code with Google Authenticator/Authy
4. Enter 6-digit code
5. Save backup codes

### Create API Key
1. Login → API Keys
2. Click "Create Key"
3. Save key and secret (shown only once!)

## 🔐 Password Rules

```
✅ At least 12 characters
✅ Mix of uppercase, lowercase, numbers, symbols
✅ Not common words or patterns

❌ "password123" - Too weak
❌ "Admin@2024" - Too short
✅ "MyShell#Prompt2024!" - Good
```

## 🔄 Password Hashing

```python
# How passwords are stored:
user.set_password("MyPassword123!")
# Becomes: pbkdf2:sha256$200000$[salt]$[hash]

# Verification:
if user.check_password("MyPassword123!"):
    # Correct password
    login_successful()
```

## 🎫 2FA Codes

```
TOTP Code Format: XXXXXX (6 digits)
Time Window: ±30 seconds
Backup Code Format: XXXXXXXX (8 hex chars, one-time use)

Example Backup Codes:
- a1b2c3d4
- 5e6f7g8h
- (10 total, saved securely!)
```

## 🔑 API Key Format

```
Key Format: [32-byte URL-safe Base64]
Example: "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"

Secret Format: [64-byte URL-safe Base64] (hashed, not stored plaintext)
Example: "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGhIjKlMnOpQrStUvWxYz012345"

⚠️ Secrets are shown ONCE. Save securely!
```

## 📝 API Usage

```bash
# Send chat message with API key
curl -X POST http://localhost:5000/api/chat/send \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "org_slug": "demo",
    "user_name": "John",
    "user_email": "john@example.com",
    "message": "Hello"
  }'

# Response:
{
  "success": true,
  "message_id": 42,
  "chat_id": "abc123def456",
  "timestamp": "2026-02-20T10:30:45.123456"
}
```

## 🗄️ Database Models

### User
```python
class User:
    id: int
    username: str (unique)
    email: str (unique)
    password_hash: str (PBKDF2-SHA256)
    role: "admin" | "operator" | "user"
    is_active: bool
    is_2fa_enabled: bool
    totp_secret: str (Base32)
    backup_codes: [str] (one-time use)
    oauth_providers: {provider: {id, email, name}}
    last_login: datetime
    last_ip: str
    locked_until: datetime (null if not locked)
```

### Organization
```python
class Organization:
    id: int
    name: str
    slug: str (unique, used in URLs)
    subdomain: str (unique)
    url: str
    logo: str
    primary_color: str (#RRGGBB)
    secondary_color: str (#RRGGBB)
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

### APIKey
```python
class APIKey:
    id: int
    key: str (public, shown in UI)
    secret_hash: str (hashed, never shown)
    name: str
    user_id: int (who created it)
    organization_id: int
    scopes: ["read", "write", "admin"]
    is_active: bool
    last_used: datetime
    expires_at: datetime (optional)
    created_at: datetime
```

### ChatMessage
```python
class ChatMessage:
    id: int
    chat_id: str (groups conversations)
    organization_id: int
    user_id: int (if admin response)
    from_type: "user" | "admin"
    from_name: str
    from_email: str (optional)
    message: str
    is_read: bool
    read_by: str (username)
    reply_to: int (message ID)
    created_at: datetime
    updated_at: datetime
```

### Log
```python
class Log:
    id: int
    log_type: str ("login", "2fa", "api_key", etc)
    level: "info" | "warning" | "error" | "critical"
    user_id: int (optional)
    organization_id: int (optional)
    message: str
    ip_address: str
    user_agent: str
    metadata: dict (JSON data)
    created_at: datetime
```

## 🔐 Security Cheat Sheet

### Password Hashing Algorithm
```
PBKDF2-SHA256
Iterations: 200,000
Salt: 16 bytes (128 bits, random per password)
Output: 256-bit hash
Time to compute: ~100ms (prevents brute force)
```

### TOTP Implementation
```
Algorithm: HMAC-SHA1 (RFC 6238)
Time step: 30 seconds
Digits: 6
Backward compatible: ±1 time window (90 seconds total)

Example:
- Current time: 10:30:45
- Valid codes: from 10:30:00 to 10:31:00
```

### Account Lockout Policy
```
Max attempts: 5 failed logins
Lockout duration: 30 minutes
Reset on: Successful login
Tracking: IP address logged
```

### Rate Limiting
```
Global: 200 requests/day per IP
              50 per hour per IP

Per-Endpoint:
- Login: 10/minute
- 2FA: 5/minute  
- Password change: 5/hour
- API key create: 10/hour
- Chat: 100/minute

Returns: 429 Too Many Requests
```

## 🛢️ Database Queries

### Find User
```python
from app_db import app, db
from models import User

with app.app_context():
    user = User.query.filter_by(username='admin').first()
    print(user.email)
```

### Reset Password
```python
with app.app_context():
    user = User.query.filter_by(username='admin').first()
    user.set_password('NewPassword123!')
    db.session.commit()
    print("Password changed")
```

### View Audit Logs
```python
with app.app_context():
    logs = Log.query.order_by(Log.created_at.desc()).limit(100).all()
    for log in logs:
        print(f"{log.created_at} - {log.message} ({log.ip_address})")
```

### List API Keys
```python
with app.app_context():
    keys = APIKey.query.all()
    for key in keys:
        print(f"{key.name}: {key.key[:8]}... (created: {key.created_at})")
```

## 🌐 OAuth Setup

### Google OAuth

1. Go to https://console.cloud.google.com/
2. Create project
3. Create OAuth 2.0 credentials (Web app)
4. Add redirect URI: `http://localhost:5000/oauth/google/callback`
5. Copy Client ID and Secret to `.env`:
```
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
```

### GitHub OAuth

1. Go to https://github.com/settings/developers
2. Create OAuth App
3. Set Authorization callback URL: `http://localhost:5000/oauth/github/callback`
4. Copy Client ID and Secret to `.env`:
```
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx
```

## 🚨 Emergency Procedures

### Reset Admin Password
```bash
python -c "
from app_db import app, db
from models import User

with app.app_context():
    admin = User.query.filter_by(role='admin').first()
    admin.set_password('NewTempPassword123!')
    db.session.commit()
    print('Admin password reset to: NewTempPassword123!')
"
```

### Unlock Locked Account
```bash
python -c "
from app_db import app, db
from models import User

with app.app_context():
    user = User.query.filter_by(username='username').first()
    user.locked_until = None
    user.login_attempts = 0
    db.session.commit()
    print('Account unlocked')
"
```

### Disable 2FA (Emergency)
```bash
python -c "
from app_db import app, db
from models import User

with app.app_context():
    user = User.query.filter_by(username='username').first()
    user.is_2fa_enabled = False
    user.totp_secret = None
    user.backup_codes = []
    db.session.commit()
    print('2FA disabled')
"
```

### Backup Database
```bash
# SQLite
cp showwise.db showwise.db.backup

# PostgreSQL
pg_dump showwise | gzip > showwise_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore Database
```bash
# SQLite
cp showwise.db.backup showwise.db

# PostgreSQL
gunzip < showwise_20260220_120000.sql.gz | psql showwise
```

## 📊 Monitoring Commands

### Check Application Health
```bash
# Application status
curl http://localhost:5000/dashboard
# Should return 200 OK

# Database connection
python -c "from models import db; db.engine.execute('SELECT 1')"
```

### View Active Sessions
```python
from models import db, User

users = User.query.filter(User.last_login != None).all()
for user in users:
    print(f"{user.username}: {user.last_login} ({user.last_ip})")
```

### Count Events by Type
```python
from models import Log
from sqlalchemy import func

log_counts = db.session.query(
    Log.log_type, 
    func.count(Log.id)
).group_by(Log.log_type).all()

for log_type, count in log_counts:
    print(f"{log_type}: {count}")
```

## 🔒 Security Checklist

Before Production:
- [ ] Change SECRET_KEY
- [ ] Use PostgreSQL (not SQLite)
- [ ] Set DATABASE_URL
- [ ] Enable HTTPS
- [ ] Configure CORS_ORIGINS
- [ ] Set up backups
- [ ] Configure email notifications
- [ ] Enable monitoring
- [ ] Run security audit
- [ ] Test disaster recovery

## 📞 Common Issues

### "No module named 'sqlalchemy'"
```bash
pip install Flask-SQLAlchemy==3.1.1
```

### "Database locked"
```bash
# SQLite only - close all connections
pkill -f app_db.py
rm showwise.db-journal
```

### "Password doesn't work"
```bash
# Reset during migration
python -c "from app_db import app, db; from models import User; 
u = User.query.filter_by(username='admin').first(); 
u.set_password('new-password'); db.session.commit()"
```

### "2FA code invalid"
- Check system time is correct
- Try code from ±1 time period
- Check secret is correct format
- Use backup code as fallback

### "Rate limited"
- Wait specified duration
- Check X-RateLimit-Reset header
- Implement exponential backoff
- Use API key for higher limits

---

**See SECURITY.md for detailed documentation**

Last Updated: 2026-02-20
