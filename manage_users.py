#!/usr/bin/env python3
"""
ShowWise Backend - User Management CLI

Command-line tool for managing admin users.
"""

import os
import sys
import argparse
from datetime import datetime
from getpass import getpass

# Initialize Flask app and database
from app_db import app
from models import db, User

def init_db_context():
    """Initialize database context for CLI operations"""
    return app.app_context()

def list_users():
    """List all users from database"""
    try:
        users = User.query.all()
        
        if not users:
            print("No users found.")
            return
        
        print("\n" + "="*80)
        print("  ShowWise Backend Users")
        print("="*80)
        print(f"\n{'ID':<5} {'Username':<20} {'Email':<25} {'Role':<12} {'Created At':<15}")
        print("-"*80)
        
        for user in users:
            created = user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'
            print(f"{user.id:<5} {user.username:<20} {user.email:<25} {user.role:<12} {created:<15}")
        
        print("-"*80)
        print(f"Total users: {len(users)}\n")
    except Exception as e:
        print(f"Error listing users: {e}")
        sys.exit(1)

def add_user():
    """Add a new user to database interactively"""
    print("\n" + "="*70)
    print("  Add New User")
    print("="*70 + "\n")
    
    username = input("Username: ").strip()
    
    if not username:
        print("Error: Username cannot be empty.")
        return False
    
    try:
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"Error: User '{username}' already exists.")
            return False
        
        email = input("Email: ").strip()
        
        if not email:
            print("Error: Email cannot be empty.")
            return False
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            print(f"Error: Email '{email}' already exists.")
            return False
        
        password = getpass("Password: ")
        password_confirm = getpass("Confirm password: ")
        
        if password != password_confirm:
            print("Error: Passwords do not match.")
            return False
        
        if not password:
            print("Error: Password cannot be empty.")
            return False
        
        if len(password) < 12:
            print("Error: Password must be at least 12 characters long.")
            return False
        
        role = input("Role [user]: ").strip() or "user"
        
        # Create new user
        new_user = User(username=username, email=email, role=role)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        print(f"\n✓ User '{username}' created successfully!")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed to create user: {e}")
        return False

def delete_user(username):
    """Delete a user from database"""
    if username == 'admin':
        print("Error: Cannot delete the admin user.")
        return False
    
    try:
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"Error: User '{username}' not found.")
            return False
        
        confirm = input(f"Are you sure you want to delete user '{username}'? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Deletion cancelled.")
            return False
        
        db.session.delete(user)
        db.session.commit()
        
        print(f"\n✓ User '{username}' deleted successfully!")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed to delete user: {e}")
        return False

def change_password(username):
    """Change a user's password"""
    try:
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"Error: User '{username}' not found.")
            return False
        
        print(f"\nChanging password for user: {username}")
        
        new_password = getpass("New password: ")
        new_password_confirm = getpass("Confirm new password: ")
        
        if new_password != new_password_confirm:
            print("Error: Passwords do not match.")
            return False
        
        if not new_password:
            print("Error: Password cannot be empty.")
            return False
        
        if len(new_password) < 12:
            print("Error: Password must be at least 12 characters long.")
            return False
        
        user.set_password(new_password)
        db.session.commit()
        
        print(f"\n✓ Password changed successfully for user '{username}'!")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed to change password: {e}")
        return False

def reset_admin():
    """Reset admin password to default"""
    try:
        admin_user = User.query.filter_by(username='admin').first()
        
        if not admin_user:
            print("Warning: Admin user does not exist. Creating it...")
            admin_user = User(username='admin', email='admin@showwise.local', role='admin')
            db.session.add(admin_user)
            db.session.commit()
        
        confirm = input("Reset admin password to 'Admin123456'? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Reset cancelled.")
            return False
        
        admin_user.set_password('Admin123456')
        db.session.commit()
        
        print("\n✓ Admin password reset to 'Admin123456'")
        print("⚠  Please change this password immediately after logging in!")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed to reset admin password: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='ShowWise Backend User Management CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s list                    List all users
  %(prog)s add                     Add a new user (interactive)
  %(prog)s delete username         Delete a user
  %(prog)s password username       Change a user's password
  %(prog)s reset-admin             Reset admin password to default
        '''
    )
    
    parser.add_argument(
        'command',
        choices=['list', 'add', 'delete', 'password', 'reset-admin'],
        help='Command to execute'
    )
    
    parser.add_argument(
        'username',
        nargs='?',
        help='Username (required for delete and password commands)'
    )
    
    args = parser.parse_args()
    
    # Initialize database context
    with init_db_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Execute command
        if args.command == 'list':
            list_users()
        
        elif args.command == 'add':
            add_user()
        
        elif args.command == 'delete':
            if not args.username:
                print("Error: Username required for delete command")
                parser.print_help()
                sys.exit(1)
            delete_user(args.username)
        
        elif args.command == 'password':
            if not args.username:
                print("Error: Username required for password command")
                parser.print_help()
                sys.exit(1)
            change_password(args.username)
        
        elif args.command == 'reset-admin':
            reset_admin()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
