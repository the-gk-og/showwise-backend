"""
routes_2fa.py
=============
2FA setup, verification, and management endpoints for ShowWise Backend API.
Integrates TOTP with backup codes and device management.
Supports both browser sessions and API key authentication.
"""

from flask import Blueprint, request, jsonify, session, g
from functools import wraps
import pyotp
import qrcode
import io
import base64
import json
from datetime import datetime, timedelta
from models import db, User
from auth import log_security_event, get_client_ip, get_user_agent

tfa_bp = Blueprint('tfa_api', __name__, url_prefix='/api/2fa')


def require_api_auth(f):
    """Decorator: Require API key or session authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check session first
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user and user.is_active:
                g.user = user
                g.auth_method = 'session'
                return f(*args, **kwargs)

        # Check API key
        api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if api_key:
            from models import APIKey
            key_obj = APIKey.query.filter_by(key=api_key, is_active=True).first()
            if key_obj and key_obj.user:
                g.user = key_obj.user
                g.auth_method = 'api_key'
                g.api_key_id = key_obj.id
                return f(*args, **kwargs)

        return jsonify({'error': 'Authentication required'}), 401
    return decorated


# ============================================================================
# SETUP & CONFIGURATION
# ============================================================================

@tfa_bp.route('/setup', methods=['GET'])
@require_api_auth
def get_2fa_setup_status():
    """Get current 2FA setup status for authenticated user."""
    user = g.user
    return jsonify({
        'is_2fa_enabled': user.is_2fa_enabled,
        'has_totp_secret': bool(user.totp_secret),
        'backup_codes_count': len(user.backup_codes or []),
        'backup_codes_generated_at': None  # Could store in model
    }), 200


@tfa_bp.route('/initiate', methods=['POST'])
@require_api_auth
def initiate_2fa_setup():
    """Generate a new TOTP secret for 2FA setup."""
    user = g.user

    if user.is_2fa_enabled:
        log_security_event(
            'totp_setup_attempted_already_enabled',
            f'User {user.username} attempted to setup 2FA when already enabled',
            'warning',
            user_id=user.id
        )
        return jsonify({'error': '2FA is already enabled'}), 400

    # Generate new secret
    new_secret = pyotp.random_base32()

    # Create TOTP object and get provisioning URI
    totp = pyotp.TOTP(new_secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.email,
        issuer_name='ShowWise Backend'
    )

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

    # Store temporary secret in session for verification
    session['pending_totp_secret'] = new_secret
    session['pending_totp_created_at'] = datetime.utcnow().isoformat()

    log_security_event(
        'totp_setup_initiated',
        f'User {user.username} initiated 2FA setup',
        'info',
        user_id=user.id
    )

    return jsonify({
        'success': True,
        'secret': new_secret,
        'qr_code': f'data:image/png;base64,{qr_code_base64}',
        'provisioning_uri': provisioning_uri,
        'message': 'Scan this QR code with your authenticator app, then verify with a 6-digit code'
    }), 200


@tfa_bp.route('/verify-setup', methods=['POST'])
@require_api_auth
def verify_2fa_setup():
    """Verify TOTP setup by checking a 6-digit code."""
    user = g.user
    data = request.json or {}
    code = data.get('code', '').strip()

    if not code or len(code) != 6 or not code.isdigit():
        log_security_event(
            'totp_verify_invalid_code',
            f'Invalid code format during 2FA setup for {user.username}',
            'warning',
            user_id=user.id
        )
        return jsonify({'error': 'Code must be a 6-digit number'}), 400

    # Get pending secret from session
    pending_secret = session.get('pending_totp_secret')
    if not pending_secret:
        log_security_event(
            'totp_verify_no_pending',
            f'2FA verification attempted without pending setup for {user.username}',
            'warning',
            user_id=user.id
        )
        return jsonify({'error': 'No pending 2FA setup found. Please initiate setup first.'}), 400

    # Check if setup is older than 15 minutes
    created_at_str = session.get('pending_totp_created_at')
    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str)
        if datetime.utcnow() - created_at > timedelta(minutes=15):
            session.pop('pending_totp_secret', None)
            session.pop('pending_totp_created_at', None)
            log_security_event(
                'totp_setup_expired',
                f'2FA setup expired for {user.username}',
                'info',
                user_id=user.id
            )
            return jsonify({'error': 'Setup session expired. Please initiate setup again.'}), 400

    # Verify the code
    totp = pyotp.TOTP(pending_secret)
    if not totp.verify(code, valid_window=1):
        log_security_event(
            'totp_verify_failed',
            f'Invalid TOTP code during verification for {user.username}',
            'warning',
            user_id=user.id
        )
        return jsonify({'error': 'Invalid code. Please try again.'}), 400

    # Code is valid - enable 2FA on the user account
    user.totp_secret = pending_secret
    user.is_2fa_enabled = True
    user.backup_codes = [pyotp.random_base32()[:8] for _ in range(10)]

    db.session.commit()

    # Clear pending session data
    session.pop('pending_totp_secret', None)
    session.pop('pending_totp_created_at', None)

    log_security_event(
        'totp_enabled',
        f'2FA successfully enabled for {user.username}',
        'info',
        user_id=user.id
    )

    return jsonify({
        'success': True,
        'message': '2FA has been successfully enabled',
        'backup_codes': user.backup_codes,
        'backup_codes_message': 'Save these backup codes in a secure location. Each can be used once if you lose access to your authenticator.'
    }), 200


# ============================================================================
# LOGIN & VERIFICATION
# ============================================================================

@tfa_bp.route('/verify-login', methods=['POST'])
def verify_login_2fa():
    """Verify 2FA during login (requires pending_2fa_user session)."""
    data = request.json or {}
    code = data.get('code', '').strip()
    use_backup = data.get('use_backup_code', False)

    if 'pending_2fa_user_id' not in session:
        log_security_event(
            'totp_verify_login_no_pending',
            'Login 2FA verification attempted without pending session',
            'warning'
        )
        return jsonify({'error': 'No pending login found'}), 400

    user = User.query.get(session['pending_2fa_user_id'])
    if not user:
        session.pop('pending_2fa_user_id', None)
        return jsonify({'error': 'User not found'}), 401

    if not user.is_2fa_enabled or not user.totp_secret:
        session.pop('pending_2fa_user_id', None)
        return jsonify({'error': '2FA not enabled for this user'}), 400

    if not code or (not use_backup and len(code) != 6):
        return jsonify({'error': 'Invalid code format'}), 400

    # Verify code
    if use_backup:
        # Verify backup code
        if not user.use_backup_code(code):
            log_security_event(
                'totp_backup_code_invalid',
                f'Invalid backup code attempt for {user.username}',
                'warning',
                user_id=user.id
            )
            return jsonify({'error': 'Invalid backup code'}), 400
        log_security_event(
            'login_backup_code_used',
            f'User {user.username} logged in using backup code',
            'info',
            user_id=user.id
        )
    else:
        # Verify TOTP code
        if not user.verify_totp(code):
            log_security_event(
                'totp_verify_failed_login',
                f'Invalid TOTP code during login for {user.username}',
                'warning',
                user_id=user.id
            )
            return jsonify({'error': 'Invalid code. Please try again.'}), 400
        log_security_event(
            'login_totp_verified',
            f'User {user.username} passed 2FA verification',
            'info',
            user_id=user.id
        )

    # 2FA verified - complete login
    session['user_id'] = user.id
    session.pop('pending_2fa_user_id', None)

    user.last_login = datetime.utcnow()
    user.last_ip = get_client_ip()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '2FA verification successful',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        }
    }), 200


# ============================================================================
# MANAGEMENT
# ============================================================================

@tfa_bp.route('/disable', methods=['POST'])
@require_api_auth
def disable_2fa():
    """Disable 2FA for the authenticated user."""
    user = g.user
    data = request.json or {}
    confirmation_code = data.get('confirmation_code', '').strip()

    if not user.is_2fa_enabled:
        return jsonify({'error': '2FA is not enabled'}), 400

    # For security, require the user to verify with their current TOTP code
    if not confirmation_code or len(confirmation_code) != 6:
        return jsonify({'error': 'Please provide your current 6-digit authenticator code'}), 400

    if not user.verify_totp(confirmation_code):
        log_security_event(
            'totp_disable_failed',
            f'Failed 2FA disable attempt for {user.username}',
            'warning',
            user_id=user.id
        )
        return jsonify({'error': 'Invalid code. Cannot disable 2FA.'}), 400

    user.is_2fa_enabled = False
    user.totp_secret = None
    user.backup_codes = []
    db.session.commit()

    log_security_event(
        'totp_disabled',
        f'2FA disabled for {user.username}',
        'warning',
        user_id=user.id
    )

    return jsonify({
        'success': True,
        'message': '2FA has been disabled'
    }), 200


@tfa_bp.route('/regenerate-backup-codes', methods=['POST'])
@require_api_auth
def regenerate_backup_codes():
    """Generate new backup codes (requires 2FA verification)."""
    user = g.user
    data = request.json or {}
    verification_code = data.get('verification_code', '').strip()

    if not user.is_2fa_enabled or not user.totp_secret:
        return jsonify({'error': '2FA is not enabled'}), 400

    if not verification_code or len(verification_code) != 6:
        return jsonify({'error': 'Please provide your 6-digit authenticator code'}), 400

    if not user.verify_totp(verification_code):
        log_security_event(
            'backup_codes_regenerate_failed',
            f'Failed backup code regeneration for {user.username}',
            'warning',
            user_id=user.id
        )
        return jsonify({'error': 'Invalid code'}), 400

    # Generate new backup codes
    user.backup_codes = [pyotp.random_base32()[:8] for _ in range(10)]
    db.session.commit()

    log_security_event(
        'backup_codes_regenerated',
        f'Backup codes regenerated for {user.username}',
        'info',
        user_id=user.id
    )

    return jsonify({
        'success': True,
        'backup_codes': user.backup_codes,
        'message': 'New backup codes have been generated. Save them in a secure location.'
    }), 200


@tfa_bp.route('/status', methods=['GET'])
@require_api_auth
def get_2fa_status():
    """Get detailed 2FA status for the authenticated user."""
    user = g.user
    return jsonify({
        'is_2fa_enabled': user.is_2fa_enabled,
        'has_totp_secret': bool(user.totp_secret),
        'backup_codes_available': len(user.backup_codes or []),
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'last_ip': user.last_ip
    }), 200
