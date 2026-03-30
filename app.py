"""
ShowWise Backend API - Rebuilt
RESTful API-first architecture with security, logging, and advanced threat detection
Version: 2.0 (API-focused)

Features:
- Versioned REST API (/api/v1/*)
- Advanced security engine with IP reputation
- Comprehensive audit logging
- 2FA authentication
- Threat detection and blocking
- Security dashboard
"""
import os
import logging
from flask import Flask, jsonify, request, session, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from datetime import timedelta

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-change-in-production')

# ==================== MIDDLEWARE & SECURITY ====================

# ProxyFix for Cloudflare headers
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# CORS Configuration
CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv('CORS_ORIGINS', '*').split(','),
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization", "X-API-Key"]
    }
})

# Session Configuration
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    SESSION_REFRESH_EACH_REQUEST=True
)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'sqlite:///showwise.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== RATE LIMITING ====================

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ==================== DATABASE ====================

from models import db, User, Organization, ChatMessage, SecurityEvent, RequestLog

db.init_app(app)

# ==================== SECURITY MIDDLEWARE ====================

@app.before_request
def security_checks():
    """Run security checks on every request"""
    from services.security_engine import IPSecurityEngine
    from services.audit_logger import AuditLogger
    
    # Skip checks for health endpoint
    if request.endpoint == 'api_health':  # Health endpoint name on app
        return
    
    security_engine = IPSecurityEngine(db)
    
    # Assess request risk
    risk_assessment = security_engine.assess_request_risk(request)
    
    # Block critical risk requests
    if risk_assessment['risk_level'] == 'CRITICAL':
        audit = AuditLogger(db)
        audit.log_suspicious_activity(
            'blocked_request',
            f"Blocked high-risk request to {request.endpoint}",
            security_engine.get_client_ip(),
            severity='CRITICAL'
        )
        logger.warning(f"Blocked critical risk request: {request.endpoint} from {security_engine.get_client_ip()}")
        return jsonify({'error': 'Access denied due to security policy'}), 403
    
    # Log high-risk requests
    if risk_assessment['risk_level'] == 'HIGH':
        audit = AuditLogger(db)
        audit.log_suspicious_activity(
            'high_risk_request',
            f"High-risk request to {request.endpoint}: {', '.join(risk_assessment['factors'])}",
            security_engine.get_client_ip(),
            severity='WARNING'
        )
    
    # Store in request context
    request.risk_assessment = risk_assessment


@app.after_request
def log_api_call(response):
    """Log all API calls"""
    from services.audit_logger import AuditLogger
    
    # Skip logging for static files and health endpoint
    if request.path.startswith('/static') or request.path == '/health':
        return response
    
    try:
        # Use silent=True to avoid exceptions for non-JSON requests
        request_data = request.get_json(silent=True) or request.form.to_dict()
        
        audit = AuditLogger(db)
        audit.log_api_call(
            endpoint=request.endpoint or 'unknown',
            method=request.method,
            status_code=response.status_code,
            request_data=request_data
        )
    except Exception as e:
        logger.error(f"Failed to log API call: {e}")
    
    return response


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def api_health():
    """API health check endpoint"""
    return jsonify({
        'status': 'online',
        'version': '2.0.0',
        'api': '/api/v1',
        'timestamp': __import__('datetime').datetime.utcnow().isoformat()
    }), 200


# ==================== DASHBOARD ====================

@app.route('/dashboard')
def dashboard():
    """Security Dashboard UI"""
    return render_template('dashboard.html')


# ==================== API BLUEPRINT REGISTRATION ====================

try:
    from api.v1 import create_api_v1_blueprint
    api_v1 = create_api_v1_blueprint()
    app.register_blueprint(api_v1)
    logger.info("[SUCCESS] API v1 blueprint registered - /api/v1/*")
except Exception as e:
    logger.error(f"[ERROR] Failed to register API v1 blueprint: {e}")
    import traceback
    traceback.print_exc()


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'message': f'The requested endpoint does not exist: {request.path}',
        'status': 404
    }), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    logger.error(f"Server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred',
        'status': 500
    }), 500


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors"""
    return jsonify({
        'error': 'Forbidden',
        'message': 'Access denied',
        'status': 403
    }), 403


@app.errorhandler(401)
def unauthorized(error):
    """Handle 401 errors"""
    return jsonify({
        'error': 'Unauthorized',
        'message': 'Authentication required',
        'status': 401
    }), 401


# ==================== INITIALIZATION ====================

if __name__ == '__main__':
    with app.app_context():
        # Create database tables
        db.create_all()
        logger.info("[SUCCESS] Database initialized")
        
        # Create default admin user if none exists
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@showwise.local',
                role='admin',
                is_active=True
            )
            admin.set_password(os.getenv('ADMIN_PASSWORD', 'Admin@123456'))
            db.session.add(admin)
            db.session.commit()
            logger.info("[SUCCESS] Default admin user created")
        
        # Display API documentation
        logger.info("=" * 60)
        logger.info("ShowWise Backend API v2.0 - API-First Architecture")
        logger.info("=" * 60)
        logger.info("Available API Endpoints:")
        logger.info("  Auth:           /api/v1/auth/*")
        logger.info("  Users:          /api/v1/users/*")
        logger.info("  Organizations: /api/v1/organizations/*")
        logger.info("  Security:       /api/v1/security/*")
        logger.info("  Logs:           /api/v1/logs/*")
        logger.info("  Admin:          /api/v1/admin/*")
        logger.info("=" * 60)
    
    # Start development server
    app.run(
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 5001)),
        debug=os.getenv('FLASK_ENV') == 'development'
    )
