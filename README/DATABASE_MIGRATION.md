# DATABASE MIGRATION & SETUP GUIDE

## Overview
ShowWise Backend has been upgraded from JSON file storage to a professional database with comprehensive security features:

- ✅ SQLAlchemy ORM database abstraction
- ✅ Password hashing with PBKDF2-SHA256 + salt
- ✅ TOTP 2FA with backup codes
- ✅ OAuth integration (Google, GitHub)
- ✅ API key management with hashed secrets
- ✅ Comprehensive audit logging
- ✅ Rate limiting on all endpoints
- ✅ CSRF protection

## Prerequisites

1. **Python 3.8+**
   ```bash
   python --version
   ```

2. **Key Generation** (macOS/Linux)
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

## Step 1: Update Dependencies

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install Flask==3.0.0 Flask-CORS==4.0.0 Flask-SQLAlchemy==3.1.1 \
            Flask-WTF==1.2.1 Werkzeug==3.0.1 python-dotenv==1.0.0 \
            gunicorn==21.2.0 bcrypt==4.1.1 pyotp==2.9.0 qrcode==7.4.2 \
            authlib==1.3.0 Flask-Limiter==3.5.0 requests==2.31.0
```

## Step 2: Configure Environment

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your configuration:**
   ```bash
   nano .env
   ```

3. **Generate SECRET_KEY:**
   ```bash
   python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env
   ```

4. **Set DATABASE_URL** (choose one):
   - **SQLite** (development/small): `sqlite:///showwise.db`
   - **PostgreSQL** (recommended): `postgresql://user:password@localhost/showwise`
   - **MySQL**: `mysql+pymysql://user:password@localhost/showwise`

## Step 3: Run Migration

1. **Backup current data:**
   ```bash
   cp -r data data.backup
   ```

2. **Run migration script:**
   ```bash
   python migrate_to_db.py
   ```

   This will:
   - Create all database tables
   - Import users from `data/users.json`
   - Migrate organizations from `data/organizations.json`
   - Transfer chat messages
   - Preserve all settings and logs

3. **Verify migration:**
   ```bash
   python -c "from app_db import app, db; app.app_context().push(); print(f'Users: {len(db.session.query(db.Model).all())}')"
   ```

## Step 4: Test the Application

1. **Start the app:**
   ```bash
   python app_db.py
   ```

2. **Access the application:**
   - Open http://localhost:5000
   - Login with existing credentials (passwords will have been hashed during migration)

3. **Test login:**
   - Username: (from your data/users.json)
   - Password: (your original password)

## Step 5: Set Up OAuth (Optional)

### Google OAuth
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "Google+ API"
4. Create "OAuth 2.0 ID" credential (Web application)
5. Add authorized redirect URIs:
   - `http://localhost:5000/oauth/google/callback` (dev)
   - `https://your-domain.com/oauth/google/callback` (prod)
6. Copy Client ID and Secret to `.env`:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   ```

### GitHub OAuth
1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Create "New OAuth App"
3. Set callback URL to:
   - `http://localhost:5000/oauth/github/callback` (dev)
   - `https://your-domain.com/oauth/github/callback` (prod)
4. Copy Client ID and Secret to `.env`:
   ```
   GITHUB_CLIENT_ID=your-client-id
   GITHUB_CLIENT_SECRET=your-client-secret
   ```

## Step 6: Enable 2FA for First Admin User

1. **Login to dashboard** with admin account
2. **Go to Settings**
3. **Enable 2FA:**
   - Click "Set up 2FA"
   - Scan QR code with authenticator app (Google Authenticator, Authy, etc.)
   - Enter 6-digit code to verify
   - Save backup codes in secure location

4. **Logout and test:**
   - Login again → should prompt for 2FA code

## Step 7: Create API Keys

1. **Login as admin**
2. **Go to API Keys section**
3. **Create new key:**
   - Set name and scopes
   - Save both key and secret (shown only once!)
   - Use in API requests:
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

## Step 8: Production Setup

### Database
1. **Use PostgreSQL in production:**
   ```bash
   # Install PostgreSQL
   sudo apt-get install postgresql postgresql-contrib

   # Create database and user
   sudo -u postgres createdb showwise
   sudo -u postgres createuser showwise_user
   sudo -u postgres psql -c "ALTER USER showwise_user WITH PASSWORD 'strong-password';"
   ```

2. **Set DATABASE_URL:**
   ```
   DATABASE_URL=postgresql://showwise_user:strong-password@localhost/showwise
   ```

### SSL/TLS
1. **Get certificate** (Let's Encrypt + Certbot):
   ```bash
   sudo apt-get install certbot
   sudo certbot certonly --standalone -d your-domain.com
   ```

2. **Enable HTTPS in app:**
   ```python
   app.run(ssl_context=('/path/to/cert.pem', '/path/to/key.pem'))
   ```

### Deployment
1. **Use Gunicorn:**
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app_db:app
   ```

2. **Use systemd service** (Linux):
   ```ini
   [Unit]
   Description=ShowWise Backend
   After=network.target

   [Service]
   Type=notify
   User=showwise
   WorkingDirectory=/opt/showwise
   Environment="PATH=/opt/showwise/venv/bin"
   ExecStart=/opt/showwise/venv/bin/gunicorn -w 4 app_db:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

3. **Use Nginx proxy:**
   ```nginx
   server {
       listen 443 ssl http2;
       server_name your-domain.com;

       ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

## Migration Checklist

- [ ] Dependencies installed
- [ ] `.env` file configured with SECRET_KEY and DATABASE_URL
- [ ] Database backup created (`data.backup/`)
- [ ] Migration script run successfully
- [ ] Application starts without errors
- [ ] Can login with existing credentials
- [ ] 2FA setup and verified
- [ ] API keys created and tested
- [ ] OAuth configured (if needed)
- [ ] HTTPS enabled (production)
- [ ] Regular backups scheduled
- [ ] Audit logs reviewed

## Rollback (If Needed)

If you need to revert to JSON storage:

1. **Restore from backup:**
   ```bash
   rm -rf showwise.db
   cp -r data.backup data
   ```

2. **Switch to old app:**
   ```bash
   # Use original app.py that uses JSON files
   python app.py  # Original version
   ```

3. **Delete new files:**
   ```bash
   rm app_db.py models.py auth.py migrate_to_db.py
   ```

## Troubleshooting

### "Database connection error"
```bash
# Check DATABASE_URL is correct
echo $DATABASE_URL

# For PostgreSQL, verify connection
psql postgresql://user:password@localhost/showwise -c "SELECT 1"
```

### "ModuleNotFoundError: No module named 'sqlalchemy'"
```bash
pip install Flask-SQLAlchemy==3.1.1
```

### "User password not working"
- Old passwords from JSON files are hashed during migration
- If password doesn't work, reset it:
  ```python
  from app_db import app, db
  from models import User
  with app.app_context():
      user = User.query.filter_by(username='admin').first()
      user.set_password('new-password')
      db.session.commit()
  ```

### "2FA not working"
- Verify system time is correct: `timedatectl`
- Ensure authenticator app is synced
- Check TOTP secret in database: Should be 32 characters

### "OAuth not connecting"
- Verify callback URL in OAuth provider settings matches exactly
- Check CLIENT_ID and CLIENT_SECRET in `.env`
- Review logs for detailed error messages

## API Migration

### Old API (JSON)
```bash
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"org_slug": "demo", "message": "Hello"}'
```

### New API (Database)
```bash
# With API Key (new)
curl -X POST http://localhost:5000/api/chat/send \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"org_slug": "demo", "message": "Hello"}'

# Without API Key (still works if origin allowed)
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"org_slug": "demo", "message": "Hello"}'
```

### Rate Limits
- Same endpoints now have rate limiting
- 100 requests/minute for `/api/chat/send`
- 200 requests/day per IP globally
- Hitting limits returns `429 Too Many Requests`

## Next Steps

1. **Read SECURITY.md** for detailed security documentation
2. **Configure email notifications** (future feature)
3. **Set up automated backups** (recommended)
4. **Enable monitoring** and alerting
5. **Schedule security audits** regularly
6. **Update documentation** for your team

## Support

For issues or questions:
1. Check logs: `tail -f logs/showwise.log`
2. Review SECURITY.md for security-related questions
3. Check .env file for configuration issues
4. Verify database connectivity

---

**Backup Original Data Before Migration!**
- `cp -r data data.backup`
- Keep for at least 30 days
