# ShowWise Backend - Lite Edition

A lightweight administration console for managing organizations and kill switches with secure authentication.

## Features

- **Organization Management** - Create, edit, toggle, and delete organizations
- **Kill Switches** - Emergency instance shutdown controls per organization
- **User Authentication** - Secure login with password hashing, 2FA (TOTP), and OAuth support
- **REST APIs** - Simple endpoints to check organization and kill switch status

## Core Files

### Application
- `app_db.py` - Main Flask application with all routes
- `models.py` - Database models (User, Organization, KillSwitch)
- `auth.py` - Authentication utilities and security decorators

### Configuration
- `.env` - Environment variables (copy `.env.example`)
- `requirements.txt` - Python dependencies
- `setup.py` - Development setup script

### Templates
- `templates/base.html` - Layout template
- `templates/login.html` - Login page
- `templates/dashboard.html` - Main dashboard
- `templates/organizations.html` - Organization list
- `templates/add_organization.html` - New organization form
- `templates/edit_organization.html` - Edit organization form
- `templates/kill_switches.html` - Kill switch management
- `templates/verify_2fa.html` - 2FA verification
- `templates/error.html` - Error pages

### Data Files
- `data/organizations.json` - Organization data (if migrating from JSON)
- `data/users.json` - User data (if migrating from JSON)
- `data/kill_switches.json` - Kill switch data (if migrating from JSON)

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env

# 3. Run the app
python app_db.py
```

Visit `http://localhost:5000` and login with:
- Username: `admin`
- Password: `Admin123456!` (change immediately!)

## API Endpoints

### Public
- `GET /api/health` - Server health check
- `GET /api/organizations` - List all organizations
- `GET /api/organizations/<slug>` - Get organization details
- `GET /api/kill-switch/<slug>` - Check kill switch status

### Web UI
- `/organizations` - Manage organizations (admin only)
- `/kill-switches` - Manage kill switches (admin only)
- `/login` - User login
- `/logout` - User logout

## Database

Uses SQLite by default. Automatically creates tables on first run.

## Security

- Passwords hashed with PBKDF2-SHA256
- 2FA support with TOTP (authenticator apps)
- CSRF protection on all forms
- Rate limiting on auth endpoints
- Secure session cookies
- OAuth support (Google, GitHub)
