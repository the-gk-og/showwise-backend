#!/usr/bin/env python
"""
ShowWise Backend Secure Setup Script
Initializes the application with database and security configuration
Run this once: python setup_secure.py
"""
import os
import sys
import secrets
import json
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")

def check_python_version():
    """Check Python version"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]}")

def check_dependencies():
    """Check all dependencies are installed"""
    print("Checking dependencies...")
    
    required = [
        ('flask', 'Flask'),
        ('flask_cors', 'Flask-CORS'),
        ('flask_sqlalchemy', 'Flask-SQLAlchemy'),
        ('flask_wtf', 'Flask-WTF'),
        ('werkzeug', 'Werkzeug'),
        ('dotenv', 'python-dotenv'),
        ('bcrypt', 'bcrypt'),
        ('pyotp', 'pyotp'),
        ('qrcode', 'qrcode'),
        ('authlib', 'authlib')
    ]
    
    missing = []
    for module, name in required:
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ❌ {name}")
            missing.append(name)
    
    if missing:
        print(f"\n❌ Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        sys.exit(1)
    
    print("✅ All dependencies installed\n")

def create_env_file():
    """Create .env file if it doesn't exist"""
    print("Setting up environment...")
    
    env_path = Path('.env')
    if env_path.exists():
        print("  ℹ️  .env already exists, skipping")
        return
    
    # Generate SECRET_KEY
    secret_key = secrets.token_urlsafe(32)
    
    env_content = f"""# ShowWise Backend Configuration
# Generated: {__import__('datetime').datetime.now().isoformat()}

# ==================== SECURITY ====================
SECRET_KEY={secret_key}
DATABASE_URL=sqlite:///showwise.db

# ==================== FLASK ====================
FLASK_ENV=development
FLASK_APP=app_db.py
PORT=5000

# CORS Origins (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:5000

# ==================== OAUTH (OPTIONAL) ====================
# Uncomment and fill in your OAuth credentials

# Google OAuth
# GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
# GOOGLE_CLIENT_SECRET=your-client-secret

# GitHub OAuth
# GITHUB_CLIENT_ID=your-client-id
# GITHUB_CLIENT_SECRET=your-client-secret
"""
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"  ✅ Created .env with SECRET_KEY={secret_key[:16]}...")

def load_flask_app():
    """Load Flask app and database"""
    from app_db import app, db
    return app, db

def init_database(app, db):
    """Initialize database"""
    print("Initializing database...")
    
    with app.app_context():
        db.create_all()
        print("  ✅ Database tables created")

def migrate_data(app, db):
    """Migrate data from JSON files to database"""
    print("Migrating data from JSON files...")
    
    from models import User, Organization
    from datetime import datetime
    
    with app.app_context():
        # Check if data already migrated
        if User.query.count() > 0:
            print("  ℹ️  Database already has data, skipping migration")
            return
        
        migrated = False
        
        # Migrate users
        if os.path.exists('data/users.json'):
            with open('data/users.json', 'r') as f:
                users_data = json.load(f)
            
            for username, user_info in users_data.items():
                if not User.query.filter_by(username=username).first():
                    user = User(
                        username=username,
                        email=user_info.get('email', f'{username}@showwise.local'),
                        role=user_info.get('role', 'user'),
                        is_active=user_info.get('active', True)
                    )
                    password = user_info.get('password')
                    if password:
                        user.set_password(password)
                    db.session.add(user)
            db.session.commit()
            migrated = True
            print(f"  ✅ Migrated {User.query.count()} users")
        
        # Migrate organizations
        if os.path.exists('data/organizations.json'):
            with open('data/organizations.json', 'r') as f:
                orgs_data = json.load(f)
            
            for slug, org_info in orgs_data.items():
                if not Organization.query.filter_by(slug=slug).first():
                    org = Organization(
                        name=org_info.get('name', slug),
                        slug=slug,
                        subdomain=org_info.get('subdomain', slug),
                        url=org_info.get('url', ''),
                        logo=org_info.get('logo', ''),
                        logo_size=org_info.get('logo_size', 'contain'),
                        logo_padding=org_info.get('logo_padding', '12px'),
                        primary_color=org_info.get('primary_color', '#0051ff'),
                        secondary_color=org_info.get('secondary_color', '#898989'),
                        description=org_info.get('description', ''),
                        website=org_info.get('website', ''),
                        is_active=org_info.get('active', True)
                    )
                    db.session.add(org)
            db.session.commit()
            migrated = True
            print(f"  ✅ Migrated {Organization.query.count()} organizations")
        
        if not migrated:
            print("  ℹ️  No legacy JSON data found, skipped migration")

def create_admin_user(app, db):
    """Create default admin user if none exists"""
    from models import User
    
    with app.app_context():
        if User.query.filter_by(role='admin').first():
            print("\n✅ Admin user already exists")
            return
        
        print("\nCreate Default Admin User")
        print("-" * 40)
        
        username = input("Username (default: admin): ").strip() or "admin"
        email = input("Email: ").strip() or f"{username}@showwise.local"
        password = input("Password (12+ chars): ").strip()
        
        while len(password) < 12:
            print("❌ Password must be at least 12 characters")
            password = input("Password: ").strip()
        
        confirm_password = input("Confirm password: ").strip()
        while password != confirm_password:
            print("❌ Passwords don't match")
            password = input("Password: ").strip()
            confirm_password = input("Confirm password: ").strip()
        
        user = User(
            username=username,
            email=email,
            role='admin',
            is_active=True
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ Admin user '{username}' created successfully")

def security_summary():
    """Print security summary"""
    print_header("Security Features Enabled")
    
    features = [
        ("✅", "Password hashing (PBKDF2-SHA256)"),
        ("✅", "TOTP 2FA (Time-based One-Time Password)"),
        ("✅", "Account lockout (5 failed attempts)"),
        ("✅", "Rate limiting (200/day, 50/hour per IP)"),
        ("✅", "CSRF protection (Flask-WTF)"),
        ("✅", "Secure sessions (HttpOnly, Secure, SameSite)"),
        ("✅", "Audit logging (all events tracked)"),
        ("✅", "OAuth support (Google, GitHub)"),
        ("✅", "API key management with hashing"),
        ("✅", "Database backend (SQLAlchemy ORM)"),
    ]
    
    for status, feature in features:
        print(f"  {status} {feature}")
    
    print("\n⚠️  IMPORTANT:")
    print("  1. Change SECRET_KEY in .env (already done)")
    print("  2. Enable HTTPS in production")
    print("  3. Set up regular database backups")
    print("  4. Use a production database (PostgreSQL recommended)")
    print("  5. Configure OAuth credentials (Google, GitHub)")
    print("  6. Enable 2FA for admin accounts\n")

def print_next_steps():
    """Print next steps"""
    print_header("Setup Complete!")
    
    print("Next steps:")
    print("  1. Start the application:")
    print("     python app_db.py")
    print()
    print("  2. Open in browser:")
    print("     http://localhost:5000")
    print()
    print("  3. Login with your credentials")
    print()
    print("  4. Enable 2FA in user settings")
    print()
    print("  5. Read SECURITY.md for detailed security documentation")
    print()
    print("Documentation:")
    print("  • DATABASE_MIGRATION.md - Migration guide")
    print("  • SECURITY.md - Security features & best practices")
    print()

def main():
    """Main setup flow"""
    print_header("ShowWise Backend Secure Setup")
    
    try:
        # Check environment
        check_python_version()
        check_dependencies()
        
        # Configure application
        create_env_file()
        
        # Load Flask app
        print("Loading application...")
        app, db = load_flask_app()
        print("  ✅ Application loaded\n")
        
        # Initialize database
        init_database(app, db)
        
        # Migrate existing data
        migrate_data(app, db)
        
        # Create admin user
        create_admin_user(app, db)
        
        # Print security summary
        security_summary()
        
        # Print next steps
        print_next_steps()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
