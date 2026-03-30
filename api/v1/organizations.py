"""
API v1 - Organizations Management
CRUD and management for organizations
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from models import Organization, db
from services.audit_logger import AuditLogger
from api.v1.auth import require_api_key
from api.v1.users import require_admin

orgs_bp = Blueprint('organizations', __name__)


@orgs_bp.route('/', methods=['GET'])
@require_api_key
def list_organizations():
    """List organizations"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    
    query = Organization.query.order_by(Organization.name)
    
    if active_only:
        query = query.filter_by(is_active=True)
    
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'organizations': [_org_to_dict(org) for org in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page
    }), 200


@orgs_bp.route('/<slug>', methods=['GET'])
@require_api_key
def get_organization(slug):
    """Get organization by slug"""
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    return jsonify({
        'success': True,
        'organization': _org_to_dict(org)
    }), 200


@orgs_bp.route('/', methods=['POST'])
@require_api_key
@require_admin
def create_organization():
    """Create new organization"""
    data = request.get_json() or {}
    
    slug = data.get('slug', '').strip().lower()
    name = data.get('name', '').strip()
    
    if not slug or not name:
        return jsonify({'error': 'Slug and name required'}), 400
    
    if Organization.query.filter_by(slug=slug).first():
        return jsonify({'error': 'Slug already exists'}), 409
    
    org = Organization(
        slug=slug,
        name=name,
        subdomain=data.get('subdomain', slug),
        url=data.get('url', ''),
        logo=data.get('logo', ''),
        primary_color=data.get('primary_color', '#0051ff'),
        secondary_color=data.get('secondary_color', '#898989'),
        description=data.get('description', ''),
        website=data.get('website', ''),
        is_active=True
    )
    
    db.session.add(org)
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('org_created', f'Organization created: {slug}', 'INFO', user_id=session.get('user_id'))
    
    return jsonify({
        'success': True,
        'organization': _org_to_dict(org),
        'message': 'Organization created'
    }), 201


@orgs_bp.route('/<slug>', methods=['PUT'])
@require_api_key
@require_admin
def update_organization(slug):
    """Update organization"""
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    data = request.get_json() or {}
    
    # Update allowed fields
    if 'name' in data:
        org.name = data['name']
    if 'subdomain' in data:
        org.subdomain = data['subdomain']
    if 'url' in data:
        org.url = data['url']
    if 'logo' in data:
        org.logo = data['logo']
    if 'primary_color' in data:
        org.primary_color = data['primary_color']
    if 'secondary_color' in data:
        org.secondary_color = data['secondary_color']
    if 'description' in data:
        org.description = data['description']
    if 'website' in data:
        org.website = data['website']
    if 'is_active' in data:
        org.is_active = data['is_active']
    
    org.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('org_updated', f'Organization updated: {slug}', 'INFO', user_id=session.get('user_id'))
    
    return jsonify({
        'success': True,
        'organization': _org_to_dict(org)
    }), 200


@orgs_bp.route('/<slug>', methods=['DELETE'])
@require_api_key
@require_admin
def delete_organization(slug):
    """Delete organization"""
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    db.session.delete(org)
    db.session.commit()
    
    # Audit log
    audit = AuditLogger(db)
    audit.log_event('org_deleted', f'Organization deleted: {slug}', 'WARNING', user_id=session.get('user_id'))
    
    return jsonify({
        'success': True,
        'message': f'Organization {slug} deleted'
    }), 200


@orgs_bp.route('/<slug>/stats', methods=['GET'])
@require_api_key
def get_org_statistics(slug):
    """Get organization statistics"""
    org = Organization.query.filter_by(slug=slug).first()
    if not org:
        return jsonify({'error': 'Organization not found'}), 404
    
    from models import ChatMessage
    
    total_messages = ChatMessage.query.filter_by(organization_id=org.id).count()
    unread_messages = ChatMessage.query.filter_by(
        organization_id=org.id,
        is_read=False,
        from_type='user'
    ).count()
    
    return jsonify({
        'success': True,
        'slug': slug,
        'name': org.name,
        'stats': {
            'total_messages': total_messages,
            'unread_messages': unread_messages,
            'is_active': org.is_active,
            'created_at': org.created_at.isoformat() if org.created_at else None,
            'updated_at': org.updated_at.isoformat() if org.updated_at else None
        }
    }), 200


def _org_to_dict(org):
    """Convert organization to dict"""
    return {
        'id': org.id,
        'slug': org.slug,
        'name': org.name,
        'subdomain': org.subdomain,
        'url': org.url,
        'logo': org.logo,
        'primary_color': org.primary_color,
        'secondary_color': org.secondary_color,
        'description': org.description,
        'website': org.website,
        'is_active': org.is_active,
        'created_at': org.created_at.isoformat() if org.created_at else None,
        'updated_at': org.updated_at.isoformat() if org.updated_at else None
    }
