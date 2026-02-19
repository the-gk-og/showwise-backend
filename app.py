from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
from flask_cors import CORS
from dotenv import load_dotenv
from functools import wraps
import json, os
import queue
import threading
from datetime import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-change-in-production')

# Enable CORS for API endpoints
CORS(app, resources={
    r"/api/*": {
        "origins": "*",  # In production, specify your ShowWise instance domains
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Configuration
DATA_DIR = 'data'
ORGANIZATIONS_FILE = os.path.join(DATA_DIR, 'organizations.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
LOGS_FILE = os.path.join(DATA_DIR, 'logs.json')
API_KEYS_FILE = os.path.join(DATA_DIR, 'api_keys.json')
UPTIME_FILE = os.path.join(DATA_DIR, 'uptime.json')
KILL_SWITCHES_FILE = os.path.join(DATA_DIR, 'kill_switches.json')
CHAT_MESSAGES_FILE = os.path.join(DATA_DIR, 'chat_messages.json')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Helper functions
def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}

def save_json(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        # Update in-memory cache for chat messages for performance
        try:
            if filepath == CHAT_MESSAGES_FILE:
                with _chat_cache_lock:
                    global _chat_cache, _chat_cache_loaded_at
                    _chat_cache = data
                    _chat_cache_loaded_at = datetime.now()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"Error saving {filepath}: {e}")
        return False

# Initialize default files if they don't exist
def init_data_files():
    if not os.path.exists(ORGANIZATIONS_FILE):
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
        save_json(ORGANIZATIONS_FILE, default_orgs)
    
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": {
                "username": "admin",
                "password": "admin123",  # Change this!
                "role": "admin",
                "created_at": datetime.now().isoformat()
            }
        }
        save_json(USERS_FILE, default_users)
    
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {
            "api_enabled": True,
            "require_auth": False,
            "allow_public_read": True,
            "rate_limit": 100,
            "version": "1.0.0"
        }
        save_json(SETTINGS_FILE, default_settings)
    
    if not os.path.exists(LOGS_FILE):
        default_logs = []
        save_json(LOGS_FILE, default_logs)
    
    if not os.path.exists(API_KEYS_FILE):
        default_api_keys = {}
        save_json(API_KEYS_FILE, default_api_keys)
    
    if not os.path.exists(UPTIME_FILE):
        default_uptime = {}
        save_json(UPTIME_FILE, default_uptime)
    
    if not os.path.exists(KILL_SWITCHES_FILE):
        default_kill_switches = {}
        save_json(KILL_SWITCHES_FILE, default_kill_switches)
    
    if not os.path.exists(CHAT_MESSAGES_FILE):
        default_chat = []
        save_json(CHAT_MESSAGES_FILE, default_chat)

init_data_files()

# In-memory subscribers for server-sent events (SSE)
_chat_subscribers = []  # list of queue.Queue objects

# Simple in-memory cache for chat messages to reduce disk I/O
_chat_cache = None
_chat_cache_loaded_at = None
_chat_cache_lock = threading.Lock()

def broadcast_chat_message(message):
    # Push message to all subscriber queues (non-blocking)
    for q in list(_chat_subscribers):
        try:
            q.put_nowait(message)
        except Exception:
            # If a queue fails, ignore and continue
            pass

def get_organizations():
    return load_json(ORGANIZATIONS_FILE)

def get_users():
    return load_json(USERS_FILE)

def get_settings():
    return load_json(SETTINGS_FILE)

def get_logs():
    return load_json(LOGS_FILE)

def get_api_keys():
    return load_json(API_KEYS_FILE)

def get_uptime():
    return load_json(UPTIME_FILE)

def get_kill_switches():
    return load_json(KILL_SWITCHES_FILE)

def get_chat_messages(force_reload=False):
    """Return chat messages, with an in-memory cache to reduce disk reads.
    Set `force_reload=True` to reload from disk.
    """
    global _chat_cache, _chat_cache_loaded_at
    if force_reload:
        with _chat_cache_lock:
            _chat_cache = load_json(CHAT_MESSAGES_FILE) or []
            _chat_cache_loaded_at = datetime.now()
            return list(_chat_cache)

    with _chat_cache_lock:
        if _chat_cache is None:
            _chat_cache = load_json(CHAT_MESSAGES_FILE) or []
            _chat_cache_loaded_at = datetime.now()
        # return a shallow copy to avoid accidental mutation
        return list(_chat_cache)

def add_log(log_type, org_slug, message, level="info", metadata=None):
    """Add a log entry"""
    logs = get_logs()
    log_entry = {
        "id": len(logs) + 1,
        "timestamp": datetime.now().isoformat(),
        "type": log_type,  # 'api', 'auth', 'system', 'user', 'instance'
        "org_slug": org_slug,
        "message": message,
        "level": level,  # 'info', 'warning', 'error', 'critical'
        "metadata": metadata or {}
    }
    logs.append(log_entry)
    # Keep only last 10000 logs
    if len(logs) > 10000:
        logs = logs[-10000:]
    save_json(LOGS_FILE, logs)
    return log_entry

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = get_users()
        
        if username in users and users[username]['password'] == password:
            session['username'] = username
            session['role'] = users[username]['role']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# ==================== DASHBOARD ROUTES ====================

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    orgs = get_organizations()
    settings = get_settings()
    
    stats = {
        'total_organizations': len(orgs),
        'active_organizations': sum(1 for org in orgs.values() if org.get('active', True)),
        'inactive_organizations': sum(1 for org in orgs.values() if not org.get('active', True)),
        'api_status': 'Enabled' if settings.get('api_enabled', True) else 'Disabled'
    }
    
    return render_template('dashboard.html', stats=stats)

@app.route('/organizations')
@login_required
def organizations_list():
    orgs = get_organizations()
    return render_template('organizations.html', organizations=orgs)

@app.route('/organizations/add', methods=['GET', 'POST'])
@login_required
def add_organization():
    if request.method == 'POST':
        slug = request.form.get('slug')
        
        if not slug:
            flash('Slug is required.', 'error')
            return redirect(url_for('add_organization'))
        
        orgs = get_organizations()
        
        if slug in orgs:
            flash('An organization with this slug already exists.', 'error')
            return redirect(url_for('add_organization'))
        
        new_org = {
            'name': request.form.get('name'),
            'subdomain': request.form.get('subdomain'),
            'url': request.form.get('url'),
            'logo': request.form.get('logo'),
            'logo_size': request.form.get('logo_size', 'contain'),
            'logo_padding': request.form.get('logo_padding', '12px'),
            'primary_color': request.form.get('primary_color', '#0051ff'),
            'secondary_color': request.form.get('secondary_color', '#898989'),
            'description': request.form.get('description'),
            'website': request.form.get('website', ''),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'active': True
        }
        
        orgs[slug] = new_org
        
        if save_json(ORGANIZATIONS_FILE, orgs):
            flash(f'Organization "{new_org["name"]}" added successfully!', 'success')
            return redirect(url_for('organizations_list'))
        else:
            flash('Failed to save organization.', 'error')
    
    return render_template('add_organization.html')

@app.route('/organizations/edit/<slug>', methods=['GET', 'POST'])
@login_required
def edit_organization(slug):
    orgs = get_organizations()
    
    if slug not in orgs:
        flash('Organization not found.', 'error')
        return redirect(url_for('organizations_list'))
    
    if request.method == 'POST':
        orgs[slug].update({
            'name': request.form.get('name'),
            'subdomain': request.form.get('subdomain'),
            'url': request.form.get('url'),
            'logo': request.form.get('logo'),
            'logo_size': request.form.get('logo_size', 'contain'),
            'logo_padding': request.form.get('logo_padding', '12px'),
            'primary_color': request.form.get('primary_color'),
            'secondary_color': request.form.get('secondary_color'),
            'description': request.form.get('description'),
            'website': request.form.get('website', ''),
            'updated_at': datetime.now().isoformat()
        })
        
        if save_json(ORGANIZATIONS_FILE, orgs):
            flash(f'Organization "{orgs[slug]["name"]}" updated successfully!', 'success')
            return redirect(url_for('organizations_list'))
        else:
            flash('Failed to update organization.', 'error')
    
    return render_template('edit_organization.html', slug=slug, org=orgs[slug])

@app.route('/organizations/toggle/<slug>')
@login_required
def toggle_organization(slug):
    orgs = get_organizations()
    
    if slug not in orgs:
        flash('Organization not found.', 'error')
        return redirect(url_for('organizations_list'))
    
    orgs[slug]['active'] = not orgs[slug].get('active', True)
    orgs[slug]['updated_at'] = datetime.now().isoformat()
    
    if save_json(ORGANIZATIONS_FILE, orgs):
        status = 'activated' if orgs[slug]['active'] else 'deactivated'
        flash(f'Organization "{orgs[slug]["name"]}" {status} successfully!', 'success')
    else:
        flash('Failed to toggle organization status.', 'error')
    
    return redirect(url_for('organizations_list'))

@app.route('/organizations/delete/<slug>')
@login_required
def delete_organization(slug):
    orgs = get_organizations()
    
    if slug not in orgs:
        flash('Organization not found.', 'error')
        return redirect(url_for('organizations_list'))
    
    org_name = orgs[slug]['name']
    del orgs[slug]
    
    if save_json(ORGANIZATIONS_FILE, orgs):
        flash(f'Organization "{org_name}" deleted successfully!', 'success')
    else:
        flash('Failed to delete organization.', 'error')
    
    return redirect(url_for('organizations_list'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        settings_data = get_settings()
        
        settings_data.update({
            'api_enabled': 'api_enabled' in request.form,
            'require_auth': 'require_auth' in request.form,
            'allow_public_read': 'allow_public_read' in request.form,
            'rate_limit': int(request.form.get('rate_limit', 100))
        })
        
        if save_json(SETTINGS_FILE, settings_data):
            flash('Settings updated successfully!', 'success')
        else:
            flash('Failed to update settings.', 'error')
        
        return redirect(url_for('settings'))
    
    settings_data = get_settings()
    return render_template('settings.html', settings=settings_data)

@app.route('/users')
@login_required
def users_list():
    users = get_users()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'admin')
        
        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('add_user'))
        
        users = get_users()
        
        if username in users:
            flash('A user with this username already exists.', 'error')
            return redirect(url_for('add_user'))
        
        users[username] = {
            'username': username,
            'password': password,  # In production, hash this!
            'role': role,
            'created_at': datetime.now().isoformat(),
            'created_by': session.get('username')
        }
        
        if save_json(USERS_FILE, users):
            flash(f'User "{username}" created successfully!', 'success')
            return redirect(url_for('users_list'))
        else:
            flash('Failed to create user.', 'error')
    
    return render_template('add_user.html')

@app.route('/users/delete/<username>')
@login_required
def delete_user(username):
    if username == 'admin':
        flash('Cannot delete the admin user.', 'error')
        return redirect(url_for('users_list'))
    
    if username == session.get('username'):
        flash('Cannot delete your own account.', 'error')
        return redirect(url_for('users_list'))
    
    users = get_users()
    
    if username not in users:
        flash('User not found.', 'error')
        return redirect(url_for('users_list'))
    
    del users[username]
    
    if save_json(USERS_FILE, users):
        flash(f'User "{username}" deleted successfully!', 'success')
    else:
        flash('Failed to delete user.', 'error')
    
    return redirect(url_for('users_list'))

@app.route('/users/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('change_password'))
        
        users = get_users()
        username = session.get('username')
        
        if users[username]['password'] != current_password:
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('change_password'))
        
        users[username]['password'] = new_password
        users[username]['password_changed_at'] = datetime.now().isoformat()
        
        if save_json(USERS_FILE, users):
            flash('Password changed successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Failed to change password.', 'error')
    
    return render_template('change_password.html')

# ==================== LOGS ROUTES ====================

@app.route('/logs')
@login_required
def logs_list():
    logs = get_logs()
    # Reverse to show newest first
    logs = list(reversed(logs))
    
    # Get filter parameters
    log_type = request.args.get('type', '')
    log_level = request.args.get('level', '')
    org_slug = request.args.get('org', '')
    search = request.args.get('search', '')
    
    # Apply filters
    if log_type:
        logs = [log for log in logs if log.get('type') == log_type]
    if log_level:
        logs = [log for log in logs if log.get('level') == log_level]
    if org_slug:
        logs = [log for log in logs if log.get('org_slug') == org_slug]
    if search:
        logs = [log for log in logs if search.lower() in log.get('message', '').lower()]
    
    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 50
    start = (page - 1) * per_page
    end = start + per_page
    total_logs = len(logs)
    logs_page = logs[start:end]
    total_pages = (total_logs + per_page - 1) // per_page
    
    orgs = get_organizations()
    
    return render_template('logs.html', 
                          logs=logs_page, 
                          organizations=orgs,
                          current_page=page,
                          total_pages=total_pages,
                          total_logs=total_logs,
                          filters={
                              'type': log_type,
                              'level': log_level,
                              'org': org_slug,
                              'search': search
                          })

@app.route('/logs/clear')
@login_required
def clear_logs():
    if save_json(LOGS_FILE, []):
        add_log('system', 'backend', f'Logs cleared by {session.get("username")}', 'info')
        flash('Logs cleared successfully!', 'success')
    else:
        flash('Failed to clear logs.', 'error')
    return redirect(url_for('logs_list'))

# ==================== API KEYS ROUTES ====================

@app.route('/api-keys')
@login_required
def api_keys_list():
    keys = get_api_keys()
    orgs = get_organizations()
    return render_template('api_keys.html', api_keys=keys, organizations=orgs)

@app.route('/api-keys/generate', methods=['POST'])
@login_required
def generate_api_key():
    org_slug = request.form.get('org_slug')
    name = request.form.get('name', 'Unnamed Key')
    
    if not org_slug:
        flash('Organization is required.', 'error')
        return redirect(url_for('api_keys_list'))
    
    orgs = get_organizations()
    if org_slug not in orgs:
        flash('Organization not found.', 'error')
        return redirect(url_for('api_keys_list'))
    
    # Generate API key
    import secrets
    api_key = 'sk_' + secrets.token_urlsafe(32)
    
    keys = get_api_keys()
    keys[api_key] = {
        'name': name,
        'org_slug': org_slug,
        'created_at': datetime.now().isoformat(),
        'created_by': session.get('username'),
        'last_used': None,
        'active': True
    }
    
    if save_json(API_KEYS_FILE, keys):
        add_log('api', org_slug, f'API key created: {name}', 'info')
        flash(f'API key created: {api_key}', 'success')
    else:
        flash('Failed to create API key.', 'error')
    
    return redirect(url_for('api_keys_list'))

@app.route('/api-keys/revoke/<key>')
@login_required
def revoke_api_key(key):
    keys = get_api_keys()
    
    if key not in keys:
        flash('API key not found.', 'error')
        return redirect(url_for('api_keys_list'))
    
    keys[key]['active'] = False
    keys[key]['revoked_at'] = datetime.now().isoformat()
    keys[key]['revoked_by'] = session.get('username')
    
    if save_json(API_KEYS_FILE, keys):
        add_log('api', keys[key]['org_slug'], f'API key revoked: {keys[key]["name"]}', 'warning')
        flash('API key revoked successfully!', 'success')
    else:
        flash('Failed to revoke API key.', 'error')
    
    return redirect(url_for('api_keys_list'))

@app.route('/api-keys/delete/<key>')
@login_required
def delete_api_key(key):
    keys = get_api_keys()
    
    if key not in keys:
        flash('API key not found.', 'error')
        return redirect(url_for('api_keys_list'))
    
    org_slug = keys[key]['org_slug']
    name = keys[key]['name']
    del keys[key]
    
    if save_json(API_KEYS_FILE, keys):
        add_log('api', org_slug, f'API key deleted: {name}', 'warning')
        flash('API key deleted successfully!', 'success')
    else:
        flash('Failed to delete API key.', 'error')
    
    return redirect(url_for('api_keys_list'))

# ==================== UPTIME ROUTES ====================

@app.route('/uptime')
@login_required
def uptime_dashboard():
    uptime_data = get_uptime()
    orgs = get_organizations()
    
    # Calculate statistics
    stats = {}
    for org_slug in orgs.keys():
        org_uptime = uptime_data.get(org_slug, {})
        pings = org_uptime.get('pings', [])
        
        if pings:
            total_pings = len(pings)
            # Calculate uptime percentage (last 24 hours)
            recent_pings = [p for p in pings if (datetime.now() - datetime.fromisoformat(p['timestamp'])).total_seconds() < 86400]
            uptime_percent = 100.0 if recent_pings else 0.0
            
            stats[org_slug] = {
                'total_pings': total_pings,
                'last_ping': pings[-1]['timestamp'] if pings else None,
                'uptime_24h': uptime_percent,
                'status': 'online' if recent_pings and (datetime.now() - datetime.fromisoformat(pings[-1]['timestamp'])).total_seconds() < 300 else 'offline'
            }
        else:
            stats[org_slug] = {
                'total_pings': 0,
                'last_ping': None,
                'uptime_24h': 0.0,
                'status': 'unknown'
            }
    
    return render_template('uptime.html', organizations=orgs, stats=stats, uptime_data=uptime_data)

# ==================== KILL SWITCH ROUTES ====================

@app.route('/kill-switches')
@login_required
def kill_switches_list():
    switches = get_kill_switches()
    orgs = get_organizations()
    return render_template('kill_switches.html', kill_switches=switches, organizations=orgs)

@app.route('/kill-switches/toggle/<org_slug>')
@login_required
def toggle_kill_switch(org_slug):
    orgs = get_organizations()
    if org_slug not in orgs:
        flash('Organization not found.', 'error')
        return redirect(url_for('kill_switches_list'))
    
    switches = get_kill_switches()
    
    if org_slug not in switches:
        switches[org_slug] = {
            'enabled': True,
            'enabled_at': datetime.now().isoformat(),
            'enabled_by': session.get('username'),
            'reason': 'Payment overdue'
        }
        add_log('system', org_slug, f'Kill switch ENABLED by {session.get("username")}', 'critical')
        flash(f'Kill switch ENABLED for {orgs[org_slug]["name"]}', 'warning')
    else:
        if switches[org_slug].get('enabled'):
            switches[org_slug]['enabled'] = False
            switches[org_slug]['disabled_at'] = datetime.now().isoformat()
            switches[org_slug]['disabled_by'] = session.get('username')
            add_log('system', org_slug, f'Kill switch DISABLED by {session.get("username")}', 'info')
            flash(f'Kill switch DISABLED for {orgs[org_slug]["name"]}', 'success')
        else:
            switches[org_slug]['enabled'] = True
            switches[org_slug]['enabled_at'] = datetime.now().isoformat()
            switches[org_slug]['enabled_by'] = session.get('username')
            add_log('system', org_slug, f'Kill switch ENABLED by {session.get("username")}', 'critical')
            flash(f'Kill switch ENABLED for {orgs[org_slug]["name"]}', 'warning')
    
    save_json(KILL_SWITCHES_FILE, switches)
    return redirect(url_for('kill_switches_list'))

@app.route('/kill-switches/update/<org_slug>', methods=['POST'])
@login_required
def update_kill_switch(org_slug):
    reason = request.form.get('reason', '')
    
    switches = get_kill_switches()
    if org_slug in switches:
        switches[org_slug]['reason'] = reason
        switches[org_slug]['updated_at'] = datetime.now().isoformat()
        switches[org_slug]['updated_by'] = session.get('username')
        
        if save_json(KILL_SWITCHES_FILE, switches):
            flash('Kill switch reason updated.', 'success')
        else:
            flash('Failed to update kill switch.', 'error')
    
    return redirect(url_for('kill_switches_list'))

# ==================== CHAT ROUTES ====================

@app.route('/chat')
@login_required
def chat_dashboard():
    messages = get_chat_messages()
    # Group by organization
    orgs = get_organizations()
    
    # Get stats
    total_messages = len(messages)
    unread_count = sum(1 for msg in messages if not msg.get('read', False))
    
    return render_template('chat.html', 
                          messages=list(reversed(messages[-100:])),  # Last 100 messages
                          organizations=orgs,
                          total_messages=total_messages,
                          unread_count=unread_count)


@app.route('/chat/inbox')
@login_required
def chat_inbox_ui():
    username = session.get('username')
    return render_template('inbox.html')

@app.route('/chat/mark-read/<int:msg_id>')
@login_required
def mark_chat_read(msg_id):
    messages = get_chat_messages()
    
    for msg in messages:
        if msg.get('id') == msg_id:
            msg['read'] = True
            msg['read_at'] = datetime.now().isoformat()
            msg['read_by'] = session.get('username')
            break
    
    save_json(CHAT_MESSAGES_FILE, messages)
    return redirect(url_for('chat_dashboard'))

@app.route('/chat/reply/<int:msg_id>', methods=['POST'])
@login_required
def reply_chat(msg_id):
    reply_text = request.form.get('reply', '')
    
    if not reply_text:
        flash('Reply cannot be empty.', 'error')
        return redirect(url_for('chat_dashboard'))
    
    messages = get_chat_messages()
    
    # Find original message
    original = None
    for msg in messages:
        if msg.get('id') == msg_id:
            original = msg
            break
    
    if not original:
        flash('Message not found.', 'error')
        return redirect(url_for('chat_dashboard'))
    
    # Add reply
    reply_message = {
        'id': len(messages) + 1,
        'timestamp': datetime.now().isoformat(),
        'org_slug': original.get('org_slug'),
        'from': 'admin',
        'from_name': session.get('username'),
        'message': reply_text,
        'reply_to': msg_id,
        'read': True
    }
    
    messages.append(reply_message)
    
    # Mark original as read
    original['read'] = True
    original['read_at'] = datetime.now().isoformat()
    original['read_by'] = session.get('username')
    
    if save_json(CHAT_MESSAGES_FILE, messages):
        add_log('chat', original.get('org_slug'), f'Admin replied to message {msg_id}', 'info')
        flash('Reply sent successfully!', 'success')
    else:
        flash('Failed to send reply.', 'error')
    
    return redirect(url_for('chat_dashboard'))

# ==================== API ROUTES ====================

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    settings = get_settings()
    return jsonify({
        'success': True,
        'status': 'healthy',
        'version': settings.get('version', '1.0.0'),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/organizations', methods=['GET'])
def api_get_all_organizations():
    """Get all organizations"""
    settings = get_settings()
    
    if not settings.get('api_enabled', True):
        return jsonify({'success': False, 'error': 'API is disabled'}), 503
    
    orgs = get_organizations()
    
    # Filter out inactive organizations if public read is not allowed
    if not settings.get('allow_public_read', True):
        orgs = {k: v for k, v in orgs.items() if v.get('active', True)}
    
    return jsonify({
        'success': True,
        'organizations': orgs,
        'count': len(orgs),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/organizations/<slug>', methods=['GET'])
def api_get_organization(slug):
    """Get a specific organization by slug"""
    settings = get_settings()
    
    if not settings.get('api_enabled', True):
        return jsonify({'success': False, 'error': 'API is disabled'}), 503
    
    orgs = get_organizations()
    
    if slug not in orgs:
        return jsonify({
            'success': False,
            'error': 'Organization not found'
        }), 404
    
    org = orgs[slug]
    
    # Check if organization is active
    if not org.get('active', True) and not settings.get('allow_public_read', True):
        return jsonify({
            'success': False,
            'error': 'Organization not found'
        }), 404
    
    return jsonify({
        'success': True,
        'organization': org,
        'slug': slug,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/organizations/by-subdomain/<subdomain>', methods=['GET'])
def api_get_organization_by_subdomain(subdomain):
    """Get organization by subdomain"""
    settings = get_settings()
    
    if not settings.get('api_enabled', True):
        return jsonify({'success': False, 'error': 'API is disabled'}), 503
    
    orgs = get_organizations()
    
    for slug, org in orgs.items():
        if org.get('subdomain') == subdomain:
            # Check if organization is active
            if not org.get('active', True) and not settings.get('allow_public_read', True):
                continue
            
            return jsonify({
                'success': True,
                'organization': org,
                'slug': slug,
                'timestamp': datetime.now().isoformat()
            })
    
    return jsonify({
        'success': False,
        'error': 'Organization not found'
    }), 404

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Get API statistics"""
    settings = get_settings()
    
    if not settings.get('api_enabled', True):
        return jsonify({'success': False, 'error': 'API is disabled'}), 503
    
    orgs = get_organizations()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_organizations': len(orgs),
            'active_organizations': sum(1 for org in orgs.values() if org.get('active', True)),
            'api_version': settings.get('version', '1.0.0')
        },
        'timestamp': datetime.now().isoformat()
    })

# ==================== UPTIME API ====================

@app.route('/api/uptime/ping', methods=['POST'])
def api_uptime_ping():
    """Receive uptime ping from instance"""
    data = request.json
    org_slug = data.get('org_slug')
    api_key = request.headers.get('X-API-Key')
    
    # Verify API key
    if api_key:
        keys = get_api_keys()
        if api_key not in keys or not keys[api_key].get('active'):
            return jsonify({'success': False, 'error': 'Invalid API key'}), 401
        
        # Update last used
        keys[api_key]['last_used'] = datetime.now().isoformat()
        save_json(API_KEYS_FILE, keys)
    
    if not org_slug:
        return jsonify({'success': False, 'error': 'org_slug required'}), 400
    
    uptime_data = get_uptime()
    
    if org_slug not in uptime_data:
        uptime_data[org_slug] = {'pings': []}
    
    ping_entry = {
        'timestamp': datetime.now().isoformat(),
        'status': data.get('status', 'online'),
        'metadata': data.get('metadata', {})
    }
    
    uptime_data[org_slug]['pings'].append(ping_entry)
    
    # Keep only last 1000 pings per org
    if len(uptime_data[org_slug]['pings']) > 1000:
        uptime_data[org_slug]['pings'] = uptime_data[org_slug]['pings'][-1000:]
    
    save_json(UPTIME_FILE, uptime_data)
    
    return jsonify({
        'success': True,
        'message': 'Ping recorded',
        'timestamp': datetime.now().isoformat()
    })

# ==================== KILL SWITCH API ====================

@app.route('/api/kill-switch/<org_slug>', methods=['GET'])
def api_check_kill_switch(org_slug):
    """Check if kill switch is enabled for an organization"""
    switches = get_kill_switches()
    
    is_enabled = switches.get(org_slug, {}).get('enabled', False)
    
    return jsonify({
        'success': True,
        'org_slug': org_slug,
        'kill_switch_enabled': is_enabled,
        'reason': switches.get(org_slug, {}).get('reason', '') if is_enabled else None,
        'timestamp': datetime.now().isoformat()
    })

# ==================== CHAT API ====================

@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    """Receive chat message from instance"""
    data = request.json
    org_slug = data.get('org_slug')
    message_text = data.get('message')
    user_name = data.get('user_name', 'Anonymous')
    user_email = data.get('user_email')
    if not org_slug or not message_text:
        return jsonify({'success': False, 'error': 'org_slug and message required'}), 400

    messages = get_chat_messages()

    chat_message = {
        'id': len(messages) + 1,
        'timestamp': datetime.now().isoformat(),
        'org_slug': org_slug,
        'from': 'user',
        'from_name': user_name,
        'from_email': user_email,
        'message': message_text,
        # Optional fields for teams/inbox
        'team': data.get('team'),
        'recipients': data.get('recipients', []),
        'read_by': [] ,
        'read': False
    }

    messages.append(chat_message)
    save_json(CHAT_MESSAGES_FILE, messages)

    add_log('chat', org_slug, f'New message from {user_name}', 'info')

    # Broadcast to SSE subscribers (in-memory)
    try:
        broadcast_chat_message(chat_message)
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message_id': chat_message['id'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/chat/messages/<org_slug>', methods=['GET'])
def api_chat_get_messages(org_slug):
    """Get chat messages for an organization"""
    messages = get_chat_messages()
    
    # Filter by org and get last 50 messages
    org_messages = [msg for msg in messages if msg.get('org_slug') == org_slug]
    org_messages = org_messages[-50:]  # Last 50
    
    return jsonify({
        'success': True,
        'messages': org_messages,
        'count': len(org_messages),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/chat/stream', methods=['GET'])
def api_chat_stream():
    """Server-Sent Events stream for new chat messages (in-memory broadcaster).
    Note: This is in-memory and will not work across multiple processes/hosts.
    """
    def event_stream(q):
        try:
            while True:
                msg = q.get()
                if msg is None:
                    break
                data = json.dumps(msg)
                yield f"data: {data}\n\n"
        except GeneratorExit:
            pass
        finally:
            # cleanup handled by outer scope
            return

    q = queue.Queue()
    _chat_subscribers.append(q)

    # Wrap generator to ensure subscriber cleanup on disconnect
    def gen():
        try:
            yield from event_stream(q)
        finally:
            try:
                _chat_subscribers.remove(q)
            except ValueError:
                pass

    return Response(gen(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})


@app.route('/api/chat/mark-read', methods=['POST'])
def api_chat_mark_read():
    data = request.json or {}
    msg_id = data.get('msg_id')
    username = data.get('username', session.get('username'))

    if not msg_id or not username:
        return jsonify({'success': False, 'error': 'msg_id and username required'}), 400

    messages = get_chat_messages()
    found = False
    for msg in messages:
        if msg.get('id') == int(msg_id):
            # mark as read for this user
            msg.setdefault('read_by', [])
            if username not in msg['read_by']:
                msg['read_by'].append(username)
            msg['read'] = True
            msg['read_at'] = datetime.now().isoformat()
            found = True
            break

    if not found:
        return jsonify({'success': False, 'error': 'Message not found'}), 404

    save_json(CHAT_MESSAGES_FILE, messages)
    return jsonify({'success': True, 'msg_id': msg_id})


@app.route('/api/chat/unread-count/<username>', methods=['GET'])
def api_chat_unread_count(username):
    """Return number of unread messages for a username."""
    messages = get_chat_messages()
    count = 0
    for msg in messages:
        read_by = msg.get('read_by', []) or []
        if username not in read_by and msg.get('from') == 'user':
            count += 1
    return jsonify({'success': True, 'unread': count})


@app.route('/api/chat/mark-all-read', methods=['POST'])
def api_chat_mark_all_read():
    """Mark all messages as read for a username or team. POST JSON: {username, team}
    """
    data = request.json or {}
    username = data.get('username')
    team = data.get('team')

    if not username and not team:
        return jsonify({'success': False, 'error': 'username or team required'}), 400

    messages = get_chat_messages()
    changed = 0
    for msg in messages:
        if team and msg.get('team') == team:
            msg.setdefault('read_by', [])
            if username not in msg['read_by']:
                msg['read_by'].append(username)
                changed += 1
                msg['read'] = True
        elif username:
            recipients = msg.get('recipients', []) or []
            if username in recipients or (not recipients and msg.get('from') == 'user'):
                msg.setdefault('read_by', [])
                if username not in msg['read_by']:
                    msg['read_by'].append(username)
                    changed += 1
                    msg['read'] = True

    save_json(CHAT_MESSAGES_FILE, messages)
    return jsonify({'success': True, 'changed': changed})


@app.route('/api/chat/inbox/<username>', methods=['GET'])
def api_chat_inbox(username):
    """Return inbox messages for a username. Optional ?team=teamname to filter by team."""
    team = request.args.get('team')
    # pagination
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 25))

    messages = get_chat_messages()

    def matches(msg):
        recipients = msg.get('recipients', []) or []
        if username in recipients:
            return True
        if team and msg.get('team') == team:
            return True
        # fallback: messages addressed to org admins are included if no recipients
        if not recipients and msg.get('from') == 'user':
            return True
        return False

    inbox = [m for m in messages if matches(m)]
    # sort newest first
    inbox = sorted(inbox, key=lambda m: m.get('id', 0), reverse=True)

    total = len(inbox)
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    start = (page - 1) * per_page
    end = start + per_page
    page_items = inbox[start:end]

    return jsonify({
        'success': True,
        'messages': page_items,
        'count': len(page_items),
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    })

# ==================== LOGGING API ====================

@app.route('/api/log', methods=['POST'])
def api_add_log():
    """Add log entry from instance"""
    data = request.json
    api_key = request.headers.get('X-API-Key')
    
    # Verify API key
    if api_key:
        keys = get_api_keys()
        if api_key not in keys or not keys[api_key].get('active'):
            return jsonify({'success': False, 'error': 'Invalid API key'}), 401
    
    log_entry = add_log(
        data.get('type', 'instance'),
        data.get('org_slug', 'unknown'),
        data.get('message', ''),
        data.get('level', 'info'),
        data.get('metadata', {})
    )
    
    return jsonify({
        'success': True,
        'log_id': log_entry['id'],
        'timestamp': datetime.now().isoformat()
    })

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
