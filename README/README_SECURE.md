# ShowWise Backend - Secure Database Edition

## 🚀 Overview

ShowWise Backend has been completely upgraded with enterprise-grade security features:

| Feature | Before | After |
|---------|--------|-------|
| **Storage** | JSON files | SQLAlchemy ORM + Database |
| **Passwords** | Plaintext ❌ | PBKDF2-SHA256 + Salt ✅ |
| **2FA** | None ❌ | TOTP + Backup Codes ✅ |
| **OAuth** | None ❌ | Google & GitHub ✅ |
| **API Keys** | Plaintext ❌ | Hashed ✅ |
| **Audit Logging** | Basic ❌ | Comprehensive ✅ |
| **Rate Limiting** | None ❌ | Global + Per-Endpoint ✅ |
| **CSRF Protection** | Basic ❌ | Flask-WTF ✅ |

## 📋 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Setup Script
```bash
python setup_secure.py
```

This will:
- Generate `.env` configuration
- Initialize database
- Migrate existing JSON data
- Create admin user
- Display security checklist

### 3. Start Application
```bash
python app_db.py
```

Visit: `http://localhost:5000`

### 4. Enable 2FA
1. Login to dashboard
2. Go to Settings → Enable 2FA
3. Scan QR code with authenticator app
4. Save backup codes

## 📁 File Structure

### Core Files
```
app_db.py              # Main Flask application (secure version)
models.py              # SQLAlchemy database models
auth.py                # Authentication & security utilities
setup_secure.py        # Setup script
migrate_to_db.py       # Legacy JSON migration
```

### Configuration
```
.env                   # Environment variables (generated)
.env.example           # Configuration template
requirements.txt       # Python dependencies
```

### Documentation
```
SECURITY.md           # Comprehensive security documentation
DATABASE_MIGRATION.md # Database migration guide
DEPLOYMENT.md         # Production deployment guide
```

### Templates
```
templates/login.html  # OAuth + 2FA enabled
templates/verify_2fa.html  # 2FA verification
templates/error.html  # Error pages
```

## 🔐 Security Features

### Password Security
- **Hashing**: PBKDF2-SHA256 (NIST standard)
- **Salt**: 16 bytes per password
- **Iterations**: 200,000
- **Minimum Length**: 12 characters (enforced)

### Two-Factor Authentication
- **Authenticator**: TOTP (Google Authenticator, Authy, etc.)
- **Backup Codes**: 10 one-time codes per user
- **Time Window**: ±30 seconds

### Account Protection
- **Lockout**: 5 failed attempts → 30-minute lockout
- **Session**: 12-hour timeout + secure cookies
- **IP Tracking**: All logins logged with IP/User Agent

### API Security
- **Keys**: Cryptographically generated (32 bytes)
- **Secrets**: Hashed like passwords
- **Scopes**: Fine-grained permissions
- **Expiration**: Optional key expiry

### Network Security
- **HTTPS**: TLS 1.2+ (production required)
- **CORS**: Configurable origins
- **CSRF**: Token protection (Flask-WTF)
- **Rate Limiting**: 200 requests/day per IP

### OAuth Integration
- **Providers**: Google, GitHub
- **Token Verification**: Server-side validation
- **Automatic User Creation**: New users from OAuth
- **CSRF Protection**: State parameter validation

### Audit Logging
- **Events Tracked**:
  - Login/Logout
  - Password changes
  - 2FA setup/disable
  - API key creation/deletion
  - Failed attempts
  - Account lockouts
  - All changes logged with timestamp, IP, user agent

## 📊 Database Models

### User
- Username, Email
- Password (hashed)
- Role (admin, operator, user)
- 2FA: Secret, Backup Codes
- OAuth: Provider accounts
- Login tracking: IP, Timestamp, Attempts

### Organization
- Name, Slug, Subdomain
- Branding: Logo, Colors, Website
- Status: Active/Inactive

### ChatMessage
- Chat ID (conversation grouping)
- Content, Timestamps
- Read Status
- Author (user/admin)
- Reply threading

### APIKey
- Key (public), Secret (hashed)
- Scopes, Expiration
- Last used tracking

### Log
- Event type and level
- User and Organization
- IP address and User Agent
- JSON metadata
- Timestamp

### And More...
- Setting, UptimeRecord, KillSwitch

## 🔧 Configuration

### Environment Variables
```bash
# Security
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///showwise.db

# OAuth (optional)
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx

# Settings
FLASK_ENV=production
PORT=5000
CORS_ORIGINS=https://domain.com
```

### Database Options
```bash
# Development
DATABASE_URL=sqlite:///showwise.db

# PostgreSQL (recommended for production)
DATABASE_URL=postgresql://user:password@localhost/showwise

# MySQL
DATABASE_URL=mysql+pymysql://user:password@localhost/showwise
```

## 📝 API Usage

### Create API Key
```bash
# Login → Settings → API Keys → Create
# Get: key and secret (shown only once!)
```

### Use API Key
```bash
curl -X POST http://localhost:5000/api/chat/send \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "org_slug": "demo",
    "user_name": "John",
    "user_email": "john@example.com",
    "message": "Hello"
  }'
```

### Rate Limiting
```
Global: 200 requests/day per IP
Login: 10 attempts/minute
2FA: 5 attempts/minute
Chat: 100 messages/minute
API Key Create: 10/hour
```

## 🚀 Production Deployment

### Database
1. Use PostgreSQL (or MySQL)
2. Secure credentials in `.env`
3. Regular backups scheduled
4. Connection pooling configured

### HTTPS
1. Get certificate (Let's Encrypt)
2. Configure Nginx/Apache as reverse proxy
3. Redirect HTTP → HTTPS
4. HSTS header enabled

### Hosting
1. Use Gunicorn + Supervisor
2. Environment variables secure
3. Debug mode disabled
4. Error logging enabled

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete guide.

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [SECURITY.md](SECURITY.md) | Complete security documentation |
| [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md) | Migration from JSON to database |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Production deployment guides |

## 🔄 Migration from Old Version

### Old Version (app.py + JSON)
```bash
python app.py  # Uses JSON files in data/
```

### New Version (app_db.py + Database)
```bash
python setup_secure.py  # Automatic migration
python app_db.py        # Uses database
```

## ⚠️ Important Notes

### Never Do This
❌ Hardcode secrets  
❌ Store passwords in plaintext  
❌ Disable 2FA  
❌ Use default SECRET_KEY  
❌ Skip database backups  
❌ Disable HTTPS in production  

### Always Do This
✅ Use strong passwords (12+ chars)  
✅ Enable 2FA for all admins  
✅ Rotate API keys regularly  
✅ Back up database daily  
✅ Monitor audit logs  
✅ Keep dependencies updated  
✅ Use HTTPS in production  

## 🧪 Testing Checklist

- [ ] Application starts without errors
- [ ] Can login with existing credentials
- [ ] Password hashing verified (check database)
- [ ] 2FA setup works
- [ ] 2FA verification required on next login
- [ ] Backup codes work
- [ ] OAuth login works (if configured)
- [ ] API key creation works
- [ ] Chat messages save to database
- [ ] Audit logs record events
- [ ] Rate limiting prevents abuse
- [ ] Database backups scheduled

## 🆘 Troubleshooting

### "Database connection error"
```bash
# Check DATABASE_URL
echo $DATABASE_URL

# For SQLite
ls -lah showwise.db

# For PostgreSQL
psql $DATABASE_URL -c "SELECT 1"
```

### "ModuleNotFoundError: sqlalchemy"
```bash
pip install -r requirements.txt
pip install Flask-SQLAlchemy==3.1.1
```

### "Password doesn't work"
Passwords hashed during setup. If old password doesn't work:
```python
python -c "
from app_db import app, db
from models import User

with app.app_context():
    user = User.query.filter_by(username='admin').first()
    user.set_password('new-password-12chars')
    db.session.commit()
    print('Password reset')
"
```

### "2FA code not working"
- Verify system time is correct
- Check authenticator app is synced
- Ensure TOTP secret is correct format

### "OAuth not working"
- Verify callback URLs match exactly
- Check CLIENT_ID and CLIENT_SECRET
- Review application logs

## 📞 Support

For issues:
1. Check application logs
2. Review [SECURITY.md](SECURITY.md)
3. Check `.env` configuration
4. Verify database connectivity
5. Check documentation

## 📄 License

ShowWise Backend - Secure Edition  
Version: 2.0.0  
Updated: February 2026

---

**IMPORTANT**: This version requires database migration from JSON files. See [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md) for instructions.

**BACKUP YOUR DATA** before migration!
```bash
cp -r data data.backup
```
