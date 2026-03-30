"""
API v1 - Audit Logs Endpoints
Access and manage audit logs
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from models import db, RequestLog, SecurityEvent
from api.v1.auth import require_api_key
from api.v1.users import require_admin

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/requests', methods=['GET'])
@require_api_key
@require_admin
def get_request_logs():
    """Get API request logs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    endpoint = request.args.get('endpoint')
    method = request.args.get('method')
    min_status = request.args.get('min_status', 400, type=int)  # Errors by default
    user_id = request.args.get('user_id', type=int)
    days = request.args.get('days', 30, type=int)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = RequestLog.query.filter(RequestLog.created_at >= cutoff)
    
    if endpoint:
        query = query.filter(RequestLog.endpoint.ilike(f'%{endpoint}%'))
    if method:
        query = query.filter_by(method=method)
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    query = query.filter(RequestLog.status_code >= min_status)
    query = query.order_by(RequestLog.created_at.desc())
    
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'logs': [_request_log_to_dict(log) for log in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page,
        'filters': {
            'endpoint': endpoint,
            'method': method,
            'min_status': min_status,
            'user_id': user_id,
            'days': days
        }
    }), 200


@logs_bp.route('/requests/<int:log_id>', methods=['GET'])
@require_api_key
@require_admin
def get_request_log_detail(log_id):
    """Get specific request log details"""
    log = RequestLog.query.get(log_id)
    if not log:
        return jsonify({'error': 'Log not found'}), 404
    
    return jsonify({
        'success': True,
        'log': _request_log_to_dict(log, full=True)
    }), 200


@logs_bp.route('/security-events', methods=['GET'])
@require_api_key
@require_admin
def get_security_logs():
    """Get security event logs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    event_type = request.args.get('event_type')
    severity = request.args.get('severity')
    ip_address = request.args.get('ip_address')
    user_id = request.args.get('user_id', type=int)
    days = request.args.get('days', 90, type=int)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = SecurityEvent.query.filter(SecurityEvent.created_at >= cutoff)
    
    if event_type:
        query = query.filter_by(event_type=event_type)
    if severity:
        query = query.filter_by(severity=severity)
    if ip_address:
        query = query.filter_by(ip_address=ip_address)
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    query = query.order_by(SecurityEvent.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'logs': [_security_event_to_dict(log) for log in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page,
        'filters': {
            'event_type': event_type,
            'severity': severity,
            'ip_address': ip_address,
            'user_id': user_id,
            'days': days
        }
    }), 200


@logs_bp.route('/user/<int:user_id>/trail', methods=['GET'])
@require_api_key
@require_admin
def get_user_audit_trail(user_id):
    """Get complete audit trail for a user"""
    from services.audit_logger import AuditLogger
    
    audit = AuditLogger(db)
    events = audit.get_user_audit_trail(user_id, days=90)
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'total_events': len(events),
        'events': [_security_event_to_dict(e) for e in events[:100]]
    }), 200


@logs_bp.route('/ip/<ip_address>/trail', methods=['GET'])
@require_api_key
@require_admin
def get_ip_audit_trail(ip_address):
    """Get all activity from an IP address"""
    from services.audit_logger import AuditLogger
    
    audit = AuditLogger(db)
    trail = audit.get_ip_audit_trail(ip_address, days=30)
    
    return jsonify({
        'success': True,
        'ip_address': ip_address,
        'security_events': len(trail['security_events']),
        'api_calls': len(trail['api_calls']),
        'events': [_security_event_to_dict(e) for e in trail['security_events'][:50]],
        'recent_calls': [_request_log_to_dict(log) for log in trail['api_calls'][:50]]
    }), 200


@logs_bp.route('/analytics', methods=['GET'])
@require_api_key
@require_admin
def get_log_analytics():
    """Get analytics and statistics about logs"""
    days = request.args.get('days', 30, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    from sqlalchemy import func
    
    # Request statistics
    request_stats = db.session.query(
        func.strftime('%Y-%m-%d', RequestLog.created_at).label('date'),
        func.count(RequestLog.id).label('total'),
        func.avg(RequestLog.status_code).label('avg_status')
    ).filter(RequestLog.created_at >= cutoff).group_by('date').all()
    
    # Top endpoints
    top_endpoints = db.session.query(
        RequestLog.endpoint,
        func.count(RequestLog.id).label('count'),
        func.avg(RequestLog.response_time_ms).label('avg_time')
    ).filter(RequestLog.created_at >= cutoff).group_by(RequestLog.endpoint).order_by(
        func.count(RequestLog.id).desc()
    ).limit(20).all()
    
    # Security event stats
    security_stats = db.session.query(
        SecurityEvent.event_type,
        func.count(SecurityEvent.id).label('count')
    ).filter(SecurityEvent.created_at >= cutoff).group_by(SecurityEvent.event_type).all()
    
    return jsonify({
        'success': True,
        'period_days': days,
        'analytics': {
            'request_trends': [
                {'date': s[0], 'requests': s[1], 'avg_status': round(s[2], 2) if s[2] else 0}
                for s in request_stats
            ],
            'top_endpoints': [
                {'endpoint': e[0], 'calls': e[1], 'avg_time_ms': round(e[2], 2) if e[2] else 0}
                for e in top_endpoints
            ],
            'security_events': {
                event_type: count for event_type, count in security_stats
            }
        }
    }), 200


@logs_bp.route('/export/csv', methods=['GET'])
@require_api_key
@require_admin
def export_logs_csv():
    """Export logs as CSV"""
    import csv
    from io import StringIO
    
    log_type = request.args.get('type', 'requests')  # requests or security
    days = request.args.get('days', 30, type=int)
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    output = StringIO()
    writer = csv.writer(output)
    
    if log_type == 'requests':
        logs = RequestLog.query.filter(RequestLog.created_at >= cutoff).order_by(
            RequestLog.created_at.desc()
        ).limit(10000).all()
        
        writer.writerow(['ID', 'Endpoint', 'Method', 'Status Code', 'User ID', 'IP Address', 'Response Time (ms)', 'Timestamp'])
        for log in logs:
            writer.writerow([
                log.id, log.endpoint, log.method, log.status_code,
                log.user_id, log.ip_address, log.response_time_ms,
                log.created_at.isoformat()
            ])
    else:
        logs = SecurityEvent.query.filter(SecurityEvent.created_at >= cutoff).order_by(
            SecurityEvent.created_at.desc()
        ).limit(10000).all()
        
        writer.writerow(['ID', 'Event Type', 'Description', 'Severity', 'User ID', 'IP Address', 'Organization ID', 'Timestamp'])
        for log in logs:
            writer.writerow([
                log.id, log.event_type, log.description, log.severity,
                log.user_id, log.ip_address, log.organization_id,
                log.created_at.isoformat()
            ])
    
    from flask import make_response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=logs_{log_type}_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response


def _request_log_to_dict(log, full=False):
    """Convert request log to dict"""
    data = {
        'id': log.id,
        'endpoint': log.endpoint,
        'method': log.method,
        'status_code': log.status_code,
        'user_id': log.user_id,
        'ip_address': log.ip_address,
        'response_time_ms': log.response_time_ms,
        'created_at': log.created_at.isoformat() if log.created_at else None
    }
    
    if full:
        data['request_data'] = log.request_data or {}
    
    return data


def _security_event_to_dict(event):
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
