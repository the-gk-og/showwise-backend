#!/usr/bin/env python
"""
Migration script: Convert JSON data to SQLAlchemy database
Run this once: python migrate_to_db.py
"""
import json
import os
from datetime import datetime
from models import db, User, Organization, APIKey, ChatMessage, Setting, UptimeRecord, KillSwitch
from app import app

def migrate_users(json_path='data/users.json'):
    """Migrate users from JSON to database"""
    print("Migrating users...")
    
    if not os.path.exists(json_path):
        print(f"No {json_path} found, skipping user migration")
        return
    
    with open(json_path, 'r') as f:
        users_data = json.load(f)
    
    for username, user_info in users_data.items():
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"  User {username} already exists, skipping")
            continue
        
        user = User(
            username=username,
            email=user_info.get('email', f'{username}@showwise.local'),
            role=user_info.get('role', 'user'),
            is_active=user_info.get('active', True)
        )
        
        # Hash password from JSON
        password = user_info.get('password')
        if password:
            user.set_password(password)
        
        db.session.add(user)
        print(f"  Migrated user: {username}")
    
    db.session.commit()
    print("User migration complete\n")

def migrate_organizations(json_path='data/organizations.json'):
    """Migrate organizations from JSON to database"""
    print("Migrating organizations...")
    
    if not os.path.exists(json_path):
        print(f"No {json_path} found, skipping organization migration")
        return
    
    with open(json_path, 'r') as f:
        orgs_data = json.load(f)
    
    for slug, org_info in orgs_data.items():
        # Check if org already exists
        existing_org = Organization.query.filter_by(slug=slug).first()
        if existing_org:
            print(f"  Organization {slug} already exists, skipping")
            continue
        
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
        print(f"  Migrated organization: {slug}")
    
    db.session.commit()
    print("Organization migration complete\n")

def migrate_chat_messages(json_path='data/chat_messages.json'):
    """Migrate chat messages from JSON to database"""
    print("Migrating chat messages...")
    
    if not os.path.exists(json_path):
        print(f"No {json_path} found, skipping chat migration")
        return
    
    with open(json_path, 'r') as f:
        messages_data = json.load(f)
    
    for msg_info in messages_data:
        # Find organization
        org_slug = msg_info.get('org_slug')
        org = Organization.query.filter_by(slug=org_slug).first()
        if not org:
            print(f"  Organization {org_slug} not found for message, skipping")
            continue
        
        # Find user if admin message
        user = None
        if msg_info.get('from') == 'admin':
            username = msg_info.get('from_name')
            user = User.query.filter_by(username=username).first()
        
        chat_msg = ChatMessage(
            chat_id=msg_info.get('chat_id', msg_info.get('id', '')),
            organization_id=org.id,
            user_id=user.id if user else None,
            from_type=msg_info.get('from', 'user'),
            from_name=msg_info.get('from_name', 'Unknown'),
            from_email=msg_info.get('from_email', ''),
            message=msg_info.get('message', ''),
            is_read=msg_info.get('read', False),
            read_by=msg_info.get('read_by'),
            read_at=datetime.fromisoformat(msg_info['read_at']) if msg_info.get('read_at') else None,
            reply_to=msg_info.get('reply_to'),
            team=msg_info.get('team'),
            recipients=msg_info.get('recipients', [])
        )
        
        # Set created date if available
        if msg_info.get('timestamp'):
            try:
                chat_msg.created_at = datetime.fromisoformat(msg_info['timestamp'])
            except:
                pass
        
        db.session.add(chat_msg)
    
    db.session.commit()
    print(f"Migrated {len(messages_data)} chat messages\n")

def migrate_settings(json_path='data/settings.json'):
    """Migrate settings from JSON to database"""
    print("Migrating settings...")
    
    if not os.path.exists(json_path):
        print(f"No {json_path} found, skipping settings migration")
        return
    
    with open(json_path, 'r') as f:
        settings_data = json.load(f)
    
    # For simplicity, create a default organization setting
    for org in Organization.query.all():
        for key, value in settings_data.items():
            setting = Setting(
                organization_id=org.id,
                key=key,
                value=value
            )
            db.session.add(setting)
    
    db.session.commit()
    print("Settings migration complete\n")

def migrate_uptime(json_path='data/uptime.json'):
    """Migrate uptime records from JSON to database"""
    print("Migrating uptime records...")
    
    if not os.path.exists(json_path):
        print(f"No {json_path} found, skipping uptime migration")
        return
    
    with open(json_path, 'r') as f:
        uptime_data = json.load(f)
    
    for org_slug, org_uptime in uptime_data.items():
        org = Organization.query.filter_by(slug=org_slug).first()
        if not org:
            continue
        
        if isinstance(org_uptime, dict) and 'pings' in org_uptime:
            for ping in org_uptime['pings']:
                record = UptimeRecord(
                    organization_id=org.id,
                    status=ping.get('status', 'up'),
                    response_time=ping.get('response_time')
                )
                if ping.get('timestamp'):
                    try:
                        record.created_at = datetime.fromisoformat(ping['timestamp'])
                    except:
                        pass
                db.session.add(record)
    
    db.session.commit()
    print("Uptime migration complete\n")

def migrate_kill_switches(json_path='data/kill_switches.json'):
    """Migrate kill switches from JSON to database"""
    print("Migrating kill switches...")
    
    if not os.path.exists(json_path):
        print(f"No {json_path} found, skipping kill switches migration")
        return
    
    with open(json_path, 'r') as f:
        switches_data = json.load(f)
    
    for org_slug, switch_info in switches_data.items():
        org = Organization.query.filter_by(slug=org_slug).first()
        if not org:
            continue
        
        # Check if kill switch already exists
        existing = KillSwitch.query.filter_by(organization_id=org.id).first()
        if existing:
            continue
        
        kill_switch = KillSwitch(
            organization_id=org.id,
            is_enabled=switch_info.get('enabled', False),
            reason=switch_info.get('reason', ''),
            enabled_by=switch_info.get('enabled_by'),
            disabled_by=switch_info.get('disabled_by')
        )
        
        if switch_info.get('enabled_at'):
            try:
                kill_switch.enabled_at = datetime.fromisoformat(switch_info['enabled_at'])
            except:
                pass
        
        if switch_info.get('disabled_at'):
            try:
                kill_switch.disabled_at = datetime.fromisoformat(switch_info['disabled_at'])
            except:
                pass
        
        db.session.add(kill_switch)
    
    db.session.commit()
    print("Kill switches migration complete\n")

def init_db():
    """Initialize database with tables"""
    print("Initializing database...")
    with app.app_context():
        db.create_all()
        print("Database tables created\n")

def run_migration():
    """Run all migrations"""
    print("=" * 60)
    print("ShowWise Backend: JSON to Database Migration")
    print("=" * 60)
    print()
    
    with app.app_context():
        init_db()
        migrate_users()
        migrate_organizations()
        migrate_chat_messages()
        migrate_settings()
        migrate_uptime()
        migrate_kill_switches()
    
    print("=" * 60)
    print("Migration complete! Database is ready.")
    print("=" * 60)

if __name__ == '__main__':
    run_migration()
