# Instance Management Features

Complete guide to the advanced instance management features in ShowWise Backend.

## Overview

The ShowWise Backend now functions as a comprehensive instance management dashboard with the following capabilities:

1. **Shared Log Management** - Centralized logging with filtering
2. **API Key System** - Secure authentication for instances
3. **Uptime Tracking** - Monitor instance health and availability
4. **Kill Switches** - Emergency instance shutdown controls
5. **Live Chat** - Customer support messaging system

## 1. Shared Log Management

### Features
- Centralized logging from all instances
- Filter by type, level, instance, or search term
- Pagination for large log volumes
- Log retention (last 10,000 entries)
- One-click log clearing

### Log Types
- `api` - API requests and responses
- `auth` - Authentication events
- `system` - System-level events
- `user` - User actions
- `instance` - Instance-specific events
- `chat` - Chat-related events

### Log Levels
- `info` - General information
- `warning` - Warning messages
- `error` - Error events
- `critical` - Critical failures

### Web Dashboard
Navigate to **Logs** in the menu to:
- View all logs with filters
- Search log messages
- Filter by type, level, or instance
- Clear all logs

### API Usage

**Add Log Entry:**
```http
POST /api/log
X-API-Key: your-api-key
Content-Type: application/json

{
  "type": "instance",
  "org_slug": "demo",
  "message": "User logged in successfully",
  "level": "info",
  "metadata": {"user_id": 123}
}
```

**Response:**
```json
{
  "success": true,
  "log_id": 12345,
  "timestamp": "2024-02-17T10:30:00"
}
```

### Integration Example (Python)

```python
import requests

BACKEND_URL = "https://backend.yourdomain.com"
API_KEY = "your-api-key"

def log_to_backend(message, level="info", log_type="instance", metadata=None):
    """Send log to centralized backend"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/log",
            headers={"X-API-Key": API_KEY},
            json={
                "type": log_type,
                "org_slug": "your-org-slug",
                "message": message,
                "level": level,
                "metadata": metadata or {}
            },
            timeout=5
        )
        return response.status_code == 200
    except:
        return False

# Usage
log_to_backend("Application started", "info", "system")
log_to_backend("Failed login attempt", "warning", "auth", {"ip": "192.168.1.1"})
```

## 2. API Key System

### Features
- Generate unique API keys per instance
- Track key usage and last access
- Revoke keys instantly
- Delete unused keys
- Key-based authentication for all API endpoints

### Web Dashboard
Navigate to **API Keys** (Dashboard → Quick Actions → API Keys) to:
- Generate new API keys
- View all active/revoked keys
- Revoke or delete keys
- Track last usage

### Generating API Keys

1. Go to API Keys page
2. Enter a descriptive name
3. Select the instance
4. Click "Generate"
5. **Copy the key immediately** - it won't be shown again

### Using API Keys

Include the API key in the `X-API-Key` header:

```python
headers = {
    "X-API-Key": "sk_xxxxxxxxxxxxx",
    "Content-Type": "application/json"
}

response = requests.post(url, headers=headers, json=data)
```

### API Key Format
Keys are prefixed with `sk_` and are 32+ characters long:
```
sk_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0
```

## 3. Uptime Tracking

### Features
- Automatic health monitoring
- 24-hour uptime percentage
- Last ping timestamp
- Online/offline status
- Historical ping data (last 1000 pings per instance)

### How It Works
Instances send heartbeat pings every 5 minutes:
- **Online**: Ping received in last 5 minutes
- **Offline**: No ping for more than 5 minutes
- **Unknown**: No pings ever received

### Web Dashboard
Navigate to **Uptime** to view:
- Real-time status for all instances
- Uptime percentage (24 hours)
- Total ping count
- Last ping timestamp

### API Usage

**Send Uptime Ping:**
```http
POST /api/uptime/ping
X-API-Key: your-api-key
Content-Type: application/json

{
  "org_slug": "demo",
  "status": "online",
  "metadata": {
    "server_load": 0.45,
    "memory_usage": "2.1GB",
    "active_users": 15
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Ping recorded",
  "timestamp": "2024-02-17T10:30:00"
}
```

### Integration Example (Python)

```python
from apscheduler.schedulers.background import BackgroundScheduler
import requests

BACKEND_URL = "https://backend.yourdomain.com"
API_KEY = "your-api-key"
ORG_SLUG = "your-org-slug"

def send_heartbeat():
    """Send heartbeat to backend every 5 minutes"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/uptime/ping",
            headers={"X-API-Key": API_KEY},
            json={
                "org_slug": ORG_SLUG,
                "status": "online",
                "metadata": {
                    "version": "1.0.0"
                }
            },
            timeout=5
        )
        if response.status_code == 200:
            print("Heartbeat sent successfully")
    except Exception as e:
        print(f"Failed to send heartbeat: {e}")

# Schedule heartbeat every 5 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(send_heartbeat, 'interval', minutes=5)
scheduler.start()

# Initial heartbeat
send_heartbeat()
```

Add this to your Flask app's startup code.

## 4. Kill Switch System

### Features
- Emergency instance shutdown
- Reason tracking
- Enable/disable toggle
- Audit trail (who enabled, when)
- API endpoint for instance checking

### Use Cases
- Non-payment / overdue accounts
- Terms of service violations
- Emergency maintenance
- Security incidents
- Contract termination

### Web Dashboard
Navigate to **Kill Switches** (Dashboard → Quick Actions → Kill Switches) to:
- View all instance kill switch states
- Enable/disable kill switches
- Set/update shutdown reasons
- View activation history

### How It Works

1. Admin enables kill switch with reason
2. Instance checks status periodically
3. If enabled, instance shows "Service Suspended" page
4. Admin disables when issue resolved

### API Usage

**Check Kill Switch Status:**
```http
GET /api/kill-switch/{org_slug}
```

**Response (Disabled):**
```json
{
  "success": true,
  "org_slug": "demo",
  "kill_switch_enabled": false,
  "reason": null,
  "timestamp": "2024-02-17T10:30:00"
}
```

**Response (Enabled):**
```json
{
  "success": true,
  "org_slug": "demo",
  "kill_switch_enabled": true,
  "reason": "Payment overdue - Account suspended",
  "timestamp": "2024-02-17T10:30:00"
}
```

### Integration Example (Python)

```python
from flask import Flask, render_template, abort
import requests

BACKEND_URL = "https://backend.yourdomain.com"
ORG_SLUG = "your-org-slug"

app = Flask(__name__)

def check_kill_switch():
    """Check if kill switch is enabled"""
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/kill-switch/{ORG_SLUG}",
            timeout=3
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('kill_switch_enabled', False), data.get('reason', '')
        return False, ''
    except:
        # If backend is unreachable, allow access
        return False, ''

@app.before_request
def check_service_status():
    """Check kill switch before every request"""
    enabled, reason = check_kill_switch()
    if enabled:
        return render_template('suspended.html', reason=reason), 503

# Rest of your app...
```

**suspended.html template:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>Service Suspended</title>
</head>
<body>
    <h1>Service Temporarily Suspended</h1>
    <p>{{ reason }}</p>
    <p>Please contact support for assistance.</p>
</body>
</html>
```

## 5. Live Chat System

### Features
- Real-time customer messages
- Unread message tracking
- Admin replies
- Message threading
- Organization filtering
- Customer contact information

### Web Dashboard
Navigate to **Chat** to:
- View all messages (newest first)
- See unread count
- Reply to messages
- Mark messages as read
- View customer details (name, email)

### API Usage

**Send Chat Message (from instance):**
```http
POST /api/chat/send
Content-Type: application/json

{
  "org_slug": "demo",
  "user_name": "John Doe",
  "user_email": "john@example.com",
  "message": "I need help with my account"
}
```

**Get Messages for Instance:**
```http
GET /api/chat/messages/{org_slug}
```

**Response:**
```json
{
  "success": true,
  "messages": [
    {
      "id": 1,
      "timestamp": "2024-02-17T10:30:00",
      "org_slug": "demo",
      "from": "user",
      "from_name": "John Doe",
      "from_email": "john@example.com",
      "message": "I need help with my account",
      "read": true
    },
    {
      "id": 2,
      "timestamp": "2024-02-17T10:35:00",
      "org_slug": "demo",
      "from": "admin",
      "from_name": "support",
      "message": "Happy to help! What can I assist you with?",
      "reply_to": 1,
      "read": true
    }
  ],
  "count": 2,
  "timestamp": "2024-02-17T10:40:00"
}
```

### Integration Example (JavaScript/React)

```javascript
// Chat component for ShowWise instance
import React, { useState, useEffect } from 'react';

const BACKEND_URL = 'https://backend.yourdomain.com';
const ORG_SLUG = 'your-org-slug';

function LiveChat() {
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');

  // Fetch messages every 10 seconds
  useEffect(() => {
    const fetchMessages = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/chat/messages/${ORG_SLUG}`);
        const data = await response.json();
        if (data.success) {
          setMessages(data.messages);
        }
      } catch (error) {
        console.error('Failed to fetch messages:', error);
      }
    };

    fetchMessages();
    const interval = setInterval(fetchMessages, 10000);
    return () => clearInterval(interval);
  }, []);

  const sendMessage = async (e) => {
    e.preventDefault();
    
    try {
      const response = await fetch(`${BACKEND_URL}/api/chat/send`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          org_slug: ORG_SLUG,
          user_name: userName,
          user_email: userEmail,
          message: newMessage
        })
      });

      if (response.ok) {
        setNewMessage('');
        // Refresh messages
        const msgResponse = await fetch(`${BACKEND_URL}/api/chat/messages/${ORG_SLUG}`);
        const data = await msgResponse.json();
        setMessages(data.messages);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  return (
    <div className="chat-widget">
      <div className="chat-messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.from}`}>
            <strong>{msg.from_name}:</strong> {msg.message}
          </div>
        ))}
      </div>
      <form onSubmit={sendMessage}>
        <input
          type="text"
          placeholder="Your name"
          value={userName}
          onChange={(e) => setUserName(e.target.value)}
          required
        />
        <input
          type="email"
          placeholder="Your email"
          value={userEmail}
          onChange={(e) => setUserEmail(e.target.value)}
          required
        />
        <textarea
          placeholder="Type your message..."
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          required
        />
        <button type="submit">Send</button>
      </form>
    </div>
  );
}

export default LiveChat;
```

## Complete Integration Example

Here's a complete example showing all features integrated into a ShowWise instance:

```python
# full_integration.py
from flask import Flask, request, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import atexit

app = Flask(__name__)

# Configuration
BACKEND_URL = "https://backend.yourdomain.com"
API_KEY = "your-api-key"
ORG_SLUG = "your-org-slug"

# === UPTIME TRACKING ===
def send_heartbeat():
    try:
        requests.post(
            f"{BACKEND_URL}/api/uptime/ping",
            headers={"X-API-Key": API_KEY},
            json={"org_slug": ORG_SLUG, "status": "online"},
            timeout=5
        )
    except:
        pass

scheduler = BackgroundScheduler()
scheduler.add_job(send_heartbeat, 'interval', minutes=5)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# === KILL SWITCH CHECK ===
@app.before_request
def check_kill_switch():
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/kill-switch/{ORG_SLUG}",
            timeout=3
        )
        if response.json().get('kill_switch_enabled'):
            return render_template('suspended.html'), 503
    except:
        pass

# === LOGGING ===
def log_to_backend(message, level="info", log_type="instance"):
    try:
        requests.post(
            f"{BACKEND_URL}/api/log",
            headers={"X-API-Key": API_KEY},
            json={
                "type": log_type,
                "org_slug": ORG_SLUG,
                "message": message,
                "level": level
            },
            timeout=5
        )
    except:
        pass

@app.route('/login', methods=['POST'])
def login():
    # Your login logic
    log_to_backend(f"User logged in: {request.form.get('username')}", "info", "auth")
    # ...

# === CHAT API ROUTES ===
@app.route('/api/chat/send', methods=['POST'])
def send_chat():
    data = request.json
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/chat/send",
            json={
                "org_slug": ORG_SLUG,
                "user_name": data.get('name'),
                "user_email": data.get('email'),
                "message": data.get('message')
            },
            timeout=5
        )
        return response.json()
    except:
        return {"success": False}, 500

if __name__ == '__main__':
    log_to_backend("Application started", "info", "system")
    app.run()
```

## Security Considerations

1. **API Keys**: Store securely in environment variables
2. **HTTPS**: Always use HTTPS for API communication
3. **Rate Limiting**: Implement client-side rate limiting
4. **Error Handling**: Gracefully handle backend unavailability
5. **Timeouts**: Use short timeouts (3-5 seconds) to avoid blocking
6. **Logging**: Don't log sensitive data (passwords, tokens)

## Troubleshooting

### Logs not appearing
- Check API key is valid
- Verify org_slug matches exactly
- Check backend is reachable
- Look for errors in instance logs

### Uptime showing offline
- Ensure heartbeat is running every 5 minutes
- Check API key authentication
- Verify scheduler is started
- Test endpoint manually

### Kill switch not working
- Check instance is polling the endpoint
- Verify before_request hook is implemented
- Test the API endpoint directly
- Check for caching issues

### Chat messages not sending
- Verify all required fields are provided
- Check Content-Type header
- Test API endpoint with curl
- Check backend logs for errors

## Support

For issues with instance management features:
- Email: bugs@sfx-crew.com
- Check backend logs at **/logs**
- Review API key status at **/api-keys**
- Monitor uptime at **/uptime**
