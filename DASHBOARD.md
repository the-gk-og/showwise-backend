# ShowWise Security Dashboard

A comprehensive security administration dashboard for managing organizations, security events, IP threats, and system-wide activity logs.

## 🚀 Access

**Dashboard URL:** http://localhost:5001/dashboard

## 📊 Dashboard Features

### 1. **Overview Dashboard**
- **Real-time Statistics:**
  - Total Organizations
  - Total Users
  - Security Events Count
  - Blocked IPs Count
- **Recent Security Events:** Live feed of latest threats and security alerts
- **Quick Access** to all management sections

### 2. **Organizations Management** 
Create, read, update, and delete organizations (instances) from a single interface.

**Features:**
- ✅ Create new organizations
- ✅ Edit existing organizations
- ✅ Delete organizations
- ✅ Search and filter organizations
- ✅ View organization metadata (created date, slug)

**API Endpoints Used:**
- `GET /api/v1/organizations` - List all organizations
- `POST /api/v1/organizations` - Create new organization
- `PUT /api/v1/organizations/<slug>` - Update organization
- `DELETE /api/v1/organizations/<slug>` - Delete organization

### 3. **Security Dashboard**
Real-time security monitoring with comprehensive event tracking.

**Statistics:**
- Critical Events (last 24h)
- Failed Login Attempts
- High-Risk Requests
- Total Threats (last 24h)

**Security Events Table:**
- Event Type (login_failed, blocked_request, suspicious_activity, etc.)
- Description
- Severity Level (CRITICAL, WARNING, INFO)
- Source IP Address
- Timestamp

**Filters:**
- Full-text search on events
- Filter by event type
- Date range filtering

**API Endpoints Used:**
- `GET /api/v1/security/dashboard?days=1` - Security overview
- `GET /api/v1/logs/security-events?limit=50` - Event list

### 4. **IP Management**
Manage IP addresses through blacklisting and quarantine systems.

#### Blacklisted IPs
Permanently blocked IP addresses with:
- IP Address
- Block Reason
- Severity Level
- Expiration Date
- Quick Remove Action

#### Quarantined IPs
IPs under monitoring with:
- IP Address
- Threat Score (0-100)
- Reason for Quarantine
- Expiration Date
- Quick Clear Action

**Features:**
- ➕ Add new IP to blacklist
- 🔍 View all blacklist and quarantine entries
- ✅ Whitelist IPs to remove from both lists
- 📋 Reason codes (Malicious activity, Brute force, SQL injection, DDoS, etc.)
- ⏱️ Configurable expiration duration

**API Endpoints Used:**
- `GET /api/v1/security/blocked-ips` - Get blacklist
- `GET /api/v1/security/quarantined-ips` - Get quarantine
- `POST /api/v1/security/ip/<ip>/blacklist` - Add to blacklist
- `POST /api/v1/security/ip/<ip>/quarantine` - Add to quarantine
- `POST /api/v1/security/ip/<ip>/whitelist` - Remove from both

### 5. **Activity & Logs**
Comprehensive audit trail of all API calls and security events.

**Log Types:**
- **API Requests:** All endpoint calls with method, status, response time
- **Security Events:** All security-related events with severity levels

**Columns:**
- Log Type (API Request or Security Event)
- Endpoint / Event Type
- Status Code / Severity
- Source IP Address
- Timestamp

**Features:**
- 🔍 Full-text search across logs
- 🏷️ Filter by log type
- 📥 Export logs as CSV
- 📊 Sortable columns
- ⏱️ Timestamp filtering

**API Endpoints Used:**
- `GET /api/v1/logs/requests?limit=50` - API call logs
- `GET /api/v1/logs/security-events?limit=50` - Security events
- `GET /api/v1/logs/export/csv` - Export logs

## 🔐 Authentication

### Login Flow
1. Open dashboard at `http://localhost:5001/dashboard`
2. Login with credentials:
   - **Username:** `admin`
   - **Password:** `Admin@123456`
3. Receive access token (stored in localStorage)
4. Access all protected endpoints with token in X-API-Key header

### API Authentication
All API calls from the dashboard use:
```
X-API-Key: <access_token>
```

**Login Endpoint:**
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "Admin@123456"
}

Response:
{
  "success": true,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@showwise.local",
    "role": "admin",
    "2fa_enabled": false
  },
  "access_token": "bearer_..."
}
```

## 📱 User Interface

### Navigation
- **Sidebar:** Quick access to all dashboard sections
- **Top Bar:** Current page title and user info
- **Cards:** Organized content in collapsible cards
- **Responsive Design:** Works on desktop and tablet

### UI Elements

**Stats Cards:**
Colorful gradient cards showing key metrics
- Large number displays
- Clear labels
- Real-time updates

**Tables:**
- Sortable columns
- Hover effects
- Action buttons (Edit, Delete, Remove)
- Empty state messages

**Modals:**
- Organization creation/edit forms
- IP blacklist forms
- Clean form validation

**Alerts:**
- Success notifications (green)
- Error messages (red)
- Warning alerts (yellow)
- Auto-dismiss after 5 seconds

**Badges:**
- Severity levels (CRITICAL, HIGH, MEDIUM, LOW)
- Status indicators (Active, Inactive)
- Color-coded for quick identification

## 🛠️ Technical Details

### Tech Stack
- **Frontend:** Vanilla JavaScript, HTML5, CSS3
- **Backend:** Python Flask, SQLAlchemy ORM
- **Database:** SQLite (production: PostgreSQL)
- **API:** RESTful, versioned at /api/v1/*

### Files Created/Modified
- `templates/dashboard.html` - Main dashboard UI
- `app.py` - Added `/dashboard` route
- No additional dependencies required

### Performance
- **Light-weight:** ~50KB HTML, single JS file
- **API Integration:** Direct calls to backend
- **Real-time:** Updates on user interaction
- **Export:** CSV export with up to 10,000 records

## 📋 API Endpoints Reference

### Authentication
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/auth/login` | POST | User login |

### Admin/System
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/admin/system/stats` | GET | System statistics |
| `/api/v1/admin/system/health` | GET | System health |

### Organizations
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/organizations` | GET | List organizations |
| `/api/v1/organizations` | POST | Create organization |
| `/api/v1/organizations/<slug>` | GET | Get organization |
| `/api/v1/organizations/<slug>` | PUT | Update organization |
| `/api/v1/organizations/<slug>` | DELETE | Delete organization |

### Security
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/security/dashboard` | GET | Security dashboard (stats) |
| `/api/v1/security/events` | GET | List security events |
| `/api/v1/security/blocked-ips` | GET | List blacklisted IPs |
| `/api/v1/security/quarantined-ips` | GET | List quarantined IPs |
| `/api/v1/security/ip/<ip>/blacklist` | POST | Add IP to blacklist |
| `/api/v1/security/ip/<ip>/quarantine` | POST | Quarantine IP |
| `/api/v1/security/ip/<ip>/whitelist` | POST | Remove IP from lists |

### Logs
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/logs/requests` | GET | API call logs |
| `/api/v1/logs/security-events` | GET | Security event logs |
| `/api/v1/logs/export/csv` | GET | Export logs as CSV |

## 🎯 Common Tasks

### Create an Organization
1. Click "Organizations" in sidebar
2. Click "➕ New Organization" button
3. Enter organization name and slug
4. Click "Save"

### Block an IP Address
1. Click "IP Management" in sidebar
2. Click "⊕ Add to Blacklist" button
3. Enter IP address
4. Select reason
5. Set severity and duration
6. Click "Blacklist"

### View Security Events
1. Click "Security" in sidebar
2. View real-time security events
3. Search for specific events
4. Filter by event type
5. View event details (IP, timestamp, severity)

### Export Logs
1. Click "Activity & Logs" in sidebar
2. Click "📥 Export CSV" button
3. CSV file downloads automatically
4. Open in Excel/Sheets for analysis

## 🔍 Troubleshooting

### Dashboard Not Loading
- Check Flask is running: `python app.py`
- Verify port 5001 is accessible
- Check browser console for JavaScript errors

### API Calls Failing
- Verify authentication token is set
- Check X-API-Key header in request
- Ensure you're logged in first

### Data Not Appearing
- Click "Refresh" or navigate away and back
- Check if data exists in system
- Verify user has permission to view data

## 📝 Notes

- Dashboard uses localStorage for auth token persistence
- All timestamps are in UTC
- Severity levels: CRITICAL > HIGH > MEDIUM > LOW
- IP expiration: Default 24 hours, configurable
- CSV export includes up to 10,000 records
- All operations are logged and auditable

## 🚀 Future Enhancements

- [ ] Real-time WebSocket updates
- [ ] Advanced filtering and search
- [ ] Data visualization charts/graphs
- [ ] User role-based access control
- [ ] 2FA management UI
- [ ] API key generation UI
- [ ] Threat intelligence integration
- [ ] Automated response rules
