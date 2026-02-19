# ⚡ Command Reference Card

**Print this or bookmark it!** Quick access to all important commands and info.

---

## 🚀 SETUP & RUNNING

```bash
# First time setup (interactive, step-by-step)
python setup_secure.py

# Start the application
python app_db.py

# Verify installation
python verify_setup.py

# Access application
http://localhost:5000
```

---

## 👤 USER MANAGEMENT

```bash
# Reset admin password
python -c "
from app_db import app, db
from models import User
with app.app_context():
    user = User.query.filter_by(username='admin').first()
    user.set_password('NewPassword123!')
    db.session.commit()
    print('Password reset')
"

# Unlock locked account
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

# Disable 2FA (emergency)
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

# List all users
python -c "
from app_db import app, db
from models import User
with app.app_context():
    for u in User.query.all():
        print(f'{u.username} ({u.email}) - {u.role}')
"
```

---

## 🗄️ DATABASE

```bash
# Backup (SQLite)
cp showwise.db showwise.db.backup

# Restore backup (SQLite)
cp showwise.db.backup showwise.db

# Check database exists
sqlite3 showwise.db ".tables"

# View users table
sqlite3 showwise.db "SELECT username, email, role FROM users"

# Count records
sqlite3 showwise.db "SELECT COUNT(*) FROM users"

# View recent logs
sqlite3 showwise.db "SELECT * FROM logs ORDER BY created_at DESC LIMIT 10"

# Check database size
ls -lh showwise.db
```

---

## 🔐 PASSWORD & SECURITY

```bash
# Password requirements
- 12+ characters minimum
- Mix of uppercase, lowercase, numbers, symbols
- NOT common words
- Example: MyApp#2026!Secure

# TOTP Code format
XXXXXX (6 digits, changes every 30 seconds)

# Backup code format
XXXXXXXX (8 hex characters, one-time use only)

# Account lockout rules
- 5 failed login attempts
- 30-minute automatic lockout
- Unlocks on successful login
- IP address logged
```

---

## 🔑 API KEY FORMAT

```bash
Key (shown): AbCdEfGhIjKlMnOpQrStUvWxYz0123456789
Secret (hidden): [hashed, never shown again]

# Create API key (in dashboard)
Settings → API Keys → Create Key

# Use API key
curl -H "X-API-Key: your-key-here" \
     http://localhost:5000/api/chat/send

# Scopes
- read: Can read data
- write: Can create/modify data
- admin: Full access
```

---

## 📊 FILE LOCATIONS

```
Project Root/
├── app_db.py          ← Main application (run this)
├── models.py          ← Database models
├── auth.py            ← Auth utilities
├── setup_secure.py    ← Setup wizard
├── migrate_to_db.py   ← Data migration
├── requirements.txt   ← Dependencies
├── .env               ← Configuration (created)
├── showwise.db        ← Database (created)
├── templates/
│   ├── login.html
│   ├── verify_2fa.html
│   └── dashboard.html
├── data/              ← Old JSON files (backup)
│   ├── users.json
│   ├── organizations.json
│   └── chat_messages.json
└── README/            ← Documentation
    ├── README_SECURE.md
    ├── SECURITY.md
    ├── DATABASE_MIGRATION.md
    ├── DEPLOYMENT.md
    ├── API_KEY_USAGE.md
    └── ...
```

---

## 🔒 SECURITY CHECKLIST

Before going live:

- [ ] Changed SECRET_KEY (not default)
- [ ] Used PostgreSQL (not SQLite)
- [ ] Set DATABASE_URL in .env
- [ ] Enabled HTTPS (in production)
- [ ] Set up CORS_ORIGINS correctly
- [ ] Admin user has strong password
- [ ] 2FA enabled for admin
- [ ] Backup codes saved offline
- [ ] Database backups configured
- [ ] Monitoring set up
- [ ] Firewall configured
- [ ] Regular updates scheduled

---

## 🌐 ENVIRONMENT VARIABLES (.env)

```bash
# Essential
SECRET_KEY=GeneratedDuring Setup
DATABASE_URL=sqlite:///showwise.db
FLASK_ENV=development
FLASK_PORT=5000

# OAuth (optional)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-secret
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-secret

# Production
FLASK_ENV=production
CORS_ORIGINS=https://yourdomain.com
SESSION_TIMEOUT=43200
```

---

## 📈 RATE LIMITS

```
Global:
- 200 requests/day per IP
- 50 requests/hour per IP

Per Endpoint:
- Login: 10/minute
- 2FA verification: 5/minute
- Password change: 5/hour
- API key creation: 10/hour
- Chat message: 100/minute

Response when limited:
429 Too Many Requests
```

---

## 🐛 TROUBLESHOOTING QUICK FIXES

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Address already in use | `FLASK_PORT=5001 python app_db.py` |
| Database locked | `pkill -f app_db.py && python app_db.py` |
| Can't login | Reset password (see USER MANAGEMENT) |
| Lost 2FA phone | Use backup code or disable 2FA |
| Forgot backup codes | Can't recover - disable 2FA |
| API key not working | Check scopes, check secret, check lockout |
| CORS error | Update CORS_ORIGINS in .env |
| Slow login | Check database size, optimize queries |

---

## 📚 DOCUMENTATION QUICK LINKS

| Need | Read |
|------|------|
| Get started fast | [QUICKSTART.md](QUICKSTART.md) |
| Understand system | [START_HERE.md](START_HERE.md) |
| Learn all security | [SECURITY.md](README/SECURITY.md) |
| Migrate data | [DATABASE_MIGRATION.md](README/DATABASE_MIGRATION.md) |
| Deploy to production | [DEPLOYMENT.md](README/DEPLOYMENT.md) |
| Manage API keys | [API_KEY_USAGE.md](README/API_KEY_USAGE.md) |
| Manage users | [USER_MANAGEMENT.md](README/USER_MANAGEMENT.md) |
| Quick lookup | [SECURITY_CHEATSHEET.md](SECURITY_CHEATSHEET.md) |
| Navigation | [INDEX.md](INDEX.md) |
| All changes | [FILE_INVENTORY.md](FILE_INVENTORY.md) |

---

## 🔗 IMPORTANT LINKS

```
Application: http://localhost:5000
Login: http://localhost:5000/login
Settings: http://localhost:5000/settings
Dashboard: http://localhost:5000/dashboard
Admin Panel: http://localhost:5000/users
API Docs: [See SECURITY_CHEATSHEET.md]
```

---

## ⏱️ TIME ESTIMATES

| Task | Time |
|------|------|
| Initial setup | 5-10 min |
| Enable 2FA | 3-5 min |
| Create API key | 2-3 min |
| User training | 10-15 min |
| Deploy production | 30-60 min |
| PostgreSQL setup | 20-30 min |
| SSL certificate | 10-15 min |

---

## 📱 PHONE APPS FOR 2FA

Recommended authenticator apps:
- Google Authenticator (iOS/Android) - Free
- Authy (iOS/Android) - Free, cloud backup
- Microsoft Authenticator (iOS/Android) - Free
- 1Password (iOS/Android) - Paid, includes password manager
- LastPass Authenticator (iOS/Android) - Free

---

## 🔐 PASSWORD STRENGTH EXAMPLES

**❌ Weak**:
- password123
- admin@2024
- Pass1234
- MyApp123

**✅ Strong**:
- MyShell#Prompt2024!
- SecureApp@v3.0#2026
- Admin$Pass#2024Key
- MyOrg!Secure#2024@Admin

**Check strength**: Use zxcvbn (available in setup_secure.py)

---

## 📞 SUPPORT RESOURCES

1. Check [SECURITY_CHEATSHEET.md](SECURITY_CHEATSHEET.md) for commands
2. Check [INDEX.md](INDEX.md) to find relevant doc
3. Check troubleshooting in relevant documentation
4. Review [SECURITY.md](README/SECURITY.md) for deep dives

---

## ⚡ SUPER QUICK START

```bash
# Copy and paste this:
pip install -r requirements.txt && \
python setup_secure.py && \
python app_db.py

# Then open: http://localhost:5000
```

---

**Last Updated**: February 20, 2026  
**Version**: 2.0 (Secure Edition)  
**Status**: Production Ready ✅

---

## 📋 PRINT VERSION

You can print this page for quick reference:
```bash
# On Linux/Mac
cat COMMAND_REFERENCE.md | lp  # or print to PDF

# On Windows  
type COMMAND_REFERENCE.md > PRN  # or copy to Word
```

---

**Bookmark this file!** 🔖
