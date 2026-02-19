"""
ShowWise Backend - Secure Control Console
Features: Database storage, password hashing, TOTP 2FA, OAuth, comprehensive security
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

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-change-in-production')

# Secure session configuration
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    SESSION_REFRESH_EACH_REQUEST=True
)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'sqlite:///showwise.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# OAuth configuration
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config['GITHUB_CLIENT_ID'] = os.getenv('GITHUB_CLIENT_ID')
app.config['GITHUB_CLIENT_SECRET'] = os.getenv('GITHUB_CLIENT_SECRET')

# Security: CSRF Protection
csrf = CSRFProtect(app)

# Security: Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Enable CORS for API endpoints
CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv('CORS_ORIGINS', '*').split(','),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "max_age": 3600
    }
})

# Import models and auth after app is configured
from models import db, User, Organization, APIKey, ChatMessage, Log, Setting, UptimeRecord, KillSwitch
from auth import (
    login_required, admin_required, require_2fa,
    get_client_ip, get_user_agent, log_security_event,
    is_account_locked, lock_account, unlock_account,
    verify_totp_token, reset_login_attempts, setup_oauth
)

# Initialize database
db.init_app(app)

# Setup OAuth
oauth, google_oauth, github_oauth = None, None, None
try:
    oauth, google_oauth, github_oauth = setup_oauth(app)
except Exception as e:
    print(f"OAuth setup failed: {e}")

# Initialize SSE subscribers
_chat_subscribers = []
_chat_cache_lock = threading.Lock()

def broadcast_chat_message(message):
    """Broadcast chat message to SSE subscribers"""
    for q in list(_chat_subscribers):
        try:
            q.put_nowait(message)
        except Exception:
            pass

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Login route with password hashing and account lockout protection"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username and password required', 'error')
            return redirect(url_for('login'))
        
        user = User.query.filter_by(username=username).first()
        
        # Account lockout check
        if user and is_account_locked(user):
            remaining_time = (user.locked_until - datetime.utcnow()).total_seconds()
            flash(f'Account locked. Try again in {int(remaining_time)} seconds', 'warning')
            log_security_event('login_attempt', f'Login attempt on locked account: {username}', 'warning')
            return redirect(url_for('login'))
        
        # Verify password
        if user and user.check_password(password) and user.is_active:
            # Password correct
            if user.is_2fa_enabled:
                # Require 2FA
                session['pending_2fa_user'] = user.id
                flash('Enter your 2FA code', 'info')
                return redirect(url_for('verify_2fa'))
            else:
                # Direct login
                reset_login_attempts(user)
                session['username'] = username
                session['user_id'] = user.id
                session['role'] = user.role
                session.permanent = True
                log_security_event('login_success', f'User logged in: {username}', 'info', user_id=user.id)
                flash(f'Welcome {username}!', 'success')
                return redirect(url_for('dashboard'))
        else:
            # Wrong password or user not found
            if user:
                lock_account(user)
                log_security_event('login_attempt_failed', f'Failed login attempt: {username}', 'warning', user_id=user.id)
            flash('Invalid credentials', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/verify-2fa', methods=['GET', 'POST'])
@require_2fa
@limiter.limit("5 per minute")
def verify_2fa():
    """Verify TOTP or backup code"""
    user_id = session.get('pending_2fa_user')
    user = User.query.get(user_id) if user_id else None
    
    if not user:
        flash('Session expired', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        token = request.form.get('token', '').replace(' ', '').replace('-', '')
        use_backup = request.form.get('use_backup') == 'on'
        
        if verify_totp_token(user, token, use_backup):
            # 2FA verified
            reset_login_attempts(user)
            session['username'] = user.username
            session['user_id'] = user.id
            session['role'] = user.role
            session.permanent = True
            session.pop('pending_2fa_user', None)
            log_security_event('login_2fa_success', f'2FA verified: {user.username}', 'info', user_id=user.id)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            lock_account(user)
            flash('Invalid 2FA code', 'error')
            log_security_event('login_2fa_failed', f'Invalid 2FA attempt: {user.username}', 'warning', user_id=user.id)
            return redirect(url_for('verify_2fa'))
    
    return render_template('verify_2fa.html')

@app.route('/dashboard')


@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard"""
    user = User.query.get(session.get('user_id'))
    organizations = Organization.query.filter_by(is_active=True).all()
    total_chats = ChatMessage.query.count()
    unread_chats = ChatMessage.query.filter_by(is_read=False).filter(ChatMessage.from_type == 'user').count()
    
    return render_template('dashboard.html',
                         username=user.username,
                         role=user.role,
                         organizations=organizations,
                         total_messages=total_chats,
                         unread_count=unread_chats,
                         is_2fa_enabled=user.is_2fa_enabled)


@app.route('/settings')
@login_required
def settings_page():
    """User settings page"""
    user = User.query.get(session.get('user_id'))
    return render_template('settings.html', user=user)

@app.route('/api/user/profile')
@login_required
def get_user_profile():
    """Get user profile"""
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify(user.to_dict())

@app.route('/api/user/password', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def change_password():
    """Change password"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json() or {}
    
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not old_password or not new_password or not confirm_password:
        return jsonify({'error': 'All fields required'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400
    
    if len(new_password) < 12:
        return jsonify({'error': 'Password must be at least 12 characters'}), 400
    
    if not user.check_password(old_password):
        log_security_event('password_change_failed', 'Wrong old password', 'warning', user_id=user.id)
        return jsonify({'error': 'Wrong password'}), 401
    
    user.set_password(new_password)
    db.session.commit()
    log_security_event('password_changed', 'User password changed', 'info', user_id=user.id)
    
    return jsonify({'success': True, 'message': 'Password changed'})

# ==================== 2FA ROUTES ====================

@app.route('/api/user/2fa/setup')
@login_required
def setup_2fa():
    """Get QR code for TOTP setup"""
    user = User.query.get(session.get('user_id'))
    
    if user.is_2fa_enabled:
        return jsonify({'error': '2FA already enabled'}), 400
    
    secret, backup_codes = user.enable_totp()
    qr_code = user.get_totp_qr_code()
    
    return jsonify({
        'success': True,
        'qr_code': qr_code,
        'secret': secret,
        'backup_codes': backup_codes
    })

@app.route('/api/user/2fa/verify', methods=['POST'])
@login_required
def verify_2fa_setup():
    """Verify TOTP setup with code"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json() or {}
    
    token = data.get('token', '').replace(' ', '')
    
    if not token:
        return jsonify({'error': 'Token required'}), 400
    
    if not user.verify_totp(token):
        return jsonify({'error': 'Invalid token'}), 401
    
    user.is_2fa_enabled = True
    db.session.commit()
    log_security_event('2fa_enabled', '2FA enabled', 'info', user_id=user.id)
    
    return jsonify({
        'success': True,
        'message': '2FA enabled successfully',
        'backup_codes': user.backup_codes
    })

@app.route('/api/user/2fa/disable', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def disable_2fa():
    """Disable TOTP 2FA"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json() or {}
    
    # Require password confirmation
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
    """Get backup codes"""
    user = User.query.get(session.get('user_id'))
    
    if not user.is_2fa_enabled:
        return jsonify({'error': '2FA not enabled'}), 400
    
    return jsonify({
        'success': True,
        'backup_codes': user.backup_codes or []
    })

@app.route('/api/user/backup-codes/regenerate', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def regenerate_backup_codes():
    """Regenerate backup codes"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json() or {}
    
    # Require password confirmation
    password = data.get('password')
    if not password or not user.check_password(password):
        return jsonify({'error': 'Invalid password'}), 401
    
    user.backup_codes = [secrets.token_hex(4) for _ in range(10)]
    db.session.commit()
    log_security_event('backup_codes_regenerated', 'Backup codes regenerated', 'info', user_id=user.id)
    
    return jsonify({
        'success': True,
        'backup_codes': user.backup_codes
    })

# ==================== ADMIN ROUTES ====================

@app.route('/users')
@login_required
@admin_required
def users_list():
    """List all users (admin only)"""
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/api/users/<int:user_id>')
@login_required
@admin_required
def get_user(user_id):
    """Get user details"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify(user.to_dict())

@app.route('/organizations')
@login_required
@admin_required
def organizations_list():
    """List all organizations"""
    orgs = Organization.query.all()
    return render_template('organizations.html', organizations=orgs)

@app.route('/logs')
@login_required
@admin_required
def logs_list():
    """View audit logs"""
    logs = Log.query.order_by(Log.created_at.desc()).limit(1000).all()
    return render_template('logs.html', logs=logs)

# ==================== CHAT ROUTES ====================

@app.route('/chat')
@login_required
def chat_dashboard():
    """Chat dashboard"""
    # Get grouped conversations
    from sqlalchemy import func
    conversations = db.session.query(
        ChatMessage.chat_id,
        ChatMessage.from_name,
        ChatMessage.from_email,
        Organization.slug.label('org_slug'),
        func.max(ChatMessage.created_at).label('last_message'),
        func.count(ChatMessage.id).label('message_count'),
        func.sum(func.cast(~ChatMessage.is_read & (ChatMessage.from_type == 'user'), db.Integer)).label('unread_count')
    ).join(Organization).filter(ChatMessage.from_type == 'user').group_by(
        ChatMessage.chat_id, ChatMessage.from_name, ChatMessage.from_email, Organization.slug
    ).order_by(func.max(ChatMessage.created_at).desc()).all()
    
    conv_list = []
    for conv in conversations:
        conv_list.append({
            'chat_id': conv[0],
            'user_name': conv[1],
            'user_email': conv[2],
            'org_slug': conv[3],
            'last_message': conv[4].isoformat() if conv[4] else None,
            'message_count': conv[5],
            'unread_count': conv[6] or 0
        })
    
    total_messages = ChatMessage.query.count()
    unread_count = ChatMessage.query.filter_by(is_read=False).filter(ChatMessage.from_type == 'user').count()
    
    return render_template('chat.html',
                         conversations=conv_list,
                         total_messages=total_messages,
                         unread_count=unread_count)

@app.route('/chat/mark-read/<int:msg_id>')
@login_required
def mark_chat_read(msg_id):
    """Mark message as read"""
    msg = ChatMessage.query.get(msg_id)
    if not msg:
        flash('Message not found', 'error')
        return redirect(url_for('chat_dashboard'))
    
    msg.is_read = True
    msg.read_at = datetime.utcnow()
    msg.read_by = session.get('username')
    db.session.commit()
    
    return redirect(url_for('chat_dashboard'))

@app.route('/chat/reply/<int:msg_id>', methods=['POST'])
@login_required
def reply_chat(msg_id):
    """Reply to chat message"""
    original = ChatMessage.query.get(msg_id)
    if not original:
        flash('Message not found', 'error')
        return redirect(url_for('chat_dashboard'))
    
    reply_text = request.form.get('reply', '').strip()
    if not reply_text:
        flash('Reply cannot be empty', 'error')
        return redirect(url_for('chat_dashboard'))
    
    user = User.query.get(session.get('user_id'))
    
    reply_msg = ChatMessage(
        chat_id=original.chat_id,
        organization_id=original.organization_id,
        user_id=user.id,
        from_type='admin',
        from_name=user.username,
        message=reply_text,
        reply_to=msg_id,
        is_read=True
    )
    
    original.is_read = True
    original.read_at = datetime.utcnow()
    original.read_by = user.username
    
    db.session.add(reply_msg)
    db.session.commit()
    
    broadcast_chat_message(reply_msg.to_dict())
    flash('Reply sent', 'success')
    return redirect(url_for('chat_dashboard'))

# ==================== API CHAT ROUTES ====================

@app.route('/api/chat/send', methods=['POST'])
@limiter.limit("100 per minute")
def api_chat_send():
    """Receive chat message from instance"""
    data = request.get_json() or {}
    
    org_slug = data.get('org_slug')
    message_text = data.get('message')
    user_name = data.get('user_name', 'Anonymous')
    user_email = data.get('user_email')
    api_key = request.headers.get('X-API-Key')
    
    if not org_slug or not message_text:
        return jsonify({'error': 'org_slug and message required'}), 400
    
    # Find organization
    org = Organization.query.filter_by(slug=org_slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    # Verify API key if provided
    if api_key:
        api_key_obj = APIKey.query.filter_by(key=api_key).first()
        if not api_key_obj or not api_key_obj.is_active:
            return jsonify({'error': 'Invalid API key'}), 401
        if api_key_obj.organization_id != org.id:
            return jsonify({'error': 'API key does not match organization'}), 403
        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
            return jsonify({'error': 'API key expired'}), 401
        api_key_obj.last_used = datetime.utcnow()
    
    # Generate or find chat_id
    if not user_email:
        user_email = None
    chat_id = hashlib.sha256(f"{user_email or user_name}:{org_slug}".lower().encode()).hexdigest()[:16]
    
    # Create chat message
    chat_msg = ChatMessage(
        chat_id=chat_id,
        organization_id=org.id,
        from_type='user',
        from_name=user_name,
        from_email=user_email,
        message=message_text,
        team=data.get('team'),
        recipients=data.get('recipients', [])
    )
    
    db.session.add(chat_msg)
    if api_key:
        db.session.commit()
        api_key_obj.last_used = datetime.utcnow()
    db.session.commit()
    
    log_security_event('chat_message', f'Chat message from {user_name}', 'info', org_id=org.id)
    
    # Broadcast to subscribers
    broadcast_chat_message(chat_msg.to_dict())
    
    return jsonify({
        'success': True,
        'message_id': chat_msg.id,
        'chat_id': chat_id,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/chat/messages/<org_slug>', methods=['GET'])
@login_required
def api_chat_get_messages(org_slug):
    """Get chat messages for an organization"""
    org = Organization.query.filter_by(slug=org_slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    messages = ChatMessage.query.filter_by(organization_id=org.id).order_by(ChatMessage.created_at.desc()).limit(50).all()
    
    return jsonify({
        'success': True,
        'messages': [msg.to_dict() for msg in messages],
        'count': len(messages),
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/chat/stream', methods=['GET'])
def api_chat_stream():
    """Server-Sent Events stream for new chat messages"""
    def event_stream(q):
        try:
            while True:
                msg = q.get()
                if msg is None:
                    break
                data = json.dumps(msg)
                yield f"data: {data}\n\n"
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
    
    return Response(gen(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})

@app.route('/api/chat/mark-read', methods=['POST'])
@login_required
def api_chat_mark_read():
    """Mark message as read via API"""
    data = request.get_json() or {}
    msg_id = data.get('msg_id')
    
    if not msg_id:
        return jsonify({'error': 'msg_id required'}), 400
    
    msg = ChatMessage.query.get(msg_id)
    if not msg:
        return jsonify({'error': 'Message not found'}), 404
    
    msg.is_read = True
    msg.read_at = datetime.utcnow()
    msg.read_by = session.get('username')
    db.session.commit()
    
    return jsonify({'success': True})

# ==================== API KEY ROUTES ====================

@app.route('/api-keys')
@login_required
@admin_required
def api_keys_list():
    """List API keys"""
    api_keys = APIKey.query.all()
    return render_template('api_keys.html', api_keys=api_keys)

@app.route('/api/api-keys', methods=['GET'])
@login_required
def get_api_keys():
    """Get user's API keys"""
    user = User.query.get(session.get('user_id'))
    keys = APIKey.query.filter_by(user_id=user.id).all()
    return jsonify({
        'success': True,
        'api_keys': [key.to_dict() for key in keys]
    })

@app.route('/api/api-keys', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def create_api_key():
    """Create new API key"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json() or {}
    
    org_id = data.get('organization_id')
    name = data.get('name', 'API Key')
    scopes = data.get('scopes', ['read'])
    
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    key = secrets.token_urlsafe(32)
    secret = secrets.token_urlsafe(64)
    
    api_key = APIKey(
        key=key,
        name=name,
        user_id=user.id,
        organization_id=org_id,
        scopes=scopes
    )
    api_key.set_secret(secret)
    
    db.session.add(api_key)
    db.session.commit()
    
    log_security_event('api_key_created', f'API key created: {name}', 'info', user_id=user.id, org_id=org_id)
    
    return jsonify({
        'success': True,
        'key': key,
        'secret': secret,
        'message': 'Save your secret securely. It will not be shown again.'
    })

@app.route('/api/api-keys/<int:key_id>', methods=['DELETE'])
@login_required
def delete_api_key(key_id):
    """Delete API key"""
    api_key = APIKey.query.get(key_id)
    if not api_key:
        return jsonify({'error': 'API key not found'}), 404
    
    user = User.query.get(session.get('user_id'))
    if api_key.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    db.session.delete(api_key)
    db.session.commit()
    
    log_security_event('api_key_deleted', f'API key deleted', 'info', user_id=user.id)
    
    return jsonify({'success': True})

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error_code=404, message='Page not found'), 404

@app.errorhandler(500)
def server_error(error):
    db.session.rollback()
    return render_template('error.html', error_code=500, message='Server error'), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html', error_code=403, message='Forbidden'), 403

# ==================== INITIALIZATION ====================

@app.before_request
def before_request():
    """Before each request"""
    if 'username' in session:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(hours=12)

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Cleanup database session"""
    db.session.remove()

def init_db():
    """Initialize database"""
    with app.app_context():
        db.create_all()
        print("Database initialized")

if __name__ == '__main__':
    with app.app_context():
        init_db()
    
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_ENV') == 'development',
        ssl_context='adhoc' if os.getenv('FLASK_ENV') == 'production' else None
    )
