#!/usr/bin/env python3
"""
ShowWise Backend - Post-Setup Verification Script

Run this after setup_secure.py to verify everything was set up correctly.
Usage: python verify_setup.py
"""

import os
import sys
import json
from pathlib import Path

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{text:^60}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✓{RESET} {text}")

def print_error(text):
    print(f"{RED}✗{RESET} {text}")

def print_warning(text):
    print(f"{YELLOW}⚠{RESET} {text}")

def print_info(text):
    print(f"{BLUE}ℹ{RESET} {text}")

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if Path(filepath).exists():
        size = Path(filepath).stat().st_size
        print_success(f"{description} exists ({size:,} bytes)")
        return True
    else:
        print_error(f"{description} missing at {filepath}")
        return False

def check_python_modules():
    """Check if all required Python modules are installed"""
    print(f"\n{BOLD}Checking Python Modules:{RESET}")
    
    modules = {
        'flask': 'Flask',
        'flask_sqlalchemy': 'Flask-SQLAlchemy',
        'werkzeug': 'Werkzeug',
        'pyotp': 'pyotp',
        'qrcode': 'qrcode',
        'authlib': 'authlib',
        'flask_limiter': 'Flask-Limiter',
        'flask_wtf': 'Flask-WTF',
        'bcrypt': 'bcrypt',
        'dotenv': 'python-dotenv'
    }
    
    all_installed = True
    for module, name in modules.items():
        try:
            __import__(module)
            print_success(f"{name} installed")
        except ImportError:
            print_error(f"{name} NOT installed - run: pip install -r requirements.txt")
            all_installed = False
    
    return all_installed

def check_environment_config():
    """Check if .env file exists and has required variables"""
    print(f"\n{BOLD}Checking Environment Configuration:{RESET}")
    
    if not Path('.env').exists():
        print_warning(".env file not found - This is OK for first run, setup_secure.py will create it")
        return False
    
    print_success(".env file exists")
    
    # Check for required variables
    required_vars = ['SECRET_KEY', 'FLASK_ENV', 'DATABASE_URL']
    with open('.env', 'r') as f:
        env_content = f.read()
    
    all_present = True
    for var in required_vars:
        if var in env_content:
            print_success(f"  {var} configured")
        else:
            print_warning(f"  {var} not configured (optional)")
            all_present = False
    
    return all_present

def check_database():
    """Check if database exists and can be accessed"""
    print(f"\n{BOLD}Checking Database:{RESET}")
    
    # Check for SQLite database
    if Path('showwise.db').exists():
        print_success("SQLite database file exists (showwise.db)")
        
        try:
            import sqlite3
            conn = sqlite3.connect('showwise.db')
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            if tables:
                print_success(f"Database has {len(tables)} tables:")
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                    count = cursor.fetchone()[0]
                    print(f"  • {table[0]}: {count} records")
                return True
            else:
                print_warning("Database exists but has no tables - run setup_secure.py")
                return False
        except Exception as e:
            print_error(f"Cannot access database: {e}")
            return False
    else:
        print_warning("SQLite database not found - This is OK, setup_secure.py will create it")
        return False

def check_templates():
    """Check if required templates exist"""
    print(f"\n{BOLD}Checking Templates:{RESET}")
    
    templates = {
        'templates/login.html': 'Login template',
        'templates/verify_2fa.html': '2FA verification template',
        'templates/dashboard.html': 'Dashboard template',
        'templates/base.html': 'Base template'
    }
    
    all_present = True
    for template_path, description in templates.items():
        if Path(template_path).exists():
            print_success(f"{description} exists")
        else:
            print_warning(f"{description} missing")
            all_present = False
    
    return all_present

def check_documentation():
    """Check if documentation files exist"""
    print(f"\n{BOLD}Checking Documentation:{RESET}")
    
    docs = {
        'QUICKSTART.md': 'Quick start guide',
        'INDEX.md': 'Documentation index',
        'SECURITY_CHEATSHEET.md': 'Security cheatsheet',
        'README/README_SECURE.md': 'Secure README',
        'README/SECURITY.md': 'Security documentation',
        'README/DATABASE_MIGRATION.md': 'Migration guide',
        'README/DEPLOYMENT.md': 'Deployment guide'
    }
    
    all_present = True
    for doc_path, description in docs.items():
        if Path(doc_path).exists():
            size = Path(doc_path).stat().st_size
            print_success(f"{description} exists ({size:,} bytes)")
        else:
            print_warning(f"{description} missing at {doc_path}")
            all_present = False
    
    return all_present

def check_requirements_file():
    """Check if requirements.txt exists and has required packages"""
    print(f"\n{BOLD}Checking Requirements File:{RESET}")
    
    if not Path('requirements.txt').exists():
        print_error("requirements.txt file not found")
        return False
    
    print_success("requirements.txt exists")
    
    with open('requirements.txt', 'r') as f:
        content = f.read()
    
    required_packages = [
        'Flask',
        'Flask-SQLAlchemy',
        'Werkzeug',
        'pyotp',
        'qrcode',
        'authlib',
        'Flask-Limiter',
        'Flask-WTF'
    ]
    
    all_present = True
    for package in required_packages:
        if package.lower() in content.lower():
            print_success(f"  {package} in requirements.txt")
        else:
            print_error(f"  {package} missing from requirements.txt")
            all_present = False
    
    return all_present

def print_next_steps():
    """Print next steps based on verification results"""
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{'NEXT STEPS':^60}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
    
    print("1. Install dependencies (if not already done):")
    print(f"   {BOLD}pip install -r requirements.txt{RESET}")
    
    print("\n2. Run the setup wizard:")
    print(f"   {BOLD}python setup_secure.py{RESET}")
    print("   This will:")
    print("   • Create .env file with secure SECRET_KEY")
    print("   • Initialize the database")
    print("   • Migrate JSON data to database")
    print("   • Create your admin user")
    
    print("\n3. Start the application:")
    print(f"   {BOLD}python app_db.py{RESET}")
    
    print("\n4. Access the dashboard:")
    print(f"   {BOLD}http://localhost:5000{RESET}")
    
    print("\n5. Read the documentation:")
    print(f"   Start with: {BOLD}QUICKSTART.md{RESET}")
    print(f"   Navigation: {BOLD}INDEX.md{RESET}")
    print(f"   Reference: {BOLD}SECURITY_CHEATSHEET.md{RESET}")

def main():
    """Run all verification checks"""
    print_header("ShowWise Backend - Setup Verification")
    
    results = []
    
    # Run checks
    results.append(("Files & Structure", check_file_exists('requirements.txt', 'Requirements file')))
    results.append(("Python Modules", check_python_modules()))
    results.append(("Environment Config", check_environment_config()))
    results.append(("Database", check_database()))
    results.append(("Templates", check_templates()))
    results.append(("Documentation", check_documentation()))
    results.append(("Requirements File", check_requirements_file()))
    
    # Print summary
    print_header("Verification Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"Passed: {GREEN}{passed}/{total}{RESET}\n")
    
    for check_name, result in results:
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{YELLOW}⚠ PARTIAL{RESET}"
        print(f"  {check_name:.<40} {status}")
    
    # Print next steps
    print_next_steps()
    
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{GREEN}Setup verification complete!{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
    
    return 0 if passed == total else 1

if __name__ == '__main__':
    sys.exit(main())
