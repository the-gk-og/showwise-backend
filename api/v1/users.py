"""
API v1 - Users Management Endpoints
CRUD operations for user management
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from models import User, db
from services.audit_logger import AuditLogger
from api.v1.auth import require_api_key
from functools import wraps

users_bp = Blueprint('users', __name__)


def require_admin(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        user = User.query.get(user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated


@users_bp.route('/', methods=['GET'])
@require_api_key
@require_admin
def list_users():
    """List all users"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = User.query.order_by(User.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'users': [user.to_dict() for user in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page
    }), 200


@users_bp.route('/<int:user_id>', methods=['GET'])
@require_api_key
def get_user(user_id):
    """Get user details"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'success': True,
        'user': user.to_dict()
    }), 200


@users_bp.route('/', methods=['POST'])
@require_api_key
@require_admin
def create_user():
    """Create new user"""
    data = request.get_json() or {}
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user')
    
    # Validation
    if not username or not password or not email:
        return jsonify({'error': 'Username, email, and password required'}), 400
    
    if len(password) < 12:
        return jsonify({'error': 'Password must be at least 12 characters'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 409
    
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409
    
    # Create user
    user = User(username=username, email=email, role=role, is_active=True)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('user_created', f'User created: {username}', 'INFO', user_id=session.get('user_id'))
    
    return jsonify({
        'success': True,
        'user': user.to_dict(),
        'message': 'User created successfully'
    }), 201


@users_bp.route('/<int:user_id>', methods=['PUT'])
@require_api_key
@require_admin
def update_user(user_id):
    """Update user information"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json() or {}
    
    # Update allowed fields
    if 'email' in data:
        user.email = data['email'].strip()
    if 'role' in data:
        user.role = data['role']
    if 'is_active' in data:
        user.is_active = data['is_active']
    
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('user_updated', f'User updated: {user.username}', 'INFO', user_id=session.get('user_id'))
    
    return jsonify({
        'success': True,
        'user': user.to_dict()
    }), 200


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@require_api_key
@require_admin
def delete_user(user_id):
    """Delete a user"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.username == 'admin':
        return jsonify({'error': 'Cannot delete admin user'}), 403
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('user_deleted', f'User deleted: {username}', 'WARNING', user_id=session.get('user_id'))
    
    return jsonify({
        'success': True,
        'message': f'User {username} deleted'
    }), 200


@users_bp.route('/<int:user_id>/change-password', methods=['POST'])
@require_api_key
def change_password(user_id):
    """Change user password"""
    current_user = User.query.get(session.get('user_id'))
    target_user = User.query.get(user_id)
    
    if not target_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only allow users to change their own password, or admins to change any
    if current_user.id != user_id and current_user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    # Validation
    if not old_password or not new_password:
        return jsonify({'error': 'Old and new passwords required'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400
    
    if len(new_password) < 12:
        return jsonify({'error': 'Password must be at least 12 characters'}), 400
    
    if not target_user.check_password(old_password):
        return jsonify({'error': 'Current password is incorrect'}), 401
    
    target_user.set_password(new_password)
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('password_changed', 'User password changed', 'INFO', user_id=target_user.id)
    
    return jsonify({
        'success': True,
        'message': 'Password changed successfully'
    }), 200


@users_bp.route('/search', methods=['GET'])
@require_api_key
@require_admin
def search_users():
    """Search users by username or email"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify({'error': 'Query must be at least 2 characters'}), 400
    
    users = User.query.filter(
        (User.username.ilike(f'%{query}%')) |
        (User.email.ilike(f'%{query}%'))
    ).limit(20).all()
    
    return jsonify({
        'success': True,
        'results': [user.to_dict() for user in users]
    }), 200
