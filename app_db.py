"""
ShowWise Backend - Lite Edition
Features: Organization Management, Kill Switches, User Auth
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import json, os, secrets
from datetime import datetime, timedelta

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
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "max_age": 3600
    }
})

from models import db, User, Organization, KillSwitch
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
    }
    return render_template('dashboard.html',
                           username=user.username,
                           role=user.role,
                           stats=stats)


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
    """Initialize database with default admin and demo org."""
    with app.app_context():
        db.create_all()

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
    )
