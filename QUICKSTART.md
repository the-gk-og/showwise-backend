# ShowWise Backend - Quick Start (5 Minutes)

## ⚡ Install & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Interactive setup (asks questions)
python setup_secure.py

# 3. Start the app
python app_db.py
```

Done! App is running at `http://localhost:5000`

## 🔓 First Login

1. Use **username and password** you created during setup
2. If 2FA is enabled, enter 6-digit code from authenticator app
3. You're in! Welcome to the dashboard

## 📚 Next Steps

| I want to... | Read this | Time |
|---|---|---|
| Understand the system | [README_SECURE.md](README/README_SECURE.md) | 15 min |
| Set up 2FA | [SECURITY_CHEATSHEET.md](SECURITY_CHEATSHEET.md#-2fa-codes) | 5 min |
| Create an API key | [API_KEY_USAGE.md](README/API_KEY_USAGE.md) | 5 min |
| Deploy to production | [DEPLOYMENT.md](README/DEPLOYMENT.md) | 30 min |
| Deep dive into security | [SECURITY.md](README/SECURITY.md) | 45 min |

## ❓ Troubleshooting

**"ModuleNotFoundError: No module named..."**
```bash
pip install -r requirements.txt
python setup_secure.py
```

**"Address already in use"**
```bash
# Change port in setup or use:
FLASK_PORT=5001 python app_db.py
```

**"Database locked"**
```bash
# SQLite issue - restart the app
pkill -f app_db.py
python app_db.py
```

**"Forgot admin password?"**
```bash
# See SECURITY_CHEATSHEET.md → Emergency Procedures
```

## 🎯 What Was Just Set Up?

✅ Secure SQLite database (`showwise.db`)  
✅ Password hashing with PBKDF2-SHA256  
✅ 2FA ready (TOTP + backup codes)  
✅ Admin user account  
✅ Audit logging system  
✅ Rate limiting  
✅ CSRF protection  

## 📖 Full Documentation

See [INDEX.md](INDEX.md) for complete documentation guide.

---

🎉 **You're ready!** Start exploring the dashboard.
