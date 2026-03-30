"""
API v1 - Authentication Endpoints
Handles login, logout, token generation, and 2FA
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from models import User, db
from services.audit_logger import AuditLogger
from services.security_engine import IPSecurityEngine
from functools import wraps

auth_bp = Blueprint('auth', __name__)


def require_api_key(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # Validate API key
        from models import APIKey
        key_obj = APIKey.query.filter_by(key=api_key, is_active=True).first()
        if not key_obj:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Store in request context
        request.api_key_user_id = key_obj.user_id
        request.api_key_org_id = key_obj.organization_id
        
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['POST'])
def api_login():
    """
    API Login endpoint
    
    POST /api/v1/auth/login
    {
        "username": "user",
        "password": "pass",
        "totp_code": "123456"  # Optional, required if 2FA enabled
    }
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    totp_code = data.get('totp_code', '').replace(' ', '')
    
    audit = AuditLogger(db)
    security = IPSecurityEngine(db)
    
    # Check IP reputation first
    ip_rep = security.check_ip_reputation()
    if ip_rep['is_blocked']:
        audit.log_ip_blocked(security.get_client_ip(), 'Attempted login from blocked IP')
        return jsonify({
            'error': 'Access denied',
            'message': 'Your IP address has been blocked due to suspicious activity'
        }), 403
    
    if not username or not password:
        audit.log_login_attempt(username or 'unknown', False, reason='Missing credentials')
        return jsonify({'error': 'Username and password required'}), 400
    
    # Find user
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.check_password(password) or not user.is_active:
        audit.log_login_attempt(username, False, reason='Invalid credentials')
        security.quarantine_ip(security.get_client_ip(), 'Failed login attempt')
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Check if 2FA is enabled
    if user.is_2fa_enabled:
        if not totp_code:
            # Return 2FA required response with temporary token
            return jsonify({
                'error': '2FA required',
                'requires_2fa': True,
                'temp_token': _generate_temp_token(user.id)
            }), 202
        
        # Verify 2FA code
        if not user.verify_totp(totp_code):
            audit.log_event(
                'login_2fa_failed',
                f'Failed 2FA attempt for user: {username}',
                'WARNING',
                user_id=user.id
            )
            return jsonify({'error': 'Invalid 2FA code'}), 401
    
    # Login successful
    session['user_id'] = user.id
    session['username'] = username
    session['role'] = user.role
    session.permanent = True
    
    audit.log_login_attempt(username, True)
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            '2fa_enabled': user.is_2fa_enabled
        },
        'access_token': _generate_access_token(user.id)
    }), 200


@auth_bp.route('/logout', methods=['POST'])
def api_logout():
    """API Logout endpoint"""
    user_id = session.get('user_id')
    username = session.get('username')
    
    if user_id:
        audit = AuditLogger(db)
        audit.log_event(
            'logout',
            f'User logged out: {username}',
            'INFO',
            user_id=user_id
        )
    
    session.clear()
    
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    }), 200


@auth_bp.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    """Verify 2FA code during login"""
    data = request.get_json() or {}
    temp_token = data.get('temp_token')
    totp_code = data.get('totp_code', '').replace(' ', '')
    
    if not temp_token or not totp_code:
        return jsonify({'error': '2FA token and code required'}), 400
    
    # Validate temp token and get user
    user_id = _validate_temp_token(temp_token)
    if not user_id:
        return jsonify({'error': 'Invalid or expired temp token'}), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Verify TOTP
    if not user.verify_totp(totp_code):
        audit = AuditLogger(db)
        audit.log_event(
            'login_2fa_failed',
            f'Failed 2FA verification',
            'WARNING',
            user_id=user.id
        )
        return jsonify({'error': 'Invalid 2FA code'}), 401
    
    # Complete login
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session.permanent = True
    
    audit = AuditLogger(db)
    audit.log_event('login_2fa_success', 'Login successful with 2FA', 'INFO', user_id=user.id)
    
    return jsonify({
        'success': True,
        'access_token': _generate_access_token(user.id)
    }), 200


@auth_bp.route('/token/refresh', methods=['POST'])
@require_api_key
def refresh_token():
    """Refresh access token"""
    user_id = request.api_key_user_id
    
    return jsonify({
        'access_token': _generate_access_token(user_id),
        'expires_in': 3600
    }), 200


@auth_bp.route('/whoami', methods=['GET'])
@require_api_key
def whoami():
    """Get current authenticated user info"""
    user = User.query.get(request.api_key_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        '2fa_enabled': user.is_2fa_enabled,
        'created_at': user.created_at.isoformat() if user.created_at else None
    }), 200


# Helper functions

def _generate_temp_token(user_id, expires_in=300):
    """Generate temporary token for 2FA verification (5 min expiry)"""
    import secrets
    import json
    from datetime import datetime, timedelta
    
    token_data = {
        'user_id': user_id,
        'expires_at': (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    }
    
    # Store in session or cache
    token = secrets.token_urlsafe(32)
    # In production, use Redis or similar
    from flask import g
    if not hasattr(g, 'temp_tokens'):
        g.temp_tokens = {}
    g.temp_tokens[token] = token_data
    
    return token


def _validate_temp_token(token):
    """Validate temporary token and return user_id"""
    from flask import g
    from datetime import datetime
    
    if not hasattr(g, 'temp_tokens'):
        return None
    
    token_data = g.temp_tokens.get(token)
    if not token_data:
        return None
    
    # Check expiry
    expires_at = datetime.fromisoformat(token_data['expires_at'])
    if expires_at < datetime.utcnow():
        del g.temp_tokens[token]
        return None
    
    return token_data.get('user_id')


def _generate_access_token(user_id):
    """Generate JWT-like access token"""
    import secrets
    import json
    from datetime import datetime, timedelta
    
    token_data = {
        'user_id': user_id,
        'issued_at': datetime.utcnow().isoformat(),
        'expires_at': (datetime.utcnow() + timedelta(hours=1)).isoformat()
    }
    
    # Use session or JWT in production
    token = f"bearer_{secrets.token_urlsafe(32)}"
    return token
