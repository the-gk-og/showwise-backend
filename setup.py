#!/usr/bin/env python3
"""
ShowWise Backend - Setup and Test Script

This script helps you initialize and test your ShowWise Backend installation.
"""

import os
import json
import sys
import requests
from datetime import datetime

def print_header(text):
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")

def print_info(text):
    print(f"ℹ {text}")

def check_dependencies():
    """Check if all required dependencies are installed"""
    print_header("Checking Dependencies")
    
    required = ['flask', 'flask_cors', 'python-dotenv']
    missing = []
    
    for package in required:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package} is installed")
        except ImportError:
            missing.append(package)
            print_error(f"{package} is NOT installed")
    
    if missing:
        print_error("\nMissing dependencies found!")
        print_info(f"Install them with: pip install {' '.join(missing)}")
        return False
    
    print_success("\nAll dependencies are installed!")
    return True

def check_env_file():
    """Check if .env file exists and is configured"""
    print_header("Checking Configuration")
    
    if not os.path.exists('.env'):
        print_error(".env file not found")
        print_info("Creating .env from template...")
        
        if os.path.exists('.env.example'):
            with open('.env.example', 'r') as src:
                with open('.env', 'w') as dst:
                    dst.write(src.read())
            print_success(".env file created from template")
            print_info("Please edit .env and set your SECRET_KEY!")
            return False
        else:
            print_error(".env.example not found")
            return False
    else:
        print_success(".env file exists")
        
        # Check if SECRET_KEY is set
        with open('.env', 'r') as f:
            content = f.read()
            if 'your-secret-key-change-this-in-production' in content:
                print_error("SECRET_KEY is still set to default value!")
                print_info("Please change SECRET_KEY in .env for security")
                return False
        
        print_success("Configuration looks good!")
        return True

def initialize_data():
    """Initialize data directory and files"""
    print_header("Initializing Data")
    
    os.makedirs('data', exist_ok=True)
    print_success("Data directory created/verified")
    
    # Initialize organizations.json
    if not os.path.exists('data/organizations.json'):
        default_orgs = {
            "demo": {
                "name": "Demo Organization",
                "subdomain": "demo",
                "url": "https://demo.sfx-crew.com",
                "logo": "/static/logos/demo.png",
                "logo_size": "contain",
                "logo_padding": "12px",
                "primary_color": "#0051ff",
                "secondary_color": "#898989",
                "description": "Demo organization for testing and exploration",
                "website": "",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "active": True
            }
        }
        
        with open('data/organizations.json', 'w') as f:
            json.dump(default_orgs, f, indent=2)
        
        print_success("organizations.json initialized with demo data")
    else:
        print_info("organizations.json already exists")
    
    # Initialize users.json
    if not os.path.exists('data/users.json'):
        default_users = {
            "admin": {
                "username": "admin",
                "password": "admin123",
                "role": "admin",
                "created_at": datetime.now().isoformat()
            }
        }
        
        with open('data/users.json', 'w') as f:
            json.dump(default_users, f, indent=2)
        
        print_success("users.json initialized")
        print_error("⚠ Default password is 'admin123' - CHANGE IT IMMEDIATELY!")
    else:
        print_info("users.json already exists")
    
    # Initialize settings.json
    if not os.path.exists('data/settings.json'):
        default_settings = {
            "api_enabled": True,
            "require_auth": False,
            "allow_public_read": True,
            "rate_limit": 100,
            "version": "1.0.0"
        }
        
        with open('data/settings.json', 'w') as f:
            json.dump(default_settings, f, indent=2)
        
        print_success("settings.json initialized")
    else:
        print_info("settings.json already exists")

def test_api(port=5001):
    """Test if API is responding"""
    print_header("Testing API")
    
    base_url = f"http://localhost:{port}/api"
    
    print_info(f"Testing API at {base_url}")
    print_info("Make sure the server is running (python app.py)")
    input("\nPress Enter when server is ready...")
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Health check: {data.get('status', 'unknown')}")
        else:
            print_error(f"Health check failed: {response.status_code}")
    except Exception as e:
        print_error(f"Could not connect to API: {e}")
        return False
    
    # Test organizations endpoint
    try:
        response = requests.get(f"{base_url}/organizations", timeout=5)
        if response.status_code == 200:
            data = response.json()
            count = data.get('count', 0)
            print_success(f"Organizations endpoint: {count} organizations found")
        else:
            print_error(f"Organizations endpoint failed: {response.status_code}")
    except Exception as e:
        print_error(f"Could not fetch organizations: {e}")
        return False
    
    # Test stats endpoint
    try:
        response = requests.get(f"{base_url}/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            stats = data.get('stats', {})
            print_success(f"Stats endpoint: {stats}")
        else:
            print_error(f"Stats endpoint failed: {response.status_code}")
    except Exception as e:
        print_error(f"Could not fetch stats: {e}")
        return False
    
    print_success("\nAll API tests passed!")
    return True

def show_next_steps():
    """Display next steps for the user"""
    print_header("Next Steps")
    
    print("1. Start the backend server:")
    print("   python app.py")
    print()
    print("2. Access the admin dashboard:")
    print("   http://localhost:5001")
    print()
    print("3. Login with default credentials:")
    print("   Username: admin")
    print("   Password: admin123")
    print("   ⚠ CHANGE THIS PASSWORD IMMEDIATELY!")
    print()
    print("4. Test the API:")
    print("   http://localhost:5001/api/health")
    print("   http://localhost:5001/api/organizations")
    print()
    print("5. Integrate with ShowWise frontend:")
    print("   See INTEGRATION_GUIDE.md for details")
    print()
    print_success("Setup complete! Enjoy using ShowWise Backend!")

def main():
    """Main setup script"""
    print_header("ShowWise Backend - Setup Script")
    
    # Check dependencies
    if not check_dependencies():
        print_error("\nPlease install missing dependencies and run again.")
        sys.exit(1)
    
    # Check configuration
    if not check_env_file():
        print_error("\nPlease configure .env and run again.")
        sys.exit(1)
    
    # Initialize data
    initialize_data()
    
    # Ask if user wants to test API
    print("\n")
    test_now = input("Do you want to test the API now? (y/n): ").lower()
    
    if test_now == 'y':
        print_info("\nPlease start the server in another terminal:")
        print_info("  python app.py")
        test_api()
    
    # Show next steps
    show_next_steps()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(0)
