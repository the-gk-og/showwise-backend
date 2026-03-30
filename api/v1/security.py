"""
API v1 - Security Endpoint
Security dashboard, threat detection, IP management, and security events
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime, timedelta
from models import db, SecurityEvent, IPBlacklist, IPQuarantine
from services.audit_logger import AuditLogger
from services.security_engine import IPSecurityEngine
from api.v1.auth import require_api_key
from api.v1.users import require_admin

security_bp = Blueprint('security', __name__)


@security_bp.route('/dashboard', methods=['GET'])
@require_api_key
@require_admin
def security_dashboard():
    """Get security overview dashboard"""
    days = request.args.get('days', 30, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Count security metrics
    total_events = SecurityEvent.query.count()
    recent_events = SecurityEvent.query.filter(SecurityEvent.created_at >= cutoff).count()
    failed_logins = SecurityEvent.query.filter(
        SecurityEvent.event_type == 'login_failed',
        SecurityEvent.created_at >= cutoff
    ).count()
    
    # IP statistics
    security_engine = IPSecurityEngine(db)
    ip_stats = security_engine.get_ip_statistics()
    
    # Get critical events
    critical_events = SecurityEvent.query.filter(
        SecurityEvent.severity == 'CRITICAL'
    ).order_by(SecurityEvent.created_at.desc()).limit(10).all()
    
    return jsonify({
        'success': True,
        'dashboard': {
            'period_days': days,
            'total_security_events': total_events,
            'recent_events': recent_events,
            'failed_login_attempts': failed_logins,
            'ip_statistics': ip_stats,
            'critical_alerts': len(critical_events),
            'critical_events': [_event_to_dict(e) for e in critical_events]
        }
    }), 200


@security_bp.route('/events', methods=['GET'])
@require_api_key
@require_admin
def get_security_events():
    """Get security events with filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    event_type = request.args.get('event_type')
    severity = request.args.get('severity')
    days = request.args.get('days', 30, type=int)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    query = SecurityEvent.query.filter(SecurityEvent.created_at >= cutoff)
    
    if event_type:
        query = query.filter_by(event_type=event_type)
    if severity:
        query = query.filter_by(severity=severity)
    
    query = query.order_by(SecurityEvent.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'events': [_event_to_dict(e) for e in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page,
        'filters': {'event_type': event_type, 'severity': severity, 'days': days}
    }), 200


@security_bp.route('/check-risk', methods=['POST'])
@require_api_key
def check_request_risk():
    """Assess risk of current request"""
    security_engine = IPSecurityEngine(db)
    risk_assessment = security_engine.assess_request_risk(request)
    
    return jsonify({
        'success': True,
        'risk_assessment': risk_assessment
    }), 200


@security_bp.route('/ip/<ip_address>/reputation', methods=['GET'])
@require_api_key
@require_admin
def get_ip_reputation(ip_address):
    """Get IP reputation and history"""
    security_engine = IPSecurityEngine(db)
    
    # Get reputation
    reputation = security_engine.check_ip_reputation(ip_address)
    
    # Get audit trail
    audit = AuditLogger(db)
    audit_trail = audit.get_ip_audit_trail(ip_address)
    
    return jsonify({
        'success': True,
        'ip_address': ip_address,
        'reputation': reputation,
        'audit_trail': {
            'security_events': len(audit_trail['security_events']),
            'api_calls': len(audit_trail['api_calls']),
            'recent_events': [_event_to_dict(e) for e in audit_trail['security_events'][:10]]
        }
    }), 200


@security_bp.route('/ip/<ip_address>/blacklist', methods=['POST'])
@require_api_key
@require_admin
def blacklist_ip(ip_address):
    """Add IP to blacklist"""
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual blacklist')
    duration_hours = data.get('duration_hours', 24)
    severity = data.get('severity', 'MEDIUM')
    
    security_engine = IPSecurityEngine(db)
    success = security_engine.blacklist_ip(ip_address, reason, duration_hours, severity)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'IP {ip_address} blacklisted for {duration_hours} hours'
        }), 201
    else:
        return jsonify({'error': 'Failed to blacklist IP'}), 500


@security_bp.route('/ip/<ip_address>/quarantine', methods=['POST'])
@require_api_key
@require_admin
def quarantine_ip(ip_address):
    """Add IP to quarantine"""
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual quarantine')
    threat_score = data.get('threat_score', 50)
    duration_hours = data.get('duration_hours', 24)
    
    security_engine = IPSecurityEngine(db)
    success = security_engine.quarantine_ip(ip_address, reason, threat_score, duration_hours)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'IP {ip_address} quarantined'
        }), 201
    else:
        return jsonify({'error': 'Failed to quarantine IP'}), 500


@security_bp.route('/ip/<ip_address>/whitelist', methods=['POST'])
@require_api_key
@require_admin
def whitelist_ip(ip_address):
    """Remove IP from blacklist/quarantine"""
    security_engine = IPSecurityEngine(db)
    success = security_engine.whitelist_ip(ip_address)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'IP {ip_address} whitelisted'
        }), 200
    else:
        return jsonify({'error': 'Failed to whitelist IP'}), 500


@security_bp.route('/blocked-ips', methods=['GET'])
@require_api_key
@require_admin
def get_blocked_ips():
    """Get list of blocked IPs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = IPBlacklist.query.filter_by(is_active=True).order_by(IPBlacklist.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'blocked_ips': [_ip_to_dict(entry) for entry in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page
    }), 200


@security_bp.route('/quarantined-ips', methods=['GET'])
@require_api_key
@require_admin
def get_quarantined_ips():
    """Get list of quarantined IPs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = IPQuarantine.query.filter_by(is_active=True).order_by(IPQuarantine.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'quarantined_ips': [_ip_to_dict(entry) for entry in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page
    }), 200


@security_bp.route('/threats/summary', methods=['GET'])
@require_api_key
@require_admin
def threats_summary():
    """Get threat summary and statistics"""
    days = request.args.get('days', 7, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Count events by type
    from sqlalchemy import func
    threat_types = db.session.query(
        SecurityEvent.event_type,
        func.count(SecurityEvent.id).label('count')
    ).filter(SecurityEvent.created_at >= cutoff).group_by(SecurityEvent.event_type).all()
    
    # Count events by severity
    threat_severity = db.session.query(
        SecurityEvent.severity,
        func.count(SecurityEvent.id).label('count')
    ).filter(SecurityEvent.created_at >= cutoff).group_by(SecurityEvent.severity).all()
    
    return jsonify({
        'success': True,
        'summary': {
            'period_days': days,
            'by_type': {event_type: count for event_type, count in threat_types},
            'by_severity': {severity: count for severity, count in threat_severity}
        }
    }), 200


def _event_to_dict(event):
    """Convert security event to dict"""
    return {
        'id': event.id,
        'event_type': event.event_type,
        'description': event.description,
        'severity': event.severity,
        'user_id': event.user_id,
        'ip_address': event.ip_address,
        'organization_id': event.organization_id,
        'metadata': event.metadata or {},
        'created_at': event.created_at.isoformat() if event.created_at else None
    }


def _ip_to_dict(entry):
    """Convert IP entry to dict"""
    return {
        'id': entry.id,
        'ip_address': entry.ip_address,
        'reason': entry.reason,
        'severity': getattr(entry, 'severity', 'MEDIUM'),
        'threat_score': getattr(entry, 'threat_score', None),
        'created_at': entry.created_at.isoformat() if entry.created_at else None,
        'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
        'is_active': entry.is_active
    }
