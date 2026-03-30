"""
Comprehensive Audit Logging Service
Tracks all security events, API calls, and system changes
"""
import json
import logging
from datetime import datetime
from functools import wraps
from flask import request, session, g
from sqlalchemy import func

logger = logging.getLogger(__name__)


class AuditLogger:
    """Centralized audit logging for security events and API activity"""
    
    def __init__(self, db):
        self.db = db
    
    def log_event(self, event_type, description, severity='INFO', user_id=None, 
                  ip_address=None, org_id=None, metadata=None):
        """
        Log a security or system event
        
        Args:
            event_type: Type of event (login_success, login_failed, api_call, etc.)
            description: Human-readable description
            severity: INFO, WARNING, ERROR, CRITICAL
            user_id: User who triggered the event
            ip_address: IP address of origin
            org_id: Organization context
            metadata: Additional JSON data
        """
        from models import SecurityEvent
        
        if not ip_address:
            ip_address = self._get_client_ip()
        
        if not user_id and 'user_id' in session:
            user_id = session.get('user_id')
        
        try:
            event = SecurityEvent(
                event_type=event_type,
                description=description,
                severity=severity,
                user_id=user_id,
                ip_address=ip_address,
                organization_id=org_id,
                metadata=metadata or {},
                created_at=datetime.utcnow()
            )
            self.db.session.add(event)
            self.db.session.commit()
            
            # Also log to application logger
            log_level = getattr(logging, severity, logging.INFO)
            logger.log(log_level, f"[{event_type}] {description} (IP: {ip_address}, User: {user_id})")
            
            return event
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            self.db.session.rollback()
            return None
    
    def log_api_call(self, endpoint, method, status_code, user_id=None, 
                    ip_address=None, response_time=None, request_data=None):
        """Log API endpoint calls"""
        from models import RequestLog
        
        if not ip_address:
            ip_address = self._get_client_ip()
        
        if not user_id and 'user_id' in session:
            user_id = session.get('user_id')
        
        try:
            # Sanitize request data to avoid logging passwords
            safe_data = self._sanitize_request_data(request_data or {})
            
            log = RequestLog(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                user_id=user_id,
                ip_address=ip_address,
                response_time_ms=response_time,
                request_data=safe_data,
                created_at=datetime.utcnow()
            )
            self.db.session.add(log)
            self.db.session.commit()
            return log
        except Exception as e:
            logger.error(f"Failed to log API call: {e}")
            self.db.session.rollback()
            return None
    
    def log_login_attempt(self, username, success, ip_address=None, reason=None):
        """Track login attempts for brute-force detection"""
        severity = 'INFO' if success else 'WARNING'
        event_type = 'login_success' if success else 'login_failed'
        description = f"Login {'successful' if success else 'failed'} for user: {username}"
        if reason:
            description += f" ({reason})"
        
        self.log_event(
            event_type=event_type,
            description=description,
            severity=severity,
            ip_address=ip_address,
            metadata={'username': username, 'reason': reason}
        )
    
    def log_ip_blocked(self, ip_address, reason, threat_score=None):
        """Log when an IP is blocked"""
        self.log_event(
            event_type='ip_blocked',
            description=f"IP blocked: {ip_address} ({reason})",
            severity='WARNING',
            ip_address=ip_address,
            metadata={'reason': reason, 'threat_score': threat_score}
        )
    
    def log_suspicious_activity(self, activity_type, description, ip_address=None, user_id=None, severity='WARNING'):
        """Log suspicious activity for investigation"""
        self.log_event(
            event_type=f'suspicious_{activity_type}',
            description=description,
            severity=severity,
            ip_address=ip_address,
            user_id=user_id
        )
    
    def get_recent_events(self, limit=100, event_type=None, severity=None, user_id=None):
        """Retrieve recent audit events with filtering"""
        from models import SecurityEvent
        
        query = SecurityEvent.query
        
        if event_type:
            query = query.filter_by(event_type=event_type)
        if severity:
            query = query.filter_by(severity=severity)
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        return query.order_by(SecurityEvent.created_at.desc()).limit(limit).all()
    
    def get_user_audit_trail(self, user_id, days=30):
        """Get complete audit trail for a user"""
        from models import SecurityEvent
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        return SecurityEvent.query.filter(
            SecurityEvent.user_id == user_id,
            SecurityEvent.created_at >= cutoff
        ).order_by(SecurityEvent.created_at.desc()).all()
    
    def get_ip_audit_trail(self, ip_address, days=30):
        """Get all activity from an IP address"""
        from models import SecurityEvent, RequestLog
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        return {
            'security_events': SecurityEvent.query.filter(
                SecurityEvent.ip_address == ip_address,
                SecurityEvent.created_at >= cutoff
            ).order_by(SecurityEvent.created_at.desc()).all(),
            'api_calls': RequestLog.query.filter(
                RequestLog.ip_address == ip_address,
                RequestLog.created_at >= cutoff
            ).order_by(RequestLog.created_at.desc()).all()
        }
    
    def get_failed_login_attempts(self, ip_address=None, hours=24):
        """Track failed login attempts for rate limiting"""
        from models import SecurityEvent
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = SecurityEvent.query.filter(
            SecurityEvent.event_type == 'login_failed',
            SecurityEvent.created_at >= cutoff
        )
        
        if ip_address:
            query = query.filter_by(ip_address=ip_address)
        
        return query.all()
    
    @staticmethod
    def _get_client_ip():
        """Extract client IP from request headers"""
        # Check Cloudflare header first
        if request.headers.get('CF-Connecting-IP'):
            return request.headers.get('CF-Connecting-IP')
        
        # Check X-Forwarded-For
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        
        # Fall back to remote_addr
        return request.remote_addr or 'unknown'
    
    @staticmethod
    def _sanitize_request_data(data):
        """Remove sensitive fields from logged request data"""
        if not data:
            return {}
        
        sensitive_fields = {
            'password', 'passwd', 'pwd', 'secret', 'token', 'api_key', 
            'authorization', 'credit_card', 'cvv', 'ssn'
        }
        
        sanitized = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = '***REDACTED***'
            else:
                sanitized[key] = str(value)[:100]  # Limit string length
        
        return sanitized


def audit_log_decorator(event_type, get_description=None):
    """Decorator to automatically log API calls"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from models import db
            start_time = datetime.utcnow()
            
            try:
                result = f(*args, **kwargs)
                elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                status_code = 200
                if isinstance(result, tuple):
                    status_code = result[1] if len(result) > 1 else 200
                
                description = get_description() if get_description else f"API call to {request.endpoint}"
                
                audit = AuditLogger(db)
                audit.log_api_call(
                    endpoint=request.endpoint,
                    method=request.method,
                    status_code=status_code,
                    response_time=elapsed,
                    request_data=request.get_json(silent=True) or request.form.to_dict()
                )
                
                return result
            except Exception as e:
                elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
                audit = AuditLogger(db)
                audit.log_api_call(
                    endpoint=request.endpoint,
                    method=request.method,
                    status_code=500,
                    response_time=elapsed
                )
                raise
        
        return decorated_function
    return decorator
