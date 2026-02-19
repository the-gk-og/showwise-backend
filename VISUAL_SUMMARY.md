# 🎬 Visual Summary Sheet

**One-page reference for everything important**

---

## ⚡ SETUP IN 3 STEPS

```
Step 1: Install                Step 2: Setup               Step 3: Run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
$ pip install -r         $ python setup_secure.py  $ python app_db.py
  requirements.txt         
                         ✓ Creates .env            ✓ Database up
                         ✓ Initializes DB          ✓ App running
                         ✓ Migrates data           ✓ Ready at
                         ✓ Creates admin           ✓ localhost:5000
```

---

## 🆕 KEY DIFFERENCES

| **Old System** | **New System** |
|---|---|
| Password in plaintext 😱 | Password hashed 🔐 |
| No access tracking | Complete audit log 📝 |
| Single login step | 2 login steps (password + code) 📱 |
| Manual admin | Self-service 2FA ⚙️ |
| JSON files | Database 🗄️ |
| No encryption | All encrypted 🔒 |

---

## 🔐 SECURITY AT A GLANCE

```
PASSWORD HASHING                ACCOUNT LOCKOUT           2FA METHODS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Algorithm: PBKDF2-SHA256        Failed Attempts: 5       1️⃣  TOTP (6-digit)
Salt: 16 bytes                  Lockout: 30 minutes      2️⃣  Backup Code
Iterations: 200,000             Auto-unlock: On success  3️⃣  OAuth (Google/GitHub)
Time/attempt: ~100ms


RATE LIMITING                    AUDIT LOGGING            SESSION SECURITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Global: 200/day                  Events: 20+ types       HttpOnly: Yes
        50/hour                   IP logged: Always       Secure: Yes (prod)
Login: 10/minute                 User agent: Tracked     SameSite: Lax
2FA: 5/minute                    Metadata: JSON          Timeout: 12 hours
```

---

## 📱 LOGIN FLOW

```
1. Go to Login Page
         ↓
2. Enter Username + Password  ← Checked against DB hash
         ↓
3. 2FA Challenge Page  ← Choose:
   │
   ├─ TOTP Code (Google Authenticator) → Check 6-digit
   │
   ├─ Backup Code (If phone lost) → Single-use
   │
   └─ OAuth (Google/GitHub) → Skip password entirely
         ↓
4. Dashboard  ← Logged in!
```

---

## 🗝️ FILE QUICK REFERENCE

### Core Files
```
app_db.py          Main application (run this) ✓
models.py          Database models ✓
auth.py            Security functions ✓
setup_secure.py    Setup wizard ✓
migrate_to_db.py   Data migration ✓
```

### Docs
```
START_HERE.md              Complete overview ⭐
SECURITY_CHEATSHEET.md     Commands quick-ref ⚡
COMMAND_REFERENCE.md       All commands 📋
SECURITY.md                Deep dive 🔐
DEPLOYMENT.md              Production setup 🚀
```

---

## 📊 DATABASE MODELS

```
┌─────────────┐ ┌──────────────┐ ┌─────────────┐
│   User      │ │ Organization │ │  APIKey     │
├─────────────┤ ├──────────────┤ ├─────────────┤
│ username    │ │ name         │ │ key         │
│ password    │ │ slug         │ │ secret_hash │
│ email       │ │ logo         │ │ scopes      │
│ totp_secret │ │ colors       │ │ expires_at  │
│ backup_codes│ │ is_active    │ │ last_used   │
│ oauth_prov  │ │              │ │             │
└─────────────┘ └──────────────┘ └─────────────┘
       │                │                │
       └────────┬───────┴────────┬───────┘
                ↓                ↓
         ┌─────────────┐ ┌──────────────┐
         │  ChatMess   │ │   Log        │
         ├─────────────┤ ├──────────────┤
         │ chat_id     │ │ log_type     │
         │ message     │ │ ip_address   │
         │ is_read     │ │ user_agent   │
         │ created_at  │ │ metadata     │
         └─────────────┘ └──────────────┘
```

---

## 🎯 COMMON TASKS

```
┌─────────────────────────────────────────────────────────────────┐
│ TASK                  │ COMMAND / LOCATION                      │
├─────────────────────────────────────────────────────────────────┤
│ Enable 2FA            │ Dashboard → Settings → Enable 2FA       │
│ Create API Key        │ Dashboard → API Keys → Create Key       │
│ Reset Password        │ python -c "... set_password()" (see ref)│
│ Unlock Account        │ python -c "... unlock_account()" (see) │
│ Backup Database       │ cp showwise.db showwise.db.backup       │
│ View Logs             │ sqlite3 showwise.db "SELECT * FROM logs"│
│ List Users            │ sqlite3 showwise.db "SELECT * FROM users"│
│ Disable 2FA (emerg)   │ python -c "... is_2fa_enabled=False"   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚨 EMERGENCY PROCEDURES

```
LOST PHONE WITH 2FA?          FORGOT PASSWORD?              ACCOUNT LOCKED?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Use backup code            1. Contact admin              1. Wait 30 minutes
2. Disable 2FA                2. Admin resets password      2. Try again
3. Re-enable with new device  3. Login with new password    3. Or: admin unlocks

FORGOT BACKUP CODES?          LOST API SECRET?              DB CORRUPTED?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Disable 2FA (use password) 1. Create new API key         1. Restore from backup
2. Re-enable 2FA              2. Delete old one             2. Run migration again
3. SAVE backup codes!         3. Update apps               3. Regenerate keys
```

---

## ✅ SETUP VERIFICATION

```
After running setup, check:

□ showwise.db exists (database created)
□ .env file has SECRET_KEY
□ Can login with admin creds
□ 2FA page appears on login
□ Passwords are hashed (not plaintext)
□ Audit logs have entries

Run: python verify_setup.py
```

---

## 📈 RATE LIMIT HITS

```
If you get: 429 Too Many Requests

Check:
├─ Login attempts (10 per min max)
├─ 2FA attempts (5 per min max)
├─ Password changes (5 per hour max)
├─ API usage (depends on key scopes)
└─ Global IP limit (200 per day max)

Solution: Wait for window to reset, then try again
```

---

## 🌐 ENVIRONMENT VARIABLES

```
REQUIRED:
  SECRET_KEY=random-generated-string
  DATABASE_URL=sqlite:///showwise.db OR postgresql://...

OPTIONAL:
  GOOGLE_CLIENT_ID=your-id
  GOOGLE_CLIENT_SECRET=your-secret
  GITHUB_CLIENT_ID=your-id
  GITHUB_CLIENT_SECRET=your-secret
  FLASK_ENV=production (or development)
  FLASK_PORT=5000
  CORS_ORIGINS=https://yourdomain.com

Note: .env.example has all variables documented
```

---

## 📚 WHICH DOC TO READ?

```
                        START HERE
                             ↓
                    ┌────────────────────┐
                    │ What do I need?    │
                    └────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   Just start        Understand       Deploy to
   (5 min)           everything       production
        │                    │                    │
        ↓                    ↓                    ↓
   QUICKSTART.md     START_HERE.md      DEPLOYMENT.md
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ↓
                        Lost? Check
                    COMMAND_REFERENCE.md
                    or INDEX.md
```

---

## 🔒 PASSWORD REQUIREMENTS

```
❌ BAD EXAMPLES          ✅ GOOD EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
password123            MyApp#Secure2024!
admin@2024             SecurePass$2026v3
Password1              Admin$Pass#2024-Key
MyPass123              MyOrg!Secure#2024@v2

Requirements:
□ 12+ characters minimum
□ Mix of:  UPPERCASE + lowercase + numbers + symbols
□ NOT common words or patterns
□ NOT same as other accounts
```

---

## 🎯 API KEY FORMAT

```
Key (Visible):
┌──────────────────────────────────────────────────────┐
│ AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/= (shown in UI)│
└──────────────────────────────────────────────────────┘

Secret (Hidden):
┌──────────────────────────────────────────────────────────────┐
│ [LONG HASH - SHOWN ONCE, THEN HIDDEN FOREVER]               │
│ Save it! Can't be recovered.                                 │
└──────────────────────────────────────────────────────────────┘

Usage:
  curl -H "X-API-Key: your-key-here" \
       http://localhost:5000/api/chat/send
```

---

## 📞 QUICK HELP

```
"How do I...?"              Check Document
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Get started                 QUICKSTART.md
Enable 2FA                  SECURITY_CHEATSHEET.md
Create API key              API_KEY_USAGE.md
Reset password              COMMAND_REFERENCE.md
Deploy to prod              DEPLOYMENT.md
Understand security         SECURITY.md
See all commands            COMMAND_REFERENCE.md
Find a topic                INDEX.md
See file list               FILE_INVENTORY.md
```

---

## 🎉 YOU'RE READY!

```
✅ All code written
✅ All docs written
✅ All security implemented
✅ Just run setup

$ python setup_secure.py
$ python app_db.py

🚀 That's it!
```

---

**Bookmark this page!** 🔖

**Last Updated**: February 20, 2026
