"""
ShowWise Backend - Secure Control Console
Features: Database storage, password hashing, TOTP 2FA, OAuth, comprehensive security
All data stored in SQLAlchemy DB — no JSON files used at runtime.
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import json, os, queue, threading, secrets, logging
from datetime import datetime, timedelta
import uuid
import hashlib

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-change-in-production')

app.config.update(
    SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV') == 'production',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    SESSION_REFRESH_EACH_REQUEST=True,
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///showwise.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID'),
    GOOGLE_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET'),
    GITHUB_CLIENT_ID=os.getenv('GITHUB_CLIENT_ID'),
    GITHUB_CLIENT_SECRET=os.getenv('GITHUB_CLIENT_SECRET'),
    WTF_CSRF_TIME_LIMIT=3600,
)

csrf = CSRFProtect(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv('CORS_ORIGINS', '*').split(','),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-API-Key"],
        "expose_headers": ["Content-Type"],
        "max_age": 3600
    }
})

from models import db, User, Organization, APIKey, ChatMessage, Log, Setting, UptimeRecord, KillSwitch
from auth import (
    login_required, admin_required, require_2fa,
    get_client_ip, get_user_agent, log_security_event,
    is_account_locked, lock_account, unlock_account,
    verify_totp_token, reset_login_attempts, setup_oauth
)

db.init_app(app)

oauth, google_oauth, github_oauth = None, None, None
try:
    oauth, google_oauth, github_oauth = setup_oauth(app)
except Exception as e:
    print(f"OAuth setup failed (optional): {e}")

# ─── SSE broadcast ────────────────────────────────────────────────────────────
_chat_subscribers = []

def broadcast_chat_message(message):
    for q in list(_chat_subscribers):
        try:
            q.put_nowait(message)
        except Exception:
            pass

# External API routes use @csrf.exempt decorator directly on each route below.
# GET routes are always CSRF-exempt by Flask-WTF default behaviour.

# =============================================================================
# AUTH ROUTES
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password required', 'error')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()

        if user and is_account_locked(user):
            remaining = (user.locked_until - datetime.utcnow()).total_seconds()
            flash(f'Account locked. Try again in {int(remaining)} seconds.', 'warning')
            log_security_event('login_locked', f'Locked account login attempt: {username}', 'warning')
            return redirect(url_for('login'))

        if user and user.check_password(password) and user.is_active:
            if user.is_2fa_enabled:
                session['pending_2fa_user'] = user.id
                flash('Enter your 2FA code', 'info')
                return redirect(url_for('verify_2fa'))
            reset_login_attempts(user)
            session['username'] = user.username
            session['user_id'] = user.id
            session['role'] = user.role
            session.permanent = True
            log_security_event('login_success', f'User logged in: {username}', 'info', user_id=user.id)
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('dashboard'))

        if user:
            lock_account(user)
            log_security_event('login_failed', f'Failed login: {username}', 'warning', user_id=user.id)
        flash('Invalid credentials', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/verify-2fa', methods=['GET', 'POST'])
@require_2fa
@limiter.limit("5 per minute")
def verify_2fa():
    user_id = session.get('pending_2fa_user')
    user = User.query.get(user_id) if user_id else None

    if not user:
        flash('Session expired', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        token = request.form.get('token', '').replace(' ', '').replace('-', '')
        use_backup = request.form.get('use_backup') == 'on'

        if verify_totp_token(user, token, use_backup):
            reset_login_attempts(user)
            session['username'] = user.username
            session['user_id'] = user.id
            session['role'] = user.role
            session.permanent = True
            session.pop('pending_2fa_user', None)
            log_security_event('login_2fa_success', f'2FA verified: {user.username}', 'info', user_id=user.id)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))

        lock_account(user)
        flash('Invalid 2FA code', 'error')
        log_security_event('login_2fa_failed', f'Invalid 2FA: {user.username}', 'warning', user_id=user.id)
        return redirect(url_for('verify_2fa'))

    return render_template('verify_2fa.html')


@app.route('/logout')
def logout():
    username = session.get('username')
    user_id = session.get('user_id')
    session.clear()
    if username and user_id:
        log_security_event('logout', f'User logged out: {username}', 'info', user_id=user_id)
    flash('Logged out', 'success')
    return redirect(url_for('login'))


@app.route('/oauth/<provider>')
@limiter.limit("30 per hour")
def oauth_login(provider):
    if provider == 'google' and google_oauth:
        return google_oauth.authorize_redirect(url_for('oauth_callback', provider=provider, _external=True))
    elif provider == 'github' and github_oauth:
        return github_oauth.authorize_redirect(url_for('oauth_callback', provider=provider, _external=True))
    flash('OAuth provider not configured', 'error')
    return redirect(url_for('login'))


@app.route('/oauth/<provider>/callback')
def oauth_callback(provider):
    try:
        if provider == 'google' and google_oauth:
            token = google_oauth.authorize_access_token()
            user_info = token.get('userinfo')
        elif provider == 'github' and github_oauth:
            token = github_oauth.authorize_access_token()
            resp = github_oauth.get('user', token=token)
            user_info = resp.json() if hasattr(resp, 'json') else resp
        else:
            raise Exception('Invalid provider')

        email = user_info.get('email')
        name = user_info.get('name', user_info.get('login', 'User'))

        user = User.query.filter_by(email=email).first()
        if not user:
            username = email.split('@')[0] + secrets.token_hex(2)
            user = User(username=username, email=email, is_active=True)
            user.set_password(secrets.token_urlsafe(32))
            user.oauth_providers = {provider: user_info}
            db.session.add(user)
            db.session.commit()
            log_security_event('oauth_signup', f'New user via {provider}', 'info', user_id=user.id)
        else:
            if not user.oauth_providers:
                user.oauth_providers = {}
            user.oauth_providers[provider] = user_info
            db.session.commit()

        session['username'] = user.username
        session['user_id'] = user.id
        session['role'] = user.role
        session.permanent = True
        log_security_event('oauth_login', f'OAuth login via {provider}', 'info', user_id=user.id)
        flash(f'Logged in via {provider.title()}!', 'success')
        return redirect(url_for('dashboard'))

    except Exception as e:
        log_security_event('oauth_error', f'OAuth error: {e}', 'error')
        flash('OAuth login failed', 'error')
        return redirect(url_for('login'))


# =============================================================================
# DASHBOARD
# =============================================================================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    total_orgs = Organization.query.count()
    active_orgs = Organization.query.filter_by(is_active=True).count()
    inactive_orgs = total_orgs - active_orgs

    stats = {
        'total_organizations': total_orgs,
        'active_organizations': active_orgs,
        'inactive_organizations': inactive_orgs,
        'api_status': 'Online',
    }
    return render_template('dashboard.html',
                           username=user.username,
                           role=user.role,
                           stats=stats,
                           is_2fa_enabled=user.is_2fa_enabled)


# =============================================================================
# ORGANIZATION ROUTES
# =============================================================================

@app.route('/organizations')
@login_required
@admin_required
def organizations_list():
    orgs = Organization.query.order_by(Organization.name).all()
    # Build dict keyed by slug for template compatibility
    orgs_dict = {o.slug: _org_to_template_dict(o) for o in orgs}
    return render_template('organizations.html', organizations=orgs_dict)


@app.route('/organizations/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_organization():
    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        name = request.form.get('name', '').strip()

        if not slug or not name:
            flash('Slug and name are required', 'error')
            return redirect(url_for('add_organization'))

        if Organization.query.filter_by(slug=slug).first():
            flash(f'Slug "{slug}" is already taken', 'error')
            return redirect(url_for('add_organization'))

        org = Organization(
            slug=slug,
            name=name,
            subdomain=request.form.get('subdomain', slug).strip(),
            url=request.form.get('url', '').strip(),
            logo=request.form.get('logo', '').strip(),
            logo_size=request.form.get('logo_size', 'contain'),
            logo_padding=request.form.get('logo_padding', '12px'),
            primary_color=request.form.get('primary_color', '#0051ff').strip(),
            secondary_color=request.form.get('secondary_color', '#898989').strip(),
            description=request.form.get('description', '').strip(),
            website=request.form.get('website', '').strip(),
            is_active=True,
        )
        db.session.add(org)

        # Create default kill switch row
        ks = KillSwitch(organization=org, is_enabled=False)
        db.session.add(ks)

        db.session.commit()
        log_security_event('org_created', f'Organization created: {slug}', 'info',
                           user_id=session['user_id'])
        flash(f'Organization "{name}" created', 'success')
        return redirect(url_for('organizations_list'))

    return render_template('add_organization.html')


@app.route('/organizations/<slug>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_organization(slug):
    org = Organization.query.filter_by(slug=slug).first_or_404()

    if request.method == 'POST':
        org.name = request.form.get('name', org.name).strip()
        org.subdomain = request.form.get('subdomain', org.subdomain).strip()
        org.url = request.form.get('url', org.url).strip()
        org.logo = request.form.get('logo', org.logo).strip()
        org.logo_size = request.form.get('logo_size', org.logo_size)
        org.logo_padding = request.form.get('logo_padding', org.logo_padding)
        org.primary_color = request.form.get('primary_color', org.primary_color).strip()
        org.secondary_color = request.form.get('secondary_color', org.secondary_color).strip()
        org.description = request.form.get('description', org.description).strip()
        org.website = request.form.get('website', org.website).strip()
        org.updated_at = datetime.utcnow()
        db.session.commit()
        log_security_event('org_updated', f'Organization updated: {slug}', 'info',
                           user_id=session['user_id'])
        flash('Organization updated', 'success')
        return redirect(url_for('organizations_list'))

    return render_template('edit_organization.html', org=_org_to_template_dict(org), slug=slug)


@app.route('/organizations/<slug>/toggle')
@login_required
@admin_required
def toggle_organization(slug):
    org = Organization.query.filter_by(slug=slug).first_or_404()
    org.is_active = not org.is_active
    org.updated_at = datetime.utcnow()
    db.session.commit()
    state = 'activated' if org.is_active else 'deactivated'
    log_security_event('org_toggled', f'Organization {state}: {slug}', 'info',
                       user_id=session['user_id'])
    flash(f'Organization {state}', 'success')
    return redirect(url_for('organizations_list'))


@app.route('/organizations/<slug>/delete')
@login_required
@admin_required
def delete_organization(slug):
    org = Organization.query.filter_by(slug=slug).first_or_404()
    db.session.delete(org)
    db.session.commit()
    log_security_event('org_deleted', f'Organization deleted: {slug}', 'warning',
                       user_id=session['user_id'])
    flash('Organization deleted', 'success')
    return redirect(url_for('organizations_list'))


def _org_to_template_dict(org):
    """Convert Organization model to the dict shape used by templates."""
    return {
        'name': org.name,
        'slug': org.slug,
        'subdomain': org.subdomain or '',
        'url': org.url or '',
        'logo': org.logo or '',
        'logo_size': org.logo_size or 'contain',
        'logo_padding': org.logo_padding or '12px',
        'primary_color': org.primary_color or '#0051ff',
        'secondary_color': org.secondary_color or '#898989',
        'description': org.description or '',
        'website': org.website or '',
        'active': org.is_active,
        'created_at': org.created_at.isoformat() if org.created_at else '',
        'updated_at': org.updated_at.isoformat() if org.updated_at else '',
    }


# =============================================================================
# USER ROUTES
# =============================================================================

@app.route('/users')
@login_required
@admin_required
def users_list():
    users = User.query.order_by(User.username).all()
    # Build dict keyed by username for template compatibility
    users_dict = {}
    for u in users:
        users_dict[u.username] = {
            'username': u.username,
            'role': u.role,
            'created_at': u.created_at.isoformat() if u.created_at else '',
            'created_by': 'system',
            'active': u.is_active,
        }
    return render_template('users.html', users=users_dict)


@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        role = request.form.get('role', 'user')
        email = request.form.get('email', f'{username}@showwise.local').strip()

        if not username or not password:
            flash('Username and password required', 'error')
            return redirect(url_for('add_user'))

        if password != password_confirm:
            flash('Passwords do not match', 'error')
            return redirect(url_for('add_user'))

        if len(password) < 12:
            flash('Password must be at least 12 characters', 'error')
            return redirect(url_for('add_user'))

        if User.query.filter_by(username=username).first():
            flash(f'Username "{username}" already exists', 'error')
            return redirect(url_for('add_user'))

        user = User(username=username, email=email, role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_security_event('user_created', f'User created: {username}', 'info',
                           user_id=session['user_id'])
        flash(f'User "{username}" created', 'success')
        return redirect(url_for('users_list'))

    return render_template('add_user.html')


@app.route('/users/<username>/delete')
@login_required
@admin_required
def delete_user(username):
    if username == 'admin':
        flash('Cannot delete the admin user', 'error')
        return redirect(url_for('users_list'))

    user = User.query.filter_by(username=username).first_or_404()
    db.session.delete(user)
    db.session.commit()
    log_security_event('user_deleted', f'User deleted: {username}', 'warning',
                       user_id=session['user_id'])
    flash(f'User "{username}" deleted', 'success')
    return redirect(url_for('users_list'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password_page():
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not user.check_password(current_pw):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('change_password_page'))

        if new_pw != confirm_pw:
            flash('Passwords do not match', 'error')
            return redirect(url_for('change_password_page'))

        if len(new_pw) < 12:
            flash('Password must be at least 12 characters', 'error')
            return redirect(url_for('change_password_page'))

        user.set_password(new_pw)
        db.session.commit()
        log_security_event('password_changed', 'Password changed', 'info', user_id=user.id)
        flash('Password changed successfully', 'success')
        return redirect(url_for('dashboard'))

    return render_template('change_password.html')


# =============================================================================
# SETTINGS
# =============================================================================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # Store global settings using org_id=None convention (key-value in Setting table)
        _set_global_setting('api_enabled', 'api_enabled' in request.form)
        _set_global_setting('require_auth', 'require_auth' in request.form)
        _set_global_setting('allow_public_read', 'allow_public_read' in request.form)
        _set_global_setting('rate_limit', int(request.form.get('rate_limit', 100)))
        flash('Settings saved', 'success')
        return redirect(url_for('settings'))

    settings_obj = _get_global_settings()
    return render_template('settings.html', settings=settings_obj)


def _get_global_settings():
    """Return a dict of global settings with sensible defaults."""
    defaults = {
        'api_enabled': True,
        'require_auth': False,
        'allow_public_read': True,
        'rate_limit': 100,
        'version': '1.0.0',
    }
    # We store global settings with organization_id of the first org, or without one using a sentinel.
    # Simplest: store under a special "global" key per setting with org_id=None workaround.
    # SQLAlchemy unique constraint is (org_id, key) so we need an org. Use id=0 sentinel via raw query.
    from sqlalchemy import text
    rows = db.session.execute(
        text("SELECT key, value FROM settings WHERE organization_id IS NULL")
    ).fetchall()
    result = dict(defaults)
    for row in rows:
        try:
            result[row[0]] = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        except Exception:
            result[row[0]] = row[1]
    return result


def _set_global_setting(key, value):
    from sqlalchemy import text
    existing = db.session.execute(
        text("SELECT id FROM settings WHERE organization_id IS NULL AND key = :key"),
        {'key': key}
    ).fetchone()
    val_str = json.dumps(value)
    if existing:
        db.session.execute(
            text("UPDATE settings SET value = :val WHERE organization_id IS NULL AND key = :key"),
            {'val': val_str, 'key': key}
        )
    else:
        db.session.execute(
            text("INSERT INTO settings (organization_id, key, value, created_at, updated_at) VALUES (NULL, :key, :val, :now, :now)"),
            {'key': key, 'val': val_str, 'now': datetime.utcnow()}
        )
    db.session.commit()


# =============================================================================
# LOGS
# =============================================================================

@app.route('/logs')
@login_required
@admin_required
def logs_list():
    page = request.args.get('page', 1, type=int)
    per_page = 50

    filters = {
        'type': request.args.get('type', ''),
        'level': request.args.get('level', ''),
        'org': request.args.get('org', ''),
        'search': request.args.get('search', ''),
    }

    query = Log.query

    if filters['type']:
        query = query.filter(Log.log_type == filters['type'])
    if filters['level']:
        query = query.filter(Log.level == filters['level'])
    if filters['org']:
        org = Organization.query.filter_by(slug=filters['org']).first()
        if org:
            query = query.filter(Log.organization_id == org.id)
    if filters['search']:
        query = query.filter(Log.message.ilike(f"%{filters['search']}%"))

    total_logs = query.count()
    total_pages = max(1, (total_logs + per_page - 1) // per_page)
    logs_page = query.order_by(Log.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    logs_list_data = []
    for log in logs_page:
        org_slug = ''
        if log.organization_id:
            org = Organization.query.get(log.organization_id)
            org_slug = org.slug if org else ''
        logs_list_data.append({
            'id': log.id,
            'type': log.log_type,
            'level': log.level,
            'message': log.message,
            'org_slug': org_slug,
            'ip_address': log.ip_address,
            'timestamp': log.created_at.isoformat() if log.created_at else '',
        })

    orgs = Organization.query.all()
    orgs_dict = {o.slug: _org_to_template_dict(o) for o in orgs}

    return render_template('logs.html',
                           logs=logs_list_data,
                           total_logs=total_logs,
                           current_page=page,
                           total_pages=total_pages,
                           filters=filters,
                           organizations=orgs_dict)


@app.route('/logs/clear')
@login_required
@admin_required
def clear_logs():
    Log.query.delete()
    db.session.commit()
    flash('All logs cleared', 'success')
    return redirect(url_for('logs_list'))


# =============================================================================
# UPTIME
# =============================================================================

@app.route('/uptime')
@login_required
def uptime_dashboard():
    orgs = Organization.query.order_by(Organization.name).all()
    orgs_dict = {o.slug: _org_to_template_dict(o) for o in orgs}

    cutoff_5min = datetime.utcnow() - timedelta(minutes=5)
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)

    stats = {}
    for org in orgs:
        last_record = UptimeRecord.query.filter_by(organization_id=org.id).order_by(
            UptimeRecord.created_at.desc()).first()

        total_24h = UptimeRecord.query.filter(
            UptimeRecord.organization_id == org.id,
            UptimeRecord.created_at >= cutoff_24h
        ).count()

        up_24h = UptimeRecord.query.filter(
            UptimeRecord.organization_id == org.id,
            UptimeRecord.created_at >= cutoff_24h,
            UptimeRecord.status == 'up'
        ).count()

        online = last_record and last_record.created_at >= cutoff_5min and last_record.status == 'up'

        stats[org.slug] = {
            'status': 'online' if online else ('offline' if last_record else 'unknown'),
            'uptime_24h': (up_24h / total_24h * 100) if total_24h else 0.0,
            'total_pings': UptimeRecord.query.filter_by(organization_id=org.id).count(),
            'last_ping': last_record.created_at.isoformat() if last_record else None,
        }

    return render_template('uptime.html', organizations=orgs_dict, stats=stats)


# =============================================================================
# KILL SWITCHES
# =============================================================================

@app.route('/kill-switches')
@login_required
@admin_required
def kill_switches_list():
    orgs = Organization.query.order_by(Organization.name).all()
    orgs_dict = {o.slug: _org_to_template_dict(o) for o in orgs}

    ks_dict = {}
    for org in orgs:
        ks = KillSwitch.query.filter_by(organization_id=org.id).first()
        if ks:
            ks_dict[org.slug] = {
                'enabled': ks.is_enabled,
                'reason': ks.reason or '',
                'enabled_by': ks.enabled_by or '',
                'enabled_at': ks.enabled_at.isoformat() if ks.enabled_at else '',
                'disabled_at': ks.disabled_at.isoformat() if ks.disabled_at else '',
            }
        else:
            ks_dict[org.slug] = {'enabled': False, 'reason': ''}

    return render_template('kill_switches.html', organizations=orgs_dict, kill_switches=ks_dict)


@app.route('/kill-switches/<org_slug>/toggle')
@login_required
@admin_required
def toggle_kill_switch(org_slug):
    org = Organization.query.filter_by(slug=org_slug).first_or_404()
    ks = KillSwitch.query.filter_by(organization_id=org.id).first()
    if not ks:
        ks = KillSwitch(organization_id=org.id, is_enabled=False)
        db.session.add(ks)

    ks.is_enabled = not ks.is_enabled
    user = User.query.get(session['user_id'])
    if ks.is_enabled:
        ks.enabled_at = datetime.utcnow()
        ks.enabled_by = user.username
    else:
        ks.disabled_at = datetime.utcnow()
        ks.disabled_by = user.username

    db.session.commit()
    state = 'enabled' if ks.is_enabled else 'disabled'
    log_security_event('kill_switch_toggled', f'Kill switch {state}: {org_slug}',
                       'warning' if ks.is_enabled else 'info', user_id=user.id)
    flash(f'Kill switch {state} for {org.name}', 'success')
    return redirect(url_for('kill_switches_list'))


@app.route('/kill-switches/<org_slug>/update', methods=['POST'])
@login_required
@admin_required
def update_kill_switch(org_slug):
    org = Organization.query.filter_by(slug=org_slug).first_or_404()
    ks = KillSwitch.query.filter_by(organization_id=org.id).first()
    if not ks:
        ks = KillSwitch(organization_id=org.id, is_enabled=False)
        db.session.add(ks)

    ks.reason = request.form.get('reason', '').strip()
    db.session.commit()
    flash('Kill switch updated', 'success')
    return redirect(url_for('kill_switches_list'))


# =============================================================================
# CHAT (UI)
# =============================================================================

@app.route('/chat')
@login_required
def chat_dashboard():
    from sqlalchemy import func

    conversations_q = db.session.query(
        ChatMessage.chat_id,
        ChatMessage.from_name,
        ChatMessage.from_email,
        Organization.slug.label('org_slug'),
        func.max(ChatMessage.created_at).label('last_message'),
        func.count(ChatMessage.id).label('message_count'),
    ).join(Organization, ChatMessage.organization_id == Organization.id
    ).filter(ChatMessage.from_type == 'user'
    ).group_by(
        ChatMessage.chat_id, ChatMessage.from_name,
        ChatMessage.from_email, Organization.slug
    ).order_by(func.max(ChatMessage.created_at).desc()).all()

    conv_list = []
    for conv in conversations_q:
        chat_id, from_name, from_email, org_slug, last_msg, msg_count = conv
        unread = ChatMessage.query.filter_by(
            chat_id=chat_id, is_read=False, from_type='user'
        ).count()
        messages = ChatMessage.query.filter_by(chat_id=chat_id).order_by(
            ChatMessage.created_at.asc()).all()
        conv_list.append({
            'chat_id': chat_id,
            'user_name': from_name,
            'user_email': from_email,
            'org_slug': org_slug,
            'last_message': last_msg.isoformat() if last_msg else None,
            'message_count': msg_count,
            'unread_count': unread,
            'messages': [m.to_dict() for m in messages],
        })

    total_messages = ChatMessage.query.count()
    unread_count = ChatMessage.query.filter_by(is_read=False, from_type='user').count()

    return render_template('chat.html',
                           conversations=conv_list,
                           total_messages=total_messages,
                           unread_count=unread_count)


@app.route('/chat/mark-read/<int:msg_id>')
@login_required
def mark_chat_read(msg_id):
    msg = ChatMessage.query.get_or_404(msg_id)
    msg.is_read = True
    msg.read_at = datetime.utcnow()
    msg.read_by = session.get('username')
    db.session.commit()
    return redirect(url_for('chat_dashboard'))


@app.route('/chat/reply/<int:msg_id>', methods=['POST'])
@login_required
def reply_chat(msg_id):
    original = ChatMessage.query.get_or_404(msg_id)
    reply_text = request.form.get('reply', '').strip()
    if not reply_text:
        flash('Reply cannot be empty', 'error')
        return redirect(url_for('chat_dashboard'))

    user = User.query.get(session['user_id'])
    reply_msg = ChatMessage(
        chat_id=original.chat_id,
        organization_id=original.organization_id,
        user_id=user.id,
        from_type='admin',
        from_name=user.username,
        message=reply_text,
        reply_to=original.id,
        is_read=True,
    )
    original.is_read = True
    original.read_at = datetime.utcnow()
    original.read_by = user.username
    db.session.add(reply_msg)
    db.session.commit()

    broadcast_chat_message(reply_msg.to_dict())
    flash('Reply sent', 'success')
    return redirect(url_for('chat_dashboard'))


@app.route('/inbox')
@login_required
def chat_inbox_ui():
    return render_template('inbox.html')


# =============================================================================
# API KEY ROUTES (UI)
# =============================================================================

@app.route('/api-keys')
@login_required
@admin_required
def api_keys_list():
    orgs = Organization.query.order_by(Organization.name).all()
    orgs_dict = {o.slug: _org_to_template_dict(o) for o in orgs}
    api_keys = APIKey.query.order_by(APIKey.created_at.desc()).all()

    # Build a flat dict keyed by key string for template (legacy template expects this)
    keys_dict = {}
    for k in api_keys:
        org = Organization.query.get(k.organization_id)
        keys_dict[k.key] = {
            'name': k.name,
            'org_slug': org.slug if org else '',
            'created_at': k.created_at.isoformat() if k.created_at else '',
            'last_used': k.last_used.isoformat() if k.last_used else None,
            'active': k.is_active,
        }

    return render_template('api_keys.html', organizations=orgs_dict, api_keys=keys_dict)


@app.route('/api-keys/generate', methods=['POST'])
@login_required
@admin_required
@limiter.limit("20 per hour")
def generate_api_key():
    org_slug = request.form.get('org_slug', '').strip()
    name = request.form.get('name', 'API Key').strip()

    org = Organization.query.filter_by(slug=org_slug).first()
    if not org:
        flash('Organization not found', 'error')
        return redirect(url_for('api_keys_list'))

    key_str = 'sk_' + secrets.token_urlsafe(32)
    secret_str = secrets.token_urlsafe(64)

    api_key = APIKey(
        key=key_str,
        name=name,
        user_id=session['user_id'],
        organization_id=org.id,
        scopes=['read', 'write'],
        is_active=True,
    )
    api_key.set_secret(secret_str)
    db.session.add(api_key)
    db.session.commit()

    log_security_event('api_key_created', f'API key created: {name}', 'info',
                       user_id=session['user_id'], org_id=org.id)
    flash(f'API key created: {key_str}', 'success')
    return redirect(url_for('api_keys_list'))


@app.route('/api-keys/<path:key>/revoke')
@login_required
@admin_required
def revoke_api_key(key):
    api_key = APIKey.query.filter_by(key=key).first_or_404()
    api_key.is_active = False
    db.session.commit()
    log_security_event('api_key_revoked', 'API key revoked', 'info', user_id=session['user_id'])
    flash('API key revoked', 'success')
    return redirect(url_for('api_keys_list'))


@app.route('/api-keys/<path:key>/delete')
@login_required
@admin_required
def delete_api_key_ui(key):
    api_key = APIKey.query.filter_by(key=key).first_or_404()
    db.session.delete(api_key)
    db.session.commit()
    log_security_event('api_key_deleted', 'API key deleted', 'info', user_id=session['user_id'])
    flash('API key deleted', 'success')
    return redirect(url_for('api_keys_list'))


# =============================================================================
# USER PROFILE / 2FA APIs
# =============================================================================

@app.route('/api/user/profile')
@login_required
def get_user_profile():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict())


@app.route('/api/user/password', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def api_change_password():
    user = User.query.get(session['user_id'])
    data = request.get_json() or {}
    old_pw = data.get('old_password')
    new_pw = data.get('new_password')
    confirm_pw = data.get('confirm_password')

    if not all([old_pw, new_pw, confirm_pw]):
        return jsonify({'error': 'All fields required'}), 400
    if new_pw != confirm_pw:
        return jsonify({'error': 'Passwords do not match'}), 400
    if len(new_pw) < 12:
        return jsonify({'error': 'Password must be at least 12 characters'}), 400
    if not user.check_password(old_pw):
        log_security_event('password_change_failed', 'Wrong old password', 'warning', user_id=user.id)
        return jsonify({'error': 'Wrong password'}), 401

    user.set_password(new_pw)
    db.session.commit()
    log_security_event('password_changed', 'Password changed via API', 'info', user_id=user.id)
    return jsonify({'success': True, 'message': 'Password changed'})


@app.route('/api/user/2fa/setup')
@login_required
def setup_2fa():
    user = User.query.get(session['user_id'])
    if user.is_2fa_enabled:
        return jsonify({'error': '2FA already enabled'}), 400
    secret, backup_codes = user.enable_totp()
    db.session.commit()
    qr_code = user.get_totp_qr_code()
    return jsonify({'success': True, 'qr_code': qr_code, 'secret': secret, 'backup_codes': backup_codes})


@app.route('/api/user/2fa/verify', methods=['POST'])
@login_required
def verify_2fa_setup():
    user = User.query.get(session['user_id'])
    data = request.get_json() or {}
    token = data.get('token', '').replace(' ', '')
    if not token:
        return jsonify({'error': 'Token required'}), 400
    if not user.verify_totp(token):
        return jsonify({'error': 'Invalid token'}), 401
    user.is_2fa_enabled = True
    db.session.commit()
    log_security_event('2fa_enabled', '2FA enabled', 'info', user_id=user.id)
    return jsonify({'success': True, 'message': '2FA enabled', 'backup_codes': user.backup_codes})


@app.route('/api/user/2fa/disable', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def disable_2fa():
    user = User.query.get(session['user_id'])
    data = request.get_json() or {}
    password = data.get('password')
    if not password or not user.check_password(password):
        return jsonify({'error': 'Invalid password'}), 401
    user.disable_totp()
    db.session.commit()
    log_security_event('2fa_disabled', '2FA disabled', 'warning', user_id=user.id)
    return jsonify({'success': True, 'message': '2FA disabled'})


@app.route('/api/user/backup-codes')
@login_required
def get_backup_codes():
    user = User.query.get(session['user_id'])
    if not user.is_2fa_enabled:
        return jsonify({'error': '2FA not enabled'}), 400
    return jsonify({'success': True, 'backup_codes': user.backup_codes or []})


@app.route('/api/user/backup-codes/regenerate', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def regenerate_backup_codes():
    user = User.query.get(session['user_id'])
    data = request.get_json() or {}
    password = data.get('password')
    if not password or not user.check_password(password):
        return jsonify({'error': 'Invalid password'}), 401
    user.backup_codes = [secrets.token_hex(4) for _ in range(10)]
    db.session.commit()
    log_security_event('backup_codes_regen', 'Backup codes regenerated', 'info', user_id=user.id)
    return jsonify({'success': True, 'backup_codes': user.backup_codes})


# =============================================================================
# PUBLIC / EXTERNAL APIs
# =============================================================================

@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'version': '2.0.0',
        'timestamp': datetime.utcnow().isoformat(),
    })


@app.route('/api/organizations')
def api_organizations():
    if not _api_enabled():
        return jsonify({'error': 'API disabled'}), 503

    include_inactive = _get_setting_bool('allow_public_read', True)
    query = Organization.query
    if not include_inactive:
        query = query.filter_by(is_active=True)

    orgs = query.all()
    result = {}
    for org in orgs:
        result[org.slug] = _org_to_template_dict(org)

    return jsonify({'success': True, 'organizations': result, 'count': len(result)})


@app.route('/api/organizations/<slug>')
def api_organization_detail(slug):
    if not _api_enabled():
        return jsonify({'error': 'API disabled'}), 503
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    return jsonify({'success': True, 'organization': _org_to_template_dict(org)})


@app.route('/api/organizations/by-subdomain/<subdomain>')
def api_organization_by_subdomain(subdomain):
    if not _api_enabled():
        return jsonify({'error': 'API disabled'}), 503
    org = Organization.query.filter_by(subdomain=subdomain).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    return jsonify({'success': True, 'organization': _org_to_template_dict(org)})


@app.route('/api/stats')
def api_stats():
    if not _api_enabled():
        return jsonify({'error': 'API disabled'}), 503
    total = Organization.query.count()
    active = Organization.query.filter_by(is_active=True).count()
    return jsonify({
        'success': True,
        'stats': {
            'total_organizations': total,
            'active_organizations': active,
            'inactive_organizations': total - active,
        }
    })


@app.route('/api/kill-switch/<slug>')
def api_kill_switch(slug):
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    ks = KillSwitch.query.filter_by(organization_id=org.id).first()
    enabled = ks.is_enabled if ks else False
    return jsonify({
        'success': True,
        'enabled': enabled,
        'reason': (ks.reason or '') if ks else '',
    })


@app.route('/api/uptime/ping', methods=['POST'])
@csrf.exempt
@limiter.limit("300 per minute")
def api_uptime_ping():
    """Receive a heartbeat ping from an instance."""
    data = request.get_json() or {}
    org_slug = data.get('org_slug')
    api_key_str = request.headers.get('X-API-Key')

    if not org_slug:
        return jsonify({'error': 'org_slug required'}), 400

    org = Organization.query.filter_by(slug=org_slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404

    if api_key_str:
        api_key_obj = APIKey.query.filter_by(key=api_key_str, is_active=True).first()
        if not api_key_obj or api_key_obj.organization_id != org.id:
            return jsonify({'error': 'Invalid API key'}), 401

    record = UptimeRecord(
        organization_id=org.id,
        status='up',
        response_time=data.get('response_time'),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({'success': True, 'timestamp': datetime.utcnow().isoformat()})


@app.route('/api/log', methods=['POST'])
@csrf.exempt
@limiter.limit("200 per minute")
def api_log():
    """Accept a log entry from an instance."""
    data = request.get_json() or {}
    org_slug = data.get('org_slug')

    org = Organization.query.filter_by(slug=org_slug).first() if org_slug else None

    entry = Log(
        log_type=data.get('type', 'instance'),
        level=data.get('level', 'info'),
        organization_id=org.id if org else None,
        message=data.get('message', ''),
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
        event_metadata=data.get('metadata', {}),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True})


# =============================================================================
# CHAT API (external-facing, CSRF exempt)
# =============================================================================

@app.route('/api/chat/send', methods=['POST'])
@csrf.exempt
@limiter.limit("100 per minute")
def api_chat_send():
    data = request.get_json() or {}
    org_slug = data.get('org_slug')
    message_text = data.get('message')
    user_name = data.get('user_name', 'Anonymous')
    user_email = data.get('user_email')
    api_key_str = request.headers.get('X-API-Key')

    if not org_slug or not message_text:
        return jsonify({'error': 'org_slug and message required'}), 400

    org = Organization.query.filter_by(slug=org_slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404

    if api_key_str:
        api_key_obj = APIKey.query.filter_by(key=api_key_str, is_active=True).first()
        if not api_key_obj:
            return jsonify({'error': 'Invalid API key'}), 401
        if api_key_obj.organization_id != org.id:
            return jsonify({'error': 'API key does not match organization'}), 403
        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
            return jsonify({'error': 'API key expired'}), 401
        api_key_obj.last_used = datetime.utcnow()

    chat_id = hashlib.sha256(
        f"{user_email or user_name}:{org_slug}".lower().encode()
    ).hexdigest()[:16]

    chat_msg = ChatMessage(
        chat_id=chat_id,
        organization_id=org.id,
        from_type='user',
        from_name=user_name,
        from_email=user_email,
        message=message_text,
        team=data.get('team'),
        recipients=data.get('recipients', []),
    )
    db.session.add(chat_msg)
    db.session.commit()

    log_security_event('chat_message', f'Chat message from {user_name}', 'info', org_id=org.id)
    broadcast_chat_message(chat_msg.to_dict())

    return jsonify({
        'success': True,
        'message_id': chat_msg.id,
        'chat_id': chat_id,
        'timestamp': datetime.utcnow().isoformat(),
    })


@app.route('/api/chat/messages/<org_slug>')
@login_required
def api_chat_get_messages(org_slug):
    org = Organization.query.filter_by(slug=org_slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    messages = ChatMessage.query.filter_by(organization_id=org.id).order_by(
        ChatMessage.created_at.desc()).limit(50).all()
    return jsonify({
        'success': True,
        'messages': [m.to_dict() for m in messages],
        'count': len(messages),
        'timestamp': datetime.utcnow().isoformat(),
    })


@app.route('/api/chat/inbox/<username>')
@login_required
def api_chat_inbox(username):
    """Paginated inbox for the Inbox UI."""
    if session.get('username') != username and session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    messages = ChatMessage.query.order_by(ChatMessage.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        'success': True,
        'messages': [m.to_dict() for m in messages.items],
        'total': messages.total,
        'page': page,
        'per_page': per_page,
    })


@app.route('/api/chat/mark-read', methods=['POST'])
@csrf.exempt
@login_required
def api_chat_mark_read():
    data = request.get_json() or {}
    msg_id = data.get('msg_id')
    if not msg_id:
        return jsonify({'error': 'msg_id required'}), 400
    msg = ChatMessage.query.get(msg_id)
    if not msg:
        return jsonify({'error': 'Message not found'}), 404
    msg.is_read = True
    msg.read_at = datetime.utcnow()
    msg.read_by = data.get('username') or session.get('username')
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/chat/stream')
def api_chat_stream():
    """SSE stream for real-time chat updates."""
    def event_stream(q):
        try:
            while True:
                msg = q.get()
                if msg is None:
                    break
                yield f"data: {json.dumps(msg)}\n\n"
        except GeneratorExit:
            pass

    q = queue.Queue()
    _chat_subscribers.append(q)

    def gen():
        try:
            yield from event_stream(q)
        finally:
            try:
                _chat_subscribers.remove(q)
            except ValueError:
                pass

    return Response(gen(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# =============================================================================
# API KEY JSON API
# =============================================================================

@app.route('/api/api-keys', methods=['GET'])
@login_required
def api_get_api_keys():
    user = User.query.get(session['user_id'])
    keys = APIKey.query.filter_by(user_id=user.id).all()
    return jsonify({'success': True, 'api_keys': [k.to_dict() for k in keys]})


@app.route('/api/api-keys', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def api_create_api_key():
    data = request.get_json() or {}
    org_id = data.get('organization_id')
    name = data.get('name', 'API Key')
    scopes = data.get('scopes', ['read'])

    org = Organization.query.get(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404

    key_str = 'sk_' + secrets.token_urlsafe(32)
    secret_str = secrets.token_urlsafe(64)

    api_key = APIKey(
        key=key_str,
        name=name,
        user_id=session['user_id'],
        organization_id=org_id,
        scopes=scopes,
        is_active=True,
    )
    api_key.set_secret(secret_str)
    db.session.add(api_key)
    db.session.commit()

    log_security_event('api_key_created', f'API key created: {name}', 'info',
                       user_id=session['user_id'], org_id=org_id)
    return jsonify({
        'success': True,
        'key': key_str,
        'secret': secret_str,
        'message': 'Save your secret securely. It will not be shown again.',
    })


@app.route('/api/api-keys/<int:key_id>', methods=['DELETE'])
@login_required
def api_delete_api_key(key_id):
    api_key = APIKey.query.get(key_id)
    if not api_key:
        return jsonify({'error': 'API key not found'}), 404
    user = User.query.get(session['user_id'])
    if api_key.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    db.session.delete(api_key)
    db.session.commit()
    log_security_event('api_key_deleted', 'API key deleted', 'info', user_id=user.id)
    return jsonify({'success': True})


# =============================================================================
# ADMIN USER API
# =============================================================================

@app.route('/api/users/<int:user_id>')
@login_required
@admin_required
def api_get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict())


# =============================================================================
# HELPERS
# =============================================================================

def _api_enabled():
    return _get_setting_bool('api_enabled', True)


def _get_setting_bool(key, default=True):
    from sqlalchemy import text
    row = db.session.execute(
        text("SELECT value FROM settings WHERE organization_id IS NULL AND key = :key"),
        {'key': key}
    ).fetchone()
    if row is None:
        return default
    try:
        return bool(json.loads(row[0]))
    except Exception:
        return default


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error_code=404, message='Page not found'), 404

@app.errorhandler(500)
def server_error(error):
    db.session.rollback()
    return render_template('error.html', error_code=500, message='Internal server error'), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html', error_code=403, message='Access forbidden'), 403

@app.errorhandler(429)
def rate_limited(error):
    return jsonify({'error': 'Rate limit exceeded. Please slow down.'}), 429


# =============================================================================
# LIFECYCLE
# =============================================================================

@app.before_request
def before_request():
    if 'username' in session:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(hours=12)


@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


def init_db():
    """Create all tables and seed a default admin if none exists."""
    with app.app_context():
        db.create_all()

        # Ensure global settings table allows NULL org_id (SQLite migration safety)
        try:
            from sqlalchemy import text
            db.session.execute(text(
                "CREATE TABLE IF NOT EXISTS settings_global "
                "(key TEXT PRIMARY KEY, value TEXT)"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # Seed admin user if no users exist
        if User.query.count() == 0:
            admin = User(
                username='admin',
                email='admin@showwise.local',
                role='admin',
                is_active=True,
            )
            admin.set_password('Admin123456!')
            db.session.add(admin)
            db.session.commit()
            print("✓ Default admin created (username: admin, password: Admin123456!)")
            print("  ⚠ Change this password immediately after first login!")

        # Seed demo organization if none exist
        if Organization.query.count() == 0:
            demo_org = Organization(
                name='Demo Organization',
                slug='demo',
                subdomain='demo',
                url='https://demo.example.com',
                primary_color='#0051ff',
                secondary_color='#898989',
                description='Demo organization for testing',
                is_active=True,
            )
            db.session.add(demo_org)
            db.session.flush()
            ks = KillSwitch(organization_id=demo_org.id, is_enabled=False)
            db.session.add(ks)
            db.session.commit()
            print("✓ Demo organization created")

        print("✓ Database initialized")


if __name__ == '__main__':
    init_db()
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_ENV') == 'development',
        ssl_context='adhoc' if os.getenv('FLASK_ENV') == 'production' else None,
    )