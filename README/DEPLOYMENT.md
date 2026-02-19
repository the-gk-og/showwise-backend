# Production Deployment Guide

## Overview
This guide covers deploying ShowWise Backend to production with high security and availability.

## Prerequisites

- Linux server (Ubuntu 20.04+ recommended)
- Python 3.8+
- PostgreSQL 12+
- Nginx or Apache
- SSL certificate (Let's Encrypt)
- Domain name

## Step 1: Server Setup

### Create Application User
```bash
sudo useradd -m -s /bin/bash showwise
sudo usermod -aG sudo showwise
sudo su - showwise
```

### Clone and Setup Application
```bash
cd /opt
git clone <your-repo> showwise
cd showwise
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Create Database (PostgreSQL)
```bash
sudo -u postgres psql

CREATE DATABASE showwise;
CREATE USER showwise_user WITH PASSWORD 'strong-password-here';
ALTER ROLE showwise_user SET client_encoding TO 'utf8';
ALTER ROLE showwise_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE showwise_user SET default_transaction_deferrable TO on;
ALTER ROLE showwise_user SET default_transaction_read_only TO off;
GRANT ALL PRIVILEGES ON DATABASE showwise TO showwise_user;
\q
```

## Step 2: Environment Configuration

### Create .env File
```bash
cat > /opt/showwise/.env << 'EOF'
# ==================== SECURITY ====================
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATABASE_URL=postgresql://showwise_user:strong-password-here@localhost/showwise

# ==================== FLASK ====================
FLASK_ENV=production
FLASK_APP=app_db.py
PORT=5000

# CORS Origins
CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com

# ==================== OAUTH ====================
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

GITHUB_CLIENT_ID=your-github-id
GITHUB_CLIENT_SECRET=your-github-secret

# ==================== LOGGING ====================
LOG_LEVEL=WARNING
LOG_FILE=/opt/showwise/logs/showwise.log
EOF

chmod 600 /opt/showwise/.env
```

### Create Directories
```bash
mkdir -p /opt/showwise/{logs,backups}
chmod 755 /opt/showwise/{logs,backups}
```

## Step 3: Database Setup

### Initialize Database
```bash
source venv/bin/activate
python3 setup_secure.py
```

### Enable Backups
```bash
mkdir -p /opt/showwise/backups

# Create backup script
cat > /opt/showwise/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/showwise/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/showwise_$DATE.sql.gz"

pg_dump showwise | gzip > "$BACKUP_FILE"
chmod 600 "$BACKUP_FILE"

# Keep only last 30 days
find "$BACKUP_DIR" -name "showwise_*.sql.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE"
EOF

chmod +x /opt/showwise/backup_db.sh

# Schedule daily backup
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/showwise/backup_db.sh") | crontab -
```

## Step 4: SSL/TLS Setup

### Install Certbot
```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
```

### Get Certificate
```bash
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com
```

### Certificate Renewal
```bash
# Verify renewal works
sudo certbot renew --dry-run

# Add to crontab (automatic)
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet") | crontab -
```

## Step 5: Gunicorn Setup

### Create Gunicorn Config
```bash
cat > /opt/showwise/gunicorn_config.py << 'EOF'
import multiprocessing

bind = "127.0.0.1:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "/opt/showwise/logs/access.log"
errorlog = "/opt/showwise/logs/error.log"
loglevel = "warning"

# Process
processname = "showwise"
umask = 0o022

# Server mechanics
daemon = False
pidfile = "/opt/showwise/showwise.pid"
EOF

chmod 644 /opt/showwise/gunicorn_config.py
```

### Test Gunicorn
```bash
source venv/bin/activate
gunicorn -c gunicorn_config.py app_db:app
```

## Step 6: Systemd Service

### Create Service File
```bash
sudo cat > /etc/systemd/system/showwise.service << 'EOF'
[Unit]
Description=ShowWise Backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=notify
User=showwise
Group=www-data
WorkingDirectory=/opt/showwise
Environment="PATH=/opt/showwise/venv/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/showwise/venv/bin/gunicorn -c gunicorn_config.py app_db:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
KillSignal=SIGTERM
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable showwise
sudo systemctl start showwise
sudo systemctl status showwise
```

## Step 7: Nginx Configuration

### Create Nginx Config
```bash
sudo cat > /etc/nginx/sites-available/showwise << 'EOF'
upstream showwise {
    server 127.0.0.1:5000;
    keepalive 32;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.com www.your-domain.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # Logging
    access_log /var/log/nginx/showwise_access.log combined;
    error_log /var/log/nginx/showwise_error.log warn;

    # Gzip Compression
    gzip on;
    gzip_types text/plain text/css text/javascript application/json application/javascript;
    gzip_min_length 1000;

    # Proxy Configuration
    location / {
        proxy_pass http://showwise;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # Static Files (if any)
    location /static/ {
        alias /opt/showwise/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Deny Access
    location ~ /\. {
        deny all;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/showwise /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and restart
sudo nginx -t
sudo systemctl restart nginx
```

## Step 8: Monitoring & Logging

### Application Logging
```bash
# View logs
sudo journalctl -u showwise -f

# View Nginx logs
sudo tail -f /var/log/nginx/showwise_error.log
sudo tail -f /var/log/nginx/showwise_access.log
```

### Health Check Script
```bash
cat > /opt/showwise/health_check.sh << 'EOF'
#!/bin/bash

# Check application
if ! curl -sf https://your-domain.com/dashboard 2>/dev/null; then
    echo "Application unhealthy!"
    sudo systemctl restart showwise
fi

# Check database
if ! sudo -u postgres psql showwise -c "SELECT 1" 2>/dev/null; then
    echo "Database unhealthy!"
    alert_admin
fi

# Check disk space
DISK_USAGE=$(df /opt/showwise | awk 'NR==2 {print $5}' | cut -d'%' -f1)
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "Disk usage critical: $DISK_USAGE%"
    alert_admin
fi
EOF

chmod +x /opt/showwise/health_check.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/showwise/health_check.sh") | crontab -
```

### Configure Monitoring Tools
- **Uptime Monitoring**: StatusCake, UptimeRobot
- **Error Tracking**: Sentry, Rollbar
- **Performance**: New Relic, DataDog
- **Logs**: ELK Stack, Splunk

## Step 9: Security Hardening

### Firewall Setup
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
```

### Fail2Ban Installation
```bash
sudo apt-get install fail2ban

sudo cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
EOF

sudo systemctl restart fail2ban
```

### File Permissions
```bash
# Set proper ownership
sudo chown -R showwise:www-data /opt/showwise
sudo chmod 755 /opt/showwise
sudo chmod 700 /opt/showwise/.env
sudo chmod 700 /opt/showwise/logs
sudo chmod 700 /opt/showwise/backups

# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable cups
```

## Step 10: Performance Tuning

### PostgreSQL Optimization
```sql
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';

SELECT pg_reload_conf();
```

### Nginx Optimization
```bash
# Increase worker count
worker_processes auto;
worker_connections 2048;

# Change in /etc/nginx/nginx.conf
```

## Maintenance Tasks

### Daily
- Monitor logs
- Check disk space
- Verify backups

### Weekly
- Review audit logs
- Check certificate expiry
- Update dependencies

### Monthly
- Review security settings
- Analyze performance metrics
- Test disaster recovery

### Quarterly
- Penetration testing
- Security audit
- Database optimization

## Troubleshooting

### Application Won't Start
```bash
# Check logs
sudo journalctl -u showwise -n 50

# Check syntax
python3 app_db.py

# Check database connection
psql $DATABASE_URL -c "SELECT 1"
```

### High Memory Usage
```bash
# Check worker count
top -p $(pgrep -f gunicorn | head -1)

# Reduce workers if needed
# Edit gunicorn_config.py
```

### Database Slow Queries
```bash
# Enable slow query log
ALTER SYSTEM SET log_min_duration_statement = 1000;
SELECT pg_reload_conf();

# View slow queries
sudo -u postgres tail -f /var/log/postgresql/postgresql.log
```

## Scaling Considerations

### Load Balancing
```bash
# Use HAProxy for multiple instances
# Round-robin traffic across servers
# Sticky sessions for authenticated users
```

### Caching
```bash
# Redis for session storage
# Memcached for query caching
# CDN for static files
```

### Database
```bash
# Read replicas for reporting
# Write master for mutations
# Connection pooling with pgBouncer
```

## Disaster Recovery

### Backup Verification
```bash
# Test restore
pg_restore -d showwise_test /path/to/backup.sql.gz

# Verify data integrity
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM organizations;
```

### Point-in-Time Recovery
```bash
# PostgreSQL WAL archiving
# Can restore to any point in time
# Configure wal_archive_command
```

---

**Important**: Test this deployment in staging first!

For questions, refer to SECURITY.md and README_SECURE.md
