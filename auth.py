"""
Authentication utilities for ShowWise Backend
"""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify, has_request_context
from datetime import datetime, timedelta
import os
import secrets
import hashlib

MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', 5))
LOCKOUT_DURATION = timedelta(minutes=int(os.getenv('LOCKOUT_DURATION', 30)))
PENDING_2FA_TTL = timedelta(minutes=5)  # how long a password-verified login may wait for its 2FA code


def get_client_ip():
    """Client IP. Behind a reverse proxy set TRUSTED_PROXY_HOPS so app_db applies ProxyFix;
    request.remote_addr is then the real client. Raw forwarding headers are never trusted here."""
    if not has_request_context():
        return 'cli'
    return request.remote_addr or '127.0.0.1'


def get_user_agent():
    if not has_request_context():
        return ''
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
    """Return True if the account is currently locked. An expired lock is cleared here."""
    if not user.locked_until:
        return False
    if user.locked_until > datetime.utcnow():
        return True
    from models import db
    user.locked_until = None
    user.login_attempts = 0  # a fresh window after the lock runs out
    db.session.commit()
    return False


def lock_account(user):
    """Count a failed attempt; lock after the threshold."""
    from models import db
    is_account_locked(user)  # clears an expired lock before counting again
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


def verify_second_factor(user, code):
    """Check an authenticator code or a backup code.

    Returns (ok, reason) where reason is None, 'invalid' or 'reused'.
    Six digits is an authenticator code; anything else is treated as a backup code.
    """
    if not user.is_2fa_enabled:
        return True, None
    compact = ''.join(ch for ch in str(code or '') if ch not in ' -')
    if compact.isdigit() and len(compact) == 6:
        status = user.check_totp(compact)
        return status == 'ok', (None if status == 'ok' else status)
    return (True, None) if user.use_backup_code(code) else (False, 'invalid')


def start_session(user):
    """Create a fresh authenticated session (drops anything set before login)."""
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session.permanent = True


def begin_pending_2fa(user):
    """Remember that the password step passed and a second factor is still owed."""
    session.clear()
    session['pending_2fa_user'] = user.id
    session['pending_2fa_at'] = datetime.utcnow().timestamp()


def pending_2fa_user():
    """The user waiting on 2FA, or None if there is none or it timed out."""
    from models import User
    uid = session.get('pending_2fa_user')
    started = session.get('pending_2fa_at')
    if not uid or not started:
        return None
    if datetime.utcnow().timestamp() - float(started) > PENDING_2FA_TTL.total_seconds():
        session.pop('pending_2fa_user', None)
        session.pop('pending_2fa_at', None)
        return None
    return User.query.get(uid)


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
    """Decorator: only reachable while a password-verified login is waiting for its 2FA code."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if pending_2fa_user() is None:
            from flask import flash
            if 'pending_2fa_user' in session or 'pending_2fa_at' in session:
                session.pop('pending_2fa_user', None)
                session.pop('pending_2fa_at', None)
            flash('Your sign-in timed out. Enter your password again.', 'warning')
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