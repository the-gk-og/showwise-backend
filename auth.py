"""
Authentication utilities for ShowWise Backend
"""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from datetime import datetime, timedelta
import secrets
import hashlib

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=30)


def get_client_ip():
    """Get client IP, respecting reverse-proxy headers."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def get_user_agent():
    return (request.headers.get('User-Agent') or '')[:255]


def log_security_event(log_type, message, level='info', user_id=None, org_id=None, metadata=None):
    """Write a security/audit log entry to the database."""
    from models import db, Log
    entry = Log(
        log_type=log_type,
        level=level,
        user_id=user_id,
        organization_id=org_id,
        message=message,
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
        event_metadata=metadata or {},
    )
    db.session.add(entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def is_account_locked(user):
    """Return True if the account is currently locked."""
    return bool(user.locked_until and user.locked_until > datetime.utcnow())


def lock_account(user):
    """Increment failed attempts; lock after threshold."""
    from models import db
    user.login_attempts = (user.login_attempts or 0) + 1
    if user.login_attempts >= MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.utcnow() + LOCKOUT_DURATION
        log_security_event(
            'account_locked',
            f'Account locked after {MAX_LOGIN_ATTEMPTS} failed attempts',
            'warning',
            user_id=user.id,
        )
    db.session.commit()


def unlock_account(user):
    """Unlock account and reset counter."""
    from models import db
    user.login_attempts = 0
    user.locked_until = None
    db.session.commit()


def reset_login_attempts(user):
    """Called on successful login to reset counters and record last login."""
    from models import db
    user.login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    user.last_ip = get_client_ip()
    db.session.commit()


def verify_totp_token(user, token, use_backup=False):
    """Verify a TOTP or backup code. Returns True on success."""
    if not user.is_2fa_enabled:
        return True
    if use_backup:
        return user.use_backup_code(token)
    return user.verify_totp(token)


def login_required(f):
    """Decorator: redirect to /login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        from models import User
        user = User.query.get(session['user_id'])
        if not user or not user.is_active:
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: return 403 if user is not an admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        from models import User
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def require_2fa(f):
    """Decorator: ensure a pending 2FA session token exists."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'pending_2fa_user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def setup_oauth(app):
    """Configure Authlib OAuth clients for Google and GitHub."""
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth(app)

    google = oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    github = oauth.register(
        name='github',
        client_id=app.config.get('GITHUB_CLIENT_ID'),
        client_secret=app.config.get('GITHUB_CLIENT_SECRET'),
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'},
    )

    return oauth, google, github


# ── Utility functions used by migration / CLI scripts ─────────────────────────

def generate_api_key():
    return secrets.token_urlsafe(32)


def generate_api_secret():
    return secrets.token_urlsafe(64)


def hash_api_secret(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def hash_password(password):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def verify_password(password_hash, password):
    from werkzeug.security import check_password_hash
    return check_password_hash(password_hash, password)