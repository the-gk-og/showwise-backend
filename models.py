"""
Database models for ShowWise Backend (Lite)
Implements secure authentication with password hashing and TOTP support
"""
from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
import hmac
import pyotp
import secrets
import time
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
    totp_last_step = db.Column(db.Integer)  # last accepted 30s step, blocks code reuse

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

    # ------------------------------------------------------------------ 2FA
    BACKUP_CODE_COUNT = 10

    def enable_totp(self):
        """Start TOTP enrolment: new secret, 2FA stays off until a code is confirmed.

        Backup codes are created by generate_backup_codes() when enrolment is confirmed,
        so the plaintext is shown once and only a keyed hash is stored.
        """
        self.totp_secret = pyotp.random_base32()
        self.totp_last_step = None
        self.backup_codes = []
        return self.totp_secret

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

    def check_totp(self, token):
        """Return 'ok', 'reused' (valid code from a step already used) or 'invalid'.

        Accepts the previous, current or next 30s step to tolerate clock drift.
        A successful check records the step so the same code cannot be used twice.
        """
        if not self.totp_secret:
            return 'invalid'
        token = ''.join(ch for ch in str(token or '') if ch.isdigit())
        if len(token) != 6:
            return 'invalid'
        totp = pyotp.TOTP(self.totp_secret)
        current_step = int(time.time()) // totp.interval
        for offset in (-1, 0, 1):
            step = current_step + offset
            if hmac.compare_digest(totp.at(step * totp.interval), token):
                if self.totp_last_step is not None and step <= self.totp_last_step:
                    return 'reused'
                self.totp_last_step = step
                db.session.commit()
                return 'ok'
        return 'invalid'

    def verify_totp(self, token):
        return self.check_totp(token) == 'ok'

    @staticmethod
    def _normalise_backup_code(code):
        return ''.join(ch for ch in str(code or '').lower() if ch.isalnum())

    @staticmethod
    def _hash_backup_code(code):
        key = current_app.config.get('SECRET_KEY') or current_app.secret_key or ''
        digest = hmac.new(str(key).encode(), User._normalise_backup_code(code).encode(), hashlib.sha256)
        return 'h1$' + digest.hexdigest()

    def generate_backup_codes(self):
        """Replace all backup codes. Returns the plaintext list (shown once, never stored)."""
        codes = [secrets.token_hex(5) for _ in range(self.BACKUP_CODE_COUNT)]  # 10 hex chars each
        self.backup_codes = [self._hash_backup_code(c) for c in codes]
        return [f'{c[:5]}-{c[5:]}' for c in codes]

    def use_backup_code(self, code):
        """Consume a backup code. Accepts 'abcde-12345' or 'abcde12345'; also old plaintext 8-char codes."""
        norm = self._normalise_backup_code(code)
        if not norm or not self.backup_codes:
            return False
        hashed = self._hash_backup_code(norm)
        match = None
        for stored in self.backup_codes:  # compare against all entries: no early exit on timing
            if stored.startswith('h1$'):
                if hmac.compare_digest(stored, hashed):
                    match = stored
            elif hmac.compare_digest(self._normalise_backup_code(stored), norm):
                match = stored  # legacy plaintext code created before hashing existed
        if match is None:
            return False
        self.backup_codes = [c for c in self.backup_codes if c != match]
        db.session.commit()
        return True

    @property
    def backup_codes_remaining(self):
        return len(self.backup_codes or [])

    def disable_totp(self):
        self.is_2fa_enabled = False
        self.totp_secret = None
        self.totp_last_step = None
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


# Association table
user_organization = db.Table(
    'user_organization',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('organization_id', db.Integer, db.ForeignKey('organizations.id'), primary_key=True),
)

class SupportSigningKey(db.Model):
    """Ed25519 key used to sign support-login tokens. The private half is Fernet-encrypted
    with SUPPORT_MASTER_KEY (see support_admin.py)."""
    __tablename__ = 'support_signing_keys'

    kid = db.Column(db.String(16), primary_key=True)
    public_b64 = db.Column(db.String(64), nullable=False)
    private_enc = db.Column(db.Text, nullable=False)       # '' once revoked
    status = db.Column(db.String(16), nullable=False, default='active', index=True)  # active|retired|revoked
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Log(db.Model):
    """Security and support audit events written by auth.py and support_admin.py."""
    __tablename__ = 'logs'

    id = db.Column(db.Integer, primary_key=True)
    log_type = db.Column(db.String(80), nullable=False, index=True)
    level = db.Column(db.String(20), nullable=False, default='info')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    message = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    event_metadata = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Setting(db.Model):
    """Per-organization feature settings used by the support access portal."""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.String(255), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('organization_id', 'key', name='uq_settings_org_key'),
    )
