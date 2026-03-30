"""
Database models for ShowWise Backend (Lite)
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

    role = db.Column(db.String(20), default='user')  # 'admin', 'operator', 'user'
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_2fa_enabled = db.Column(db.Boolean, default=False)
    totp_secret = db.Column(db.String(32))
    backup_codes = db.Column(db.JSON)

    oauth_providers = db.Column(db.JSON)

    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(45))
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")
        self.password_hash = generate_password_hash(
            password, method='pbkdf2:sha256', salt_length=16
        )

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def enable_totp(self):
        self.totp_secret = pyotp.random_base32()
        self.backup_codes = [secrets.token_hex(4) for _ in range(10)]
        return self.totp_secret, self.backup_codes

    def get_totp_qr_code(self, issuer_name="ShowWise"):
        totp = pyotp.TOTP(self.totp_secret)
        url = totp.provisioning_uri(name=self.email, issuer_name=issuer_name)

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode()

    def verify_totp(self, token):
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)

    def use_backup_code(self, code):
        if not self.backup_codes or code not in self.backup_codes:
            return False
        self.backup_codes = [c for c in self.backup_codes if c != code]
        db.session.commit()
        return True

    def disable_totp(self):
        self.is_2fa_enabled = False
        self.totp_secret = None
        self.backup_codes = []

    def to_dict(self, include_secret=False):
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'is_2fa_enabled': self.is_2fa_enabled,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
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
    subdomain = db.Column(db.String(120), index=True)
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class KillSwitch(db.Model):
    """Kill switch for organizations"""
    __tablename__ = 'kill_switches'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'),
                                 nullable=False, index=True, unique=True)

    is_enabled = db.Column(db.Boolean, default=False, index=True)
    reason = db.Column(db.String(255))

    enabled_at = db.Column(db.DateTime)
    enabled_by = db.Column(db.String(120))

    disabled_at = db.Column(db.DateTime)
    disabled_by = db.Column(db.String(120))

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'is_enabled': self.is_enabled,
            'reason': self.reason,
            'enabled_at': self.enabled_at.isoformat() if self.enabled_at else None,
            'enabled_by': self.enabled_by,
            'disabled_at': self.disabled_at.isoformat() if self.disabled_at else None,
            'disabled_by': self.disabled_by,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
