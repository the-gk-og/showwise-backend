"""
Advanced IP Reputation and Security Engine
Manages IP blacklisting, threat scoring, and intelligent blocking
"""
import re
import hashlib
from datetime import datetime, timedelta
from flask import request
import logging

logger = logging.getLogger(__name__)


class IPSecurityEngine:
    """Manages IP reputation, blacklisting, and threat assessment"""
    
    THREAT_PATTERNS = {
        'sql_injection': [
            r"union\s+select",
            r"select.*from.*where",
            r"or\s+1\s*=\s*1",
            r";drop\s+table",
            r"exec(\s|\()+xp_",
        ],
        'xss': [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on(click|load|error|mouse)\s*=",
            r"<iframe[^>]*>",
            r"<img[^>]*on",
        ],
        'path_traversal': [
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e/",
            r"etc/passwd",
        ],
    }
    
    def __init__(self, db):
        self.db = db
    
    def get_client_ip(self):
        """Extract client IP from request"""
        if request.headers.get('CF-Connecting-IP'):
            return request.headers.get('CF-Connecting-IP')
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or 'unknown'
    
    def check_ip_reputation(self, ip_address=None):
        """
        Check if IP is blacklisted or has history of attacks
        
        Returns: {'is_blocked': bool, 'threat_score': 0-100, 'reason': str, 'details': dict}
        """
        from models import IPBlacklist, IPQuarantine
        
        if not ip_address:
            ip_address = self.get_client_ip()
        
        # Check active blacklist
        blacklist_entry = IPBlacklist.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        if blacklist_entry and blacklist_entry.expires_at > datetime.utcnow():
            return {
                'is_blocked': True,
                'threat_score': 100,
                'reason': blacklist_entry.reason,
                'details': {
                    'blacklist_id': blacklist_entry.id,
                    'added_at': blacklist_entry.created_at.isoformat(),
                    'expires_at': blacklist_entry.expires_at.isoformat() if blacklist_entry.expires_at else None
                }
            }
        
        # Check quarantine list (warning status)
        quarantine_entry = IPQuarantine.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        if quarantine_entry and quarantine_entry.expires_at > datetime.utcnow():
            threat_score = min(50 + quarantine_entry.threat_score, 100)
            return {
                'is_blocked': False,
                'threat_score': threat_score,
                'reason': f'IP under monitoring: {quarantine_entry.reason}',
                'details': {
                    'quarantine_id': quarantine_entry.id,
                    'added_at': quarantine_entry.created_at.isoformat(),
                    'threat_score': quarantine_entry.threat_score
                }
            }
        
        # Calculate threat score from recent activity
        threat_score = self._calculate_ip_threat_score(ip_address)
        
        return {
            'is_blocked': threat_score > 85,
            'threat_score': threat_score,
            'reason': 'Calculated from recent activity patterns',
            'details': {}
        }
    
    def detect_attack_patterns(self, data, source='request'):
        """
        Detect common attack patterns in data
        
        Returns: {'detected': bool, 'patterns': [str], 'severity': str}
        """
        detected_patterns = []
        max_severity = 'LOW'
        
        if isinstance(data, dict):
            data_str = ' '.join(str(v) for v in data.values())
        else:
            data_str = str(data)
        
        # Check all threat patterns
        for pattern_type, patterns in self.THREAT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, data_str, re.IGNORECASE):
                    detected_patterns.append(pattern_type)
                    max_severity = 'CRITICAL' if pattern_type == 'sql_injection' else 'HIGH'
        
        return {
            'detected': len(detected_patterns) > 0,
            'patterns': list(set(detected_patterns)),
            'severity': max_severity,
            'data_sample': data_str[:100]
        }
    
    def assess_request_risk(self, request_obj=None):
        """
        Comprehensive request risk assessment
        
        Returns: {'risk_level': 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL', 'factors': [...], 'score': 0-100}
        """
        if not request_obj:
            request_obj = request
        
        risk_factors = []
        risk_score = 0
        
        # Check IP reputation
        ip_rep = self.check_ip_reputation()
        if ip_rep['threat_score'] > 50:
            risk_factors.append(f"IP threat score: {ip_rep['threat_score']}")
            risk_score += 30
        
        if ip_rep['is_blocked']:
            return {
                'risk_level': 'CRITICAL',
                'factors': ['IP is blacklisted'],
                'score': 100
            }
        
        # Check for attack patterns in request
        request_data = request_obj.get_json(silent=True) or request_obj.form.to_dict()
        attack_detection = self.detect_attack_patterns(request_data)
        
        if attack_detection['detected']:
            risk_factors.append(f"Attack patterns detected: {', '.join(attack_detection['patterns'])}")
            risk_score += 40 if attack_detection['severity'] == 'CRITICAL' else 20
        
        # Check User-Agent
        user_agent = (request_obj.headers.get('User-Agent') or '').lower()
        scanner_patterns = ['burpsuite', 'zap', 'sqlmap', 'nikto', 'metasploit']
        if any(p in user_agent for p in scanner_patterns):
            risk_factors.append("Scanner detected in User-Agent")
            risk_score += 25
        
        # Check for suspicious headers
        suspicious_headers = request_obj.headers.get('X-Scanner') or request_obj.headers.get('X-Burp')
        if suspicious_headers:
            risk_factors.append("Suspicious headers detected")
            risk_score += 25
        
        # Determine risk level
        if risk_score >= 80:
            risk_level = 'CRITICAL'
        elif risk_score >= 60:
            risk_level = 'HIGH'
        elif risk_score >= 40:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        return {
            'risk_level': risk_level,
            'factors': risk_factors,
            'score': min(risk_score, 100)
        }
    
    def blacklist_ip(self, ip_address, reason, duration_hours=24, severity='MEDIUM'):
        """Add IP to blacklist"""
        from models import IPBlacklist
        from services.audit_logger import AuditLogger
        
        try:
            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
            
            # Remove from quarantine if exists
            IPQuarantine.query.filter_by(ip_address=ip_address).delete()
            
            entry = IPBlacklist(
                ip_address=ip_address,
                reason=reason,
                severity=severity,
                is_active=True,
                expires_at=expires_at,
                added_at=datetime.utcnow()
            )
            self.db.session.add(entry)
            self.db.session.commit()
            
            # Log the action
            audit = AuditLogger(self.db)
            audit.log_ip_blocked(ip_address, reason)
            
            logger.warning(f"IP blacklisted: {ip_address} - {reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist IP: {e}")
            self.db.session.rollback()
            return False
    
    def quarantine_ip(self, ip_address, reason, threat_score=50, duration_hours=24):
        """Add IP to quarantine (monitoring status)"""
        from models import IPQuarantine
        
        try:
            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
            
            entry = IPQuarantine(
                ip_address=ip_address,
                reason=reason,
                threat_score=threat_score,
                is_active=True,
                expires_at=expires_at,
                added_at=datetime.utcnow()
            )
            self.db.session.add(entry)
            self.db.session.commit()
            
            logger.warning(f"IP quarantined: {ip_address} - {reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to quarantine IP: {e}")
            self.db.session.rollback()
            return False
    
    def whitelist_ip(self, ip_address):
        """Remove IP from blacklist and quarantine"""
        from models import IPBlacklist, IPQuarantine
        
        try:
            IPBlacklist.query.filter_by(ip_address=ip_address).delete()
            IPQuarantine.query.filter_by(ip_address=ip_address).delete()
            self.db.session.commit()
            
            logger.info(f"IP whitelisted: {ip_address}")
            return True
        except Exception as e:
            logger.error(f"Failed to whitelist IP: {e}")
            self.db.session.rollback()
            return False
    
    def get_ip_statistics(self):
        """Get statistics about IP security"""
        from models import IPBlacklist, IPQuarantine
        
        now = datetime.utcnow()
        
        return {
            'total_blacklisted': IPBlacklist.query.filter(
                IPBlacklist.is_active,
                IPBlacklist.expires_at > now
            ).count(),
            'total_quarantined': IPQuarantine.query.filter(
                IPQuarantine.is_active,
                IPQuarantine.expires_at > now
            ).count(),
            'blocked_24h': IPBlacklist.query.filter(
                IPBlacklist.created_at >= now - timedelta(hours=24)
            ).count(),
        }
    
    def _calculate_ip_threat_score(self, ip_address):
        """Calculate threat score based on historical activity"""
        from models import SecurityEvent
        from datetime import timedelta
        
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        cutoff_7d = datetime.utcnow() - timedelta(days=7)
        
        # Count failed login attempts in last 24h
        failed_logins_24h = SecurityEvent.query.filter(
            SecurityEvent.ip_address == ip_address,
            SecurityEvent.event_type == 'login_failed',
            SecurityEvent.created_at >= cutoff_24h
        ).count()
        
        # Count blocked attempts
        blocked_attempts = SecurityEvent.query.filter(
            SecurityEvent.ip_address == ip_address,
            SecurityEvent.event_type == 'ip_blocked',
            SecurityEvent.created_at >= cutoff_7d
        ).count()
        
        # Calculate score
        score = 0
        score += min(failed_logins_24h * 5, 50)  # Max 50 points for login failures
        score += min(blocked_attempts * 10, 50)  # Max 50 points for blocked attempts
        
        return min(score, 100)
