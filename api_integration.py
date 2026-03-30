"""
api_integration.py
==================
Secure cross-application API integration for 2FA and security data sharing.
Allows ShowWise-home and ShowWise-Backend to share user credentials and 2FA status.
Uses database-level synchronization with API key authentication.
"""

import hashlib
import json
import hmac
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
import os

# Integration configuration
ENABLE_CROSS_APP_SYNC = os.getenv('ENABLE_CROSS_APP_SYNC', 'true').lower() == 'true'
API_INTEGRATION_SECRET = os.getenv('API_INTEGRATION_SECRET', '')
API_INTEGRATION_KEY = os.getenv('API_INTEGRATION_KEY', '')


def verify_integration_signature(f):
    """Verify request signature for secure cross-app communication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ENABLE_CROSS_APP_SYNC:
            return jsonify({'error': 'Cross-app sync not enabled'}), 403

        if not API_INTEGRATION_SECRET:
            return jsonify({'error': 'Integration not configured'}), 500

        # Get signature from header
        signature = request.headers.get('X-Integration-Signature')
        if not signature:
            return jsonify({'error': 'Missing signature'}), 401

        # Verify signature
        body = request.get_data()
        expected_sig = hmac.new(
            API_INTEGRATION_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return jsonify({'error': 'Invalid signature'}), 401

        return f(*args, **kwargs)
    return decorated


def create_integration_signature(body):
    """Create a request signature for outgoing API calls."""
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    elif isinstance(body, str):
        body = body.encode()

    return hmac.new(
        API_INTEGRATION_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()


# ============================================================================
# USER 2FA SYNCHRONIZATION
# ============================================================================

def sync_user_2fa_status(user_id, is_2fa_enabled, totp_secret=None):
    """
    Sync user 2FA status across applications.
    Called when a user enables/disables 2FA on any app.

    Args:
        user_id: User ID across applications
        is_2fa_enabled: Whether 2FA is currently enabled
        totp_secret: TOTP secret (optional, for sync)
    """
    if not ENABLE_CROSS_APP_SYNC or not API_INTEGRATION_KEY:
        return None

    # Get target app URL from environment
    target_url = os.getenv('SECONDARY_APP_API_URL')
    if not target_url:
        return None

    import requests

    payload = {
        'user_id': user_id,
        'is_2fa_enabled': is_2fa_enabled,
        'timestamp': datetime.utcnow().isoformat(),
        'app_instance': os.getenv('APP_INSTANCE_NAME', 'default')
    }

    body = json.dumps(payload)
    signature = create_integration_signature(body)

    try:
        response = requests.post(
            f"{target_url}/api/integration/sync-2fa",
            json=payload,
            headers={
                'X-Integration-Key': API_INTEGRATION_KEY,
                'X-Integration-Signature': signature,
                'Content-Type': 'application/json'
            },
            timeout=5
        )
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"[ERROR] Failed to sync 2FA status: {e}")
        return None


def get_user_2fa_status_from_peer(user_id):
    """
    Get user 2FA status from peer application.
    Useful for SSO: check if user has 2FA enabled in main app.

    Args:
        user_id: User ID

    Returns:
        dict with 2FA status or None if unavailable
    """
    if not ENABLE_CROSS_APP_SYNC or not API_INTEGRATION_KEY:
        return None

    target_url = os.getenv('SECONDARY_APP_API_URL')
    if not target_url:
        return None

    import requests

    try:
        response = requests.get(
            f"{target_url}/api/integration/user/{user_id}/2fa-status",
            headers={
                'X-Integration-Key': API_INTEGRATION_KEY,
            },
            timeout=5
        )
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"[ERROR] Failed to get 2FA status from peer: {e}")
        return None


# ============================================================================
# SECURITY EVENT SHARING
# ============================================================================

def log_security_event_to_shared_db(event_type, ip_address, severity, description, app_instance=None):
    """
    Log security event to shared security database.
    Centralizes threat detection across all ShowWise instances.

    Args:
        event_type: Type of event (burp_detected, login_failed, etc)
        ip_address: Source IP address
        severity: Event severity (low, medium, high, critical)
        description: Event description
        app_instance: Which app instance detected this
    """
    if not ENABLE_CROSS_APP_SYNC or not API_INTEGRATION_KEY:
        return None

    target_url = os.getenv('SHARED_SECURITY_DB_URL')
    if not target_url:
        return None

    import requests

    payload = {
        'event_type': event_type,
        'ip_address': ip_address,
        'severity': severity,
        'description': description,
        'app_instance': app_instance or os.getenv('APP_INSTANCE_NAME', 'default'),
        'timestamp': datetime.utcnow().isoformat()
    }

    body = json.dumps(payload)
    signature = create_integration_signature(body)

    try:
        response = requests.post(
            f"{target_url}/api/security/events",
            json=payload,
            headers={
                'X-Integration-Key': API_INTEGRATION_KEY,
                'X-Integration-Signature': signature,
                'Content-Type': 'application/json'
            },
            timeout=5
        )
        return response.json() if response.status_code in [200, 201] else None
    except Exception as e:
        print(f"[ERROR] Failed to log security event: {e}")
        return None


# ============================================================================
# IP REPUTATION SHARING
# ============================================================================

def check_ip_reputation(ip_address):
    """
    Check IP reputation from shared security database.
    Blocks IPs that are blacklisted or quarantined on any app.

    Args:
        ip_address: IP address to check

    Returns:
        dict with reputation info or None
    """
    if not ENABLE_CROSS_APP_SYNC or not API_INTEGRATION_KEY:
        return None

    target_url = os.getenv('SHARED_SECURITY_DB_URL')
    if not target_url:
        return None

    import requests

    try:
        response = requests.get(
            f"{target_url}/api/security/ip/{ip_address}/reputation",
            headers={
                'X-Integration-Key': API_INTEGRATION_KEY,
            },
            timeout=5
        )
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"[ERROR] Failed to check IP reputation: {e}")
        return None


def report_ip_threat(ip_address, threat_type, severity, details):
    """
    Report an IP threat to shared security database.
    Helps protect all ShowWise instances from bad actors.

    Args:
        ip_address: Threatening IP address
        threat_type: Type of threat (burpsuite, sqli, xss, etc)
        severity: Severity level
        details: Additional threat details
    """
    if not ENABLE_CROSS_APP_SYNC or not API_INTEGRATION_KEY:
        return None

    target_url = os.getenv('SHARED_SECURITY_DB_URL')
    if not target_url:
        return None

    import requests

    payload = {
        'ip_address': ip_address,
        'threat_type': threat_type,
        'severity': severity,
        'details': details,
        'reported_by': os.getenv('APP_INSTANCE_NAME', 'default'),
        'timestamp': datetime.utcnow().isoformat()
    }

    body = json.dumps(payload)
    signature = create_integration_signature(body)

    try:
        response = requests.post(
            f"{target_url}/api/security/ip-threat",
            json=payload,
            headers={
                'X-Integration-Key': API_INTEGRATION_KEY,
                'X-Integration-Signature': signature,
                'Content-Type': 'application/json'
            },
            timeout=5
        )
        return response.json() if response.status_code in [200, 201] else None
    except Exception as e:
        print(f"[ERROR] Failed to report IP threat: {e}")
        return None


# ============================================================================
# ENDPOINTS FOR RECEIVING CROSS-APP REQUESTS
# ============================================================================

def create_integration_bp():
    """Create Blueprint with integration endpoints."""
    from flask import Blueprint

    integration_bp = Blueprint('integration', __name__, url_prefix='/api/integration')

    @integration_bp.route('/sync-2fa', methods=['POST'])
    @verify_integration_signature
    def receive_2fa_sync():
        """Receive 2FA sync from peer application."""
        data = request.json or {}
        user_id = data.get('user_id')
        is_2fa_enabled = data.get('is_2fa_enabled')

        if user_id is None or is_2fa_enabled is None:
            return jsonify({'error': 'Missing required fields'}), 400

        # Import User model
        try:
            from models import User, db
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Update 2FA status
            user.is_2fa_enabled = is_2fa_enabled
            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'2FA status sync received for user {user_id}'
            }), 200
        except Exception as e:
            return jsonify({'error': f'Sync failed: {str(e)}'}), 500

    @integration_bp.route('/user/<int:user_id>/2fa-status', methods=['GET'])
    def get_user_2fa_status_endpoint(user_id):
        """Get user 2FA status (requires API key)."""
        # Verify API key
        api_key = request.headers.get('X-Integration-Key')
        if api_key != API_INTEGRATION_KEY:
            return jsonify({'error': 'Invalid API key'}), 401

        try:
            from models import User
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404

            return jsonify({
                'user_id': user.id,
                'is_2fa_enabled': user.is_2fa_enabled,
                'has_totp_secret': bool(user.totp_secret),
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return integration_bp
