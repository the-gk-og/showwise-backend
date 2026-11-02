"""
ShowWise Backend - Lite Edition
Features: Organization Management, Kill Switches, User Auth
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os, secrets, time
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
APP_STARTED_AT = time.monotonic()

_secret = os.getenv('SECRET_KEY', '').strip()
_placeholders = {'', 'your-super-secret-key-here-change-this-in-production', 'fallback-secret-key-change-in-production'}
if _secret in _placeholders:
    if os.getenv('FLASK_ENV') == 'production':
        raise RuntimeError('SECRET_KEY is not set. Generate one with: '
                           'python -c "import secrets; print(secrets.token_urlsafe(32))"')
    _secret = secrets.token_urlsafe(32)  # dev only: sessions reset on restart
    print('! SECRET_KEY not set: using a temporary key (sessions will reset on restart)')
app.secret_key = _secret

# Behind Cloudflare Tunnel / nginx / Tailscale Funnel set TRUSTED_PROXY_HOPS=1 (number of proxies that
# append to X-Forwarded-For). Without it every visitor looks like the proxy and shares one rate-limit bucket.
_hops = int(os.getenv('TRUSTED_PROXY_HOPS', '0') or 0)
if _hops > 0:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_hops, x_proto=_hops, x_host=_hops)

app.config.update(
    SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV') == 'production',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.getenv('SESSION_TIMEOUT', 12))),
    SESSION_REFRESH_EACH_REQUEST=True,
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///showwise.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID'),
    GOOGLE_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET'),
    GITHUB_CLIENT_ID=os.getenv('GITHUB_CLIENT_ID'),
    GITHUB_CLIENT_SECRET=os.getenv('GITHUB_CLIENT_SECRET'),
    WTF_CSRF_TIME_LIMIT=None,  # a login page left open overnight should still submit; the session still binds the token
)

csrf = CSRFProtect(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["2000 per day", "400 per hour"],
    default_limits_exempt_when=lambda: request.endpoint == 'static',
    storage_uri="memory://"
)

CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv('CORS_ORIGINS', '*').split(','),
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "max_age": 3600
    }
})

from models import db, User, Organization, KillSwitch, Log
from auth import (
    login_required, admin_required, require_2fa,
    get_client_ip, get_user_agent, log_security_event,
    is_account_locked, lock_account, unlock_account,
    verify_second_factor, reset_login_attempts, setup_oauth,
    start_session, begin_pending_2fa, pending_2fa_user,
)

db.init_app(app)

# Support access portal (log in to customer instances for support)
from support_admin import init_support_admin
init_support_admin(app, limiter)

# Self-service 2FA (enrol, disable, backup codes) at /account/security
from account_security import init_account_security
init_account_security(app, limiter)

oauth, google_oauth, github_oauth = None, None, None
try:
    oauth, google_oauth, github_oauth = setup_oauth(app)
except Exception as e:
    print(f"OAuth setup failed (optional): {e}")


# =============================================================================
# AUTH ROUTES
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute", methods=["POST"])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Enter your username and password.', 'error')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()

        if user and is_account_locked(user):
            remaining = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1)
            flash(f'This account is locked after too many failed attempts. Try again in about {remaining} min.', 'warning')
            log_security_event('login_locked', f'Locked account login attempt: {username}', 'warning', user_id=user.id)
            return redirect(url_for('login'))

        if user and user.is_active and user.check_password(password):
            if user.is_2fa_enabled:
                begin_pending_2fa(user)
                return redirect(url_for('verify_2fa'))
            reset_login_attempts(user)
            start_session(user)
            log_security_event('login_success', f'User logged in: {username}', 'info', user_id=user.id)
            return redirect(url_for('dashboard'))

        if user:
            lock_account(user)
            log_security_event('login_failed', f'Failed login: {username}', 'warning', user_id=user.id)
        else:
            log_security_event('login_failed', f'Failed login for unknown user: {username[:80]}', 'warning')
        flash('That username and password do not match.', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/verify-2fa', methods=['GET', 'POST'])
@limiter.limit("15 per minute", methods=["POST"])  # page loads are not counted; the account lockout is the real brute-force guard
@require_2fa
def verify_2fa():
    user = pending_2fa_user()

    if is_account_locked(user):
        session.pop('pending_2fa_user', None)
        session.pop('pending_2fa_at', None)
        flash('This account is locked after too many failed attempts. Try again later.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        code = request.form.get('token', '')
        ok, reason = verify_second_factor(user, code)

        if ok:
            reset_login_attempts(user)
            start_session(user)
            log_security_event('login_2fa_success', f'2FA verified: {user.username}', 'info', user_id=user.id)
            return redirect(url_for('dashboard'))

        lock_account(user)
        log_security_event('login_2fa_failed', f'Invalid 2FA ({reason}): {user.username}', 'warning', user_id=user.id)
        if is_account_locked(user):
            session.pop('pending_2fa_user', None)
            session.pop('pending_2fa_at', None)
            flash('Too many wrong codes. This account is locked for a while.', 'warning')
            return redirect(url_for('login'))
        if reason == 'reused':
            flash('That code was already used. Wait for your app to show the next one.', 'error')
        else:
            flash('That code is not valid. Check the code for ShowWise and try again.', 'error')
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
    from models import Setting
    from support_admin import DISABLED_KEY
    user = User.query.get(session['user_id'])
    since = datetime.utcnow() - timedelta(hours=24)

    orgs = Organization.query.order_by(Organization.name).all()
    kill_on = {ks.organization_id for ks in KillSwitch.query.filter_by(is_enabled=True)}
    support_off = {st.organization_id for st in Setting.query.filter_by(key=DISABLED_KEY, value='1')}
    last_support = dict(db.session.query(Log.organization_id, db.func.max(Log.created_at))
                        .filter(Log.log_type == 'support_login').group_by(Log.organization_id).all())

    instances = [{
        'slug': o.slug, 'name': o.name, 'url': o.url or '', 'active': o.is_active,
        'color': o.primary_color or '#0051ff', 'logo': o.logo or '',
        'kill': o.id in kill_on, 'support_off': o.id in support_off,
        'last_support': last_support.get(o.id),
    } for o in orgs]

    stats = {
        'total_organizations': len(orgs),
        'active_organizations': sum(1 for o in orgs if o.is_active),
        'inactive_organizations': sum(1 for o in orgs if not o.is_active),
        'kill_switches_on': len(kill_on),
        'locked_accounts': User.query.filter(User.locked_until > datetime.utcnow()).count(),
        'failed_logins_24h': Log.query.filter(Log.log_type.in_(('login_failed', 'login_2fa_failed')),
                                              Log.created_at >= since).count(),
        'support_logins_24h': Log.query.filter(Log.log_type == 'support_login', Log.created_at >= since).count(),
        'users_without_2fa': User.query.filter_by(role='admin', is_active=True, is_2fa_enabled=False).count(),
    }
    activity = Log.query.filter(Log.log_type != 'logout').order_by(Log.created_at.desc()).limit(12).all()
    return render_template('dashboard.html', username=user.username, role=user.role, user=user,
                           stats=stats, instances=instances, activity=activity)


@app.route('/api/admin/instances/<slug>/health')
@login_required
@admin_required
@limiter.limit("120 per minute")
def api_instance_health(slug):
    """JSON health of one instance; the dashboard and uptime pages call this per instance so pages load instantly."""
    from instance_checks import instance_health
    org = Organization.query.filter_by(slug=slug).first_or_404()
    resp = jsonify(instance_health(org.url))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# =============================================================================
# ORGANIZATION ROUTES
# =============================================================================

@app.route('/organizations')
@login_required
@admin_required
def organizations_list():
    orgs = Organization.query.order_by(Organization.name).all()
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


@app.route('/organizations/<slug>/toggle', methods=['POST'])
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


@app.route('/organizations/<slug>/delete', methods=['POST'])
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
    """Convert Organization model to dict for templates."""
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
# KILL SWITCH ROUTES
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


@app.route('/kill-switches/<org_slug>/toggle', methods=['POST'])
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
    if ks.is_enabled and request.form.get('reason') is not None:
        ks.reason = request.form.get('reason', '').strip()[:255]
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
# PUBLIC APIs
# =============================================================================

@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat(),
    })


@app.route('/api/organizations')
def api_organizations():
    orgs = Organization.query.filter_by(is_active=True).all()
    result = {}
    for org in orgs:
        result[org.slug] = _org_to_template_dict(org)
    return jsonify({'success': True, 'organizations': result, 'count': len(result)})


@app.route('/api/organizations/<slug>')
def api_organization_detail(slug):
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    return jsonify({'success': True, 'organization': _org_to_template_dict(org)})


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



# =============================================================================
# ADMIN MONITORING AND MANAGEMENT
# =============================================================================

@app.route('/logs')
@login_required
@admin_required
def logs_list():
    query = Log.query
    log_type = request.args.get('type', '').strip()[:80]
    level = request.args.get('level', '').strip()[:20]
    search = request.args.get('q', '').strip()[:120]
    if log_type:
        query = query.filter(Log.log_type == log_type)
    if level:
        query = query.filter(Log.level == level)
    if search:
        pattern = f"%{search}%"
        query = query.filter(db.or_(Log.message.ilike(pattern), Log.ip_address.ilike(pattern),
                                    Log.user_agent.ilike(pattern)))
    logs = query.order_by(Log.created_at.desc()).limit(250).all()
    types = [row[0] for row in db.session.query(Log.log_type).distinct().order_by(Log.log_type).all()]
    return render_template('logs.html', logs=logs, types=types, selected_type=log_type,
                           selected_level=level, search=search)


@app.route('/users')
@login_required
@admin_required
def users_list():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users.html', users=users, current_user_id=session.get('user_id'),
                           now=datetime.utcnow())


@app.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for('users_list'))
    user.is_active = not user.is_active
    db.session.commit()
    log_security_event('user_toggled', f"User {user.username} {'activated' if user.is_active else 'deactivated'}",
                       'warning' if not user.is_active else 'info', user_id=session.get('user_id'))
    flash(f"User {user.username} {'activated' if user.is_active else 'deactivated'}.", 'success')
    return redirect(url_for('users_list'))


@app.route('/users/<int:user_id>/unlock', methods=['POST'])
@login_required
@admin_required
def unlock_user(user_id):
    user = User.query.get_or_404(user_id)
    unlock_account(user)
    log_security_event('user_unlocked', f"Login lockout cleared for {user.username}",
                       'warning', user_id=session.get('user_id'))
    flash(f"Login lockout cleared for {user.username}.", 'success')
    return redirect(url_for('users_list'))


@app.route('/uptime')
@login_required
@admin_required
def uptime_dashboard():
    database_ok = True
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        db.session.rollback()
        database_ok = False
    orgs = Organization.query.order_by(Organization.name).all()
    return render_template('uptime.html', orgs=orgs, database_ok=database_ok,
                           uptime_seconds=max(0, int(time.monotonic() - APP_STARTED_AT)))


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
    message = 'Too many requests. Wait a minute, then try again.'
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': message}), 429
    return render_template('error.html', error_code=429, message=message), 429

@app.errorhandler(400)
def bad_request(error):
    description = getattr(error, 'description', '') or ''
    if 'CSRF' in description:
        message = 'This page expired. Go back, reload it and try again.'
    else:
        message = 'The request could not be understood.'
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': message}), 400
    return render_template('error.html', error_code=400, message=message), 400


# =============================================================================
# LIFECYCLE
# =============================================================================

@app.before_request
def before_request():
    if 'username' in session:
        session.permanent = True


@app.after_request
def security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('Content-Security-Policy', "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    if 'user_id' in session and request.endpoint != 'static':
        resp.headers['Cache-Control'] = 'no-store'  # admin pages must not sit in a shared browser cache
    return resp


@app.context_processor
def inject_nav_user():
    """Gives base.html the signed-in person for the side rail (name, role, whether 2FA is on)."""
    uid = session.get('user_id')
    if not uid:
        return {'nav_user': None}
    user = db.session.get(User, uid)
    if not user:
        return {'nav_user': None}
    return {'nav_user': {'username': user.username, 'role': user.role, 'twofa': bool(user.is_2fa_enabled)}}


@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


def ensure_schema():
    """Add columns introduced after a database was first created (create_all never alters tables)."""
    inspector = db.inspect(db.engine)
    if 'users' in inspector.get_table_names():
        columns = {c['name'] for c in inspector.get_columns('users')}
        if 'totp_last_step' not in columns:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN totp_last_step INTEGER'))
            db.session.commit()


def init_db():
    """Create tables, add new columns, and make a first admin plus a demo org when the database is empty."""
    with app.app_context():
        db.create_all()
        ensure_schema()

        if User.query.count() == 0:
            initial_password = os.getenv('ADMIN_INITIAL_PASSWORD') or secrets.token_urlsafe(14)
            admin = User(
                username='admin',
                email='admin@showwise.local',
                role='admin',
                is_active=True,
            )
            admin.set_password(initial_password)
            db.session.add(admin)
            db.session.commit()
            print('✓ First admin created')
            print('  username: admin')
            if os.getenv('ADMIN_INITIAL_PASSWORD'):
                print('  password: the value of ADMIN_INITIAL_PASSWORD')
            else:
                print(f'  password: {initial_password}   (shown once: sign in and set up 2FA at /account/security)')

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
            print('✓ Demo organization created')

        print('✓ Database initialized')


# ---- Recovery commands (run on the server) -----------------------------------------------------
#   flask --app app_db reset-2fa <username>      turn 2FA off for someone locked out of their authenticator
#   flask --app app_db unlock <username>         clear a login lockout
#   flask --app app_db set-password <username>   set a new password (prompts, hidden)
import click


@app.cli.command('reset-2fa')
@click.argument('username')
def cli_reset_2fa(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        raise click.ClickException(f'No user named {username!r}')
    user.disable_totp()
    unlock_account(user)
    db.session.commit()
    log_security_event('2fa_reset_cli', f'2FA reset from the command line for {username}', 'warning', user_id=user.id)
    click.echo(f'2FA is off for {username}. Sign in, then turn it on again at /account/security.')


@app.cli.command('unlock')
@click.argument('username')
def cli_unlock(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        raise click.ClickException(f'No user named {username!r}')
    unlock_account(user)
    click.echo(f'Lockout cleared for {username}.')


@app.cli.command('set-password')
@click.argument('username')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def cli_set_password(username, password):
    user = User.query.filter_by(username=username).first()
    if not user:
        raise click.ClickException(f'No user named {username!r}')
    try:
        user.set_password(password)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    unlock_account(user)
    db.session.commit()
    click.echo(f'Password updated for {username}.')


if __name__ == '__main__':
    init_db()
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_ENV') == 'development',
    )
