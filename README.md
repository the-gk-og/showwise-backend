# ShowWise Backend - Centralized Organization Management

A centralized backend service for managing all ShowWise organization deployments. This service provides a unified API and admin dashboard for managing organization configurations across multiple ShowWise instances.

## 🌟 Features

- **Centralized Organization Management**: Manage all ShowWise organizations from one place
- **Instance Management Dashboard**: Comprehensive monitoring and control
- **Shared Log Management**: Centralized logging with filtering and search
- **API Key System**: Secure authentication for instance API calls
- **Uptime Tracking**: Monitor instance health with heartbeat pings
- **Kill Switch Controls**: Emergency instance shutdown for non-payment
- **Live Chat System**: Customer support messaging integrated into instances
- **User Management**: Create and manage admin users via web dashboard or CLI
- **REST API**: Full-featured API for organization data with CORS support
- **Real-time Updates**: Changes are immediately reflected across all connected instances
- **JSON-based Storage**: Simple, human-readable data storage
- **Command-Line Tools**: Manage users and settings from terminal/container

## 📋 Requirements

- Python 3.8+
- Flask 3.0+
- Modern web browser for dashboard

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or download the project
cd showwise-backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your configuration
# Change the SECRET_KEY to something secure!
```

### 3. Run the Service

```bash
# Development mode
python app.py

# Production mode with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5001 app:app
```

The service will be available at `http://localhost:5001`

### 4. Default Login

- **Username**: `admin`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change the default password immediately after first login!

## 📚 Documentation

- **[README.md](README.md)** - Main documentation (this file)
- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - How to integrate with ShowWise frontend
- **[USER_MANAGEMENT.md](USER_MANAGEMENT.md)** - Complete user management guide
- **[INSTANCE_MANAGEMENT.md](INSTANCE_MANAGEMENT.md)** - Logs, uptime, kill switches, chat

## 👥 User Management

### Web Dashboard

1. Log in to the dashboard
2. Click **Users** in the navigation
3. Add, delete users, or change your password

### Command Line (CLI)

```bash
# List all users
python manage_users.py list

# Add a new user (interactive)
python manage_users.py add

# Delete a user
python manage_users.py delete username

# Change a user's password
python manage_users.py password username

# Reset admin password to default
python manage_users.py reset-admin
```

**Docker Usage:**
```bash
docker exec -it showwise-backend python manage_users.py list
docker exec -it showwise-backend python manage_users.py add
```

See [USER_MANAGEMENT.md](USER_MANAGEMENT.md) for complete documentation.

## 📁 Project Structure

```
showwise-backend/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── .gitignore            # Git ignore rules
├── data/                 # Data storage (auto-created)
│   ├── organizations.json # Organization configurations
│   ├── users.json        # User accounts
│   └── settings.json     # API settings
├── templates/            # HTML templates
│   ├── base.html        # Base template
│   ├── login.html       # Login page
│   ├── dashboard.html   # Dashboard
│   ├── organizations.html      # Organizations list
│   ├── add_organization.html   # Add organization form
│   ├── edit_organization.html  # Edit organization form
│   └── settings.html    # Settings page
└── README.md            # This file
```

## 🔌 API Usage

### Authentication

Currently, the API does not require authentication for read operations. Write operations are only available through the admin dashboard.

### Endpoints

#### Health Check
```http
GET /api/health
```

Returns service status and version.

**Response:**
```json
{
  "success": true,
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-02-17T10:30:00"
}
```

#### Get All Organizations
```http
GET /api/organizations
```

Returns all organization configurations.

**Response:**
```json
{
  "success": true,
  "organizations": {
    "demo": {
      "name": "Demo Organization",
      "subdomain": "demo",
      "url": "https://demo.sfx-crew.com",
      "logo": "/static/logos/demo.png",
      "primary_color": "#0051ff",
      "description": "Demo organization",
      "active": true
    }
  },
  "count": 1,
  "timestamp": "2024-02-17T10:30:00"
}
```

#### Get Organization by Slug
```http
GET /api/organizations/{slug}
```

**Example:**
```http
GET /api/organizations/demo
```

**Response:**
```json
{
  "success": true,
  "organization": {
    "name": "Demo Organization",
    "subdomain": "demo",
    "url": "https://demo.sfx-crew.com",
    ...
  },
  "slug": "demo",
  "timestamp": "2024-02-17T10:30:00"
}
```

#### Get Organization by Subdomain
```http
GET /api/organizations/by-subdomain/{subdomain}
```

Useful for subdomain-based routing in your ShowWise instances.

**Example:**
```http
GET /api/organizations/by-subdomain/demo
```

#### Get API Statistics
```http
GET /api/stats
```

Returns statistics about organizations and API usage.

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_organizations": 3,
    "active_organizations": 2,
    "api_version": "1.0.0"
  },
  "timestamp": "2024-02-17T10:30:00"
}
```

## 🔗 Integrating with ShowWise Instances

### Option 1: Replace Local organizations.json

Update your ShowWise instances to fetch from the backend API:

```python
# In your ShowWise instance app.py
import requests

BACKEND_API = "http://your-backend-url:5001/api"

def get_organizations():
    try:
        response = requests.get(f"{BACKEND_API}/organizations")
        if response.status_code == 200:
            data = response.json()
            return data.get('organizations', {})
    except Exception as e:
        print(f"Error fetching organizations: {e}")
    
    # Fallback to local file if API fails
    return load_local_organizations()
```

### Option 2: Dynamic Loading on Each Request

```python
@app.route('/organizations')
def organizations_list():
    # Fetch fresh data from backend
    response = requests.get(f"{BACKEND_API}/organizations")
    orgs = response.json().get('organizations', {})
    return render_template('organizations.html', organizations=orgs)
```

### Option 3: Periodic Sync

```python
from apscheduler.schedulers.background import BackgroundScheduler

def sync_organizations():
    response = requests.get(f"{BACKEND_API}/organizations")
    if response.status_code == 200:
        data = response.json().get('organizations', {})
        # Update local cache
        save_to_cache(data)

scheduler = BackgroundScheduler()
scheduler.add_job(sync_organizations, 'interval', minutes=5)
scheduler.start()
```

## 🎨 Dashboard Features

### Dashboard Home
- Overview statistics
- Quick actions
- API endpoint reference
- System information

### Organizations Management
- View all organizations
- Add new organizations
- Edit existing organizations
- Toggle active/inactive status
- Delete organizations
- Logo and branding configuration

### API Settings
- Enable/disable API
- Configure authentication requirements
- Set rate limits
- API documentation

## 🔒 Security

### Changing Default Password

1. Log into the dashboard with default credentials
2. Navigate to `data/users.json`
3. Update the password field (or implement a password change feature)
4. Restart the service

### Production Deployment

For production deployment:

1. **Change SECRET_KEY**: Use a strong, randomly generated key
2. **Enable HTTPS**: Deploy behind a reverse proxy with SSL
3. **Restrict CORS**: Update CORS origins to specific domains
4. **Set Strong Passwords**: Change all default passwords
5. **Enable Authentication**: Implement API key authentication
6. **Use Environment Variables**: Never commit .env to version control
7. **Regular Backups**: Backup the `data/` directory regularly

### Environment Variables

```bash
SECRET_KEY=your-secret-key-change-this-in-production
PORT=5001
FLASK_ENV=production
```

## 🚢 Deployment

### Using Gunicorn (Recommended)

```bash
gunicorn -w 4 -b 0.0.0.0:5001 --timeout 120 app:app
```

### Using Systemd Service

Create `/etc/systemd/system/showwise-backend.service`:

```ini
[Unit]
Description=ShowWise Backend Service
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/showwise-backend
Environment="PATH=/path/to/showwise-backend/venv/bin"
ExecStart=/path/to/showwise-backend/venv/bin/gunicorn -w 4 -b 0.0.0.0:5001 app:app

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable showwise-backend
sudo systemctl start showwise-backend
```

### Using Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5001", "app:app"]
```

Build and run:
```bash
docker build -t showwise-backend .
docker run -d -p 5001:5001 -v $(pwd)/data:/app/data showwise-backend
```

## 📊 Data Structure

### organizations.json
```json
{
  "slug": {
    "name": "Organization Name",
    "subdomain": "subdomain",
    "url": "https://subdomain.domain.com",
    "logo": "https://example.com/logo.svg",
    "logo_size": "contain",
    "logo_padding": "12px",
    "primary_color": "#0051ff",
    "secondary_color": "#898989",
    "description": "Description",
    "website": "https://org-website.com",
    "created_at": "2024-02-17T10:00:00",
    "updated_at": "2024-02-17T10:00:00",
    "active": true
  }
}
```

## 🛠️ Future Enhancements

- [ ] API key authentication
- [ ] Rate limiting implementation
- [ ] User management UI
- [ ] Organization statistics and analytics
- [ ] Backup and restore functionality
- [ ] Multi-user support with roles
- [ ] Activity logs and audit trail
- [ ] Webhook notifications
- [ ] Custom field support
- [ ] Import/export functionality

## 🤝 Contributing

This is a central management service for ShowWise instances. Feel free to fork and modify for your needs.

## 📝 License

Same license as ShowWise main project.

## 📧 Support

For issues or questions about the ShowWise Backend:
- Email: bugs@sfx-crew.com
- Main ShowWise documentation: https://sfx-crew.com

## 🎉 Acknowledgments

Built to centralize and simplify management of multiple ShowWise production management deployments.
