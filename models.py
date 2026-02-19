"""
Database models for ShowWise Backend
Implements secure authentication with password hashing and TOTP support
"""
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pyotp
import secrets
from datetime import datetime
import qrcode
import io
import base64

db = SQLAlchemy()

class User(db.Model):
    """User model with secure password hashing and TOTP support"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Security
    role = db.Column(db.String(20), default='user')  # 'admin', 'operator', 'user'
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_2fa_enabled = db.Column(db.Boolean, default=False)
    totp_secret = db.Column(db.String(32))  # Base32-encoded secret
    backup_codes = db.Column(db.JSON)  # Backup 2FA codes
    
    # OAuth
    oauth_providers = db.Column(db.JSON)  # {provider: {id, email, name}}
    
    # Login tracking
    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(45))  # IPv4 or IPv6
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)  # Account lockout time
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organizations = db.relationship('Organization', secondary='user_organization', backref='users')
    api_keys = db.relationship('APIKey', backref='user', lazy=True, cascade='all, delete-orphan')
    logs = db.relationship('Log', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password using bcrypt (via werkzeug)"""
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
    
    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def enable_totp(self):
        """Generate and enable TOTP (Time-based One-Time Password)"""
        # Generate a new secret
        self.totp_secret = pyotp.random_base32()
        
        # Generate 10 backup codes
        self.backup_codes = [secrets.token_hex(4) for _ in range(10)]
        
        return self.totp_secret, self.backup_codes
    
    def get_totp_qr_code(self, issuer_name="ShowWise"):
        """Generate QR code for TOTP setup"""
        totp = pyotp.TOTP(self.totp_secret)
        url = totp.provisioning_uri(
            name=self.email,
            issuer_name=issuer_name
        )
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return qr_code_base64
    
    def verify_totp(self, token):
        """Verify TOTP token"""
        if not self.totp_secret:
            return False
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)
    
    def use_backup_code(self, code):
        """Use a backup code (one-time use)"""
        if not self.backup_codes or code not in self.backup_codes:
            return False
        
        self.backup_codes.remove(code)
        db.session.commit()
        return True
    
    def disable_totp(self):
        """Disable TOTP and clear backup codes"""
        self.is_2fa_enabled = False
        self.totp_secret = None
        self.backup_codes = []
    
    def to_dict(self, include_secret=False):
        """Convert to dictionary (safe for serialization)"""
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'is_2fa_enabled': self.is_2fa_enabled,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        if include_secret:
            data['totp_secret'] = self.totp_secret
        return data


class Organization(db.Model):
    """Organization model"""
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    subdomain = db.Column(db.String(120), unique=True, index=True)
    url = db.Column(db.String(255))
    logo = db.Column(db.String(255))
    logo_size = db.Column(db.String(50), default='contain')
    logo_padding = db.Column(db.String(50))
    primary_color = db.Column(db.String(7), default='#0051ff')
    secondary_color = db.Column(db.String(7), default='#898989')
    description = db.Column(db.Text)
    website = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    api_keys = db.relationship('APIKey', backref='organization', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='organization', lazy=True, cascade='all, delete-orphan')
    logs = db.relationship('Log', backref='organization', lazy=True, cascade='all, delete-orphan')
    settings = db.relationship('Setting', backref='organization', lazy=True, cascade='all, delete-orphan')
    uptime_records = db.relationship('UptimeRecord', backref='organization', lazy=True, cascade='all, delete-orphan')
    kill_switches = db.relationship('KillSwitch', backref='organization', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'subdomain': self.subdomain,
            'url': self.url,
            'logo': self.logo,
            'logo_size': self.logo_size,
            'logo_padding': self.logo_padding,
            'primary_color': self.primary_color,
            'secondary_color': self.secondary_color,
            'description': self.description,
            'website': self.website,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class APIKey(db.Model):
    """API Key model for service authentication"""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    secret_hash = db.Column(db.String(255), nullable=False)  # Hashed secret
    name = db.Column(db.String(120))
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True)
    
    scopes = db.Column(db.JSON)  # ['read', 'write', 'admin']
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    last_used = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime)
    
    def set_secret(self, secret):
        """Hash the secret"""
        self.secret_hash = generate_password_hash(secret, method='pbkdf2:sha256', salt_length=16)
    
    def check_secret(self, secret):
        """Verify the secret"""
        return check_password_hash(self.secret_hash, secret)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'key': self.key[:8] + '...',  # Only show first 8 chars
            'scopes': self.scopes,
            'is_active': self.is_active,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }


class ChatMessage(db.Model):
    """Chat message model"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(16), nullable=False, index=True)
    
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    from_type = db.Column(db.String(20))  # 'user', 'admin'
    from_name = db.Column(db.String(120))
    from_email = db.Column(db.String(120), index=True)
    
    message = db.Column(db.Text, nullable=False)
    
    is_read = db.Column(db.Boolean, default=False, index=True)
    read_by = db.Column(db.String(120))
    read_at = db.Column(db.DateTime)
    
    reply_to = db.Column(db.Integer, db.ForeignKey('chat_messages.id'))
    
    team = db.Column(db.String(120))
    recipients = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'from': self.from_type,
            'from_name': self.from_name,
            'from_email': self.from_email,
            'message': self.message,
            'org_slug': self.organization.slug if self.organization else None,
            'read': self.is_read,
            'read_by': self.read_by,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'reply_to': self.reply_to,
            'timestamp': self.created_at.isoformat(),
            'team': self.team,
            'recipients': self.recipients
        }


class Log(db.Model):
    """Audit log model for security and compliance"""
    __tablename__ = 'logs'
    
    id = db.Column(db.Integer, primary_key=True)
    log_type = db.Column(db.String(50), nullable=False, index=True)  # 'login', 'api', 'action', etc
    level = db.Column(db.String(20), default='info')  # 'info', 'warning', 'error', 'critical'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), index=True)
    
    message = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), index=True)
    user_agent = db.Column(db.String(255))
    
    # Event metadata (JSON)
    event_metadata = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'type': self.log_type,
            'level': self.level,
            'message': self.message,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'event_metadata': self.event_metadata,
            'timestamp': self.created_at.isoformat()
        }


class Setting(db.Model):
    """Application settings"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True)
    
    key = db.Column(db.String(120), nullable=False)
    value = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('organization_id', 'key'),)


class UptimeRecord(db.Model):
    """Uptime monitoring records"""
    __tablename__ = 'uptime_records'
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True)
    
    status = db.Column(db.String(20))  # 'up', 'down', 'degraded'
    response_time = db.Column(db.Float)  # milliseconds
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class KillSwitch(db.Model):
    """Kill switch for organizations"""
    __tablename__ = 'kill_switches'
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True, unique=True)
    
    is_enabled = db.Column(db.Boolean, default=False, index=True)
    reason = db.Column(db.String(255))
    
    enabled_at = db.Column(db.DateTime)
    enabled_by = db.Column(db.String(120))
    
    disabled_at = db.Column(db.DateTime)
    disabled_by = db.Column(db.String(120))
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Association table for user-organization relationship
user_organization = db.Table(
    'user_organization',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('organization_id', db.Integer, db.ForeignKey('organizations.id'), primary_key=True)
)
