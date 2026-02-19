# ShowWise Backend Security Documentation

## Overview
This document details the comprehensive security measures implemented in ShowWise Backend Control Console.

## Password Security

### Password Hashing
- **Algorithm**: PBKDF2-SHA256 (via werkzeug.security)
- **Salt Length**: 16 bytes (128 bits)
- **Iterations**: 200,000 (werkzeug default)
- **Minimum Length**: 12 characters

**Implementation**:
```python
user.set_password(password)  # Hashes with salt
user.check_password(password)  # Verifies
```

### Password Requirements
- Minimum 12 characters (enforced on backend and frontend)
- Alphanumeric + special characters recommended
- Never stored in plaintext
- No password hints or recovery questions

## Two-Factor Authentication (2FA)

### TOTP (Time-based One-Time Password)
- **Library**: pyotp
- **Time Window**: 30-second intervals
- **Valid Window**: ±1 interval for clock skew tolerance
- **QR Code**: Generated for easy setup with authenticator apps

### Backup Codes
- **Count**: 10 codes per user
- **Format**: Hex encoded (8 characters)
- **Usage**: One-time use for emergency access
- **Storage**: Encrypted in database

### Implementation
```python
# Enable 2FA
secret, backup_codes = user.enable_totp()
qr_code = user.get_totp_qr_code()

# Verify code
if user.verify_totp(token):
    # Valid

# Use backup code
if user.use_backup_code(code):
    # Valid (automatically removed)
```

## Account Security

### Login Attempt Limiting
- **Max Attempts**: 5 failed attempts
- **Lockout Duration**: 30 minutes
- **Automatic Reset**: Successful login clears counter
- **Logging**: All failed attempts logged with IP and user agent

### Account Lockout
```python
lock_account(user)  # Locks after N failed attempts
unlock_account(user)  # Manual unlock (admin)
```

### Session Management
- **Secure Cookies**: HttpOnly, Secure, SameSite=Lax
- **HTTPS Only**: Enforced in production
- **Session Timeout**: 12 hours configurable
- **Auto-Refresh**: Session refreshed on each request
- **User Agent**: Validated to prevent session fixation

## API Security

### API Keys
- **Key Format**: URL-safe Base64 (32 bytes)
- **Secret Storage**: Hashed (PBKDF2-SHA256)
- **Scopes**: Fine-grained permissions (read, write, admin)
- **Expiration**: Optional expiry dates
- **Tracking**: Last used timestamp
- **Revocation**: Immediate upon deletion

### Authentication
```python
# Create API key
key = secrets.token_urlsafe(32)
secret = secrets.token_urlsafe(64)
api_key.set_secret(secret)  # Hashed before storage

# Verify API key
if api_key_obj.check_secret(secret):
    # Valid
```

### Rate Limiting
- **Global**: 200 requests/day, 50/hour per IP
- **Login**: 10 attempts/minute
- **2FA Verify**: 5 attempts/minute
- **API Key Create**: 10 per hour
- **Chat Send**: 100 per minute
- **Password Change**: 5 per hour

## OAuth Integration

### Supported Providers
- **Google**: OAuth 2.0 with OpenID Connect
- **GitHub**: OAuth 2.0

### Security Measures
- **State Parameter**: CSRF protection
- **Secure Redirection**: Verified callback URLs
- **Email Verification**: User email must match provider
- **Token Validation**: Server-side verification
- **No Token Storage**: Only user metadata stored
- **Automatic User Creation**: New users from OAuth

### Implementation
```python
@app.route('/oauth/<provider>')
def oauth_login(provider):
    return oauth[provider].authorize_redirect(...)

@app.route('/oauth/<provider>/callback')
def oauth_callback(provider):
    token = oauth[provider].authorize_access_token()
    user_info = verify_oauth_token(token, provider)
```

## Cryptographic Security

### Secrets Generation
- **crypto library**: Python's `secrets` module
- **Token Formats**:
  - API Keys: 32-byte URL-safe Base64
  - API Secrets: 64-byte URL-safe Base64
  - Backup Codes: 4-byte hex (single use)

### Password Hashing
- **Algorithm**: PBKDF2 (NIST approved)
- **Salt**: 16 bytes random per password
- **Iterations**: 200,000 (2024 standard)
- **Output**: 256-bit hash

## CSRF Protection

### Mechanism
- **Library**: Flask-WTF
- **Method**: Double-submit cookies
- **Token Location**: Form hidden field + session
- **Validation**: Automatic for POST/PUT/DELETE

### Usage
```html
<form method="POST">
  {{ csrf_token() }}
</form>
```

## Audit Logging

### Logged Events
- **Authentication**: Login, logout, 2FA setup/disable
- **Account Changes**: Password changes, security updates
- **API Operations**: Key creation/deletion
- **Chat Messages**: All messages and replies
- **Security Events**: Failed attempts, lockouts, OAuth errors
- **Admin Actions**: User management, system changes

### Log Data
- **Timestamp**: UTC timezone
- **User**: Username and ID
- **IP Address**: Client IP (with proxy support)
- **User Agent**: Browser/client identification
- **Event Type**: Categorized action
- **Metadata**: JSON with additional context

### Query Logs
```python
logs = Log.query.filter_by(log_type='login').order_by(Log.created_at.desc()).all()
```

## Database Security

### Models
- **SQLAlchemy ORM**: Prevents SQL injection
- **Parameterized Queries**: All queries escaped
- **Foreign Keys**: Referential integrity
- **Indexes**: Performance + security

### Password Hashing in DB
- **Never Plaintext**: Passwords hashed before storage
- **Per-User Salt**: Each password has unique salt
- **Hash Verification**: Time-constant comparison

### Sensitive Data
- **API Secrets**: Hashed like passwords
- **TOTP Secrets**: Stored encrypted
- **Session Data**: Encrypted cookies
- **User Metadata**: Non-sensitive only

## Certificate Security

### SSL/TLS
- **Protocol**: TLS 1.2+ minimum
- **Cipher Suites**: Strong, no weak algorithms
- **Certificate Pinning**: Recommended for mobile apps
- **HSTS**: HTTP Strict-Transport-Security headers

### Self-Signed Certificates (Development Only)
```bash
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

### Production Certificates
- Use proper CA-signed certificates
- Automatic renewal (Let's Encrypt supported)
- Monitor expiration dates

## Environment Configuration

### Secrets Management
```bash
# Generate strong SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Required in Production
- `SECRET_KEY`: Cryptographically secure
- `DATABASE_URL`: Secure database connection
- `GOOGLE_CLIENT_ID`/`SECRET`: From Google Cloud Console
- `GITHUB_CLIENT_ID`/`SECRET`: From GitHub Developer settings

### Never Hardcode
- API keys
- Database passwords
- OAuth secrets
- Encryption keys

## Security Best Practices

### For Administrators
1. **Regular Backups**: Daily automated backups
2. **Log Rotation**: Archive logs regularly
3. **Updates**: Keep dependencies updated
4. **Monitoring**: Monitor failed login attempts
5. **Audit**: Review logs for suspicious activity
6. **Passwords**: Enforce strong passwords
7. **2FA**: Encourage all users to enable 2FA
8. **API Keys**: Rotate API keys periodically

### For Users
1. **Passwords**: Use strong, unique passwords
2. **2FA**: Enable TOTP authentication
3. **Backup Codes**: Store safely offline
4. **Sessions**: Logout from untrusted devices
5. **API Keys**: Keep secrets confidential
6. **Updates**: Keep authenticator app updated

### For Developers
1. **Input Validation**: Validate all inputs
2. **SQL Injection**: Use ORM (SQLAlchemy)
3. **XSS Prevention**: Template auto-escaping
4. **CSRF**: Use CSRF tokens
5. **Secrets**: Never commit secrets to git
6. **Dependencies**: Audit third-party packages
7. **Code Review**: Peer review before merge

## Security Headers

### Automatically Set
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'
```

## Rate Limiting

### Rules
```python
# Global limits
200 requests per day per IP
50 requests per hour per IP

# Specific endpoints
Login: 10/minute
2FA: 5/minute
Password Change: 5/hour
API Key Create: 10/hour
Chat: 100/minute
```

## Incident Response

### If Breach Occurs
1. **Disable Access**: Lock affected accounts
2. **Force Reset**: Require password change
3. **Notify Users**: Email affected users
4. **Rotate Keys**: Force API key rotation
5. **Audit Logs**: Review for unauthorized access
6. **Monitor**: Watch for suspicious activity

### Data Retention
- **Logs**: 90 days by default
- **Chat**: Indefinite (configure as needed)
- **Audit Trail**: Should not be deleted

## Compliance

### Standards Followed
- **OWASP Top 10**: Addressed
- **NIST Guidelines**: Password/crypto standards
- **CWE**: Common Weakness Enumeration addressed
- **CVSS**: Vulnerability scoring considered

## Testing Security

### Not Included
- **No automatic security testing**: Manual security audits recommended
- **Penetration testing**: Hire professionals
- **Vulnerability scanning**: Use tools like Snyk, OWASP ZAP

### Recommended Tools
- **OWASP ZAP**: Web application security scanner
- **Snyk**: Dependency vulnerability scanner
- **SQLMap**: SQL injection testing
- **Burp Suite**: Comprehensive security testing

## Version Information
- **Component**: ShowWise Backend Control Console
- **Version**: 2.0.0 (Database + Security)
- **Updated**: 2026-02-20

## Support & Reporting
For security issues:
1. **Do Not** create public issues
2. Email: security@showwise.local
3. Include: Vulnerability details, impact, reproduction
4. Allow: 90 days for patches before disclosure
