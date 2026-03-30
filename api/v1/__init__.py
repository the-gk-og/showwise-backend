"""
API v1 - Main entry point for versioned REST API
Routes all v1 endpoints through organized blueprints
"""
from flask import Blueprint

# Create v1 API blueprint hub
api_v1_bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')


def create_api_v1_blueprint():
    """Factory function to create and register all API v1 blueprints"""
    
    # Import sub-blueprints
    from .auth import auth_bp
    from .users import users_bp
    from .organizations import orgs_bp
    from .security import security_bp
    from .logs import logs_bp
    from .admin import admin_bp
    
    # Register all sub-blueprints under /api/v1
    api_v1_bp.register_blueprint(auth_bp, url_prefix='/auth')
    api_v1_bp.register_blueprint(users_bp, url_prefix='/users')
    api_v1_bp.register_blueprint(orgs_bp, url_prefix='/organizations')
    api_v1_bp.register_blueprint(security_bp, url_prefix='/security')
    api_v1_bp.register_blueprint(logs_bp, url_prefix='/logs')
    api_v1_bp.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Health check endpoint
    @api_v1_bp.route('/health', methods=['GET'])
    def api_health():
        from flask import jsonify
        return jsonify({
            'status': 'online',
            'version': '1.0.0',
            'timestamp': __import__('datetime').datetime.utcnow().isoformat()
        }), 200
    
    return api_v1_bp
