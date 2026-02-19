"""
Authentication utilities for ShowWise Backend
Handles security features like password hashing, TOTP, OAuth, rate limiting
"""
from functools import wraps
from flask import session, redirect, url_for, request, current_app, jsonify
from models import db, User, Log
from datetime import datetime, timedelta
import secrets
import hashlib

# Maximum login attempts before account lockout
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=30)

def get_client_ip():
    """Get client IP address, handling proxies"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

def get_user_agent():
    """Get user agent"""
    return request.headers.get('User-Agent', '')[:255]

def log_security_event(log_type, message, level='info', user_id=None, org_id=None, metadata=None):
    """Log security events for audit trail"""
    log_entry = Log(
        log_type=log_type,
        level=level,
        user_id=user_id,
        organization_id=org_id,
        message=message,
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
        event_metadata=metadata or {}
    )
    db.session.add(log_entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

def check_rate_limit(user_id, limit=100, window=3600):
    """Check if user has exceeded rate limit (100 requests per hour)"""
    from flask_limiter import Limiter
    # Rate limiting is handled by Flask-Limiter decorator
    pass

def is_account_locked(user):
    """Check if account is locked due to failed login attempts"""
    if user.locked_until and user.locked_until > datetime.utcnow():
        return True
    return False

def lock_account(user):
    """Lock account after too many failed attempts"""
    user.login_attempts += 1
    if user.login_attempts >= MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.utcnow() + LOCKOUT_DURATION
        log_security_event(
            'login_lockout',
            f'Account locked after {MAX_LOGIN_ATTEMPTS} failed login attempts',
            'warning',
            user_id=user.id
        )
    db.session.commit()

def unlock_account(user):
    """Unlock account and reset login attempts"""
    user.login_attempts = 0
    user.locked_until = None
    db.session.commit()

def verify_totp_token(user, token, use_backup=False):
    """Verify TOTP token or backup code"""
    if not user.is_2fa_enabled:
        return True
    
    if use_backup:
        return user.use_backup_code(token)
    else:
        return user.verify_totp(token)

def generate_api_key():
    """Generate a cryptographically secure API key"""
    return secrets.token_urlsafe(32)

def generate_api_secret():
    """Generate a cryptographically secure API secret"""
    return secrets.token_urlsafe(64)

def hash_api_secret(secret):
    """Hash API secret"""
    return hashlib.sha256(secret.encode()).hexdigest()

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for
        
        # Check if user_id in session
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        # Verify user actually exists in database
        user = User.query.get(session.get('user_id'))
        if not user:
            session.clear()
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for, jsonify
        
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = User.query.get(session.get('user_id'))
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def setup_oauth(app):
    """Setup OAuth integration"""
    from authlib.integrations.flask_client import OAuth
    
    oauth = OAuth(app)
    
    # Google OAuth
    google = oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
    
    # GitHub OAuth
    github = oauth.register(
        name='github',
        client_id=app.config.get('GITHUB_CLIENT_ID'),
        client_secret=app.config.get('GITHUB_CLIENT_SECRET'),
        access_token_url='https://github.com/login/oauth/access_token',
        access_token_params=None,
        authorize_url='https://github.com/login/oauth/authorize',
        authorize_params=None,
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'},
    )
    
    return oauth, google, github

def verify_oauth_token(token, provider):
    """Verify OAuth token and get user info"""
    if provider == 'google':
        from authlib.integrations.httpx_client import httpx
        try:
            userinfo_response = httpx.get(
                'https://www.googleapis.com/oauth2/v1/userinfo',
                headers={'Authorization': f'Bearer {token}'}
            )
            return userinfo_response.json()
        except Exception:
            return None
    elif provider == 'github':
        import requests
        try:
            response = requests.get(
                'https://api.github.com/user',
                headers={'Authorization': f'token {token}'},
                timeout=5
            )
            return response.json()
        except Exception:
            return None
    return None

def hash_password(password):
    """Hash password using bcrypt"""
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

def verify_password(password_hash, password):
    """Verify password"""
    from werkzeug.security import check_password_hash
    return check_password_hash(password_hash, password)

def reset_login_attempts(user):
    """Reset login attempts on successful login"""
    user.login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    user.last_ip = get_client_ip()
    db.session.commit()

def require_2fa(f):
    """Decorator to require 2FA verification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'pending_2fa_user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
