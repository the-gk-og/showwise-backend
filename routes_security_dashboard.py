"""
routes_security_dashboard.py
============================
Security Dashboard API endpoints for ShowWise Backend.
Provides admin access to:
- Security events and logs
- IP threat detection
- Quarantined IPs
- Blacklisted IPs
- 2FA audit trails
- Login attempts
"""

from flask import Blueprint, request, jsonify, g
from functools import wraps
from datetime import datetime, timedelta
from models import db, User, Log, APIKey
from auth import log_security_event, get_client_ip

security_dashboard_bp = Blueprint('security_dashboard', __name__, url_prefix='/api/security')


def admin_api_required(f):
    """Decorator: Require admin access via API key or session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check session
        from flask import session
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user and user.is_active and user.role == 'admin':
                g.user = user
                g.auth_method = 'session'
                return f(*args, **kwargs)

        # Check API key
        api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if api_key:
            key_obj = APIKey.query.filter_by(key=api_key, is_active=True).first()
            if key_obj and key_obj.user and key_obj.user.role == 'admin':
                g.user = key_obj.user
                g.auth_method = 'api_key'
                g.api_key_id = key_obj.id
                return f(*args, **kwargs)

        return jsonify({'error': 'Admin access required'}), 403
    return decorated


# ============================================================================
# DASHBOARD OVERVIEW
# ============================================================================

@security_dashboard_bp.route('/overview', methods=['GET'])
@admin_api_required
def get_security_overview():
    """Get security dashboard overview statistics."""
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Get stats from logs
    login_attempts_24h = Log.query.filter(
        Log.log_type.in_(['login_success', 'login_failed']),
        Log.created_at >= last_24h
    ).count()

    failed_logins_24h = Log.query.filter(
        Log.log_type == 'login_failed',
        Log.created_at >= last_24h
    ).count()

    account_lockouts_7d = Log.query.filter(
        Log.log_type == 'account_locked',
        Log.created_at >= last_7d
    ).count()

    totp_enabled_count = User.query.filter_by(is_2fa_enabled=True).count()
    total_users = User.query.count()

    # Get recent security events
    recent_events = Log.query.filter(
        Log.log_type.in_(['account_locked', 'totp_failed', 'api_error']),
        Log.created_at >= last_24h
    ).order_by(Log.created_at.desc()).limit(20).all()

    events_data = []
    for event in recent_events:
        events_data.append({
            'id': event.id,
            'type': event.log_type,
            'message': event.message,
            'level': event.level,
            'user_id': event.user_id,
            'ip_address': event.ip_address,
            'timestamp': event.created_at.isoformat()
        })

    return jsonify({
        'overview': {
            'login_attempts_24h': login_attempts_24h,
            'failed_logins_24h': failed_logins_24h,
            'account_lockouts_7d': account_lockouts_7d,
            '2fa_enabled_users': totp_enabled_count,
            'total_users': total_users,
            '2fa_adoption_rate': round((totp_enabled_count / total_users * 100) if total_users > 0 else 0, 2)
        },
        'recent_events': events_data
    }), 200


# ============================================================================
# SECURITY LOGS
# ============================================================================

@security_dashboard_bp.route('/logs', methods=['GET'])
@admin_api_required
def get_security_logs():
    """Get filtered security logs."""
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    log_type = request.args.get('log_type')
    level = request.args.get('level')  # 'warning', 'error', etc
    days = int(request.args.get('days', 7))

    since = datetime.utcnow() - timedelta(days=days)

    query = Log.query.filter(Log.created_at >= since)

    if log_type:
        query = query.filter_by(log_type=log_type)
    if level:
        query = query.filter_by(level=level)

    total = query.count()
    logs = query.order_by(Log.created_at.desc()).offset(offset).limit(limit).all()

    logs_data = []
    for log in logs:
        logs_data.append({
            'id': log.id,
            'type': log.log_type,
            'level': log.level,
            'message': log.message,
            'user_id': log.user_id,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent,
            'timestamp': log.created_at.isoformat(),
            'metadata': log.event_metadata
        })

    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'logs': logs_data
    }), 200


# ============================================================================
# USER SECURITY STATUS
# ============================================================================

@security_dashboard_bp.route('/users/security-status', methods=['GET'])
@admin_api_required
def get_users_security_status():
    """Get security status for all users."""
    limit = min(int(request.args.get('limit', 100)), 500)

    users = User.query.order_by(User.created_at.desc()).limit(limit).all()

    users_data = []
    for user in users:
        # Get failed login attempts in last 7 days
        failed_attempts = Log.query.filter(
            Log.user_id == user.id,
            Log.log_type == 'login_failed',
            Log.created_at >= datetime.utcnow() - timedelta(days=7)
        ).count()

        users_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'is_2fa_enabled': user.is_2fa_enabled,
            'login_attempts': user.login_attempts or 0,
            'is_locked': user.locked_until and user.locked_until > datetime.utcnow(),
            'failed_attempts_7d': failed_attempts,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'last_ip': user.last_ip,
            'created_at': user.created_at.isoformat()
        })

    return jsonify({
        'total': len(users_data),
        'users': users_data
    }), 200


@security_dashboard_bp.route('/users/<int:user_id>/security-details', methods=['GET'])
@admin_api_required
def get_user_security_details(user_id):
    """Get detailed security information for a specific user."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    days = int(request.args.get('days', 30))
    since = datetime.utcnow() - timedelta(days=days)

    # Get login attempts
    login_logs = Log.query.filter(
        Log.user_id == user_id,
        Log.log_type.in_(['login_success', 'login_failed']),
        Log.created_at >= since
    ).order_by(Log.created_at.desc()).all()

    # Get 2FA events
    totp_logs = Log.query.filter(
        Log.user_id == user_id,
        Log.log_type.in_(['totp_enabled', 'totp_disabled', 'totp_verify_failed']),
        Log.created_at >= since
    ).order_by(Log.created_at.desc()).all()

    # Get all security events
    all_logs = Log.query.filter(
        Log.user_id == user_id,
        Log.created_at >= since
    ).order_by(Log.created_at.desc()).all()

    login_data = []
    for log in login_logs:
        login_data.append({
            'type': log.log_type,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent,
            'timestamp': log.created_at.isoformat()
        })

    totp_data = []
    for log in totp_logs:
        totp_data.append({
            'event': log.log_type,
            'timestamp': log.created_at.isoformat()
        })

    security_events = []
    for log in all_logs:
        security_events.append({
            'type': log.log_type,
            'level': log.level,
            'message': log.message,
            'ip_address': log.ip_address,
            'timestamp': log.created_at.isoformat()
        })

    return jsonify({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_2fa_enabled': user.is_2fa_enabled,
            'is_locked': user.locked_until and user.locked_until > datetime.utcnow()
        },
        'login_history': login_data,
        '2fa_events': totp_data,
        'security_events': security_events[:50]  # Last 50
    }), 200


# ============================================================================
# THREAT MANAGEMENT
# ============================================================================

@security_dashboard_bp.route('/threats/summary', methods=['GET'])
@admin_api_required
def get_threat_summary():
    """Get summary of recent threats."""
    days = int(request.args.get('days', 7))
    since = datetime.utcnow() - timedelta(days=days)

    threat_logs = Log.query.filter(
        Log.log_type.in_(['account_locked', 'totp_verify_failed', 'login_failed']),
        Log.created_at >= since,
        Log.level.in_(['warning', 'error', 'critical'])
    ).all()

    threat_summary = {
        'lockouts': 0,
        'totp_failures': 0,
        'login_failures': 0,
        'unique_ips': set(),
        'unique_users': set()
    }

    for log in threat_logs:
        if log.log_type == 'account_locked':
            threat_summary['lockouts'] += 1
        elif log.log_type == 'totp_verify_failed':
            threat_summary['totp_failures'] += 1
        elif log.log_type == 'login_failed':
            threat_summary['login_failures'] += 1

        if log.ip_address:
            threat_summary['unique_ips'].add(log.ip_address)
        if log.user_id:
            threat_summary['unique_users'].add(log.user_id)

    threat_summary['unique_ips'] = len(threat_summary['unique_ips'])
    threat_summary['unique_users'] = len(threat_summary['unique_users'])

    return jsonify({
        'period_days': days,
        'summary': threat_summary
    }), 200


@security_dashboard_bp.route('/alerts/critical', methods=['GET'])
@admin_api_required
def get_critical_alerts():
    """Get critical security alerts."""
    hours = int(request.args.get('hours', 24))
    since = datetime.utcnow() - timedelta(hours=hours)

    critical_logs = Log.query.filter(
        Log.level.in_(['error', 'critical']),
        Log.created_at >= since
    ).order_by(Log.created_at.desc()).limit(50).all()

    alerts = []
    for log in critical_logs:
        alerts.append({
            'id': log.id,
            'type': log.log_type,
            'level': log.level,
            'message': log.message,
            'user_id': log.user_id,
            'ip_address': log.ip_address,
            'timestamp': log.created_at.isoformat()
        })

    return jsonify({
        'alerts': alerts,
        'count': len(alerts)
    }), 200


# ============================================================================
# API KEY MANAGEMENT
# ============================================================================

@security_dashboard_bp.route('/api-keys/active', methods=['GET'])
@admin_api_required
def get_active_api_keys():
    """Get all active API keys with usage statistics."""
    api_keys = APIKey.query.filter_by(is_active=True).all()

    keys_data = []
    for key in api_keys:
        # Count API key usage in logs
        usage_count = Log.query.filter(
            Log.log_type == 'api_call',
            Log.created_at >= datetime.utcnow() - timedelta(days=7)
        ).count()

        keys_data.append({
            'id': key.id,
            'name': key.name,
            'user_id': key.user_id,
            'user_email': key.user.email,
            'expires_at': key.expires_at.isoformat() if key.expires_at else None,
            'last_used': key.last_used.isoformat() if key.last_used else None,
            'usage_7d': usage_count
        })

    return jsonify({
        'total': len(keys_data),
        'api_keys': keys_data
    }), 200


# ============================================================================
# AUDIT & COMPLIANCE
# ============================================================================

@security_dashboard_bp.route('/compliance/mfa-status', methods=['GET'])
@admin_api_required
def get_mfa_compliance_status():
    """Get MFA adoption and compliance statistics."""
    total_users = User.query.count()
    mfa_enabled = User.query.filter_by(is_2fa_enabled=True).count()
    mfa_disabled = total_users - mfa_enabled

    mfa_adoption_rate = round((mfa_enabled / total_users * 100) if total_users > 0 else 0, 2)

    return jsonify({
        'total_users': total_users,
        'mfa_enabled': mfa_enabled,
        'mfa_disabled': mfa_disabled,
        'adoption_rate': mfa_adoption_rate,
        'compliance_status': 'good' if mfa_adoption_rate >= 80 else 'warning' if mfa_adoption_rate >= 50 else 'critical'
    }), 200


@security_dashboard_bp.route('/compliance/password-status', methods=['GET'])
@admin_api_required
def get_password_compliance_status():
    """Get password policy compliance (if tracking policy compliance)."""
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()

    users_with_recent_login = User.query.filter(
        User.last_login >= datetime.utcnow() - timedelta(days=90)
    ).count()

    dormant_accounts = active_users - users_with_recent_login

    return jsonify({
        'total_users': total_users,
        'active_users': active_users,
        'recent_login_90d': users_with_recent_login,
        'dormant_accounts': dormant_accounts,
        'recommendations': [
            'Review and update password policies' if dormant_accounts > (active_users * 0.1) else None,
            'Enforce 2FA for all users' if mfa_adoption_rate < 80 else None,
        ]
    }), 200
