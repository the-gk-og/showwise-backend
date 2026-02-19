# ShowWise Backend - Documentation Index

## 📚 Documentation Structure

All documentation files are organized in the `README/` folder. Here's what you need:

### 🚀 Getting Started (Start Here!)

1. **[README_SECURE.md](README/README_SECURE.md)** - 15 min read
   - Quick start guide
   - Before/after comparison
   - File structure overview
   - Configuration reference

2. **[SECURITY_CHEATSHEET.md](SECURITY_CHEATSHEET.md)** - 5 min lookup
   - Quick reference for developers
   - Common commands
   - Emergency procedures
   - API examples

### 🔐 Deep Dives

3. **[SECURITY.md](README/SECURITY.md)** - 30 min detailed read
   - Complete security architecture
   - Password hashing explained
   - 2FA implementation details
   - OAuth flow explanation
   - Account lockout mechanism
   - Audit logging system
   - CSRF protection
   - Rate limiting rules
   - Incident response procedures

4. **[DATABASE_MIGRATION.md](README/DATABASE_MIGRATION.md)** - 20 min step-by-step
   - Migration from old JSON-based system
   - Setup and configuration
   - Data migration process
   - OAuth setup instructions
   - 2FA enablement
   - Troubleshooting guide

5. **[DEPLOYMENT.md](README/DEPLOYMENT.md)** - Production deployment
   - Server setup (Linux/Ubuntu)
   - PostgreSQL configuration
   - Gunicorn setup
   - Nginx reverse proxy
   - SSL/TLS with Let's Encrypt
   - Security hardening
   - Monitoring and logging
   - Disaster recovery

### 📋 Reference Documents

6. **[UPGRADE_SUMMARY.md](README/UPGRADE_SUMMARY.md)** - Overview of all changes
   - Version history
   - Complete feature list
   - Migration checklist
   - Performance improvements
   - Compliance standards

7. **[API_KEY_USAGE.md](README/API_KEY_USAGE.md)** - API key management
   - Creating API keys
   - Adding scopes
   - Rate limiting
   - Security best practices

8. **[USER_MANAGEMENT.md](README/USER_MANAGEMENT.md)** - User administration
   - Creating users
   - Managing roles
   - Password reset
   - Account recovery

9. **[INSTANCE_MANAGEMENT.md](README/INSTANCE_MANAGEMENT.md)** - Instance operations
   - Starting/stopping
   - Configuration
   - Monitoring
   - Health checks

10. **[INTEGRATION_GUIDE.md](README/INTEGRATION_GUIDE.md)** - Integration examples
    - Chat API integration
    - OAuth integration
    - API key authentication
    - WebSocket streaming

## 🎯 Common Tasks

### I want to...

**...get started immediately**
→ Run `python setup_secure.py` then read [README_SECURE.md](README/README_SECURE.md)

**...understand the security**
→ Read [SECURITY.md](README/SECURITY.md)

**...migrate from old system**
→ Follow [DATABASE_MIGRATION.md](README/DATABASE_MIGRATION.md)

**...deploy to production**
→ Follow [DEPLOYMENT.md](README/DEPLOYMENT.md)

**...manage users and API keys**
→ See [USER_MANAGEMENT.md](README/USER_MANAGEMENT.md) and [API_KEY_USAGE.md](README/API_KEY_USAGE.md)

**...integrate chat API**
→ See [INTEGRATION_GUIDE.md](README/INTEGRATION_GUIDE.md)

**...look up a quick command**
→ Check [SECURITY_CHEATSHEET.md](SECURITY_CHEATSHEET.md)

## 🔧 Core Files

### Application
- `app_db.py` - Secure Flask application with all routes
- `models.py` - SQLAlchemy ORM models
- `auth.py` - Authentication utilities
- `setup_secure.py` - Interactive setup wizard

### Data
- `migrate_to_db.py` - Migration script (JSON → Database)

### Configuration
- `.env.example` - Environment template
- `requirements.txt` - Python dependencies

### Templates
- `templates/login.html` - Login page with OAuth
- `templates/verify_2fa.html` - 2FA verification page
- `templates/error.html` - Error page
- (+ other dashboard templates)

## 📊 Security Features Summary

✅ **Password Security**
- PBKDF2-SHA256 hashing (200,000 iterations)
- 16-byte salts per password
- Timing-constant comparison

✅ **2FA - TOTP**
- RFC 6238 compliant
- QR code setup
- 10 backup codes per user
- ±1 time window tolerance

✅ **2FA - Backup Codes**
- Cryptographically generated
- One-time use enforcement
- Automatic removal on use

✅ **OAuth Integration**
- Google OAuth 2.0
- GitHub OAuth 2.0
- Automatic user creation
- CSRF protection with state parameter

✅ **Account Security**
- Login attempt tracking
- 5-strike lockout (30 min)
- Automatic unlock on success
- IP logging

✅ **API Key Management**
- Cryptographic generation
- Secret hashing
- Scope-based permissions
- Expiration dates

✅ **Session Security**
- HttpOnly cookies
- Secure flag (production)
- SameSite=Lax
- 12-hour timeout

✅ **Rate Limiting**
- Global: 200/day, 50/hour
- Login: 10/minute
- 2FA: 5/minute
- Password change: 5/hour
- API key create: 10/hour
- Chat: 100/minute

✅ **CSRF Protection**
- Flask-WTF token validation
- All POST/PUT/DELETE protected

✅ **Audit Logging**
- 20+ event types
- IP address tracking
- User agent logging
- JSON metadata support

✅ **Security Headers**
- Strict-Transport-Security
- X-Content-Type-Options
- X-Frame-Options
- Content-Security-Policy
- Referrer-Policy

## 🛬 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run setup
python setup_secure.py

# 3. Start application
python app_db.py

# 4. Access
# http://localhost:5000
```

## 📞 Support

- Security issues: See [SECURITY.md](README/SECURITY.md#incident-response)
- Deployment issues: See [DEPLOYMENT.md](README/DEPLOYMENT.md#troubleshooting)
- General issues: See respective documentation file

## 📅 Last Updated

February 20, 2026

---

**Ready to get started?** → Run `python setup_secure.py` then see [README_SECURE.md](README/README_SECURE.md)
