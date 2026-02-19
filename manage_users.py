#!/usr/bin/env python3
"""
ShowWise Backend - User Management CLI

Command-line tool for managing admin users.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from getpass import getpass

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

def load_users():
    """Load users from JSON file"""
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {USERS_FILE} not found. Have you initialized the backend?")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading users: {e}")
        sys.exit(1)

def save_users(users):
    """Save users to JSON file"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving users: {e}")
        return False

def list_users():
    """List all users"""
    users = load_users()
    
    if not users:
        print("No users found.")
        return
    
    print("\n" + "="*70)
    print("  ShowWise Backend Users")
    print("="*70)
    print(f"\n{'Username':<20} {'Role':<15} {'Created At':<25}")
    print("-"*70)
    
    for username, data in users.items():
        created = data.get('created_at', 'N/A')
        if created != 'N/A':
            created = created[:19]  # Trim to datetime without microseconds
        print(f"{username:<20} {data.get('role', 'admin'):<15} {created:<25}")
    
    print("-"*70)
    print(f"Total users: {len(users)}\n")

def add_user():
    """Add a new user interactively"""
    print("\n" + "="*70)
    print("  Add New User")
    print("="*70 + "\n")
    
    username = input("Username: ").strip()
    
    if not username:
        print("Error: Username cannot be empty.")
        return False
    
    users = load_users()
    
    if username in users:
        print(f"Error: User '{username}' already exists.")
        return False
    
    password = getpass("Password: ")
    password_confirm = getpass("Confirm password: ")
    
    if password != password_confirm:
        print("Error: Passwords do not match.")
        return False
    
    if not password:
        print("Error: Password cannot be empty.")
        return False
    
    role = input("Role [admin]: ").strip() or "admin"
    
    users[username] = {
        'username': username,
        'password': password,
        'role': role,
        'created_at': datetime.now().isoformat(),
        'created_by': 'cli'
    }
    
    if save_users(users):
        print(f"\n✓ User '{username}' created successfully!")
        return True
    else:
        print("\n✗ Failed to create user.")
        return False

def delete_user(username):
    """Delete a user"""
    if username == 'admin':
        print("Error: Cannot delete the admin user.")
        return False
    
    users = load_users()
    
    if username not in users:
        print(f"Error: User '{username}' not found.")
        return False
    
    confirm = input(f"Are you sure you want to delete user '{username}'? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Deletion cancelled.")
        return False
    
    del users[username]
    
    if save_users(users):
        print(f"\n✓ User '{username}' deleted successfully!")
        return True
    else:
        print("\n✗ Failed to delete user.")
        return False

def change_password(username):
    """Change a user's password"""
    users = load_users()
    
    if username not in users:
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
    
    users[username]['password'] = new_password
    users[username]['password_changed_at'] = datetime.now().isoformat()
    users[username]['password_changed_by'] = 'cli'
    
    if save_users(users):
        print(f"\n✓ Password changed successfully for user '{username}'!")
        return True
    else:
        print("\n✗ Failed to change password.")
        return False

def reset_admin():
    """Reset admin password to default"""
    users = load_users()
    
    if 'admin' not in users:
        print("Warning: Admin user does not exist. Creating it...")
        users['admin'] = {
            'username': 'admin',
            'role': 'admin',
            'created_at': datetime.now().isoformat(),
            'created_by': 'cli'
        }
    
    confirm = input("Reset admin password to 'admin123'? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Reset cancelled.")
        return False
    
    users['admin']['password'] = 'admin123'
    users['admin']['password_reset_at'] = datetime.now().isoformat()
    users['admin']['password_reset_by'] = 'cli'
    
    if save_users(users):
        print("\n✓ Admin password reset to 'admin123'")
        print("⚠  Please change this password immediately after logging in!")
        return True
    else:
        print("\n✗ Failed to reset admin password.")
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
    
    # Check if data directory exists
    if not os.path.exists(DATA_DIR):
        print(f"Error: Data directory '{DATA_DIR}' not found.")
        print("Have you initialized the backend? Run: python app.py")
        sys.exit(1)
    
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
