# Integration Guide: ShowWise Frontend → Backend API

This guide shows how to integrate your ShowWise frontend with the centralized backend.

## Method 1: Direct API Integration (Recommended)

Replace the local organizations.json loading with API calls.

### Updated app.py for ShowWise Frontend

```python
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_mail import Mail, Message
from flask_cors import CORS
from dotenv import load_dotenv
import json, os, requests
from functools import lru_cache
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key')

# Backend API Configuration
BACKEND_API_URL = os.getenv('BACKEND_API_URL', 'http://localhost:5001/api')
CACHE_TIMEOUT = 300  # 5 minutes

# Enable CORS
CORS(app)

# Mail configuration (existing code)
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 587)),
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
)

mail = Mail(app)

# Organization cache
_org_cache = {}
_cache_time = None

def fetch_organizations():
    """Fetch organizations from backend API with caching"""
    global _org_cache, _cache_time
    
    # Check cache
    if _cache_time and (datetime.now() - _cache_time).seconds < CACHE_TIMEOUT:
        return _org_cache
    
    try:
        response = requests.get(f"{BACKEND_API_URL}/organizations", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                _org_cache = data.get('organizations', {})
                _cache_time = datetime.now()
                return _org_cache
    except Exception as e:
        print(f"Error fetching organizations from backend: {e}")
    
    # Fallback to local file if API fails
    return load_local_organizations()

def load_local_organizations():
    """Fallback: Load from local organizations.json"""
    try:
        with open('organizations.json') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading local organizations.json: {e}")
        return {}

def get_organizations():
    """Get organizations (wrapper for compatibility)"""
    return fetch_organizations()

# ==================== WEB ROUTES ====================

@app.route('/')
def index():
    return redirect('/home')

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/learn-more')
def learn_more():
    return render_template('learn_more.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/contact/send', methods=['POST'])
def send_contact_message():
    # (existing code)
    pass

@app.route('/quote', methods=['GET', 'POST'])
def quote():
    # (existing code)
    pass

@app.route('/organizations')
def organizations_list():
    orgs = get_organizations()
    return render_template('organizations.html', organizations=orgs)

@app.route('/organizations/select/<org_slug>')
def select_organization(org_slug):
    orgs = get_organizations()
    
    if org_slug not in orgs:
        flash('Organization not found')
        return redirect(url_for('organizations_list'))
    
    org = orgs[org_slug]
    return redirect(org['url'] + '/login')

# ==================== API ROUTES (Optional: Proxy to backend) ====================

@app.route('/api/organizations', methods=['GET'])
def api_proxy_organizations():
    """Proxy API requests to backend"""
    try:
        response = requests.get(f"{BACKEND_API_URL}/organizations", timeout=5)
        return response.json(), response.status_code
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== EMAIL FUNCTION ====================

def send_email(subject, recipient, body):
    msg = Message(subject, recipients=[recipient], body=body)
    mail.send(msg)

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
```

### Updated .env for ShowWise Frontend

Add this line to your .env file:

```bash
BACKEND_API_URL=http://localhost:5001/api
```

For production:
```bash
BACKEND_API_URL=https://backend.yourdomain.com/api
```

## Method 2: Periodic Sync with Background Job

For better reliability, sync periodically instead of on each request.

### Install APScheduler

```bash
pip install apscheduler
```

### Updated app.py with Background Sync

```python
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# ... (existing imports and config)

ORGANIZATIONS = {}

def sync_organizations():
    """Sync organizations from backend every 5 minutes"""
    global ORGANIZATIONS
    try:
        response = requests.get(f"{BACKEND_API_URL}/organizations", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                ORGANIZATIONS = data.get('organizations', {})
                print(f"[{datetime.now()}] Organizations synced: {len(ORGANIZATIONS)} found")
    except Exception as e:
        print(f"[{datetime.now()}] Error syncing organizations: {e}")
        # Keep using cached data

# Initial sync
sync_organizations()

# Schedule periodic sync
scheduler = BackgroundScheduler()
scheduler.add_job(func=sync_organizations, trigger="interval", minutes=5)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

def get_organizations():
    """Get organizations from in-memory cache"""
    return ORGANIZATIONS

# ... (rest of your routes use get_organizations() as before)
```

## Method 3: Webhook-Based Updates (Advanced)

For real-time updates, implement webhooks in the backend.

### Backend Addition (app.py)

```python
# Add to backend app.py
WEBHOOKS = []  # Store webhook URLs

@app.route('/webhooks/register', methods=['POST'])
@login_required
def register_webhook():
    data = request.json
    webhook_url = data.get('url')
    if webhook_url and webhook_url not in WEBHOOKS:
        WEBHOOKS.append(webhook_url)
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

def notify_webhooks(event_type, data):
    """Notify all registered webhooks"""
    for webhook_url in WEBHOOKS:
        try:
            requests.post(webhook_url, json={
                'event': event_type,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }, timeout=5)
        except:
            pass

# Update save operations to notify webhooks
# In add_organization, edit_organization, etc:
if save_json(ORGANIZATIONS_FILE, orgs):
    notify_webhooks('organization.updated', {'slug': slug})
    # ... rest of the code
```

### Frontend Webhook Receiver

```python
@app.route('/webhooks/backend', methods=['POST'])
def webhook_receiver():
    """Receive updates from backend"""
    data = request.json
    event = data.get('event')
    
    if event == 'organization.updated':
        # Invalidate cache
        global _cache_time
        _cache_time = None
        print(f"Cache invalidated due to backend update")
    
    return jsonify({'success': True})
```

## Testing the Integration

### 1. Start Backend Service

```bash
cd showwise-backend
python app.py
```

Backend runs on: http://localhost:5001

### 2. Start Frontend Service

```bash
cd showwise-frontend
python app.py
```

Frontend runs on: http://localhost:5000

### 3. Test API Connection

```python
# test_integration.py
import requests

BACKEND_API = "http://localhost:5001/api"

# Test health
response = requests.get(f"{BACKEND_API}/health")
print("Health Check:", response.json())

# Test organizations
response = requests.get(f"{BACKEND_API}/organizations")
print("Organizations:", response.json())
```

### 4. Verify Frontend

Visit http://localhost:5000/organizations and verify that organizations are loaded from the backend.

## Monitoring and Debugging

### Add Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def fetch_organizations():
    try:
        logger.info("Fetching organizations from backend...")
        response = requests.get(f"{BACKEND_API_URL}/organizations", timeout=5)
        logger.info(f"Backend response: {response.status_code}")
        # ... rest of the code
    except Exception as e:
        logger.error(f"Failed to fetch organizations: {e}")
```

### Health Check Endpoint

```python
@app.route('/health')
def health():
    """Frontend health check"""
    backend_status = "unknown"
    try:
        response = requests.get(f"{BACKEND_API_URL}/health", timeout=2)
        backend_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        backend_status = "unreachable"
    
    return jsonify({
        'status': 'healthy',
        'backend_status': backend_status,
        'organizations_count': len(get_organizations()),
        'timestamp': datetime.now().isoformat()
    })
```

## Production Considerations

1. **SSL/TLS**: Always use HTTPS in production
2. **Error Handling**: Implement robust fallback mechanisms
3. **Caching**: Use Redis for distributed caching
4. **Load Balancing**: Put both services behind load balancer
5. **Monitoring**: Use tools like Prometheus/Grafana
6. **Rate Limiting**: Implement rate limiting on both ends
7. **Authentication**: Add API key authentication for backend

## Troubleshooting

### Organizations Not Loading

1. Check backend is running: `curl http://localhost:5001/api/health`
2. Check BACKEND_API_URL in .env
3. Check network/firewall settings
4. Check logs for error messages

### Stale Data

1. Reduce CACHE_TIMEOUT value
2. Implement webhook notifications
3. Add manual refresh button in UI
4. Check background sync is running

### Connection Timeouts

1. Increase timeout values
2. Check network latency
3. Consider adding retry logic
4. Implement circuit breaker pattern
