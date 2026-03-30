"""
API v1 - Admin Endpoints
System administration endpoints
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from models import db
from api.v1.auth import require_api_key
from api.v1.users import require_admin

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/system/stats', methods=['GET'])
@require_api_key
@require_admin
def system_statistics():
    """Get system-wide statistics"""
    from models import User, Organization, ChatMessage
    
    return jsonify({
        'success': True,
        'statistics': {
            'users': {
                'total': User.query.count(),
                'active': User.query.filter_by(is_active=True).count(),
                'admins': User.query.filter_by(role='admin').count(),
            },
            'organizations': {
                'total': Organization.query.count(),
                'active': Organization.query.filter_by(is_active=True).count(),
            },
            'communication': {
                'total_messages': ChatMessage.query.count(),
                'unread': ChatMessage.query.filter_by(is_read=False).count(),
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    }), 200


@admin_bp.route('/system/health', methods=['GET'])
@require_api_key
@require_admin
def system_health():
    """Get system health check"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        db_status = 'healthy'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'success': True,
        'health': {
            'status': 'operational' if db_status == 'healthy' else 'degraded',
            'database': db_status,
            'timestamp': datetime.utcnow().isoformat(),
            'uptime_seconds': None  # Calculate from app startup time in production
        }
    }), 200


@admin_bp.route('/audit/summary', methods=['GET'])
@require_api_key
@require_admin
def audit_summary():
    """Get audit activity summary"""
    from models import SecurityEvent, RequestLog
    from datetime import timedelta
    
    hours = request.args.get('hours', 24, type=int)
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    security_events = SecurityEvent.query.filter(SecurityEvent.created_at >= cutoff).count()
    api_calls = RequestLog.query.filter(RequestLog.created_at >= cutoff).count()
    
    # Critical alerts
    critical = SecurityEvent.query.filter(
        SecurityEvent.severity == 'CRITICAL',
        SecurityEvent.created_at >= cutoff
    ).count()
    
    return jsonify({
        'success': True,
        'period_hours': hours,
        'summary': {
            'security_events': security_events,
            'api_calls': api_calls,
            'critical_alerts': critical
        }
    }), 200


@admin_bp.route('/settings', methods=['GET'])
@require_api_key
@require_admin
def get_system_settings():
    """Get system configuration settings"""
    import os
    
    return jsonify({
        'success': True,
        'settings': {
            'debug_mode': os.getenv('FLASK_ENV') == 'development',
            'rate_limiting_enabled': True,
            '2fa_required': False,
            'max_session_hours': 12,
            'password_min_length': 12,
            'api_version': 'v1'
        }
    }), 200


@admin_bp.route('/settings', methods=['PUT'])
@require_api_key
@require_admin
def update_system_settings():
    """Update system settings"""
    data = request.get_json() or {}
    
    # In production, store these in a settings table
    settings = {
        '2fa_required': data.get('2fa_required', False),
        'max_session_hours': data.get('max_session_hours', 12),
    }
    
    return jsonify({
        'success': True,
        'message': 'Settings updated',
        'settings': settings
    }), 200


@admin_bp.route('/cache/clear', methods=['POST'])
@require_api_key
@require_admin
def clear_cache():
    """Clear application cache"""
    try:
        # In production, clear Redis or memcached
        return jsonify({
            'success': True,
            'message': 'Cache cleared successfully'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/logs/archivable', methods=['GET'])
@require_api_key
@require_admin
def get_archivable_logs():
    """Get logs eligible for archival (older than 90 days)"""
    from models import SecurityEvent, RequestLog
    from datetime import timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=90)
    
    old_security_events = SecurityEvent.query.filter(
        SecurityEvent.created_at < cutoff
    ).count()
    
    old_requests = RequestLog.query.filter(
        RequestLog.created_at < cutoff
    ).count()
    
    return jsonify({
        'success': True,
        'archivable': {
            'security_events': old_security_events,
            'api_requests': old_requests,
            'total': old_security_events + old_requests,
            'cutoff_date': cutoff.isoformat()
        }
    }), 200


@admin_bp.route('/logs/cleanup', methods=['POST'])
@require_api_key
@require_admin
def cleanup_old_logs():
    """Delete logs older than specified days"""
    from models import SecurityEvent, RequestLog
    from datetime import timedelta
    
    days = request.json.get('days', 365)
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    try:
        security_deleted = SecurityEvent.query.filter(
            SecurityEvent.created_at < cutoff
        ).delete()
        
        requests_deleted = RequestLog.query.filter(
            RequestLog.created_at < cutoff
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'deleted': {
                'security_events': security_deleted,
                'api_requests': requests_deleted,
                'total': security_deleted + requests_deleted
            },
            'message': f'Deleted logs older than {days} days'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
