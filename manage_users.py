#!/usr/bin/env python3
"""
ShowWise Backend - User Management CLI
"""
import os
import sys
import argparse
from datetime import datetime
from getpass import getpass

from app_db import app
from models import db, User


def init_db_context():
    return app.app_context()


def list_users():
    users = User.query.all()
    if not users:
        print("No users found.")
        return

    print("\n" + "=" * 80)
    print("  ShowWise Backend Users")
    print("=" * 80)
    print(f"\n{'ID':<5} {'Username':<20} {'Email':<30} {'Role':<12} {'2FA':<5} {'Created':<17}")
    print("-" * 80)

    for user in users:
        created = user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'
        twofa = 'Yes' if user.is_2fa_enabled else 'No'
        print(f"{user.id:<5} {user.username:<20} {(user.email or ''):<30} {user.role:<12} {twofa:<5} {created:<17}")

    print("-" * 80)
    print(f"Total users: {len(users)}\n")


def add_user():
    print("\n" + "=" * 70)
    print("  Add New User")
    print("=" * 70 + "\n")

    username = input("Username: ").strip()
    if not username:
        print("Error: Username cannot be empty.")
        return False

    if User.query.filter_by(username=username).first():
        print(f"Error: User '{username}' already exists.")
        return False

    email = input(f"Email [{username}@showwise.local]: ").strip() or f"{username}@showwise.local"

    if User.query.filter_by(email=email).first():
        print(f"Error: Email '{email}' already in use.")
        return False

    password = getpass("Password (min 12 chars): ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("Error: Passwords do not match.")
        return False

    if len(password) < 12:
        print("Error: Password must be at least 12 characters.")
        return False

    role = input("Role [user/admin, default=user]: ").strip() or "user"

    try:
        user = User(username=username, email=email, role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"\n✓ User '{username}' created successfully!")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed to create user: {e}")
        return False


def delete_user(username):
    if username == 'admin':
        print("Error: Cannot delete the built-in admin user.")
        return False

    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"Error: User '{username}' not found.")
        return False

    confirm = input(f"Delete user '{username}'? This cannot be undone. (yes/no): ")
    if confirm.lower() != 'yes':
        print("Deletion cancelled.")
        return False

    try:
        db.session.delete(user)
        db.session.commit()
        print(f"\n✓ User '{username}' deleted.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed: {e}")
        return False


def change_password(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"Error: User '{username}' not found.")
        return False

    print(f"\nChanging password for: {username}")
    new_pw = getpass("New password (min 12 chars): ")
    confirm = getpass("Confirm new password: ")

    if new_pw != confirm:
        print("Error: Passwords do not match.")
        return False

    if len(new_pw) < 12:
        print("Error: Password must be at least 12 characters.")
        return False

    try:
        user.set_password(new_pw)
        db.session.commit()
        print(f"\n✓ Password changed for '{username}'.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed: {e}")
        return False


def reset_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        print("Admin user not found. Creating it...")
        admin = User(username='admin', email='admin@showwise.local', role='admin', is_active=True)
        db.session.add(admin)

    confirm = input("Reset admin password to 'Admin123456!'? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Reset cancelled.")
        return False

    try:
        admin.set_password('Admin123456!')
        db.session.commit()
        print("\n✓ Admin password reset to 'Admin123456!'")
        print("⚠  Change this password immediately after logging in!")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='ShowWise Backend User Management CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s list
  %(prog)s add
  %(prog)s delete <username>
  %(prog)s password <username>
  %(prog)s reset-admin
        '''
    )
    parser.add_argument('command',
                        choices=['list', 'add', 'delete', 'password', 'reset-admin'])
    parser.add_argument('username', nargs='?', help='Username (for delete/password)')

    args = parser.parse_args()

    with init_db_context():
        db.create_all()

        if args.command == 'list':
            list_users()
        elif args.command == 'add':
            add_user()
        elif args.command == 'delete':
            if not args.username:
                print("Error: Username required for delete")
                sys.exit(1)
            delete_user(args.username)
        elif args.command == 'password':
            if not args.username:
                print("Error: Username required for password")
                sys.exit(1)
            change_password(args.username)
        elif args.command == 'reset-admin':
            reset_admin()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)